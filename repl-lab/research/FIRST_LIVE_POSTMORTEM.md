# First experiment: read-only failure analysis

**Source/scoring unchanged. No sealed reruns. No new inference.**

The cold-boot direct control supports a limited policy result: retained and
original policies both completed 8/8; mean makespan was 59.5 versus 204.125 ticks.
The retained policy matched the existing estimate baseline. The earlier 1/8
held-out result reflects worker failures, not seven observed bad schedules.
[Full results and accounting](FIRST_LIVE_RESULTS.md).

## Failure separation

| Category | Finding | Exact evidence |
|---|---|---|
| Development infrastructure | Three original-policy executions failed before recorded policy calls. Durations were 11.658, 13.303 and 13.278 seconds. The same policy completed the corresponding cases in the earlier frozen task. Do not count these failures as algorithmic gain. | Acquisition `tasks/evolving-0/episodes/development-64448a54-a199-409e-88d5-47c36d21fa7f.edn`, `development-48ac4fca-84e0-4cdf-9f65-aa4bb91dfeea.edn`, `development-ccffa944-822f-45ed-8f5a-00cb0306bd42.edn` |
| Retained-policy held-out execution | Seven of eight direct cases report `Worker terminated without result`; one completed in 39 ticks. Failed wall times were 12.253–14.629 seconds. The original-policy removal control also had two worker failures. | Held-out `episodes/retained-code-{0,1,2,3,4,6,7}.edn`; `episodes/skill-removed-{4,5}.edn` |
| Model code rejection | The first generated policy's `letfn` form was rejected by SCI with `clojure.core/alter-var-root is not allowed!`; all six cases failed. This is a code/environment compatibility failure, separate from worker disappearance. | Acquisition `tasks/frozen-0/episodes/development-f1169f18-a52e-4e18-9976-9550a850c8ec.edn`; candidate `567d990ffcd0…` |
| Temporary policies | All eight evolving held-out tasks selected temporary code. Five completed. One omitted capacity checks and produced 4,991 rejected capacity actions before event-budget exhaustion. Two failed loading. These are not executions of the retained policy. | Held-out `episodes/evolving-0.edn`, artifact `5b9ed95b9c01…`; `sessions/evolving-{6,7}.jsonl`, `policy/use` receipts at sequence 21 |
| Frozen agent failures | Seven roots exhausted the shared six-call allowance; one emitted trailing EDN. The automatic analyst used 23 of the arm's 44 model calls. | Held-out `sessions/frozen-{0..7}.jsonl`, `session-finished` events |
| Cold transport | CLI 2.1.311 appeared during the run. The transport stayed pinned to 2.1.310 and rejected later requests before dispatch. Twelve reservations remain uncertain. No model or pin switch was made. | [Doctor](evidence/first-live-20261027/transport-doctor-during-coldboot.json), [file timestamps](evidence/first-live-20261027/cli-change-observation.json), cold `sessions/{frozen,evolving}-{4..7}.jsonl` |

Paths above are relative to [acquisition](../var/runs/model-1793062055972/),
[held-out](../var/evaluations/evaluation-1793062969450/), or
[cold boot](../var/evaluations/evaluation-1793064236328/), as indicated.
[Compact per-case evidence](evidence/first-live-20261027/heldout-audit.json)
preserves exact hashes and metrics without requiring the large raw report.

## Why the worker failures remain partly unexplained

The generic error comes from [isolation/request!](../src/repl_lab/isolation.clj).
It carries worker stderr in exception data. However,
[development-panel!](../src/repl_lab/live.clj) and
[episode!/code-panel!](../src/repl_lab/evaluation.clj) retain only the exception
message. Docker uses no log driver and removes each container. The detailed
supervisor cause is therefore unavailable in the saved episode.

The [supervisor](../scripts/isolation.py) starts its 10-second response timer while
the JVM/SCI worker starts. Failure timing, the earlier near-limit positive control,
and failures of the unchanged original policy make startup timing a plausible
cause. It is **not proven**. Timeout, daemon delay, memory/process termination and
other worker faults cannot be separated from these records. Normal policy-call
exceptions would retain partial execution as `policy-error`; these recorded
failures occur in the startup/definition-loading path.

The fixed FIFO and estimate baselines achieved 8/8 because their schedules solved
all eight workloads. They also bypass this failure path:
[evaluate-live!](../src/repl_lab/evaluation.clj) calls trusted host functions through
`experiment/panel!`, while model policies use `live/run-policy!` and Docker/SCI.
This is a measured reliability asymmetry, not evidence of algorithmic superiority.

A second reporting defect affects failed agent episodes: after a temporary policy
is selected, an execution exception can cause the report's `artifact` field to
fall back to the retained-policy hash. The `policy/use` receipts identify the
actual selection. The direct retained/removal arms have no replacements and are
unaffected. No raw record has been corrected or overwritten.

## Workflow finding

The accepted workflow actually selected 12 full permitted job rows instead of
four restricted rows, and removed automatic delegation. Held-out inference cost
was $0.392848 equivalent versus $0.410536, but tokens slightly increased
(160,660 versus 160,524). Policy, context and delegation changed together; agents
also synthesized temporary policies. No controlled workflow-only effect or
context-quality metric was measured. **Harness improvement remains unproven.**

## One next experiment: policy-runtime-diagnostic-v1

**PROPOSED / NOT RUN.** Keep Sonnet 5.5 fixed as the source model. No new model
calls are needed for this diagnostic; its inference allowance is zero.

1. Freeze the exact original and accepted policy forms, worker image, simulator,
   scorer and resource limits in a new source/manifest version. Do not reuse the
   consumed final splits. Use seeds 830000–830011: six 12-job layered cases, three
   24-job fanout cases and three 24-job chain cases, with the existing respective
   fault/resource profiles. Record complete world hashes before any execution.
2. Run both policies on each identical world through the same isolated SCI path.
   Use two predeclared repetitions with reversed order: 48 total episodes. No
   synthesis, workflow, task-local replacement, adaptive retry or promotion.
3. First pass the actual isolation suite. For every disposable worker, record
   startup/ready timing, a fixed positive control, code-load acknowledgement,
   response timing, bounded stderr, exit/OOM status and confirmed cleanup. Preserve
   the existing limits. If execution health is not established, stop the diagnostic
   and report the infrastructure blocker; do not increase limits to secure a score.
4. Classify failures explicitly: confirmed infrastructure/transport, code rejection,
   algorithm/contract failure, resource exhaustion, or unresolved. Report every
   attempted episode and infrastructure rate. Compare makespan on paired episodes
   with healthy execution in both arms as a **conditional secondary analysis**;
   do not drop unhealthy episodes from the overall completion denominator.

This tests whether the observed cold policy benefit repeats under equivalent
execution and whether the earlier losses arose before policy execution. It does
not test harness learning. Pin the CLI by immutable binary for any later authorized
model work. Do not add Prime benchmarking or change the model while these results
remain unresolved.
