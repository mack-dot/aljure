# Uncertainty-aware semantic review: development evaluation protocol

**Status:** preregistered before any review run. No inference has used the review switches.

**Question:** do item-level labels with explicit unknowns, deterministic audits,
and targeted review of open items reduce Aljure's judged-count error, while
keeping its cost near half of Prime's?

## Why this is the next experiment

Across four Opus runs of the dev suite (`d6e9b40d`, control, F1 and F2), the
signed count errors on the four judged-count tasks were (— = no answer):

| Task (gold) | Aljure | Prime |
| --- | --- | --- |
| MultiNLI contradictions (129) | −9, −3, −3, — | 0, −5, −2, — |
| AG News Sci/Tech (171) | +1, −4, −3, −3 | −2, 0, −1, −1 |
| AG News Business (40) | +6, +5, +4, +2 | +2, +2, +2, +2 |
| AG News World (16) | +6, +6, +5, +6 | +6, +6, +5, +7 |
| **Mean absolute error** (15 answered cases each) | **4.4** | **2.9** |

**What these numbers show:**
- On MultiNLI, Aljure named its uncertain pairs and then dropped them
  (`MULTINLI_COUNT_FAILURE_ANALYSIS.md`).
- On AG News World, both harnesses make the same error, so that part is a shared
  semantic ceiling. Review is not expected to move it.

## Mechanism under test (`aljure_contract`)

| Switch | Role |
| --- | --- |
| `verification_helpers` | Record item labels in SCI. `audit-labels` reports coverage, conflicts, unknowns and count ranges. `show-items` shows whole items |
| `uncertainty_review` | Label unsure items `:unknown` instead of guessing or dropping them; before `done`, reread and decide open items, then audit again |
| `evidence_gate` | At most once, a root `done` with an open audit is answered with that audit, so extra reasoning is spent only where items are open |

**Not used:**
- gold labels, benchmark-specific classification rules, subagents, or skill caching;
- any controller-side judgement of label correctness. The audit checks coverage
  and arithmetic only.

## Design: the smallest controlled run the planner supports

The planner pairs Prime with Aljure on every task of a pinned suite, and allows no subsets.

- **Configurations:** identical except for the three review switches.
  - **R0, no-review control:** base contract.
  - **R1, review:** base contract plus the three switches.
- **Base contract:** F1 only (`truncated_turn_retries: 1`), per `CONTRACT_ABLATION_RESULTS.md`. F2 was rejected.
- **Runs, in this order:** R1, R0, R1. Each run is the full 21-task dev suite
  (`b157ee63…`) with Opus 5.5, under the same limits as plan `d6e9b40d`. Prime is unchanged.
- **Historical no-review reference:** the earlier Opus run and the control, F1 and
  F2 runs. These are labelled as non-concurrent.
- **Not used:** the sealed held-out suite.

## Endpoints

**Primary:** mean absolute count error on the four judged-count tasks:
- review: 2 runs × 4 tasks;
- no-review: the concurrent R0, plus the historical runs, shown separately.

**Secondary:**
- signed count error;
- mean score and paired difference against Prime per run, with a context-clustered bootstrap;
- completion;
- Aljure/Prime cost ratio;
- calls;
- p50 and p95 latency.

**Mechanism invocation, per Aljure arm, from traces:**
- `audit-labels` called;
- unknowns recorded at the first audit;
- open items reduced by a later audit;
- evidence gate fired;
- open items when `done` was accepted.

A score change on a task is attributed to review only if the mechanism was invoked on that task.

## Decision rule (fixed before the runs)

**Retain review** only if all of these hold:
1. **Invoked:** `audit-labels` is used on at least 3 of the 4 count tasks in each R1 run.
2. **Better:** R1's mean absolute count error is at least 1.5 lower than the
   no-review mean (concurrent R0 and historical together, 4.4 now).
3. **No harm:** no task that scored 1.0 in every no-review run scores below 0.9
   in both R1 runs.
4. **Cost advantage kept:** Aljure/Prime cost ≤ 0.55 in each R1 run. The
   no-review runs so far are 0.42–0.48.
5. **Contract intact:** every Aljure arm passes `scripts/contract_audit.py`.

**Outcomes:**
- **Reject** if condition 1 fails (the model does not use the mechanism), or
  condition 4 or 5 fails.
- **Inconclusive** if 1, 4 and 5 hold but 2 or 3 does not. More repeats would
  then need their own approval.

## Offline evidence before the run

- **SCI proof:** 7 verification probes in the real isolated worker (`evidence/verification/`).
- **Runtime tests:** `test/repl_lab/verification_test.clj`.
- **Review fixture:** `paired-review-fixture`. It drives the helpers, gate and
  re-audit through the real gateway and SCI worker, against a no-review control
  on the identical script.

## Frozen plans (2026-10-29)

**Source:** clean commit `60fa124`, execution checkout `/Users/mackianni/aljure-review-v1`.
The control/F1/F2 checkout (`41b53fa`) and its evidence are untouched.

| Plan | Aljure contract | plan_sha256 | Runs |
| --- | --- | --- | --- |
| R0, no-review control | `truncated_turn_retries: 1` | `5743ef29a09c97b8b46cf6d47af8a26d67249a03fde6c70e3eeccc77bbcab9c8` | 1 (second in order) |
| R1, review | the same, plus `verification_helpers`, `uncertainty_review`, `evidence_gate` | `a02824eb68ae0d1e683f4fd90f5e0431e44fc68a356176536527d6738d936ecc` | 2 (first and third) |

**Settings:**
- Both plans: Opus 5.5, subscription only, with no API fallback.
- The same limits, rates, pins and images as the control/F1/F2 plans.
- 21 dev tasks, 42 arms per run, native Prime unchanged.

**Gates, regenerated in this checkout with zero model calls:**
- SCI isolation 9/9;
- Prime isolation 10/10;
- SCI contract 76/76, including the 7 verification probes;
- subscription relay fixture 15/15;
- review fixture 9/9;
- preflight ready for both plans, with no blockers.

A failed worker isolation preflight now stops a plan (`IsolationPreflightFailed`).

**Spend:**
- **Expected:**
  - R0 about $5.4–5.8: Aljure $1.6–1.8, Prime $3.7–4.0, as in the control and F1 runs.
  - Each R1 about $5.6–6.5: Aljure $1.8–2.4, if review adds 10–40%.
  - Total about **$17–19** at API-rate equivalent.
- **Hard caps:** $100 per arm and $4,200 per plan (the sum of its 42 arm allowances).
  The three runs total $12,600 nominal. These are caps, not estimates.

**Evidence:** `evidence/review-ablation-opus/`, holding the configs, plans, preflights, fixture reports and proofs.
