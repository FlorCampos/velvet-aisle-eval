#!/usr/bin/env python3
"""Reference solver: computes the expected answer of every task from the catalog and
the store policies, independently of any model.

It writes reference/answers.json, which the grader compares model answers against.
For variant-set tasks it also records, for every variant in scope, which conditions
it fails. The grader uses this to explain why an extra item in a model answer is wrong.

Usage:
    python reference/solve.py           # writes reference/answers.json and prints the answers
"""
from __future__ import annotations

import json
from datetime import date
from itertools import product as cartesian
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
TASKS_DIR = ROOT / "tasks"
OUT = ROOT / "reference" / "answers.json"

PROMO_BRAND = "Aurevia"
PROMO_RATE = 0.20
SHIPPING_FEE = 6.95
FREE_SHIPPING_FROM = 50.00
RETURN_WINDOW_DAYS = 30


def cents(x: float) -> float:
    """Round to cents, half up (avoids banker's rounding on .xx5 values)."""
    return float(f"{(x * 100 + 1e-9):.0f}") / 100 if x >= 0 else -cents(-x)


def load_catalog() -> tuple[dict, dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    products = {p["sku"]: p for p in catalog["products"]}
    variants = {v["variant_id"]: (p, v) for p in catalog["products"] for v in p["variants"]}
    return products, variants


def load_tasks() -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(TASKS_DIR.glob("T*.json"))]


def promo_applies(p: dict) -> bool:
    return p["brand"] == PROMO_BRAND and not p["is_new"] and not p["final_sale"]


def line_discount(p: dict, v: dict, qty: int) -> float:
    return cents(v["price"] * qty * PROMO_RATE) if promo_applies(p) else 0.0


def paid_unit_price(p: dict, v: dict) -> float:
    return cents(v["price"] - line_discount(p, v, 1))


def shipping_for(subtotal_after_discounts: float) -> float:
    return 0.0 if subtotal_after_discounts >= FREE_SHIPPING_FROM else SHIPPING_FEE


# ---------------------------------------------------------------- variant_set
def variant_failures(p: dict, v: dict, spec: dict) -> list[str]:
    """Return every condition of the spec that this variant fails (empty = valid)."""
    fails = []
    shade = v["shade"] or {}
    if "category" in spec and p["category"] != spec["category"]:
        fails.append(f"category is {p['category']}, not {spec['category']}")
    if "categories" in spec and p["category"] not in spec["categories"]:
        fails.append(f"category is {p['category']}, not one of {', '.join(spec['categories'])}")
    if "color_families" in spec and shade.get("color_family") not in spec["color_families"]:
        fails.append(f"color family is {shade.get('color_family')}, not {' or '.join(spec['color_families'])}")
    if spec.get("vegan") and not p["vegan"]:
        fails.append("not vegan")
    if spec.get("cruelty_free") and not p["cruelty_free"]:
        fails.append("not cruelty-free")
    if "skin_type" in spec and spec["skin_type"] not in (p["suitable_skin_types"] or []):
        fails.append(f"not listed for {spec['skin_type']} skin")
    if "brand" in spec and p["brand"] != spec["brand"]:
        fails.append(f"brand is {p['brand']}, not {spec['brand']}")
    if "depth" in spec and shade.get("depth") != spec["depth"]:
        fails.append(f"shade depth is {shade.get('depth')}, not {spec['depth']}")
    if "undertone" in spec and shade.get("undertone") != spec["undertone"]:
        fails.append(f"undertone is {shade.get('undertone')}, not {spec['undertone']}")
    if "finish" in spec and p["finish"] != spec["finish"]:
        fails.append(f"finish is {p['finish']}, not {spec['finish']}")
    if spec.get("fragrance_free") and not p["fragrance_free"]:
        fails.append("not fragrance-free")
    if "max_paid_price_exclusive" in spec:
        paid = paid_unit_price(p, v)
        if paid >= spec["max_paid_price_exclusive"]:
            note = f" (list ${v['price']:.2f}, promotion applied)" if promo_applies(p) else ""
            if p["brand"] == PROMO_BRAND and not promo_applies(p):
                note = " (Aurevia, but excluded from the promotion)"
            fails.append(f"pays ${paid:.2f}, not under ${spec['max_paid_price_exclusive']:.2f}{note}")
    if "max_paid_price_inclusive" in spec:
        paid = paid_unit_price(p, v)
        if paid > spec["max_paid_price_inclusive"] + 1e-9:
            note = f" (list ${v['price']:.2f}, promotion applied)" if promo_applies(p) else ""
            if p["brand"] == PROMO_BRAND and not promo_applies(p):
                note = " (Aurevia, but excluded from the promotion)"
            fails.append(f"pays ${paid:.2f}, more than ${spec['max_paid_price_inclusive']:.2f}{note}")
    if spec.get("in_stock") and v["stock"] <= 0:
        fails.append("sold out (stock 0)")
    return fails


