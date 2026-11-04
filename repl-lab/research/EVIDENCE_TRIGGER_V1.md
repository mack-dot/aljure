# Evidence trigger v1: pre-registration (2026-11-04)

Written and committed **before** the rule is run on the disjoint evaluation set
below. Implementation: `benchmark/evidence.py`, version `evidence-v1`. No gold
answer and no post-answer score is an input to the rule; scores are used only
afterwards to measure it.

## 1. Why this exists

The first detector draft ("no sufficient item-level tally recorded") was replayed
over every recorded arm of pilot 1, Phase B and the verification ablation. On
label-judgement tasks it fired on nearly every arm: recall on wrong answers 100%,
but it also fired on 55–65% of right answers, because correct answers are usually
reached without an item-level record too. That is too high for a cost-sensitive
policy. Two follow-up looks at the same data (count margin; share of the context
displayed) showed weak separation on small counts. **All of that is exploratory**
and is frozen in `evidence/evidence-trigger-exploratory-20261104/`; those 66
contexts are now the detector-development set and are not used to evaluate v1.

## 2. The rule

Applies only when the trusted task text is a label-judgement question
(`label-comparison`, `label-count`, `pairs`) or a structural count. Inputs: the
controller's ordered ledger of the root session's evaluations (source, status,
returned value). Four interpretable observables, each a fact about what was
computed before the answer:

| Observable | Definition | Applies to |
| --- | --- | --- |
| O1 contradiction | two successive count results (short vectors of numbers) point in opposite directions and no item-level record follows | label tasks |
| O2 narrow margin | the last two-way count has \|a − b\| / (a + b) < 0.30 and no item-level record exists | label-comparison |
| O3 missing aggregation | no count result at all and no item-level record: the answer comes from reading alone | label tasks; structural counts with no computed number |
| O4 incomplete coverage | an item-level record exists but has fewer than 8 entries, or a per-item record covers under 90% of the items displayed, or the last step of an aggregation failed | label tasks |

**Trigger = O1 or O2 or O3 or O4.** No trigger for: a wide-margin count, a single
label count from a pattern (no margin can be formed), a complete item-level
record, structural counts with a computed number, and any task the classifier
does not recognise (`undeterminable`, fail-safe). An "item-level record" is
literal label data typed into the worker: index collections, label strings over
a small alphabet, id-to-label maps; at least 8 entries.

The rule establishes structural sufficiency only. A triggered answer may be
right; an untriggered answer may be wrong; a complete record may hold wrong
labels.

## 3. Disjoint evaluation set (fixed here)

Recorded baseline Aljure arms, Sonnet 5.5, no library, no verification
contract, on contexts that do not appear in the exploratory set (checked
mechanically by dataset, context length and window id; any overlapping task is
dropped):

| Run | Arms | Suite |
| --- | --- | --- |
| thesis pilot, arm A, seeds 101, 202, 303 (`aljure-thesis-v1/.../thesis-pilot/runs/A-s*`) | 54 | `7b23fbbb` trec_coarse and spam validation windows |
| reuse pilot, arm S, runs 1 and 2 (`aljure-unblock-v1/.../reuse-S-r*`) | 48 completed | `806c5b2b` |
| reuse pilot 1b, arm S (`aljure-unblock-v4/.../reuse-1b-S-r1`) | 23 completed | `7dd5e1d4` |
| ten-case Pairs 8K, Aljure arms (`sonnet-ten-live`) | 9 completed | `90f719a5` |

These ledgers come from earlier harness commits (28–30 October: native tools,
before text answers and the pilot-2 prelude). The observables depend only on the
tool-call ledger, which has the same shape. Scores are the recorded official
scores; "wrong" is a score below 0.9. Arms that did not complete are reported
separately and not counted as trigger evaluations.

## 4. Measures and pass criteria (fixed here)

- Precision: triggered arms that were wrong / triggered arms.
- Recall: wrong arms that were triggered / wrong arms.
- False-trigger rate: triggered right arms / right arms.
- Trigger rate overall and by observable; by task class.
- Estimated avoidable errors: wrong and triggered arms × the fix rate observed in
  the ablation when verification was applied (A1 corrected 3 of A0's 8 wrong
  label items, 0.375), with that rate's uncertainty stated.
- Estimated added inference cost: trigger rate × the mean extra cost A1 paid on
  decisive items ($0.037 per triggered task), against the always-on contract's
  measured +$0.015 per task.

**Pass:** precision ≥ 0.50 and recall ≥ 0.50 and false-trigger rate ≤ 0.30 on the
pooled disjoint set. **Fail** on any of the three means v1 is not adopted as the
selective trigger; the result is reported and the rule is not re-tuned on the
evaluation set.

## 5. What a pass would and would not justify

A pass justifies wiring v1 into the controller as an at-most-once request before
finalization and testing it in a frozen paid ablation against the prompt-only
audit. It does not show that triggered verification fixes answers; only a live
run can show that. A fail leaves the prompt-only audit contract as the best
measured mechanism.
