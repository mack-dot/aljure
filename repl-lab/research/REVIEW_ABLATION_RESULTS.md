# L0–L3 review ablation: results

**Status:** LIVE MODEL RUNS, development evidence, run on 2026-10-29.
- **Approval:** the operator approved four frozen plans (`REVIEW_ABLATION_PROTOCOL.md`).
- **Model and billing:** Opus 5.5, subscription only.
- **Suite:** the dev label-count suite `dc164044…`, 11 tasks over 5 windows.
- **Prime:** native Prime ran unchanged in every plan.
- **Source:** commit `40270ba`, checkout `aljure-review-v1`.

**Evidence:**
- `evidence/review-levels-opus/comparison.json`, from `scripts/review_levels_compare.py`;
- `config-difference.json`;
- the plans, preflights and proofs.

| Plan | Hash | Arms | Outcome | Cost (Aljure + Prime, API-rate equivalent) |
| --- | --- | --- | --- | --- |
| L0, baseline | `def381f5…` | 22/22 | clean | $2.47 + $5.85 |
| L1, structured labels | `240ce694…` | 22/22 | clean | $2.68 + $5.86 |
| L2, + uncertainty audit | `51687387…` | 22/22 | clean | $2.77 + $4.34 |
| L3, + targeted review | `20f25624…` | 1/22 | **stopped**: `IsolationPreflightFailed` on arm 1; 21 arms not attempted | $0.57 |

**How L3 stopped:**
- A `docker info` stall hit both bounded readiness attempts (5.12 s and 5.08 s) for one of that arm's six worker starts.
- That worker was refused; no code ran in it.
- The runner then stopped the plan, and the chain exited before the next arm.
- Host load was high (load average about 15), from unrelated workloads.
- Total spend: about $24.5.

## Count accuracy (signed error; gold in parentheses)

| Task | Aljure L0 | L1 | L2 | Prime, run in L0 | in L1 | in L2 |
| --- | --- | --- | --- | --- | --- | --- |
| imdb negative (32) | 0 | 0 | 0 | 0 | 0 | 0 |
| imdb positive (49) | 0 | 0 | 0 | 0 | 0 | 0 |
| negation True (261) | 0 | −1 | 0 | 0 | +2 | +1 |
| negation False (422) | −1 | +11 | −2 | −1 | +1 | +30 |
| formality formal (245) | +40 | +10 | +15 | 0 | +2 | +9 |
| formality informal (357) | −26 | −18 | −8 | −10 | −29 | −14 |
| multinli entailment (145) | −8 | −19 | −9 | −6 | −12 | −9 |
| multinli neutral (164) | +12 | +12 | +16 | +12 | +16 | no answer |
| multinli contradiction (129) | −8 | −9 | −1 | −6 | −4 | −7 |
| app_reviews negative (303) | −24 | −18 | −20 | −17 | −15 | −29 |
| app_reviews positive (324) | +19 | +11 | +9 | +14 | −13 | +14 |

| | L0 | L1 | L2 |
| --- | --- | --- | --- |
| Aljure mean absolute error (11 answered) | 12.5 | 9.9 | 7.3 |
| Aljure mean signed error | +0.4 | −1.9 | 0.0 |
| Prime mean absolute error, same run | 6.0 | 8.5 | 11.3 (10 answered) |
| Aljure mean official score | 0.36 | 0.27 | 0.42 |
| Aljure calls / cost | 106 / $2.47 | 112 / $2.68 | 107 / $2.77 |
| Aljure output tokens | 42.8K | 50.3K | 51.2K |
| Aljure p50 / p95 latency | 56 / 152 s | 60 / 344 s | 95 / 134 s |
| Aljure/Prime cost | 0.42 | 0.46 | 0.64 (Prime's L2 cost is low: one Prime arm failed) |

**Count definition:** the declared count, meaning the integer right after
`Answer:`. Official scores are as scored.

**Official parses that failed** because prose follows `Answer: N` (the scorer
takes the text after the last colon):
- Aljure: 1 arm per level, 3 in total;
- Prime: 0.

## Paired comparisons (absolute error, by task; bootstrap over 5 window clusters)

| Comparison | Mean change | Better / tie / worse | 95% interval | Mechanism activation |
| --- | --- | --- | --- | --- |
| L1 − L0 | −2.6 | 4 / 3 / 4 | [−11.7, +3.8] | per-item state 6/11, against 4/11 in L0 |
| L2 − L1 | −2.6 | 6 / 2 / 3 | [−4.4, −0.5] | **0/11** (no `:unknown`, no audit, no `show-items`) |
| L3 − L2 | not evaluated | | | L3 stopped |

**Run-to-run reference:** Prime's mean absolute error across its three identical
runs was 6.0, 8.5 and 11.3. One Prime task moved from −1 to +30.

## Contract and integrity

- Every Aljure arm in L0–L2 is conformant: 33/33, 0 violations, 0 gates, 0 retries.
- The configuration report confirms:
  - L0 is byte-identical to the original prompt;
  - the tools are identical across levels;
  - each level adds only its own text.
- The held-out suite was not accessed.
