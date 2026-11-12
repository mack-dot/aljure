# OOLONG-synth independent contexts, 32K (dev): results

**LIVE MODEL RUN, development evidence.** Plan `0b6a0451…` (commit `dfd82fb`),
approved by the operator and run on 2026-10-29. All 42 arms ran; cost
accounting is complete. Protocol: `SYNTH_INDEPENDENT_32K_PROTOCOL.md`.
Evidence: `evidence/synth-indep-32k-dev/` (plan, preflight, run report sha256
`3f944e23…`, results, statistics).

## Primary endpoint (7 independent contexts, 21 tasks)

| | Aljure | Prime |
| --- | --- | --- |
| Deadline-aware mean score | **0.768** | **0.800** |
| Tasks with score ≥ 0.9 | 16 | 16 |
| Completed with an answer | 21 / 21 | 20 / 21 |

- Paired difference, Aljure − Prime, each context weighted equally:
  **−0.031**.
  - 95% cluster bootstrap interval (10,000 resamples, seed 0): [−0.174, +0.111].
  - 90% interval: [−0.143, +0.095].
- Aljure's wins, ties and losses: 1, 15, 5.
- Decision under the protocol: **inconclusive**.
  - The interval includes 0, so the result is neither superior nor inferior.
  - The 90% interval is not inside ±0.05, so the harnesses are not shown to be equivalent.

## Secondary endpoints

| | Aljure | Prime |
| --- | --- | --- |
| Total wall time | **501 s** | 564 s |
| Latency p50 / p95 | 22.1 s / 35.8 s | 24.1 s / 40.2 s |
| Model calls | 95 | 94 |
| API-rate-equivalent cost | **$0.815** | $1.590 |
| Cost per task with score ≥ 0.9 | $0.051 | $0.099 |
| Cost per score point | $0.050 | $0.095 |
| Score per model call | 0.170 | 0.179 |

**Preregistered target: met** (development result, not a held-out claim). All three conditions hold:
- The primary result is not inferior.
- The point estimate (−0.031) is at least −0.05.
- Aljure's cost (51% of Prime's) and wall time (89% of Prime's) are both lower.

## Per context

| Context | Aljure scores | Prime scores | Mean difference | Wall time A / P | Calls A / P | Cost A / P |
| --- | --- | --- | --- | --- | --- | --- |
| negation | 1, 1, 1 | 1, 1, 1 | 0 | 100 / 120 s | 15 / 16 | $0.14 / $0.27 |
| formality | **0**, 1, 1 | 1, 1, 1 | −0.333 | 57 / 65 s | 12 / 12 | $0.07 / $0.15 |
| imdb | 1, 1, 1 | 1, 1, 1 | 0 | 67 / 57 s | 15 / 12 | $0.11 / $0.18 |
| app_reviews | 1, 1, 1 | 1, 1, 1 | 0 | 42 / 54 s | 10 / 12 | $0.04 / $0.14 |
| yahoo | 1, 1, 1 | 1, 1, 1 | 0 | 67 / 87 s | 12 / 15 | $0.11 / $0.26 |
| multinli | 0.00, **1**, 1 | 0.01, **0**, 1 | +0.333 | 74 / 80 s | 16 / 14 | $0.13 / $0.25 |
| agnews | 0.02, 0.01, 0.10 | 0.24, 0.42, 0.13 | −0.220 | 94 / 101 s | 15 / 13 | $0.21 / $0.34 |

## What the differences were

- **Formality, "which user has the most informal instances":** Aljure
  labelled "informal" with a regex heuristic and answered at once, without
  reviewing any sentence: user 15684 (8 matches) against the correct 27575
  (6 matches). This is the same rules-only failure as in A1c
  (`RESIDUAL_REASONING_ANALYSIS.md`).
- **Multinli, user-filtered count:** Prime worked out a candidate answer but
  ended with "I did not write /work/answer.txt". A missing answer scores 0.
  This is a model behaviour, not an infrastructure failure: the native harness
  exited normally.
- **Multinli and agnews exact counts:** both harnesses failed or scored low.
  On agnews both read essentially every article (339–341 of 341 shown in the
  checked arm), so the gap is labelling accuracy at that scale, not skipped
  review. The scorer gives partial credit of 0.75^|error|, so Prime's counts
  were off by roughly 3–7 and Aljure's by roughly 8–16.
- **Every other task:** both harnesses scored 1.0. Aljure was cheaper in all 7
  contexts and faster in 6.

## Limits

- 7 contexts, one run each; one context per dataset. The interval is wide.
- The tasks are the dev suite. The sealed held-out suite (`c74547bd…`, windows
  …17) was not run, scored or inspected.
- Another session's `buildx_buildkit` container ran on the host during the
  run. Both harnesses shared that load.
- Compute boundary (`PRIME_PARITY_MATRIX.md` row 4): Aljure's controller runs
  on the host, while Prime's loop shares its 1-CPU container.
