# Review replay ablation (A1c, zero inference)

How much did the review output the model recorded change each A1c Aljure
score? Each arm's recorded commands are re-run in a fresh isolated SCI worker,
with no model calls. Development evidence only. Related:
`RESIDUAL_REASONING_ANALYSIS.md`.

Source: A1c (`sci-ablation-speed-64k`, plan `30654ed6…`, run report sha256
`859bbe82…`), Aljure commit `dd98108`, SCI image `58550c92…`. All 10 cases
share one context (787 questions, 693 distinct), so they are 10 questions over
one dataset, not 10 independent samples.

## Method

1. **Control.** `repl-lab.replay` re-runs every recorded tool call of an arm in
   order (failed calls included) through the current broker and a fresh real
   worker over the same public context, and stops at the first `done`. The
   replay is accepted only if its answer is byte-identical to the recorded
   `answer.txt` and its official F1 is equal.
2. **Ablation.** The same replay with the review output withheld by exact
   source edits. Each edit's old text is copied from the recorded command by
   `scripts/review_replay_ablation.py` and must occur exactly once
   (`replay/edit-commands`; test `replay-edits-match-exactly-once`). Nothing
   else changes: same data, transformations, pair construction and scorer.
3. A trajectory with no deterministic computation to fall back to is marked
   **unresolved**. No counterfactual is invented for it.

Reproduce (no model calls):
`source var/worker.env && python3 scripts/review_replay_ablation.py <A1c run dir> var/review-replay-ablation-a1c`.
Evidence: `evidence/a1c-review-replay/ablation-spec.json` (every edit) and
`ablation-results.json`.

## Trajectory types

The earlier observation "rules plus review" (cases 2, 4, 5, 7, 9) contained
two different strategies:

| Type | Cases | What the code and the model did |
| --- | --- | --- |
| Rules only | 1, 3, 6, 8, 10 | Regex rules labelled questions; the model saw about 1% of them (the first lines) and answered. |
| Rules, then review | 2, 5, 7 | Regex rules, then the model read the questions the rules decided weakly and changed the result. |
| Model labels everything | 4, 9 | No label rules. The model read all 787 records and wrote its own labels (case 4, `H` and `Lc`: 111 each) or its own user list (case 9, `dq` and `Q`). Code handled only dates and pairs. |

## Results

All 10 controls reproduce the recorded answer byte for byte, with the same F1
and the same number of failed calls.

| Case | Arm | Type | Recorded F1 | Control | Review output withheld | F1 without it | Difference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `00-aljure` | rules only | 0.826 | identical | none recorded | — | — |
| 2 | `03-aljure` | rules, then review | 0.961 | identical | 26 users removed (`no`), 5 added (step 5) | 0.770 | **−0.191** |
| 3 | `04-aljure` | rules only | 0.887 | identical | none recorded | — | — |
| 4 | `07-aljure` | model labels everything | 0.938 | identical | — | unresolved | — |
| 5 | `08-aljure` | rules, then review | 0.902 | identical | 67 entity confirmations, 32 numeric relabels, 1 exclusion; rule labels used directly (step 8) | 0.264 | **−0.638** |
| 5 | `08-aljure` | sensitivity | 0.902 | identical | the same sets emptied, `final` unchanged | 0.581 | −0.321 |
| 6 | `11-aljure` | rules only | 0.770 | identical | none recorded | — | — |
| 7 | `12-aljure` | rules, then review | 0.795 | identical | the rewrite of `abbr?`, `num?` and `desc?` after reading 228 questions (step 5); step-4 rules kept | 0.643 | **−0.152** |
| 8 | `15-aljure` | rules only | 0.737 | identical | none recorded | — | — |
| 9 | `16-aljure` | model labels everything | 0.905 | identical | — | unresolved | — |
| 10 | `19-aljure` | rules only | 0.733 | identical | none recorded | — | — |

In all three resolvable cases the review raised F1: by 0.15–0.64, mean
**+0.33**. The size depends on how wrong the rules were. In case 5 the rules
put every unmatched question into `:else :ent`, a target class, so the
entity set was about 3.6 times too large (266 against 73 gold entities); the
review removed most of that.

Case 5 has two readings. In the primary one, the final label is the rule
label, which is what the arm would have computed without review. In the
sensitivity reading, the review sets are emptied but the arm's `final`
expression is kept. That expression already encodes a review decision
(unconfirmed defaults become `:other`), so it is not a rules-only arm. Both
readings are reported.

## What this does and does not show

- It measures the contribution of the **recorded** review output inside a
  **fixed** computation. It does not show what the agent would have done if
  review had been disabled during live reasoning: it might have written
  better rules, or worse ones.
- Cases 4 and 9 have no rules-only counterfactual. Their scores (0.938, 0.905)
  come from model judgment over all items, with deterministic dates and pairs.
- n = 3 resolvable cases from one context and one run each. This is not
  evidence of an effect size on new data.
- Item-level correctness of the rules and of the review is measured
  separately in `RESIDUAL_REASONING_ANALYSIS.md`.
