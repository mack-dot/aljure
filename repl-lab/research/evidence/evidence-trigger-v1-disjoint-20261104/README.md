# Trigger v1 on the pre-registered disjoint set (2026-11-04)

One evaluation, run after commit 70a63e0 (pre-registration `research/EVIDENCE_TRIGGER_V1.md`), with
`benchmark/evidence.py` evidence-v1 unchanged. `trigger-v1-disjoint.json`: one row per arm (run, task,
context hash prefix, recorded official score, class, state, trigger, observables). Scores were read only
to compute the metrics.

134 completed baseline Aljure arms (12 not completed, reported separately), 20 contexts, none in the
exploratory set. The rule applies to 123 arms (11 are of an unrecognised class and never trigger).

| Set | Arms | Right | Wrong | Triggered | Precision | Recall | False-trigger rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pooled | 123 | 43 | 80 | 67 (54%) | 0.46 | 0.39 | 0.84 |
| label-comparison | 34 | 23 | 11 | 30 (88%) | 0.37 | 1.00 | 0.83 |
| label-count | 80 | 13 | 67 | 33 (41%) | 0.61 | 0.30 | 1.00 |
| pairs | 9 | 7 | 2 | 4 (44%) | 0.00 | 0.00 | 0.57 |

By observable (fired, of which wrong): O3 missing aggregation 50 (26); O2 narrow margin 14 (4);
O1 contradiction 3 (1); O4 incomplete coverage 0.

**Verdict: FAIL** on all three pre-registered criteria (precision >= 0.50, recall >= 0.50,
false-trigger rate <= 0.30). Trigger v1 is not adopted and was not re-tuned on this set.

Estimated effect had it been used: 31 wrong-and-triggered arms x 0.375 fix rate = about 12 of 80 errors
avoidable; added cost 0.54 x $0.037 = $0.020 per task, more than the always-on audit contract's measured
+$0.0145 per task.
