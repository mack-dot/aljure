# Sonnet → Opus paired decomposition (OOLONG-synth 32K dev)

This compares the same 21 tasks (7 independent contexts) across four arms:
Aljure and native Prime, each with Sonnet 5.5 (plan `0b6a0451…`) and with
Opus 5.5 (plan `d6e9b40d…`). It reads recorded traces only; there are no
model calls.

- Script: `scripts/model_harness_decomposition.py`.
- Evidence: `evidence/opus-capability-gap/decomposition.json`, one row per arm-task.

## Verified totals

These match the saved official scorer reports.

| | Aljure Sonnet | Prime Sonnet | Aljure Opus | Prime Opus |
| --- | --- | --- | --- | --- |
| Mean score (21 tasks) | 0.768 | 0.800 | 0.771 | 0.919 |
| Answered | 21 | 20 | 19 | 21 |
| Model calls | 95 | 94 | 96 | 125 |
| Output tokens (incl. thinking) | 29,846 | 30,263 | 27,974 | 33,548 |
| Cost | $0.81 | $1.59 | $1.73 | $3.81 |
| Tool-call or expression errors | 5 | 0 | 2 | 1 |
| Child sessions or sub-agents | 0 | 0 | 0 | 6 (all in one arm) |
| Mean share of items shown to the model | 0.42 | 0.42 | 0.38 | 0.54 |

## Same-subset comparison

Means over different task sets are not compared. These are the 19 tasks that
Aljure Opus answered:

| Same 19 tasks | Sonnet | Opus | Change |
| --- | --- | --- | --- |
| Aljure | 0.744 | 0.852 | **+0.108** |
| Prime | 0.779 | 0.911 | **+0.132** |

On tasks where both harnesses delivered an answer, Opus improved Aljure about
as much as it improved Prime.

Aljure's aggregate stayed flat (0.768 → 0.771) because two new delivery
failures (tasks 6 and 7) cancelled its gains on tasks 4 and 19–21.

## Per task

S = Sonnet, O = Opus, A = Aljure, P = Prime. "Review" is the share of the
context's distinct instances that appeared in any tool result the model saw.
It is a proxy for semantic review: an item that was shown was not necessarily
judged.

| # | Context | Type | Aljure S → O | Prime S → O | Opus A − P | Review A S/O | Review P S/O | Calls A S/O | Calls P S/O | How the Opus Aljure arm ended |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | negation | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.09 / 0.09 | 0.10 / 0.09 | 4 / 3 | 5 / 5 | done |
| 2 | negation | label | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.01 / 0.25 | 0.21 / 0.50 | 4 / 5 | 5 / 6 | done |
| 3 | negation | label | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.49 / 0.25 | 0.50 / 0.50 | 7 / 6 | 6 / 6 | done, after a text-only reply |
| 4 | formality | user | 0.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.12 / 0.19 | 0.10 / 0.31 | 4 / 6 | 4 / 5 | done |
| 5 | formality | label | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.11 / 0.01 | 0.09 / 0.10 | 4 / 3 | 4 / 4 | done |
| 6 | formality | label | 1.00 → **0.00** | 1.00 → 1.00 | −1.00 | 0.39 / 0.38 | 0.40 / 0.41 | 4 / 5 | 4 / 5 | **no answer**: two text-only replies |
| 7 | imdb | comparison | 1.00 → **0.00** | 1.00 → 1.00 | −1.00 | 0.91 / 0.04 | 0.03 / 1.00 | 5 / 6 | 4 / 5 | **no answer**: provider-truncated turn |
| 8 | imdb | user | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.18 / 0.17 | 0.20 / 0.20 | 4 / 2 | 4 / 4 | done |
| 9 | imdb | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.25 / 0.25 | 0.28 / 0.28 | 6 / 4 | 4 / 4 | done |
| 10 | app_reviews | numeric | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.00 / 0.02 | 0.02 / 0.02 | 3 / 3 | 3 / 3 | done |
| 11 | app_reviews | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.09 / 0.00 | 0.09 / 0.10 | 3 / 4 | 4 / 4 | done |
| 12 | app_reviews | label | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.02 / 0.32 | 0.34 / 0.34 | 4 / 4 | 5 / 4 | done |
| 13 | yahoo | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.96 / 0.96 | 0.65 / 1.00 | 4 / 5 | 7 / 4 | done |
| 14 | yahoo | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.06 / 0.96 | 0.65 / 1.00 | 3 / 5 | 4 / 5 | done, after a text-only reply |
| 15 | yahoo | comparison | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.96 / 0.96 | 1.00 / 1.00 | 5 / 5 | 4 / 6 | done |
| 16 | multinli | numeric | 0.00 → 0.08 | 0.01 → **1.00** | −0.92 | 0.97 / 0.97 | 1.00 / 1.00 | 5 / 8 | 6 / 26 | done |
| 17 | multinli | numeric | 1.00 → 1.00 | 0.00 → 1.00 | +0.00 | 0.02 / 0.03 | 0.03 / 0.04 | 5 / 2 | 3 / 4 | done |
| 18 | multinli | user | 1.00 → 1.00 | 1.00 → 1.00 | +0.00 | 0.13 / 0.13 | 0.24 / 0.35 | 6 / 5 | 5 / 6 | done |
| 19 | agnews | numeric | 0.02 → 0.75 | 0.24 → 0.56 | +0.19 | 0.99 / 0.99 | 1.00 / 1.00 | 4 / 5 | 4 / 6 | done |
| 20 | agnews | numeric | 0.01 → 0.18 | 0.42 → 0.56 | −0.38 | 0.99 / 0.99 | 1.00 / 1.00 | 6 / 5 | 4 / 6 | done, after a text-only reply |
| 21 | agnews | numeric | 0.10 → 0.18 | 0.13 → 0.18 | +0.00 | 0.99 / 0.02 | 1.00 / 1.00 | 5 / 5 | 5 / 7 | done |

## Where the Opus gap comes from

The gap is Aljure − Prime under Opus, summed over tasks and divided by 21:
−0.148.

| Source | Tasks | Contribution |
| --- | --- | --- |
| Answer delivery | 6 (text-only final answer), 7 (provider-truncated turn) | −0.095 (64%) |
| MultiNLI exact count | 16 | −0.044 (30%) |
| AG News counts | 19 (+0.19), 20 (−0.38), 21 (0) | −0.009 (6%) |

Prime's own Sonnet → Opus gain was +0.119 over 21 tasks. It came from:

- task 16, +0.99 (`PRIME_MULTINLI_TRAJECTORY_ANALYSIS.md`);
- task 17, +1.00 (under Sonnet, Prime never wrote its answer file);
- AG News, +0.32, +0.14 and +0.05.

## Limits

- **One run per arm-task.** Run-to-run variance is not measured.
- **The count tasks are noisy.** The scorer gives 0.75^|error|, so an error of 2 scores 0.56 and an error of 6 scores 0.18.
- **The review proxy measures exposure, not correctness.** It counts what was shown, not what was judged correctly.
- **These dev tasks have already been observed.** This is diagnostic evidence, not a held-out claim.
