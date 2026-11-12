# Opus capability ablations

Five separately switched interventions. Each one is tested against a control
that runs at the same time, with native Prime unchanged as the external reference.
- No ablation combines changes.
- The observed dev suite (`b157ee63…`) is for development only.
- The sealed held-out suite (`c74547bd…`) is run once, for one frozen candidate.

This document updates `ADAPTIVE_COMPUTE_ABLATION_PLAN.md`. Interventions 3, 6
and 7 there are folded into ablations 3 to 5 below; delegation is not proposed.

## Summary

| # | Ablation | Switch (`aljure_contract`) | Built | Offline proof | Live plan |
| --- | --- | --- | --- | --- | --- |
| 1 | Finalization compatibility | `terminal_text_answer` | yes (`41b53fa`) | captured replay, 12 refusals, fixture 8/8 | **frozen** `b1844732…` |
| 2 | Transport recovery | `truncated_turn_retries: 1` | yes (`41b53fa`) | captured replay, 13 new transport-failure tests, fixture 8/8 | **frozen** `52f51590…` |
| 3 | Deterministic verification | `verification_helpers` | yes (dev repo) | 7 probes in the real worker; 4 runtime tests | designed |
| 4 | Targeted semantic review | `+ uncertainty_review` | yes (dev repo) | prompt-gating test only | designed |
| 5 | Adaptive continuation | `+ evidence_gate` | yes (dev repo) | gate tests; auditor checks | designed |
| — | Control | none | — | — | **frozen** `87d8c949…` |

All switches are off by default. With all of them off, the worker definitions,
the system text and the declared capabilities are byte-identical to the original.

## Ablation 1: finalization compatibility

- **Hypothesis:** a text-only final answer that does not recover costs whole tasks
  (Opus task 6).
- **Change:** after a text-only root reply, the one correction offers `done` or a
  single `FINAL ANSWER:` line, and accepts only that exact line.
- **Mechanism:** the model gets a second, narrow way to deliver an answer it
  already has.
- **Test:** plan F2 against the control. Count each text-only trigger and its
  outcome: `done`, `FINAL ANSWER`, or failure.
- **Overhead:** none unless triggered. No extra call, because the correction
  already exists.
- **Failure conditions:**
  - any trigger ends in failure;
  - an arm that recovers through `done` under the control fails under F2.
- **Rollback:** switch off. Nothing else depends on it.
- **Criteria:** `CONTRACT_FIX_ACCEPTANCE_CRITERIA.md`, part C.

## Ablation 2: transport recovery

- **Hypothesis:** a provider-truncated tool turn with a known outcome can be
  resent safely, and that recovers the task (Opus task 7).
- **Change:** resend the identical request, at most once, on a separate counter.
- **Mechanism:** the provider fault is transient. The model's thinking had
  already reached the right answer.
- **Test:** plan F1 against the control. The rate is about 1 in 500 responses, so
  a live trigger has only a ~16% chance per plan. The live plan is mainly a
  regression check, and the offline replay carries the proof.
- **Overhead:** one call per event.
- **Failure conditions:**
  - any F1 arm ends on a truncation;
  - any `f1-retry` audit violation.
- **Rollback:** switch off.
- **Criteria:** part B.

## Ablation 3: deterministic verification

- **Hypothesis:** answers built from per-item records checked by `audit-labels`
  remove structural errors: cut items, missing items, and estimates stated
  instead of counted. Without a structural problem they do not change the score.
- **Change:**
  - load `show-items` and `audit-labels`;
  - add 103 words of interface text (`DETERMINISTIC_VERIFICATION_DESIGN.md`).
- **Mechanism:** labels move from the model's head into SCI state, where coverage
  and arithmetic can be checked.
- **Test:** see the protocol below. Measure:
  - the share of judgement tasks that keep a ledger;
  - open items when the model calls `done`;
  - never-shown items;
  - signed count error;
  - score, calls, output tokens, time.
- **Overhead:**
  - ~140 cached prompt tokens per request;
  - about 0.5–3K output tokens on tasks that use the ledger.
- **Failure conditions:**
  - ledgers are used on fewer than half the judgement tasks;
  - no structural error is removed;
  - output tokens rise by more than 40% with no score gain.
- **Rollback:** switch off.

## Ablation 4: targeted semantic review (requires 3)

- **Hypothesis:** dropping uncertain items biases judged counts downward. Opus
  Aljure dropped 11 uncertain MultiNLI pairs, and 6 of them were contradictions.
  Recording them as `:unknown` and reviewing them reduces that bias.
- **Change:** add 30 words: label unsure items `:unknown`, never drop them, and
  reread and decide them before `done`.
- **Mechanism:** the model's own uncertainty becomes a review queue instead of a
  default.
- **Test:** compare with ablation 3 alone, on signed count error and on the
  `:unknown` items recorded and decided.
- **Overhead:** the review reads only open items. Expect 0–1 extra calls and a
  few hundred output tokens on judgement-heavy tasks.
- **Failure conditions:**
  - the signed error is not smaller than under ablation 3 across repeats;
  - unknowns are recorded and then decided the same way as before;
  - extra calls bring no gain.
- **Rollback:** switch off; ablation 3 stays.

## Ablation 5: adaptive continuation (requires 3)

- **Hypothesis:** the model sometimes calls `done` with its own audit still open.
  Showing it that audit once, only then, buys accuracy where the evidence says
  the answer is unsupported, and costs nothing elsewhere.
- **Change:** the evidence gate (at most once; root `done`; open audit only).
- **Mechanism:** compute is spent where a deterministic signal says it is needed,
  not on every task.
- **Test:** compare with ablation 3 alone. Measure:
  - how often the gate fires;
  - open items before and after it fires;
  - score change on the tasks where it fired;
  - extra calls on the tasks where it did not (must be 0).
- **Overhead:** one call per firing, only when an audit is open.
- **Failure conditions:**
  - it fires on tasks whose answers do not change;
  - it never fires (no audits are open at `done`), which means ablation 4 already covers it;
  - it adds calls on tasks where it did not fire (a bug).
- **Rollback:** switch off.

## Not proposed: delegation

The only Prime delegation in 42 arms (Opus MultiNLI) went like this:
- 6 children started; 5 failed on Prime's own sandbox errors.
- 1 child labelled 73 pairs at 93% accuracy.
- That is no better than the root's own reading of 365 pairs, which was off by
  4 in absolute terms.

The traces show no value from delegation beyond equivalent sequential
computation, so delegation gets no ablation now (`MULTINLI_COUNT_FAILURE_ANALYSIS.md`).

## Protocol for ablations 3 to 5

- **Tasks:** the dev suite's judged-count tasks 16, 19, 20 and 21, with 3 repeats
  each. Signed error is the primary metric, because it is far less noisy than a
  0.75^|error| score on one run.
- **Side-effect check:** the three yahoo comparisons and the two formality label
  tasks.
- **Plans, each with Prime:** control, 3, 3+4, 3+5. All Opus, open limits.
- **After that:** one full 21-task dev run of the best configuration, as a
  regression check.
- **Then:** freeze one candidate for the sealed held-out suite.

A replay with an injected answer is not evidence that the live model would
produce it. Offline, these ablations prove only that the mechanisms exist, are
isolated, are switchable and are audited. The effect needs live runs.