def solve_variant_set(task: dict, products: dict) -> dict:
    spec = task["spec"]
    scope = [(p, v) for p in products.values() if p["category"] in task["context_categories"]
             for v in p["variants"]]
    explanations = {v["variant_id"]: variant_failures(p, v, spec) for p, v in scope}
    expected = sorted(vid for vid, f in explanations.items() if not f)
    # Ambiguity check: would the answer change if budgets used list prices?
    list_price_answer = sorted(
        v["variant_id"] for p, v in scope
        if not [f for f in variant_failures(p, v, spec) if not f.startswith("pays ")]
        and ("max_paid_price_exclusive" not in spec or v["price"] < spec["max_paid_price_exclusive"])
        and ("max_paid_price_inclusive" not in spec or v["price"] <= spec["max_paid_price_inclusive"])
    )
    near_misses = {vid: f for vid, f in explanations.items() if len(f) == 1}
    return {
        "type": "variant_set",
        "expected": {"variant_ids": expected},
        "explanations": {vid: f for vid, f in explanations.items() if f},
        "near_misses": near_misses,
        "notes": {"answer_if_budget_used_list_price": list_price_answer},
    }


# --------------------------------------------------------------- set_and_total
def solve_set_and_total(task: dict, products: dict, variants: dict) -> dict:
    """One unit of every variant matching the spec, then the order total for that cart."""
    base = solve_variant_set(task, products)
    cart = {"spec": {"cart": [{"variant_id": vid, "quantity": 1}
                              for vid in base["expected"]["variant_ids"]]}}
    totals = solve_cart_total(cart, variants)
    return {
        "type": "set_and_total",
        "expected": {"variant_ids": base["expected"]["variant_ids"],
                     "order_total": totals["expected"]["order_total"]},
        "explanations": base["explanations"],
        "near_misses": base["near_misses"],
        "working": totals["expected"] | {"lines": totals["working"]["lines"]},
    }


# ------------------------------------------------------------------ cart_total
def solve_cart_total(task: dict, variants: dict) -> dict:
    lines, subtotal, discount = [], 0.0, 0.0
    for item in task["spec"]["cart"]:
        p, v = variants[item["variant_id"]]
        qty = item["quantity"]
        gross = cents(v["price"] * qty)
        disc = line_discount(p, v, qty)
        subtotal += gross
        discount += disc
        lines.append({"variant_id": v["variant_id"], "quantity": qty, "unit_price": v["price"],
                      "line_total": gross, "discount": disc, "promo_applies": promo_applies(p)})
    subtotal, discount = cents(subtotal), cents(discount)
    after = cents(subtotal - discount)
    shipping = shipping_for(after)
    return {
        "type": "cart_total",
        "expected": {"merchandise_subtotal": subtotal, "discount_total": discount,
                     "shipping": shipping, "order_total": cents(after + shipping)},
        "working": {"lines": lines, "subtotal_after_discounts": after},
    }


# --------------------------------------------------------------------- returns
def solve_returns(task: dict, variants: dict) -> dict:
    spec = task["spec"]
    days = (date.fromisoformat(spec["requested"]) - date.fromisoformat(spec["delivered"])).days
    on_time = days <= RETURN_WINDOW_DAYS
    decisions, refund = {}, 0.0
    for line in spec["lines"]:
        p, v = variants[line["variant_id"]]
        reasons = []
        if not on_time:
            reasons.append(f"late: requested {days} days after delivery")
        if p["final_sale"]:
            reasons.append("final sale")
        if p["category"] == "mascara" and line["opened"]:
            reasons.append("opened mascara")
        ok = not reasons
        decisions[str(line["line"])] = {"returnable": ok, "reasons": reasons}
        if ok:
            refund += line["unit_price_paid"] * line["quantity"]
    returnable = sorted(int(k) for k, d in decisions.items() if d["returnable"])
    return {
        "type": "returns",
        "expected": {"returnable_lines": returnable, "refund_total": cents(refund)},
        "working": {"days_since_delivery": days, "on_time": on_time, "lines": decisions},
    }


