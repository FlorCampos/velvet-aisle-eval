#!/usr/bin/env python3
"""Velvet Aisle eval harness.

For every enabled model in models.json, every task in tasks/, and every trial, it sends
one fresh single-turn request (store policies + the relevant part of the catalog + the
customer's message), saves the full transcript, grades the reply with graders/grade.py,
and writes results/results.jsonl, results/summary.json and results/summary.md.

Each trial is an independent API call with no shared state. Re-running the command
skips trials that already have a successful transcript, so an interrupted run resumes.

Usage:
    python run_eval.py --oracle                 # grade the reference answers (no API keys needed)
    python run_eval.py --trials 5               # run every enabled model
    python run_eval.py --models-only claude-haiku-5-5 --tasks T01,T05 --trials 1   # quick pilot
    python run_eval.py --summarize-only         # regrade saved transcripts and rebuild the summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from graders.grade import grade, load_answers, reference_reply  # noqa: E402

DATA = ROOT / "data"
TASKS_DIR = ROOT / "tasks"
TRANSCRIPTS = ROOT / "transcripts"
RESULTS = ROOT / "results"

SYSTEM_HEADER = (
    "You are the shopping assistant for Velvet Aisle, a fictional online beauty store.\n"
    "Answer using only the store policies and the catalog below. Do not invent products, "
    "prices, stock or rules.\n"
)
ANSWER_INSTRUCTION = (
    "You may think step by step first. End your reply with the JSON object inside a "
    "```json code block."
)


# ------------------------------------------------------------------ prompts
def load_tasks(selected: list[str] | None = None) -> list[dict]:
    tasks = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(TASKS_DIR.glob("T*.json"))]
    return [t for t in tasks if not selected or t["id"] in selected]


def drop_nulls(obj):
    if isinstance(obj, dict):
        return {k: drop_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [drop_nulls(v) for v in obj]
    return obj


CONTEXT = "focused"  # "focused": only the task's categories; "full": the whole catalog


def build_system_prompt(task: dict) -> str:
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    policies = (DATA / "policies.md").read_text(encoding="utf-8")
    if CONTEXT == "full":
        cats = sorted({p["category"] for p in catalog["products"]})
        intro = "The full store catalog"
    else:
        cats = task["context_categories"]
        intro = f"Products in the categories relevant to this request ({', '.join(cats)})"
    lines = [json.dumps(drop_nulls(p), separators=(",", ":"), ensure_ascii=False)
             for p in catalog["products"] if p["category"] in cats]
    return (
        f"{SYSTEM_HEADER}\n{policies}\n"
        f"# Catalog\n"
        f"{intro}, one JSON object per line. Prices are in USD; `stock` is the number of "
        f"units available for each variant.\n\n" + "\n".join(lines) + "\n"
    )


def build_user_prompt(task: dict) -> str:
    return f"{task['prompt']}\n\n{task['output_format']}\n\n{ANSWER_INSTRUCTION}"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- providers
def call_anthropic(m: dict, system: str, user: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ[m.get("api_key_env", "ANTHROPIC_API_KEY")])
    kwargs = {"model": m["model"], "max_tokens": m.get("max_tokens", 8192), "system": system,
              "messages": [{"role": "user", "content": user}]}
    if m.get("temperature") is not None:  # not a named SDK argument in anthropic>=2; sent as raw body field
        kwargs["extra_body"] = {"temperature": m["temperature"]}
    resp = client.messages.create(**kwargs)
    return {
        "text": "".join(getattr(b, "text", "") for b in resp.content if b.type == "text"),
        "model_id": resp.model,
        "stop_reason": resp.stop_reason,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def call_openai(m: dict, system: str, user: str) -> dict:
    from openai import OpenAI
    base_url = os.environ.get(m["base_url_env"]) if m.get("base_url_env") else m.get("base_url")
    client = OpenAI(api_key=os.environ[m.get("api_key_env", "OPENAI_API_KEY")], base_url=base_url)
    kwargs = {"model": m["model"],
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    kwargs[m.get("max_tokens_param", "max_completion_tokens")] = m.get("max_tokens", 8192)
    if m.get("temperature") is not None:
        kwargs["temperature"] = m["temperature"]
    resp = client.chat.completions.create(**kwargs)
    usage = resp.usage
    return {
        "text": resp.choices[0].message.content or "",
        "model_id": resp.model,
        "stop_reason": resp.choices[0].finish_reason,
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
    }


PROVIDERS = {"anthropic": call_anthropic, "openai": call_openai, "openai_compatible": call_openai}
DEFAULT_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                   "openai_compatible": "OPENAI_API_KEY"}
# Errors that will not go away on retry (bad key, unknown model, invalid request).
NON_RETRYABLE = {"KeyError", "TypeError", "AuthenticationError", "PermissionDeniedError",
                 "NotFoundError", "BadRequestError", "UnprocessableEntityError"}


def missing_env(models: list[dict]) -> list[str]:
    missing = []
    for m in models:
        for var in (m.get("api_key_env") or DEFAULT_KEY_ENV.get(m["provider"]), m.get("base_url_env")):
            if var and not os.environ.get(var):
                missing.append(f"{m['name']}: environment variable {var} is not set")
    return missing


def cost_usd(m: dict, input_tokens, output_tokens) -> float | None:
    prices = m.get("price_per_mtok") or {}
    if prices.get("input") is None or prices.get("output") is None or input_tokens is None:
        return None
    return (input_tokens * prices["input"] + (output_tokens or 0) * prices["output"]) / 1_000_000


# -------------------------------------------------------------------- trials
def transcript_path(model_name: str, task_id: str, trial: int) -> Path:
    return TRANSCRIPTS / model_name / task_id / f"trial_{trial}.json"


def run_trial(m: dict, task: dict, trial: int, system: str, user: str, answers: dict) -> dict:
    path = transcript_path(m["name"], task["id"], trial)
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not saved.get("error"):
            return saved
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    response, error = None, None
    for attempt in range(8):  # rate limits (429) can take a minute or more to clear
        try:
            response = PROVIDERS[m["provider"]](m, system, user)
            error = None
            break
        except Exception as e:  # noqa: BLE001 - record any provider error
            error = f"{type(e).__name__}: {e}"
            if type(e).__name__ in NON_RETRYABLE or attempt == 7:
                break
            time.sleep(min(60, 2 * 2 ** attempt))
    record = {
        "model": m["name"],
        "provider": m["provider"],
        "requested_model": m["model"],
        "settings": {"temperature": m.get("temperature"), "max_tokens": m.get("max_tokens", 8192)},
        "task": task["id"],
        "trial": trial,
        "started_at": started.isoformat(),
        "latency_s": round(time.monotonic() - t0, 2),
        "context": CONTEXT,
        "system_prompt_file": str((TRANSCRIPTS / "_prompts" / f"{task['id']}.system.md").relative_to(ROOT)),
        "system_prompt_sha256": sha256(system),
        "user_prompt": user,
        "error": error,
    }
    if response:
        record.update({
            "response_model_id": response["model_id"],
            "stop_reason": response["stop_reason"],
            "input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
            "cost_usd": cost_usd(m, response["input_tokens"], response["output_tokens"]),
            "response_text": response["text"],
            "grade": grade(task["id"], response["text"], answers),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


# ------------------------------------------------------------------- summary
def summarize(records: list[dict], trials: int) -> dict:
    ok = [r for r in records if not r.get("error")]
    models = sorted({r["model"] for r in records})
    tasks = sorted({r["task"] for r in records})
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "context": CONTEXT,
               "trials_per_task": trials,
               "models": {}, "per_task": {}, "failure_modes": {}, "errors": len(records) - len(ok)}
    for model in models:
        mr = [r for r in ok if r["model"] == model]
        per_task = {}
        for t in tasks:
            tr = [r for r in mr if r["task"] == t]
            if tr:
                per_task[t] = {"n": len(tr), "passes": sum(r["grade"]["passed"] for r in tr),
                               "mean_score": sum(r["grade"]["score"] for r in tr) / len(tr)}
        costs = [r.get("cost_usd") for r in mr]
        summary["models"][model] = {
            "requested_model": mr[0]["requested_model"] if mr else None,
            "response_model_ids": sorted({r.get("response_model_id") or "?" for r in mr}),
            "settings": mr[0]["settings"] if mr else None,
            "trials": len(mr),
            "pass_rate": sum(r["grade"]["passed"] for r in mr) / len(mr) if mr else 0,
            "mean_score": sum(r["grade"]["score"] for r in mr) / len(mr) if mr else 0,
            "pass_at_k": sum(v["passes"] > 0 for v in per_task.values()) / len(per_task) if per_task else 0,
            "pass_hat_k": sum(v["passes"] == v["n"] for v in per_task.values()) / len(per_task) if per_task else 0,
            "cost_usd": None if not costs or any(c is None for c in costs) else round(sum(costs), 4),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in mr),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in mr),
            "mean_latency_s": round(sum(r["latency_s"] for r in mr) / len(mr), 2) if mr else None,
            "per_task": per_task,
        }
    for t in tasks:
        fails: dict[str, int] = {}
        for r in ok:
            if r["task"] == t:
                for c in r["grade"]["checks"]:
                    if not c["passed"]:
                        fails[c["name"]] = fails.get(c["name"], 0) + 1
        summary["failure_modes"][t] = dict(sorted(fails.items(), key=lambda kv: -kv[1]))
    return summary


def write_summary_md(summary: dict, tasks: list[dict]) -> str:
    k = summary["trials_per_task"]
    out = ["# Results", "", f"Context: {summary['context']} catalog. "
           f"Generated {summary['generated_at']}. Trials per task: {k}. "
           f"API errors excluded from scores: {summary['errors']}.", "",
           f"| Model (version, settings) | Trials | Pass rate | Mean score | pass@{k} | pass^{k} | Cost per full run |",
           "|---|---|---|---|---|---|---|"]
    for name, m in summary["models"].items():
        settings = ", ".join(f"{a}={b}" for a, b in (m["settings"] or {}).items())
        ids = ", ".join(m["response_model_ids"])
        cost = f"${m['cost_usd']:.2f}" if m["cost_usd"] is not None else \
            f"n/a ({m['input_tokens']:,} in / {m['output_tokens']:,} out tokens)"
        out.append(f"| {name} (`{ids}`; {settings}) | {m['trials']} | {m['pass_rate']:.0%} | "
                   f"{m['mean_score']:.2f} | {m['pass_at_k']:.0%} | {m['pass_hat_k']:.0%} | {cost} |")
    out += ["", "## Passes per task (passes / trials, mean partial score)", "",
            "| Task | " + " | ".join(summary["models"]) + " |",
            "|---|" + "---|" * len(summary["models"])]
    titles = {t["id"]: t["title"] for t in tasks}
    for t in sorted(titles):
        cells = []
        for m in summary["models"].values():
            pt = m["per_task"].get(t)
            cells.append(f"{pt['passes']}/{pt['n']} ({pt['mean_score']:.2f})" if pt else "-")
        out.append(f"| {t} {titles[t]} | " + " | ".join(cells) + " |")
    out += ["", "## Most frequent failed checks per task", ""]
    for t, fails in summary["failure_modes"].items():
        top = "; ".join(f"{name} ({n}x)" for name, n in list(fails.items())[:4]) or "none"
        out.append(f"- **{t}**: {top}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="models.json", help="model config file")
    ap.add_argument("--models-only", help="comma-separated model names to run (default: all enabled)")
    ap.add_argument("--tasks", help="comma-separated task IDs (default: all)")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--oracle", action="store_true", help="grade the reference answers; no API calls")
    ap.add_argument("--summarize-only", action="store_true", help="regrade saved transcripts, no API calls")
    ap.add_argument("--context", choices=["focused", "full"], default="focused",
                    help="focused: only the task's categories in the prompt (results in results/, "
                         "transcripts/); full: the whole catalog (results/full/, transcripts/full/)")
    args = ap.parse_args()

    global CONTEXT, TRANSCRIPTS, RESULTS
    CONTEXT = args.context
    if CONTEXT == "full":
        TRANSCRIPTS, RESULTS = ROOT / "transcripts" / "full", ROOT / "results" / "full"

    answers = load_answers()
    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)

    if args.oracle:
        bad = 0
        for t in tasks:
            r = grade(t["id"], reference_reply(t["id"], answers), answers)
            bad += not r["passed"]
            print(f"{t['id']}: {'PASS' if r['passed'] else 'FAIL'} (score {r['score']:.2f})")
        print("oracle: all reference answers pass" if not bad else f"oracle: {bad} task(s) failed")
        sys.exit(1 if bad else 0)

    models = [m for m in json.loads((ROOT / args.models).read_text(encoding="utf-8"))
              if m.get("enabled", True)]
    if args.models_only:
        wanted = set(args.models_only.split(","))
        models = [m for m in models if m["name"] in wanted]
    if not models:
        sys.exit("No enabled models. Edit models.json.")

    prompts = {}
    (TRANSCRIPTS / "_prompts").mkdir(parents=True, exist_ok=True)
    for t in tasks:
        system, user = build_system_prompt(t), build_user_prompt(t)
        prompts[t["id"]] = (system, user)
        (TRANSCRIPTS / "_prompts" / f"{t['id']}.system.md").write_text(system, encoding="utf-8")

    records = []
    if args.summarize_only:
        for m in models:
            for t in tasks:
                for i in range(1, args.trials + 1):
                    p = transcript_path(m["name"], t["id"], i)
                    if p.exists():
                        r = json.loads(p.read_text(encoding="utf-8"))
                        if not r.get("error"):
                            r["grade"] = grade(t["id"], r["response_text"], answers)
                            r["cost_usd"] = cost_usd(m, r.get("input_tokens"), r.get("output_tokens"))
                            p.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                        records.append(r)
    else:
        if problems := missing_env(models):
            sys.exit("Cannot start:\n  " + "\n  ".join(problems) +
                     "\nFill in .env and load it (see README), or disable the model in models.json.")
        jobs = [(m, t, i) for m in models for t in tasks for i in range(1, args.trials + 1)]
        print(f"Running {len(jobs)} trials ({len(models)} models x {len(tasks)} tasks x {args.trials} trials)")
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(run_trial, m, t, i, *prompts[t["id"]], answers): (m, t, i)
                       for m, t, i in jobs}
            for n, fut in enumerate(as_completed(futures), 1):
                r = fut.result()
                records.append(r)
                status = "ERROR " + r["error"][:80] if r.get("error") else \
                    f"{'PASS' if r['grade']['passed'] else 'fail'} {r['grade']['score']:.2f}"
                print(f"[{n}/{len(jobs)}] {r['model']} {r['task']} trial {r['trial']}: {status}")

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda r: (r["model"], r["task"], r["trial"])):
            f.write(json.dumps({k: r.get(k) for k in (
                "model", "requested_model", "response_model_id", "task", "trial", "started_at",
                "latency_s", "input_tokens", "output_tokens", "cost_usd", "error")} | {
                "passed": r.get("grade", {}).get("passed"), "score": r.get("grade", {}).get("score"),
                "transcript": str(transcript_path(r["model"], r["task"], r["trial"]).relative_to(ROOT)),
            }) + "\n")
    summary = summarize(records, args.trials)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    md = write_summary_md(summary, load_tasks())
    (RESULTS / "summary.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    if summary["errors"]:
        print(f"WARNING: {summary['errors']} trial(s) hit API errors. Re-run the same command to retry them.")


if __name__ == "__main__":
    main()
