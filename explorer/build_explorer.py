#!/usr/bin/env python3
"""Build explorer/index.html: a self-contained page to browse every graded trial.

It reads the saved results and transcripts (no API calls) and embeds them as JSON in
explorer/template.html. Open the output file in any browser; no server is needed.

Usage:
    python explorer/build_explorer.py                  # writes explorer/index.html
    python explorer/build_explorer.py --bare OUT.html  # same page without the <html> wrapper
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "explorer"

CONDITIONS = [
    {"id": "full", "label": "Full catalog (136 products)", "short": "full",
     "results": ROOT / "results" / "full"},
    {"id": "focused", "label": "Focused catalog (relevant categories)", "short": "focused",
     "results": ROOT / "results"},
]
MODEL_LABELS = {
    "gemini-4-argon": "Gemini 4 Argon",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
}


def load_condition(c: dict) -> dict | None:
    results = c["results"] / "results.jsonl"
    summary = c["results"] / "summary.json"
    if not results.exists() or not summary.exists():
        return None
    s = json.loads(summary.read_text(encoding="utf-8"))
    trials = []
    for line in results.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("error"):
            continue
        t = json.loads((ROOT / r["transcript"]).read_text(encoding="utf-8"))
        g = t["grade"]
        trials.append({
            "model": r["model"], "task": r["task"], "trial": r["trial"],
            "passed": g["passed"], "score": g["score"], "answer": g["answer"],
            "checks": g["checks"], "reply": t.get("response_text", ""),
            "input_tokens": t.get("input_tokens"),
        })
    return {
        "id": c["id"], "label": c["label"], "short": c["short"],
        "trialsPerTask": s["trials_per_task"],
        "summary": {m: {"pass_rate": v["pass_rate"], "pass_hat_k": v["pass_hat_k"], "cost_usd": v["cost_usd"]}
                    for m, v in s["models"].items()},
        "failureModes": {t: list(f.items()) for t, f in s["failure_modes"].items()},
        "trials": trials,
    }


def build() -> str:
    tasks = {}
    for f in sorted((ROOT / "tasks").glob("T*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        tasks[t["id"]] = {"title": t["title"], "prompt": t["prompt"], "why_hard": t["why_hard"]}
    answers = json.loads((ROOT / "reference" / "answers.json").read_text(encoding="utf-8"))
    conditions = [x for x in (load_condition(c) for c in CONDITIONS) if x]
    models = sorted({t["model"] for c in conditions for t in c["trials"]},
                    key=lambda m: list(MODEL_LABELS).index(m) if m in MODEL_LABELS else 99)
    data = {
        "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tasks": tasks,
        "reference": {tid: a["expected"] for tid, a in answers.items()},
        "models": models,
        "modelLabels": {m: MODEL_LABELS.get(m, m) for m in models},
        "conditions": conditions,
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (HERE / "template.html").read_text(encoding="utf-8").replace("__DATA_JSON__", payload)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bare", metavar="OUT", help="write the page without the <html> wrapper to OUT")
    args = ap.parse_args()
    page = build()
    if args.bare:
        Path(args.bare).write_text(page, encoding="utf-8")
        print(f"wrote {args.bare}")
        return
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "<style>body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
            + page + "\n</body>\n</html>\n")
    out = HERE / "index.html"
    out.write_text(full, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(full) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
