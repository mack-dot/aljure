# Residual reasoning analysis (A1c, offline)

Separates **coverage** (did a rule decide an item?), **correctness** (was the
decision right?) and **uncertainty** (which items need judgment?) for the
regex rules Aljure wrote in A1c. Then it asks which items a review should
cover. Development evidence only; no model calls. Related:
`REVIEW_REPLAY_ABLATION.md`.

## Data and method

- **Item-level gold.** The pinned source parquet (`oolong-synth` validation
  shard 6, sha256 `5a7464d4…`) has `context_window_text_with_labels`. Exactly
  one 32K `trec_coarse` window matches the A1c public context (window 0); its
  787 lines carry gold labels (abbreviation 175, numeric 154, human 123,
  description 135, location 127, entity 73). Gold is used here only for
  offline measurement, never for a live decision.
- **Each arm's own labels.** Each arm's recorded commands are replayed in
  isolated SCI, and only the final `done` expression is replaced so that it
  returns one label per question from the arm's own rule function
  (`scripts/residual_reasoning_analysis.py`, `evidence/a1c-review-replay/`).
  Case 7 is read before its post-review rule rewrite. Cases 4 and 9 have no
  label rules and are excluded.
- **Unknown.** An item the rules did not decide. The `:else :ent` default in
  cases 2 and 5 counts as unknown: the arm used it as entity, but no rule
  decided it.
- **Task semantics.** Pairs are computed from per-item labels with the
  official rule: both users have a target-class instance, plus the date
  condition where present. Check: gold labels give F1 = 1.000 on all 10
  cases. Check: rule labels reproduce the recorded F1 of all five rules-only
  arms and the replay-ablation F1 of cases 2, 5 and 7, so two independent
  computations agree.
- **Conflict.** Another arm's rules decide the same item differently on a
  class this task depends on. These are the model's own rules from other A1c
  sessions, written independently. A single live task has no such second
  rule set unless the agent builds one or reuses a retained one.

## Coverage, correctness and uncertainty

"Rule errors" counts errors that matter to the task: the rule's class or the
gold class is one the task depends on.

| Case | Coverage | Unknown | Rule errors among decided | Conflict items wrong | Other decided items wrong | Target precision / recall |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 27% | 574 | 18 / 213 (8%) | 14 / 22 (64%) | 4 / 191 (2%) | 0.92 / 0.70 |
| 2 | 75% | 196 | 21 / 591 (4%) | 1 / 2 | 20 / 589 (3%) | 0.66 / 0.90 |
| 3 | 36% | 506 | 51 / 281 (18%) | 16 / 146 (11%) | 35 / 135 (26%) | 0.96 / 0.87 |
| 5 | 66% | 266 | 5 / 521 (1%) | 1 / 19 (5%) | 4 / 502 (1%) | 0.57 / 0.98 |
| 6 | 30% | 551 | 16 / 236 (7%) | 14 / 144 (10%) | 2 / 92 (2%) | 0.93 / 0.73 |
| 7 | 57% | 338 | 208 / 449 (46%) | 140 / 160 (88%) | 68 / 289 (24%) | 0.57 / 0.89 |
| 8 | 38% | 489 | 113 / 298 (38%) | 53 / 69 (77%) | 60 / 229 (26%) | 0.63 / 0.73 |
| 10 | 38% | 491 | 22 / 296 (7%) | 19 / 158 (12%) | 3 / 138 (2%) | 0.93 / 0.83 |

Findings:

1. **Coverage was low.** The rules decided 27–75% of items. Most rules
   decided only the task's target classes, so "not a target" and "unknown"
   were the same bucket. Rules that also decide the non-target classes
   (cases 2 and 5) leave a smaller unknown set.
2. **A default branch hides uncertainty.** Cases 2 and 5 sent every unmatched
   question to a target class. Coverage then looked like 100%, and target
   precision fell to 0.66 and 0.57.
3. **Decided does not mean correct.** In cases 7 and 8, 46% and 38% of the
   items the rules decided were wrong on a task class.
4. **Disagreement between independent rule sets flags likely errors.** Pooled
   over the 8 arms, 258 of 720 conflict items were wrong (36%), against 196
   of 2,165 other decided items (9%). The signal holds in 7 of 8 arms; case 3
   is the exception (11% against 26%).

## Which items should a review cover? (oracle upper bound)

The reviewer here is the gold label, so these numbers are **upper bounds**.
A real model review is imperfect (next section). The number after the slash
is the number of items reviewed.

| Case | Recorded F1 | A: rules only | C: unknown only | D: unknown + conflict | B: all items |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.826 | 0.826 / 0 | 0.984 / 574 | 1.000 / 596 | 1.000 / 787 |
| 2 | 0.961 | 0.770 / 0 | 0.940 / 196 | 0.940 / 198 | 1.000 / 787 |
| 3 | 0.887 | 0.887 / 0 | 0.979 / 506 | 0.993 / 652 | 1.000 / 787 |
| 5 | 0.902 | 0.264 / 0 | 0.986 / 266 | 0.986 / 285 | 1.000 / 787 |
| 6 | 0.770 | 0.770 / 0 | 0.956 / 551 | 1.000 / 695 | 1.000 / 787 |
| 7 | 0.795 | 0.643 / 0 | 0.666 / 338 | 0.848 / 498 | 1.000 / 787 |
| 8 | 0.737 | 0.737 / 0 | 0.842 / 489 | 0.925 / 558 | 1.000 / 787 |
| 10 | 0.733 | 0.733 / 0 | 0.903 / 491 | 1.000 / 649 | 1.000 / 787 |

- **Reviewing only unknown items misses rule errors.** C leaves case 7 at
  0.666 and case 8 at 0.842. Adding conflict items (D) raises them to 0.848
  and 0.925, and brings cases 1, 6 and 10 to 1.000.
- **The smallest subset is not cheap here.** Because coverage was low, C
  already reviews 25–73% of items and D reviews 25–88%. Better rule coverage,
  including negative evidence for non-target classes, would shrink both.
- Strategy E (a fixed preregistered selection) and F (expected gain per unit
  of cost) are not evaluated. Nothing here shows that the simpler policies
  are inadequate.

## Measured quality of the model's own review

Where the model wrote item-level judgments, they can be checked:

| Where | Items | Result |
| --- | --- | --- |
| Case 4, human labels (`H`) | 111 | precision 0.99, recall 0.89 |
| Case 4, location labels (`Lc`) | 111 | precision 0.99, recall 0.87 |
| Case 5, entity / numeric / other on every item it was shown | 514 | model 95.1% correct; the rules 60.9% on the same items |
| Case 7, items whose label changed in the post-review rule rewrite | 205 | 175 changed to correct, 20 changed from correct |

The model's review was precise, but it missed about 11–13% of the items in
case 4's classes. Expect real C and D results below the oracle bounds above.

## Limits

- One context and one run per case. The arms' rules are not independent
  samples of rule quality, because the same model wrote them.
- The conflict signal uses other sessions' rules. A live agent would need its
  own second, independent method, or a retained rule set from earlier tasks.
  That is a reuse question (`REUSABLE_LABEL_ARTIFACTS.md`, not yet written).
- Costs are counted as items reviewed. Model time and tokens per reviewed
  item are not yet modelled (`REASONING_ECONOMICS.md`, not yet written).
