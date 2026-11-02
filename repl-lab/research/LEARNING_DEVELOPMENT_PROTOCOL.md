# Development acquisition and reuse protocol v1 — 2026-11-02

Status: preregistered design. A frozen execution plan must bind this file, source,
config, data, panel, images, and proofs before inference. Approval is pending.

## Question and scope

Can the model propose a useful executable classifier during ordinary development
work, have it pass fixed validation, retain it through a cold restart, and choose
to invoke it on a later task? This stage measures mechanism activation. It cannot
establish superiority, independent transfer, or cost savings against a control.

Use `config/learning-development-sonnet.json`: the existing ES structured mode,
Sonnet 5.5, adaptive thinking with medium effort, subscription transport only,
no API-key fallback. The proposal may decline with a reason. Do not force code,
seed a library, add auto-capture, or rewrite model proposals after observing them.

## Fixed development data and runs

- Suite: the existing 18-task thesis validation suite, hash
  `7b23fbbb1912ce78a04b5708a7936eb869810e04cbce7db7572711a84937a5ad`.
- Panel: `7ae02b6da356765c75427273f360c654bfa5727203eaf53e226b5a62635fda1b`.
- These tasks were previously exposed. Their traces informed interface design.
  They are development data, even when a new conversation runs them.
- Three ES trajectories: ordering seeds 101, 202, 303. Each has 14 compatible
  F1 tasks and four incompatible F2 tasks. Total: 54 task runs.
- Keep the original positions of F2 (8, 11, 14, 17). Stop after task 9 and resume
  with a new runner process, JVM, worker, and conversation. Carry only the
  verified library and ledger. Run seeds in order, each with its own empty library.
- Process one Docker job at a time. Keep all completed and failed task outputs.

## Promotion and reuse

Use rule v2 with at least 95% precision, at least 10% coverage on admitted panel
records, no execution/type failure, no loss of a previously correct record,
nondecreasing library coverage, and at least one additional correct record.
Disable label-abstention adaptation. The panel is fixed; no held-out feedback
enters proposal, validation, ranking, or selection. Receipts retain rejection
reasons, code hash, source proposal, parent, panel hash, and validation time.

Autonomous reuse means the model chooses an invocation through its task tools.
Preloading an artifact is not reuse. Count calls and returns by code hash. A
scripted response is not a model decision. Do not insert a task-specific call
into the prompt or add an externally written solution to make the gate pass.

## Fixed development gate

Advance only if at least two of the three complete trajectories each have:

1. At least one model-authored proposal promoted before the task-9 cold restart.
2. A verified committed library pin retained across that restart.
3. At least one later task where the model invokes that earlier code hash and
   the function returns successfully, without a controller-supplied answer.
4. Complete provider accounting and no unresolved isolation/cleanup failure.

A later invocation must be on a different task, but these development contexts
may overlap. Independent transfer is reserved for the next stage. Record task
accuracy beside activation: a function returning does not prove a correct final
answer. A complete run that misses the gate is NO-GO. An interrupted run is
INCOMPLETE. No selective rerun, favorable-order selection, or threshold change.

## Accounting, limits, and stopping

- Per task: at most 12 model calls including acquisition, 300 seconds, $5
  API-rate-equivalent, and the existing token/output ceilings.
- **Hard aggregate ceiling: $10 API-rate-equivalent.** Before each task, known
  spend plus unknown reservations plus the full $5 task cap must fit within $10.
  The config sets the spend-check margin to $5. No task borrows another task's
  budget. Actual subscription billing remains unknown.
- Stop on unknown provider outcome, isolation refusal, Docker restart, integrity
  failure, unconfirmed cleanup, promotion-stage failure, or free disk below 6 GiB.
  Preserve output and reservations. Do not renew credentials or fall back to API.
- The approval covers this development plan only. It does not authorize Pilot 1b
  retries, held-out execution, model switching, or a second mechanism variant.

Report task success (official score exactly 1), mean official score, attempted
and unattempted counts, all task/acquisition model cost, cost per success,
validation seconds, p50/p95 task latency, requests, tool success/error counts,
proposal decisions, promotions, and post-restart invocation evidence. A zero
success denominator is infinite/undefined, never zero cost. Unknown cost is not
silently treated as zero. Include failures in accuracy and cost.

`python3 -m benchmark.learning_report --plan <plan> --suite <development-suite>
--runs <runs> --out <new-report.json>` computes these endpoints without inference.
The new-record scoring command may be used on this development suite only; it
does not promote, tune, or replace the primary lifecycle endpoint.

## Readiness and approval

Before approval: targeted regressions; current image isolation; SCI contract;
artifact/acquisition proofs; real-worker subscription and acquisition fixtures;
reconciled scripted receipts; clean frozen source; `trajectory-preflight` ready.
Copy proofs and plans into an evidence index with hashes. The execution checkout
must remain unchanged. Recheck credential metadata and disk just before dispatch.

Request approval for the exact 54-task plan and $10 hard ceiling. Without it,
finish offline work and stop. After a live GO, prepare the separate held-out
execution freeze described in `LEARNING_HELDOUT_PROTOCOL.md`.
