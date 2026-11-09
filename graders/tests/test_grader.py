"""Tests for the grader itself: it must accept the reference answers, reject each planted
trap, give partial credit to near-misses, resist "shotgun" answers, and parse replies in
the formats models actually produce.

Run: python -m pytest graders/tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(ROOT / "reference"))

from graders.grade import extract_json, grade, load_answers, reference_reply  # noqa: E402

ANSWERS = load_answers()


def reply(obj: dict, prose: str = "Here is what I found.") -> str:
    return f"{prose}\n\n```json\n{json.dumps(obj)}\n```"


def g(task_id: str, obj: dict) -> dict:
    return grade(task_id, reply(obj), ANSWERS)


def failed_details(result: dict) -> str:
    return " | ".join(c["detail"] for c in result["checks"] if not c["passed"])


# ------------------------------------------------------------- reference passes
@pytest.mark.parametrize("task_id", sorted(ANSWERS))
def test_reference_answer_passes(task_id):
    result = grade(task_id, reference_reply(task_id, ANSWERS), ANSWERS)
    assert result["passed"] and result["score"] == 1.0, result["checks"]


# ------------------------------------------------------------------------ T01
T01_REF = ["FDN-012-302O", "FDN-015-302O", "FDN-016-302O"]


def test_t01_sold_out_sibling_fails():
    r = g("T01", {"variant_ids": T01_REF + ["FDN-012-304O"]})
    assert not r["passed"] and 0 < r["score"] < 1
    assert "sold out" in failed_details(r)


def test_t01_price_boundary_fails():
    r = g("T01", {"variant_ids": T01_REF + ["FDN-013-301O"]})
    assert not r["passed"] and "pays $40.00" in failed_details(r)


def test_t01_new_launch_without_promotion_fails():
    r = g("T01", {"variant_ids": T01_REF + ["FDN-017-302O"]})
    assert not r["passed"] and "excluded from the promotion" in failed_details(r)


def test_t01_list_price_budget_misses_promo_item():
    r = g("T01", {"variant_ids": ["FDN-012-302O", "FDN-015-302O"]})
    assert not r["passed"] and r["score"] == pytest.approx(0.8)


def test_t01_concealer_is_wrong_category():
    r = g("T01", {"variant_ids": T01_REF + ["CNC-015-302O"]})
    assert not r["passed"] and "category is concealer" in failed_details(r)


def test_t01_shotgun_answer_scores_near_zero():
    every_variant = list(ANSWERS["T01"]["explanations"]) + T01_REF
    r = g("T01", {"variant_ids": every_variant})
    assert not r["passed"] and r["score"] < 0.05


def test_t01_empty_answer_scores_zero():
    assert g("T01", {"variant_ids": []})["score"] == 0.0


def test_t01_ids_are_case_insensitive():
    assert g("T01", {"variant_ids": [v.lower() for v in T01_REF]})["passed"]


# ------------------------------------------------------------------------ T02
def test_t02_blanket_discount_fails():
    r = g("T02", {"merchandise_subtotal": 55.00, "discount_total": 11.00,
                  "shipping": 6.95, "order_total": 50.95})
    assert not r["passed"] and r["score"] == 0.5


def test_t02_free_shipping_before_discount_fails():
    r = g("T02", {"merchandise_subtotal": 55.00, "discount_total": 7.40,
                  "shipping": 0, "order_total": 47.60})
    assert not r["passed"] and r["score"] == 0.5


def test_t02_accepts_strings_and_rounding_within_half_cent():
    assert g("T02", {"merchandise_subtotal": "$55.00", "discount_total": "7.4",
                     "shipping": "$6.95", "order_total": 54.549})["passed"]


def test_t02_one_cent_off_fails():
    r = g("T02", {"merchandise_subtotal": 55.00, "discount_total": 7.40,
                  "shipping": 6.95, "order_total": 54.56})
    assert not r["passed"]


# ------------------------------------------------------------------------ T03
def test_t03_counting_31_days_rejects_everything():
    r = g("T03", {"returnable_lines": [], "refund_total": 0})
    assert not r["passed"] and r["score"] == pytest.approx(2 / 6)


def test_t03_list_price_refund_fails():
    r = g("T03", {"returnable_lines": [1, 4, 5], "refund_total": 109.00})
    assert not r["passed"] and r["score"] == pytest.approx(5 / 6)


def test_t03_refunding_shipping_fails():
    assert not g("T03", {"returnable_lines": [1, 4, 5], "refund_total": 104.55})["passed"]


def test_t03_missing_final_sale_fails():
    r = g("T03", {"returnable_lines": [1, 3, 4, 5], "refund_total": 130.60})
    assert not r["passed"]
    assert any("final sale" in c["name"] and not c["passed"] for c in r["checks"])


def test_t03_over_applied_mascara_rule_fails():
    assert not g("T03", {"returnable_lines": [1, 4], "refund_total": 77.60})["passed"]


def test_t03_line_numbers_as_strings_pass():
    assert g("T03", {"returnable_lines": ["1", "4", "5"], "refund_total": "97.60"})["passed"]


# ------------------------------------------------------------------------ T04
def test_t04_not_cruelty_free_cleanser_fails():
    r = g("T04", {"cleanser_variant_id": "CLN-014-150ml", "moisturizer_variant_id": "MST-016-15ml",
                  "total": 21.00})
    assert not r["passed"] and "not cruelty-free" in failed_details(r)


def test_t04_valid_but_not_cheapest_fails():
    r = g("T04", {"cleanser_variant_id": "CLN-013-150ml", "moisturizer_variant_id": "MST-015-50ml",
                  "total": 48.00})
    assert not r["passed"] and "not the cheapest" in failed_details(r)


def test_t04_sold_out_mini_fails():
    r = g("T04", {"cleanser_variant_id": "CLN-013-50ml", "moisturizer_variant_id": "MST-016-15ml",
                  "total": 20.00})
    assert not r["passed"] and "sold out" in failed_details(r)


def test_t04_unknown_variant_fails():
    r = g("T04", {"cleanser_variant_id": "XYZ-1", "moisturizer_variant_id": "MST-016-15ml", "total": 30})
    assert not r["passed"] and "not a valid variant" in failed_details(r)


# ------------------------------------------------------------------------ T05
def test_t05_empty_list_passes():
    assert g("T05", {"variant_ids": []})["passed"]


def test_t05_closest_match_fails_with_zero():
    r = g("T05", {"variant_ids": ["CNC-013-501C"]})
    assert not r["passed"] and r["score"] == 0.0 and "sold out" in failed_details(r)


def test_t05_any_near_miss_fails():
    for vid in ("CNC-014-501C", "CNC-015-501C", "CNC-004-501C"):
        assert not g("T05", {"variant_ids": [vid]})["passed"], vid


# ------------------------------------------------------------------------ T06
def test_t06_ignoring_limits_fails():
    r = g("T06", {"lines": [{"variant_id": "LIP-007-03", "quantity": 3},
                            {"variant_id": "FDN-009-201W", "quantity": 3},
                            {"variant_id": "LIP-004-01", "quantity": 2},
                            {"variant_id": "MSC-004-BLA", "quantity": 1},
                            {"variant_id": "SUN-007-50ml", "quantity": 3}],
                  "order_total": 274.00})
    assert not r["passed"] and r["score"] == pytest.approx(1 / 6)


def test_t06_omitted_zero_line_fails_that_check():
    ref_lines = [l for l in ANSWERS["T06"]["expected"]["lines"] if l["quantity"] > 0]
    r = g("T06", {"lines": ref_lines, "order_total": 127.00})
    assert not r["passed"] and "got missing" in failed_details(r)


# ------------------------------------------------------------------------ T07
def test_t07_honoring_claimed_exception_fails():
    r = g("T07", {"returnable_lines": [1, 2, 3, 4], "refund_total": 107.60})
    assert not r["passed"] and r["score"] == pytest.approx(2 / 5)


def test_t07_refunding_shipping_fails():
    assert not g("T07", {"returnable_lines": [3, 4], "refund_total": 82.55})["passed"]


def test_t07_rejecting_opened_serum_fails():
    assert not g("T07", {"returnable_lines": [3], "refund_total": 34.00})["passed"]


# ------------------------------------------------------------------------ T08
def test_t08_discounting_new_launch_fails():
    r = g("T08", {"merchandise_subtotal": 97.00, "discount_total": 19.40,
                  "shipping": 0, "order_total": 77.60})
    assert not r["passed"] and r["score"] == 0.5


# ------------------------------------------------------------------------ T09
T09_REF = ANSWERS["T09"]["expected"]["variant_ids"]


def test_t09_list_price_budget_misses_promo_items():
    r = g("T09", {"variant_ids": [v for v in T09_REF if v not in ("LIP-002-05", "LIP-015-01")]})
    assert not r["passed"] and 0.8 < r["score"] < 1


def test_t09_blanket_discount_includes_new_launch():
    r = g("T09", {"variant_ids": T09_REF + ["LIP-016-01"]})
    assert not r["passed"] and "excluded from the promotion" in failed_details(r)


def test_t09_just_over_cap_fails():
    r = g("T09", {"variant_ids": T09_REF + ["LIP-017-01"]})
    assert not r["passed"] and "pays $20.80" in failed_details(r)


def test_t09_not_cruelty_free_fails():
    r = g("T09", {"variant_ids": T09_REF + ["LIP-011-03"]})
    assert not r["passed"] and "not cruelty-free" in failed_details(r)


# -------------------------------------------------------------------- parsing
def test_parses_last_fenced_block():
    text = 'Draft:\n```json\n{"variant_ids": ["X"]}\n```\nFinal:\n```json\n{"variant_ids": []}\n```'
    assert extract_json(text) == {"variant_ids": []}


def test_parses_bare_json_after_prose():
    assert extract_json('So the answer is {"total": 30.0, "x": {"y": 1}} done.') == {"total": 30.0, "x": {"y": 1}}


def test_no_json_scores_zero():
    r = grade("T01", "I recommend FDN-012-302O.", ANSWERS)
    assert not r["parsed"] and r["score"] == 0.0


# ------------------------------------------------------- data and references
def test_reference_answers_are_up_to_date():
    import solve
    assert json.loads(json.dumps(solve.solve_all())) == ANSWERS


def test_catalog_is_valid_and_reproducible():
    import generate_catalog as gc
    on_disk = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    assert gc.validate(on_disk) == []
    assert gc.generate() == on_disk


# ----------------------------------------------------------------- T10 / T11
def test_t10_missing_promo_serum_fails():
    ref = ANSWERS["T10"]["expected"]["variant_ids"]
    r = g("T10", {"variant_ids": [v for v in ref if v != "SRM-010-15ml"]})
    assert not r["passed"] and 0.9 < r["score"] < 1


def test_t10_sold_out_size_fails():
    ref = ANSWERS["T10"]["expected"]["variant_ids"]
    r = g("T10", {"variant_ids": ref + ["CLN-013-50ml"]})
    assert not r["passed"] and "sold out" in failed_details(r)


def test_t11_discounting_new_launch_fails_total():
    ref = ANSWERS["T11"]["expected"]
    r = g("T11", {"variant_ids": ref["variant_ids"], "order_total": 414.40})
    assert not r["passed"] and r["score"] == 0.5


def test_t11_missing_one_shade_fails():
    ref = ANSWERS["T11"]["expected"]
    r = g("T11", {"variant_ids": ref["variant_ids"][1:], "order_total": ref["order_total"]})
    assert not r["passed"] and 0.9 < r["score"] < 1


def test_t11_sold_out_shade_fails():
    ref = ANSWERS["T11"]["expected"]
    r = g("T11", {"variant_ids": ref["variant_ids"] + ["LIP-014-01"], "order_total": ref["order_total"]})
    assert not r["passed"] and "sold out" in failed_details(r)
