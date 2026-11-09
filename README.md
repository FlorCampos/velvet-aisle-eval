# Velvet Aisle: do shopping assistants respect every constraint?

**Browse every graded trial online:** [https://florcampos.github.io/Hackaton-Evals/](https://florcampos.github.io/Hackaton-Evals/)

**Code and data:** [https://github.com/FlorCampos/velvet-aisle-eval](https://github.com/FlorCampos/velvet-aisle-eval)

## What it tests

Whether a model acting as a store's shopping assistant returns answers that satisfy **every**
hard constraint at once, including when the customer pushes for an exception: stock,
budgets that depend on an active promotion, promotion exclusions, a free-shipping threshold,
return rules, and per-order limits. Each task has one
correct, machine-checkable answer, and each one is surrounded by planted near-misses that
break exactly one rule.

## Who it's for and why it matters

Retailers are putting LLM assistants in front of customers. When an assistant recommends a
sold-out shade, quotes the wrong total, or approves a return that policy forbids, the cost is
real: cancelled orders, refunds paid by hand, chargebacks, and customers who stop trusting
the assistant. These failures are hard to catch with spot checks because the answer looks
plausible: it is almost right. I come from 8+ years of QA automation, where this is the
classic boundary-and-interaction bug: each rule works alone and fails in combination.

## The store

Velvet Aisle is a fictional online beauty store. Every brand, product and shade is invented.

- `data/catalog.json`: 136 products and 520 variants in 10 categories, with shades (depth
  and undertone), sizes, prices, stock, and flags such as fragrance-free, vegan,
  cruelty-free, new launch, final sale and per-order limits.
  - 120 products come from `data/generate_catalog.py`, which uses a fixed seed and always
    produces the same file.
  - 16 products in `data/hand_crafted.json` were written by hand to plant the valid answers
    and the near-misses for specific tasks.
- `data/policies.md`: the store rules (availability, per-order limits, the "Aurevia Week"
  promotion, budgets, shipping, returns, and no exceptions). They are short and unambiguous on purpose, so
  every grading rule can be traced to a sentence in the policy or the task.

## Tasks

Each task is a single customer message. The model receives the policies and the catalog,
and must answer with a JSON object in a fixed format. Every task runs in two conditions:

- **Focused:** only the categories relevant to the task, plus distractor categories
  (about 5k-15k tokens).
- **Full:** the entire catalog of 136 products (about 29k tokens), as a real store
  assistant would see it.

Comparing the two shows whether failures come from the rules themselves or from finding the
right items in a realistic catalog.

| ID | Task | Answer | Why it's hard |
|---|---|---|---|
| T01 | Foundation shade match under a budget | 3 variant IDs | Six constraints at once. One valid shade is only under budget after the promotion, and the near-misses include sold-out siblings, a shade at exactly $40.00, a new Aurevia launch the promotion doesn't cover, and concealers in the same shade |
| T02 | Cart total | 4 amounts | All three items are Aurevia, but the blush is excluded (new launch and final sale). The cart is $55.00 before discounts and $47.60 after, so the free-shipping threshold flips depending on the order of operations |
| T03 | Return eligibility and refund | Lines + refund | The request is on day 30 (on time; October has 31 days). One item is final sale only according to the catalog. Opened mascara is not returnable but unopened mascara is. The refund uses prices paid, not list prices, and excludes shipping |
| T04 | Cheapest cleanser + moisturizer pair | 2 variant IDs + total | The cheapest-looking options each break one rule (not cruelty-free, not for sensitive skin, not fragrance-free, sold out). The cheapest valid moisturizer is a 15 ml mini |
| T05 | No product meets every condition | Empty list | Every deep, cool concealer misses exactly one condition. The correct answer is "nothing qualifies" |
| T06 | Gift order with limits | 5 quantities + total | Each line is capped by a different rule (per-order limit, stock below the limit, sold out, limit plus promotion) |
| T07 | Return with a claimed exception | Lines + refund | The customer says an agent promised an exception and asks for a courtesy shipping refund. The policy allows no exceptions, but the opened serum is still returnable |
| T08 | Cart total under pressure | 4 amounts | The customer insists the promotion covers a new launch. The correct total applies 20% to only two of the three items |
| T09 | Every vegan, cruelty-free red or berry shade up to $20 | 9 variant IDs | A long list across two categories. The cap is inclusive and depends on the promotion: two shades pay exactly $20.00 (valid), one pays $20.80, and a new launch gets no discount |
| T10 | Every fragrance-free skincare option for sensitive skin under $35 | 12 variant IDs | An exhaustive search over about 140 skincare variants in five categories, with more than 20 near-misses. Sizes count separately, and one serum is only under $35 after the promotion |
| T11 | One of every in-stock Aurevia lip shade, and the total | 22 variant IDs + total | The model must enumerate 22 shades across six products, skip two sold-out shades, and add 22 prices where a new launch gets no discount |

Each task file in `tasks/` lists its planted traps and why it is hard. The model never
sees these files; the harness sends only `prompt` and `output_format`.

## Grading

All grading is deterministic code (`graders/grade.py`). There is no LLM judge.

1. `reference/solve.py` computes the expected answer for every task directly from the
   catalog and the policies, and writes `reference/answers.json`. It also records, for every
   variant in scope, which condition it fails, so the grader can explain wrong items. It
   raises an error if a "cheapest" answer is not unique.
2. The grader extracts the last JSON object from the reply and runs one check per component.
   - **Variant-list tasks (T01, T05, T09, T10):** one check per expected item and per extra item.
     The score is F1, so listing everything scores near 0. In T05 the only passing answer is
     an empty list. T11 scores half on F1 over its list and half on its order total.
   - **Amounts (T02, T03, T04, T06, T07, T08):** must be within half a cent ($54.549 passes, $54.56
     fails). Strings like `"$54.55"` are accepted.
   - **Score:** the fraction of checks passed (partial credit). A trial **passes** only if
     every check passes.

**How I validated the grader:**

- `python run_eval.py --oracle` grades the reference answers: all 11 pass.
- `python -m pytest graders/tests -q` runs 56 tests:
  - the reference answer passes for every task;
  - every planted trap fails, with the right explanation;
  - near-misses get partial credit;
  - a "shotgun" answer listing every variant scores below 0.05;
  - answers in different formats (strings, lower-case IDs, prose before the JSON) are
    parsed;
  - `reference/answers.json` matches a fresh solve;
  - the catalog regenerates byte-for-byte.
- I checked every reference answer by hand against the catalog and the
  policies (worked steps are stored in `reference/answers.json` under `working`).

## How to run

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest graders/tests -q          # grader tests (no API keys needed)
python run_eval.py --oracle                # reference answers through the grader (no API keys)

cp .env.example .env                       # then fill in the keys for the models you enable
set -a && source .env && set +a            # load the keys into the shell
python run_eval.py --context full --trials 5   # full catalog -> results/full/, transcripts/full/
python run_eval.py --trials 3                  # focused catalog -> results/, transcripts/
```

- **Models:** they are configured in `models.json` (provider, model ID, settings, and price
  per million tokens for the cost column). Any OpenAI-compatible endpoint works through
  `openai_compatible`.
- **Fresh state:** each trial is a fresh API call with no shared state. Transcripts go to
  `transcripts/<model>/<task>/trial_N.json`, and the exact system prompt of each task to
  `transcripts/_prompts/`.
- **Results:** `results/summary.md`, `results/summary.json` and `results/results.jsonl`.
- **Re-runs:** running the same command again skips finished trials, so an interrupted run
  resumes. `--summarize-only` regrades saved transcripts without calling any API.

## Results

Models were run on 2026-11-09 (UTC), through Google's OpenAI-compatible endpoint with each
model's default sampling settings and `max_tokens` 32000:

- **Full catalog:** 5 trials per task, the main result.
- **Focused catalog:** 3 trials per task, for comparison.

**Full catalog** ([results/full/summary.md](results/full/summary.md)): 165 trials, 0 API errors.

| Model | Trials per task | Pass rate | Mean score | pass@5 | pass^5 | Cost per full run |
|---|---|---|---|---|---|---|
| Gemini 4 Argon (`gemini-4-argon`) | 5 | 100% | 1.00 | 100% | 100% | $4.84 |
| Gemini 3.8 Flash (`gemini-3.8-flash`) | 5 | 100% | 1.00 | 100% | 100% | $1.82 |
| Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) | 5 | 71% | 0.90 | 91% | 55% | $0.86 |

**Focused catalog** ([results/summary.md](results/summary.md)):

| Model | Trials per task | Pass rate | Mean score | pass@3 | pass^3 | Cost (3 trials) |
|---|---|---|---|---|---|---|
| Gemini 4 Argon (`gemini-4-argon`) | 3 | 100% | 1.00 | 100% | 100% | $1.23 |
| Gemini 3.8 Flash (`gemini-3.8-flash`) | 3 | 100% | 1.00 | 100% | 100% | $0.45 |
| Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) | 3 | 82% | 0.95 | 100% | 55% | $0.27 |

**Same tasks, bigger catalog: the small model gets worse.** Flash-Lite's pass rate drops from 82% with
the focused catalog to 71% with the full one.

| Task | Focused | Full |
|---|---|---|
| T01 | 2/3 | 0/5 |
| T09 | 2/3 | 2/5 |
| T10 | 1/3 | 1/5 |
| T11 | 2/3 | 2/5 |

Argon and Flash stay at 100% in both conditions. In the focused run, 12 trials first hit Google API
rate limits (429); they were re-run once the account's spending limit was raised, and the final
results have 0 API errors.

**pass@k** means the task passed in at least one of the k trials. **pass^k** means it passed
in all k trials, which is what a store needs from an assistant serving every customer.

### Per-task notes (full catalog)

| Task | Argon | Flash | Flash-Lite | What went wrong |
|---|---|---|---|---|
| T01 | 5/5 | 5/5 | **0/5** | See below |
| T02 | 5/5 | 5/5 | 5/5 | Promotion exclusion and shipping threshold always handled |
| T03 | 5/5 | 5/5 | 5/5 | Day-30 boundary, catalog-only final-sale flag and paid-price refund always handled |
| T04 | 5/5 | 5/5 | 4/5 | Flash-Lite once chose MST-017-15ml ($9), which is not fragrance-free ([transcript](transcripts/full/gemini-3.5-flash-lite/T04/trial_3.json)) |
| T05 | 5/5 | 5/5 | 5/5 | Every model correctly answered that nothing qualifies |
| T06 | 5/5 | 5/5 | 5/5 | All limits applied |
| T07 | 5/5 | 5/5 | 5/5 | No model honored the claimed exception or refunded shipping |
| T08 | 5/5 | 5/5 | 5/5 | No model extended the discount to the new launch |
| T09 | 5/5 | 5/5 | 2/5 | Omissions: 1 to 4 of the 9 valid shades left out ([transcript](transcripts/full/gemini-3.5-flash-lite/T09/trial_3.json)) |
| T10 | 5/5 | 5/5 | 1/5 | Omissions; in the worst trial only 4 of 12 options listed ([transcript](transcripts/full/gemini-3.5-flash-lite/T10/trial_1.json)) |
| T11 | 5/5 | 5/5 | 2/5 | **Close call:** see below |

- **T01: Flash-Lite failed all 5 trials, and in every one it excluded FDN-016-302O for
  costing "$48.00", the list price.**
  - It never applied the Aurevia Week discount, which brings that shade to $38.40, under
    the customer's $40 limit.
  - In 2 of the 5 trials it also skipped FDN-015 entirely.
  - Argon not only got it right but explained each exclusion: sold out, exactly $40.00, and
    a new launch without the discount.
  - Transcripts: [Flash-Lite](transcripts/full/gemini-3.5-flash-lite/T01/trial_1.json),
    [Argon](transcripts/full/gemini-4-argon/T01/trial_1.json).
- **T11: the clearest "came close" case.**
  - Flash-Lite listed exactly the right 22 shades in all 5 trials.
  - In 3 of them it got the total wrong: $364.00, $374.00 and $444.00 instead of $424.00.
  - It knew what to buy and could not add it up.
  - Transcript: [T11 trial 1](transcripts/full/gemini-3.5-flash-lite/T11/trial_1.json).

### How the task set evolved

- **Pilot:** I first ran T01-T09 once per model with the focused catalog. Every model passed
  every task.
- **Changes after the pilot:** I added the full-catalog condition and two tasks that need
  exhaustive enumeration and arithmetic (T10, T11), because a real store assistant sees the
  whole catalog and is asked for lists and totals.
- **Nothing was removed or edited for being failed:** no task was dropped and no reference
  answer changed after seeing results.

## Main failure mode and hot take

**The policies were not the problem. The bookkeeping was.**

- **Single decisions held up.** Every model, including the cheapest, applied the rules
  correctly whenever the answer was one decision: return or not, discount or not. No model
  gave in to a customer claiming a promised exception (T07) or insisting on a wider
  discount (T08).
- **The small model broke when a rule had to change a number, or when many items had to be
  handled.**
  - It compared a budget against the list price instead of the promotional price (T01, 5 of
    5 trials).
  - It dropped items from long lists (T09, T10).
  - It mis-added a 22-line order whose items it had identified perfectly (T11).
- **More context made it worse:** given the whole catalog instead of only the relevant categories,
  its pass rate fell from 82% to 71% (T01: 2/3 to 0/5).
- **Its pass^5 was 55%:** a customer-facing assistant on this model would quote a wrong list
  or a wrong total for a large share of these requests.

**Takeaway:** cost-efficient "lite" models are the ones retailers are tempted to deploy for
customer service. For anything that quotes a price, a list or a total, that model needs a
calculator or catalog-query tool and a deterministic checker like this grader, not just a
longer prompt.

**On the frontier side**, Argon and Flash solved all 11 tasks in all trials. This eval does
not separate them; that needs harder settings (see Limitations).

## Cost and runtime

- **Cost:** one full run with the full catalog (11 tasks x 5 trials per model) cost about
  **$7.50** in total: $4.84 for Argon, $1.82 for Flash and $0.86 for Flash-Lite.
  - Prices are Google's paid-tier list prices as of November 2026.
  - Output tokens are as reported by the endpoint's `completion_tokens`.
- **Runtime:** about 10 minutes with `--concurrency 4`.
- **Prompt size:** about 29k input tokens with the full catalog, and 5k-15k with the
  focused one.

## Browse the results

**Live version:** [https://florcampos.github.io/Hackaton-Evals/](https://florcampos.github.io/Hackaton-Evals/) (the same page as `explorer/index.html`).

Open `explorer/index.html` in any browser (no server needed) to inspect every graded trial:
the model's answer, each grader check, and how the models compare on that task. Failed
trials are listed at the top for one-click access. Rebuild the page from saved results with
`python explorer/build_explorer.py` (no API calls).

## Limitations

- **One provider:** every model tested is from Google's Gemini family.
- **Frontier models are not separated:** Argon and Flash scored 100%. Separating them would need
  multi-turn dialogue, tool use, larger catalogs, or policies written less explicitly.
- **Small and single-turn:** 11 tasks, one turn each. The catalog slice is in the prompt; there
  is no tool use or multi-turn dialogue.
- **Explicit attributes:** shade depth, undertone and product attributes are given as fields.
  The eval measures constraint handling, not cosmetic judgment.
- **Fictional data:** the store is not real, and real catalogs are larger and messier.

## Provenance

- **Built during the hackathon:** the catalog generator, the planted products, the policies,
  the tasks, the reference solver, the grader and its tests, the harness, and the results
  explorer page. Nothing existed before it.
- **Data:** entirely synthetic. No real store data, no scraped data, and no employer or
  client data.
- **Related work:** a retail store with written policies is similar in spirit to the retail
  domain of τ-bench (Sierra Research, MIT licence). No tasks, data or code were taken from it.

## AI use

- **What Claude (Anthropic) drafted:** the catalog generator, the harness, the grader and
  its tests, first drafts of the eleven tasks, the results explorer page, and this README.
- **What I did:**
  - chose the domain and the failure modes to target;
  - reviewed every task, policy and planted near-miss;
  - checked each reference answer by hand;
  - read the failing transcripts myself;
  - wrote the results analysis and the hot take.
