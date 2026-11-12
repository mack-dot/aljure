# Capability-extraction ablations: plan

**Question:** which small, general mechanisms let Aljure extract more of a
stronger model's ability, without losing its cost and latency advantage?

**Rules:**
- Each intervention is a separate switch. They are never combined into one
  uncontrolled patch.
- Native Prime is unchanged and runs in every plan as the external reference.
- The observed dev suite (`b157ee63…`) is used for development only. The
  sealed held-out suite (`c74547bd…`) is used once, after a single candidate
  configuration has been frozen.
- Scores include timeouts and protocol failures. Uncertainty is clustered by
  context (`STATISTICAL_EVALUATION_PROTOCOL.md`).

## Interventions

| # | Intervention | Change | Hypothesis | Expected effect | Added cost and latency | Falsified if |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Current Aljure (control) | none | — | Opus: 0.771 (one run) | — | — |
| 2a | Truncation retry (F1) | `truncated_turn_retries: 1` | Provider-truncated turns cause lost tasks | Removes a rare loss (1 in 557 responses); otherwise no change | one call per event | Retries occur and the arm still fails, or any regression appears against the control |
| 2b | Terminal text answer (F2) | `terminal_text_answer: true` | A text-only final answer that does not recover costs tasks | Rescues arms like task 6 if the model follows the instruction | none unless triggered | No text-only arm ends in an accepted `FINAL ANSWER`, or arms that used to recover through `done` start failing |
| 3 | Completion instruction | One base-prompt sentence: "When the task asks for a final answer in a given form, put exactly that text in done's summary." | The task's chat-style answer instruction competes with `done` | Fewer text-only replies, so the one correction is kept for real format errors | ~30 prompt tokens | Text-only replies do not fall below the control's rate (9 of 21 Sonnet arms, 4 of 21 Opus arms) |
| 4 | Explicit uncertainty checks | Prelude helpers from `RESIDUAL_REASONING_ANALYSIS.md`: rules return `:unknown`; a review queue covers unknown and conflicting items | Rules-only answers on semantic tasks (Sonnet tasks 4 and 16) skip the items that need judgement | Higher scores on label and count tasks where rules leak | +1–2 calls when the queue is non-empty | No score gain on rule-heavy tasks, or added calls with no gain |
| 5 | Adaptive additional inference | One extra turn after a draft answer on count or label tasks: re-check one batch and reconcile | Exact counts fail from accumulated judgement error | Smaller count errors (tasks 16, 19–21) | +1–2 calls on those tasks | The count error does not fall below its noise band over 3 repeats |
| 6 | Optional delegation | A fuller `agent_call` description (batching example, shared budget) | Stronger models use child sessions when told how | More delegation on large-batch tasks; benefit unknown | Children share the budget; possibly more calls | No delegation occurs, or it does but scores do not rise |
| 7 | Per-batch tally | One base-prompt sentence, or a prelude `tally!` helper (`PRIME_MULTINLI_TRAJECTORY_ANALYSIS.md`, controls B and C) | Counting after each batch beats one count at the end | Exact-count tasks improve | none | No gain over the control on tasks 16 and 19–21 across 3 repeats |

**Measurement:** each plan reports score, completion, calls, cost and wall
time, and its own mechanism counters. These are: retries; corrections ending
in `done` against `FINAL ANSWER`; text-only replies; review coverage; children
used; batch tallies recorded.

To ask "do stronger models benefit disproportionately", run each intervention
that works with both Sonnet and Opus, on the same tasks.

## Frozen now: control, F1 and F2 (dev suite, Opus)

All three plans are frozen at clean commit `41b53fa` and use the same settings
as plan `d6e9b40d`:
- `claude-opus-5-5`, adaptive thinking, effort medium;
- open limits: 1,000 calls, 900 s, 4 MiB requests;
- 21 dev tasks; native Prime unchanged.

**Gates, all with zero model calls:**
- SCI isolation 9/9 (gate unchanged since `276a0ab`);
- SCI contract proof regenerated for the new `model_protocol.clj` (TESTED);
- Prime isolation proof current;
- relay fixture PASSED;
- contract fixture 8/8 PASSED;
- preflight ready for all three, with no blockers.

| Plan | Aljure contract | plan_sha256 |
| --- | --- | --- |
| Control | original | `87d8c949a5dafe983c8965fd0d352ebafe8977210d27663a65c64013ff369eb7` |
| F1 | `truncated_turn_retries: 1` | `52f51590c44e60df2af1cb7e7284792a2d35b0a6f16f868cb11fbca062bb0773` |
| F2 | `terminal_text_answer: true` | `b1844732305d2b9236a89af7ddd7078667fad530b04777ccb326b12547ed6e5d` |

**Spend:**
- **Expected:** about $5–7 per plan, about $16–20 for all three. Plan
  `d6e9b40d` cost $5.54 over the same 42 arms.
- **Hard caps:** $100 per arm (1,000 calls, 200M tokens, 900 s). Each plan's
  ceiling is $4,200, the sum of its 42 arm allowances; the three ceilings total
  $12,600. These are caps, not estimates.

**Why a new control:**
- Both failure modes are stochastic. A control run at the same time measures
  run-to-run variance in Aljure's completion and score.
- The three runs of Prime measure Prime's variance.
- Plan `d6e9b40d` remains the historical reference and is not modified.

**Expected power:**
- **F1 is a safety check:** truncation is rare, so it mostly tests for
  regressions.
- **F2 matters only if text-only replies occur:** 4 of 21 Opus arms did. Most
  of those already recovered through `done`.
- A 21-task dev run can show a mechanism working. It cannot establish an effect
  size.

**Evidence:** `evidence/contract-ablation-opus/` holds the plans, configs,
preflights, both fixture reports and the contract proof.
