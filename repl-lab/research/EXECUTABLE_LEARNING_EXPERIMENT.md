# Executable learning experiment (Q-LEARNING)

Does constructing, validating, retaining and reusing executable artifacts
improve later task performance, once acquisition and validation costs are
counted? This is Aljure's distinctive hypothesis. Native Prime has no
counterpart, and this experiment does not compare against Prime. Labels follow
`STATISTICAL_EVALUATION_PROTOCOL.md`; in `EXPERIMENT_PROTOCOL.md` this question
is H2.

## 1. What exists (audit, 2026-10-28)

| Mechanism | State | Evidence |
| --- | --- | --- |
| Content-hashed, immutable artifacts; patch; tamper detection | implemented, tested, used live | `artifact.clj`; `runtime_test.clj` |
| Validation by development panel; paired promotion gate (no invariant violation, no regression, gain ≥ 1) | implemented | `live.clj` `development-panel!`; `artifact.clj` `promotion-evidence` |
| Durable retention across process restarts (registry, checkpoint, bundle, cold boot) | implemented, tested | `bundle.clj`; `main.clj`; `experiment_test.clj` |
| Sealed splits and a one-time final seal; library frozen during evaluation | implemented, tested | `evaluation.clj` |
| Model-driven selection (`skills/list`, `policy/select`) | implemented, **never used live** | `runtime.clj` |
| Automated selection (selector track, fixed guard) | implemented, fixture-only | `selector_*.clj` |
| Arm A (no memory) | runs (`:frozen`) | `live.clj` |
| Arm B (unverified retention) | **missing** | — |
| Arm C (validated retention) | runs (`:evolving`) | `live.clj` |
| Arm D (validated + automated selection) | partial (zero-inference `code-panel!`; selector over a fixed library) | `evaluation.clj`; `selector_tasks.clj` |
| Invalidation or revalidation of retained artifacts | **missing** | only manual `rollback!` |

## 2. Prior evidence

- **One live acquisition run** (`FIRST_LIVE_RESULTS.md`):
  - Each arm completed only 1 of 3 acquisition tasks.
  - Held-out completion was 0/8 for the frozen agent and 5/8 for the evolving
    agent, but **all five successes used temporary policies, not the retained
    one**.
  - Run directly on cold boot, the retained policy completed 8/8, matching a
    fixed baseline. On held-out it completed 1/8, mostly because workers
    failed.
- **No agent ever invoked a retained artifact explicitly**
  (`SKILL_REUSE_ANALYSIS.md`). Reuse happened only through the default policy.
- **Skill discovery V4 (fixtures):** blind reuse failed both shifted cases; a
  fixed applicability guard matched the scripted selector.

These are integration results. They show neither benefit nor harm.

## 3. Defects to fix before any inference

1. **The promotion gain sums scores, so infrastructure failures inflate it**
   (recorded gain 37,630 with three failed parent workers). Exclude
   infrastructure-failed pairs, or score both members equally. The selector
   gate's `infrastructure-failure?` rule is the model.
2. **A failed episode records the retained hash as its artifact, which
   overstates reuse.** Record no artifact on failure, and count reuse only from
   invocation events.
3. **Arm B:** add an explicit unverified-retention path (promotion without
   development evidence, labelled as such) and generalise the paired runner to
   N libraries.
4. **Invalidation:** add a revalidation step that demotes an artifact failing
   its recorded checks on a fresh panel, plus a refusal path when its declared
   contract does not match the task.
5. **Task sources:** panel sizes are hard-coded, and held-out tasks come from
   the same in-house generator (fresh seeds, same distribution). Add
   provenance-independent transfer tasks (section 4).
6. **Provider:** live learning runs use the Claude CLI transport, pinned to
   `2.1.310`, but `2.1.312` is installed. Re-pin with approval, or port the
   learning loop to the subscription gateway used by the paired runs (which
   also gives complete per-call accounting).

## 4. Proposed design

**Task family.** OOLONG-synth and OOLONG-Pairs templates. These are official
data with official scorers. Tasks share computational structure (parse records,
classify, group, count, pair) across **independent contexts**, so a verified
parser or aggregator is genuinely reusable. Splits:

| Split | Content | Purpose |
| --- | --- | --- |
| Acquisition | 6 tasks over 6 contexts, template family T1 | build artifacts |
| Development (validation) | 6 tasks over 6 other contexts, T1 | promotion evidence; never held out |
| Held-out transfer | 12 tasks over 12 unseen contexts: 6 in T1, 6 in a shifted family T2 (different label or aggregation rule) | where reuse should help (T1) and where blind reuse should fail (T2) |
| Refusal probes | 4 tasks whose templates contradict a retained artifact's contract | where reuse must be refused |

**Arms.** A (no memory), B (retained without validation), C (retained after
validation), D (C plus automated selection, first as the fixed-rule
`code-panel!`; the learned selector only if C beats A). Each arm gets 3
independent acquisition runs. Processes restart between acquisition and
transfer, and transfer runs as a cold boot that loads the sealed bundle only.

**Evidence of reuse.** Reuse counts only where a trace shows an artifact or
workflow invocation whose hash is in the bundle and whose output fed the
answer. Mere presence in the library does not count.

## 5. Measures

- **Primary:** held-out verified completion, C − A, resampled by acquisition
  run (3 runs × 12 tasks, clustered by context).
- **Secondary:**
  - B − A and C − B (does validation matter?);
  - the T2 penalty (negative transfer);
  - the refusal rate on probes;
  - cost per solved held-out task;
  - break-even reuse count, including acquisition and validation USD and the
    calls of failed acquisitions;
  - the reuse rate from invocation events.

## 6. Falsification

The hypothesis is **not supported** if any of these holds:
- C fails to beat A on held-out T1 (by the decision rule in
  `STATISTICAL_EVALUATION_PROTOCOL.md` §5);
- C does not differ from B (so verification adds nothing);
- C's T2 score falls below A's (harmful reuse) without refusal;
- the break-even N exceeds the number of related tasks a user would plausibly
  run.

A null result is reported with the same prominence as a positive one.

## 7. Cost estimate

About 36 acquisition tasks and 36 development episodes (local SCI, no model
calls for the panel), plus 3 runs × 4 arms × 16 transfer and probe tasks
(192 model tasks at about 32K context), at roughly $0.10–0.20 each:
**about $25–45 API-rate-equivalent**, plus acquisition calls (about
$10–20). Freeze the exact plan and caps before authorization.