# ------------------------------------------------------------------------ pair
def pair_failures(p: dict, v: dict, spec: dict) -> list[str]:
    fails = []
    if spec.get("vegan") and not p["vegan"]:
        fails.append("not vegan")
    if spec.get("cruelty_free") and not p["cruelty_free"]:
        fails.append("not cruelty-free")
    if spec.get("fragrance_free") and not p["fragrance_free"]:
        fails.append("not fragrance-free")
    if spec["skin_type"] not in (p["suitable_skin_types"] or []):
        fails.append(f"not listed for {spec['skin_type']} skin")
    if spec.get("in_stock") and v["stock"] <= 0:
        fails.append("sold out (stock 0)")
    return fails


def solve_pair(task: dict, products: dict) -> dict:
    spec = task["spec"]
    cleanser_cat, moisturizer_cat = spec["categories"]
    explanations, valid = {}, {cleanser_cat: [], moisturizer_cat: []}
    for p in products.values():
        if p["category"] not in valid:
            continue
        for v in p["variants"]:
            fails = pair_failures(p, v, spec)
            explanations[v["variant_id"]] = fails
            if not fails:
                valid[p["category"]].append((paid_unit_price(p, v), v["variant_id"]))
    pairs = sorted((cents(a[0] + b[0]), a[1], b[1])
                   for a, b in cartesian(valid[cleanser_cat], valid[moisturizer_cat]))
    if not pairs:
        raise ValueError(f"{task['id']}: no valid pair")
    if len(pairs) > 1 and pairs[0][0] == pairs[1][0]:
        raise ValueError(f"{task['id']}: cheapest pair is not unique: {pairs[:2]}")
    total, cleanser, moisturizer = pairs[0]
    return {
        "type": "pair",
        "expected": {"cleanser_variant_id": cleanser, "moisturizer_variant_id": moisturizer,
                     "total": total},
        "explanations": {vid: f for vid, f in explanations.items() if f},
        "working": {"valid_cleansers": valid[cleanser_cat], "valid_moisturizers": valid[moisturizer_cat],
                    "runner_up_pair": pairs[1] if len(pairs) > 1 else None},
    }


# ------------------------------------------------------------------ quantities
def solve_quantities(task: dict, variants: dict) -> dict:
    per_product: dict[str, int] = {}
    lines, subtotal, discount = [], 0.0, 0.0
    working = []
    for item in task["spec"]["requested"]:
        p, v = variants[item["variant_id"]]
        caps = {"requested": item["quantity"], "stock": v["stock"]}
        if p["max_per_order"] is not None:
            caps["max_per_order (remaining)"] = p["max_per_order"] - per_product.get(p["sku"], 0)
        qty = max(0, min(caps.values()))
        per_product[p["sku"]] = per_product.get(p["sku"], 0) + qty
        subtotal += cents(v["price"] * qty)
        discount += line_discount(p, v, qty)
        lines.append({"variant_id": v["variant_id"], "quantity": qty})
        working.append({"variant_id": v["variant_id"], "caps": caps, "quantity": qty,
                        "promo_applies": promo_applies(p)})
    after = cents(cents(subtotal) - cents(discount))
    shipping = shipping_for(after) if after > 0 else 0.0
    return {
        "type": "quantities",
        "expected": {"lines": lines, "order_total": cents(after + shipping)},
        "working": {"lines": working, "merchandise_subtotal": cents(subtotal),
                    "discount_total": cents(discount), "shipping": shipping},
    }


def solve_all() -> dict:
    products, variants = load_catalog()
    answers = {}
    for task in load_tasks():
        kind = task["type"]
        if kind == "variant_set":
            answers[task["id"]] = solve_variant_set(task, products)
        elif kind == "cart_total":
            answers[task["id"]] = solve_cart_total(task, variants)
        elif kind == "returns":
            answers[task["id"]] = solve_returns(task, variants)
        elif kind == "pair":
            answers[task["id"]] = solve_pair(task, products)
        elif kind == "quantities":
            answers[task["id"]] = solve_quantities(task, variants)
        elif kind == "set_and_total":
            answers[task["id"]] = solve_set_and_total(task, products, variants)
        else:
            raise ValueError(f"unknown task type {kind}")
    return answers


def main() -> None:
    answers = solve_all()
    OUT.write_text(json.dumps(answers, indent=2) + "\n", encoding="utf-8")
    for tid, a in answers.items():
        print(f"{tid} ({a['type']}): {json.dumps(a['expected'])}")


if __name__ == "__main__":
    main()
