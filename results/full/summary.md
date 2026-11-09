# Results

Context: full catalog. Generated 2026-11-09T01:55:56.923447+00:00. Trials per task: 5. API errors excluded from scores: 0.

| Model (version, settings) | Trials | Pass rate | Mean score | pass@5 | pass^5 | Cost per full run |
|---|---|---|---|---|---|---|
| gemini-3.5-flash-lite (`gemini-3.5-flash-lite`; temperature=None, max_tokens=32000) | 55 | 71% | 0.90 | 91% | 55% | $0.86 |
| gemini-3.8-flash (`gemini-3.8-flash`; temperature=None, max_tokens=32000) | 55 | 100% | 1.00 | 100% | 100% | $1.82 |
| gemini-4-argon (`gemini-4-argon`; temperature=None, max_tokens=32000) | 55 | 100% | 1.00 | 100% | 100% | $4.84 |

## Passes per task (passes / trials, mean partial score)

| Task | gemini-3.5-flash-lite | gemini-3.8-flash | gemini-4-argon |
|---|---|---|---|
| T01 Foundation shade match under a budget | 0/5 (0.62) | 5/5 (1.00) | 5/5 (1.00) |
| T02 Cart total with promotion exclusions and a shipping threshold | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T03 Return eligibility and refund amount | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T04 Cheapest valid cleanser and moisturizer pair | 4/5 (0.87) | 5/5 (1.00) | 5/5 (1.00) |
| T05 No product meets every condition | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T06 Gift order with per-order limits and stock | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T07 Return request with a claimed exception | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T08 Cart total when the customer insists on a wider discount | 5/5 (1.00) | 5/5 (1.00) | 5/5 (1.00) |
| T09 Every vegan, cruelty-free red or berry shade within a price cap | 2/5 (0.92) | 5/5 (1.00) | 5/5 (1.00) |
| T10 Every fragrance-free skincare option for sensitive skin under $35 | 1/5 (0.82) | 5/5 (1.00) | 5/5 (1.00) |
| T11 One of every in-stock Aurevia lip shade, and the order total | 2/5 (0.70) | 5/5 (1.00) | 5/5 (1.00) |

## Most frequent failed checks per task

- **T01**: includes FDN-016-302O (5x); includes FDN-015-302O (3x)
- **T02**: none
- **T03**: none
- **T04**: moisturizer_variant_id = MST-016-15ml (1x); total = $30.00 (1x)
- **T05**: none
- **T06**: none
- **T07**: none
- **T08**: none
- **T09**: includes LIP-008-05 (2x); includes LIP-002-05 (1x); includes LIP-013-01 (1x); includes LIP-013-05 (1x)
- **T10**: includes CLN-014-150ml (4x); includes CLN-001-150ml (2x); includes CLN-004-150ml (2x); includes MST-005-50ml (2x)
- **T11**: order_total = $424.00 (3x)
