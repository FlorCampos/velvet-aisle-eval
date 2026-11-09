# Results

Context: focused catalog. Generated 2026-11-09T01:55:57.293724+00:00. Trials per task: 3. API errors excluded from scores: 0.

| Model (version, settings) | Trials | Pass rate | Mean score | pass@3 | pass^3 | Cost per full run |
|---|---|---|---|---|---|---|
| gemini-3.5-flash-lite (`gemini-3.5-flash-lite`; temperature=None, max_tokens=32000) | 33 | 82% | 0.95 | 100% | 55% | $0.27 |
| gemini-3.8-flash (`gemini-3.8-flash`; temperature=None, max_tokens=32000) | 33 | 100% | 1.00 | 100% | 100% | $0.45 |
| gemini-4-argon (`gemini-4-argon`; temperature=None, max_tokens=32000) | 33 | 100% | 1.00 | 100% | 100% | $1.23 |

## Passes per task (passes / trials, mean partial score)

| Task | gemini-3.5-flash-lite | gemini-3.8-flash | gemini-4-argon |
|---|---|---|---|
| T01 Foundation shade match under a budget | 2/3 (0.93) | 3/3 (1.00) | 3/3 (1.00) |
| T02 Cart total with promotion exclusions and a shipping threshold | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T03 Return eligibility and refund amount | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T04 Cheapest valid cleanser and moisturizer pair | 2/3 (0.78) | 3/3 (1.00) | 3/3 (1.00) |
| T05 No product meets every condition | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T06 Gift order with per-order limits and stock | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T07 Return request with a claimed exception | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T08 Cart total when the customer insists on a wider discount | 3/3 (1.00) | 3/3 (1.00) | 3/3 (1.00) |
| T09 Every vegan, cruelty-free red or berry shade within a price cap | 2/3 (0.93) | 3/3 (1.00) | 3/3 (1.00) |
| T10 Every fragrance-free skincare option for sensitive skin under $35 | 1/3 (0.93) | 3/3 (1.00) | 3/3 (1.00) |
| T11 One of every in-stock Aurevia lip shade, and the order total | 2/3 (0.83) | 3/3 (1.00) | 3/3 (1.00) |

## Most frequent failed checks per task

- **T01**: includes FDN-016-302O (1x)
- **T02**: none
- **T03**: none
- **T04**: cleanser_variant_id = CLN-013-150ml (1x); total = $30.00 (1x)
- **T05**: none
- **T06**: none
- **T07**: none
- **T08**: none
- **T09**: includes LIP-002-05 (1x); includes LIP-008-05 (1x); includes LIP-015-01 (1x)
- **T10**: excludes SRM-009-15ml (1x); excludes SRM-009-30ml (1x); includes TNR-005-200ml (1x); excludes CLN-007-150ml (1x)
- **T11**: order_total = $424.00 (1x)
