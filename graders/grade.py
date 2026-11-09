"""Deterministic, code-based grader for the Velvet Aisle eval.

No LLM judge is used. Every task has one correct answer that reference/solve.py
computes from the catalog and the store policies. The grader:

1. extracts the last JSON object from the model's reply (a ```json block, or bare JSON);
2. runs one check per component of the answer (each expected item, each line, each amount);
3. scores the task as the fraction of checks passed (partial credit), with
   "passed" = every check passed.

For variant-list tasks the score is F1 over the variant IDs, so listing every
variant in the store (a "shotgun" answer) scores close to zero. Money amounts must
be within half a cent of the reference ($54.549 passes, $54.56 does not).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "reference" / "answers.json"
MONEY_TOLERANCE = 0.005

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def load_answers() -> dict:
    return json.loads(ANSWERS.read_text(encoding="utf-8"))


def extract_json(text: str) -> dict | None:
    """Return the last JSON object in the reply: fenced blocks first, then bare JSON."""
    for block in reversed(_FENCE.findall(text or "")):
        try:
            obj = json.loads(block)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    decoder, last, i = json.JSONDecoder(), None, 0
    while text and (i := text.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
            if isinstance(obj, dict):
                last = obj
            i = end
        except json.JSONDecodeError:
            i += 1
    return last


def to_number(x) -> float | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    return None


def money_ok(got, expected: float) -> bool:
    n = to_number(got)
    return n is not None and abs(n - expected) <= MONEY_TOLERANCE + 1e-9


def norm_id(x) -> str:
    return str(x).strip().upper()


def check(name: str, passed: bool, detail: str = "") -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _fmt(x) -> str:
    n = to_number(x)
    return f"${n:.2f}" if n is not None else repr(x)


# ------------------------------------------------------------------ per type
def grade_variant_set(answer: dict, ref: dict) -> tuple[list, float]:
    got_raw = answer.get("variant_ids")
    if not isinstance(got_raw, list):
        return [check("answer has a variant_ids list", False, f"got {got_raw!r}")], 0.0
    canon = {norm_id(v): v for v in ref["expected"]["variant_ids"]}
    canon.update({norm_id(v): v for v in ref["explanations"]})
    got = {norm_id(v) for v in got_raw}
    expected = {norm_id(v) for v in ref["expected"]["variant_ids"]}
    checks = []
    if not expected:
        checks.append(check("returns an empty list (nothing qualifies)", not got,
                            "" if not got else f"returned {len(got)} item(s)"))
    for vid in sorted(expected):
        checks.append(check(f"includes {canon[vid]}", vid in got))
    for vid in sorted(got - expected):
        reasons = ref["explanations"].get(canon.get(vid, vid))
        detail = "; ".join(reasons) if reasons else "not a variant in the catalog scope"
        checks.append(check(f"excludes {canon.get(vid, vid)}", False, detail))
    if not expected:
        score = 1.0 if not got else 0.0
    else:
        tp = len(expected & got)
        precision = tp / len(got) if got else 0.0
        recall = tp / len(expected)
        score = 0.0 if tp == 0 else 2 * precision * recall / (precision + recall)
    return checks, score


def grade_cart_total(answer: dict, ref: dict) -> tuple[list, float]:
    checks = []
    for field, exp in ref["expected"].items():
        got = answer.get(field)
        checks.append(check(f"{field} = ${exp:.2f}", money_ok(got, exp), f"got {_fmt(got)}"))
    return checks, sum(c["passed"] for c in checks) / len(checks)


def grade_returns(answer: dict, ref: dict) -> tuple[list, float]:
    got_lines = answer.get("returnable_lines")
    if not isinstance(got_lines, list):
        got_lines = []
    got = set()
    for x in got_lines:
        n = to_number(x)
        if n is not None:
            got.add(int(n))
    checks = []
    for line, d in ref["working"]["lines"].items():
        exp = d["returnable"]
        verdict = "returnable" if exp else "not returnable (" + ", ".join(d["reasons"]) + ")"
        checks.append(check(f"line {line} is {verdict}", (int(line) in got) == exp))
    exp_refund = ref["expected"]["refund_total"]
    got_refund = answer.get("refund_total")
    checks.append(check(f"refund_total = ${exp_refund:.2f}", money_ok(got_refund, exp_refund),
                        f"got {_fmt(got_refund)}"))
    return checks, sum(c["passed"] for c in checks) / len(checks)


def grade_pair(answer: dict, ref: dict) -> tuple[list, float]:
    checks = []
    valid = {norm_id(v) for _, v in ref["working"]["valid_cleansers"] + ref["working"]["valid_moisturizers"]}
    for field in ("cleanser_variant_id", "moisturizer_variant_id"):
        exp = ref["expected"][field]
        got = answer.get(field)
        ok = got is not None and norm_id(got) == norm_id(exp)
        if ok:
            detail = ""
        elif got is not None and norm_id(got) in valid:
            detail = f"got {got}: meets every condition but is not the cheapest"
        else:
            reasons = next((r for vid, r in ref["explanations"].items()
                            if got is not None and norm_id(vid) == norm_id(got)), None)
            detail = f"got {got}: " + ("; ".join(reasons) if reasons else "not a valid variant")
        checks.append(check(f"{field} = {exp}", ok, detail))
    exp_total = ref["expected"]["total"]
    checks.append(check(f"total = ${exp_total:.2f}", money_ok(answer.get("total"), exp_total),
                        f"got {_fmt(answer.get('total'))}"))
    return checks, sum(c["passed"] for c in checks) / len(checks)


def grade_quantities(answer: dict, ref: dict) -> tuple[list, float]:
    got = {}
    for line in answer.get("lines") or []:
        if isinstance(line, dict) and "variant_id" in line:
            n = to_number(line.get("quantity"))
            got[norm_id(line["variant_id"])] = int(n) if n is not None else None
    caps = {w["variant_id"]: w["caps"] for w in ref["working"]["lines"]}
    checks = []
    for line in ref["expected"]["lines"]:
        vid, exp = line["variant_id"], line["quantity"]
        g = got.get(norm_id(vid), "missing")
        limits = ", ".join(f"{k} {v}" for k, v in caps[vid].items())
        checks.append(check(f"{vid} quantity = {exp}", g == exp, f"got {g}; limits: {limits}"))
    exp_total = ref["expected"]["order_total"]
    checks.append(check(f"order_total = ${exp_total:.2f}", money_ok(answer.get("order_total"), exp_total),
                        f"got {_fmt(answer.get('order_total'))}"))
    return checks, sum(c["passed"] for c in checks) / len(checks)


def grade_set_and_total(answer: dict, ref: dict) -> tuple[list, float]:
    """Half the score is F1 over the variant IDs, half is the order total."""
    checks, f1 = grade_variant_set(answer, ref)
    exp_total = ref["expected"]["order_total"]
    total_ok = money_ok(answer.get("order_total"), exp_total)
    checks.append(check(f"order_total = ${exp_total:.2f}", total_ok, f"got {_fmt(answer.get('order_total'))}"))
    return checks, 0.5 * f1 + 0.5 * float(total_ok)


GRADERS = {
    "set_and_total": grade_set_and_total,
    "variant_set": grade_variant_set,
    "cart_total": grade_cart_total,
    "returns": grade_returns,
    "pair": grade_pair,
    "quantities": grade_quantities,
}


def grade(task_id: str, reply_text: str, answers: dict | None = None) -> dict:
    """Grade one model reply for one task."""
    answers = answers or load_answers()
    ref = answers[task_id]
    answer = extract_json(reply_text)
    if answer is None:
        return {"task": task_id, "parsed": False, "answer": None, "score": 0.0, "passed": False,
                "checks": [check("reply contains a JSON object", False, "no JSON object found")]}
    checks, score = GRADERS[ref["type"]](answer, ref)
    passed = all(c["passed"] for c in checks)
    return {"task": task_id, "parsed": True, "answer": answer, "score": score,
            "passed": passed, "checks": checks}


def reference_reply(task_id: str, answers: dict | None = None) -> str:
    """The reference answer formatted as a model reply (used by the oracle run)."""
    answers = answers or load_answers()
    return "```json\n" + json.dumps(answers[task_id]["expected"], indent=2) + "\n```"
