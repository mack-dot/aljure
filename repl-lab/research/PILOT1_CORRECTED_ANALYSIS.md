# Pilot 1: corrected analysis (2026-10-30)

`PILOT1_RESULTS.md` and its evidence are preserved as the original report. This document records a
re-analysis of the same frozen records under a corrected analysis script, and nothing else changed:
the seed, the task selection, the S/D/P mechanisms and the recorded runs are untouched.

## Defects in `scripts/reuse_pilot_compare.py` at `748905c`

1. **Two failure policies.** The headline mean dropped tasks with no delivered count, while the
   paired difference imputed each arm's own worst observed error for them. An arm could therefore
   improve its headline error by failing to deliver, and the two numbers could disagree in sign
   (they did for D: 0.244 against S's 0.281 in the table, +0.055 paired).
2. **Parsing differed from the official scorer.** The script took the first integer after
   "Answer:" anywhere in the text; the scorer reads the text after the last colon. A count followed
   by a note ("Answer: 42\n\nNote: …") was scored 0 by the official scorer but counted as delivered
   by the script.

## The corrected policy (preregistered for Pilot 1b)

- A count is "delivered" only if the official parser yields an integer
  (`benchmark/vendor/oolong_synth.py synth_attempt_answer_parse`, then `int()`).
- A task with no delivered count takes a **fixed, arm-independent penalty**: the log-error of
  answering 0, `log(gold + 1)`, the worst *under*-count for that task. The same value enters the
  headline mean, the paired difference and the decision rule. Two boundary cases are acknowledged:
  a gold of 0 makes the penalty 0, and an over-count beyond `(gold+1)² − 1` exceeds it, so
  non-delivery is not always the worst outcome by this measure. For that reason the decision rules
  never use the error alone: an arm is "useful" only if it also delivers at least as many counts as
  S and its official score is within 0.03 of S's. Delivery counts are reported beside every error.
- Negative transfer is `None`, not assumed, on a suite with no incompatible tasks.
- Regression tests: `test_python/test_reuse_compare.py` (mixed numeric/comparison tasks, a missing
  count, an arm delivering no counts, half-delivered-but-exact against fully-delivered near misses,
  malformed numeric strings, two-run averaging).

## Pilot 1 under the corrected policy

Compatible (F1) tasks, 2 runs × 21; 14 count-task runs per run.

| | S | D | P |
| --- | --- | --- | --- |
| Counts delivered (official parser) | 24 / 28 | 24 / 28 | 23 / 28 |
| Mean count log-error, non-delivery penalised | 0.775 | 0.613 | 0.797 |
| Paired log-error difference vs S (95% CI, window-clustered) | — | −0.162 (−0.99, +0.39) | +0.022 (−0.89, +0.92) |
| Mean official score (unchanged) | 0.315 | 0.324 | 0.377 |
| Cost per run, F1 (unchanged) | $0.385 | $0.442 | $0.584 |

Original report, for comparison (answered tasks only): 0.281 / 0.244 / 0.252.

**Decision:** unchanged. None of criteria (a)–(c) holds; the library is not useful when supplied by
the preregistered rule. The corrected count errors are about three times the originals because
every undelivered count is now charged in full; the intervals are wide, and no arm's count error
is distinguishable from S's. The claim in the original report that D's count error "fell" rested
on the dropped-tasks convention and is withdrawn; D's delivered counts were better on average,
but D delivered no more of them than S.

The original outputs are kept: `evidence/pilot1-results/pilot1-compare-frozen.json` (script at
`6b7feb9`) and `pilot1-compare-fixed.json` (generator fix only). The corrected output is
`evidence/pilot1-results/pilot1-compare-corrected.json`.
