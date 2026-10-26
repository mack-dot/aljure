# Experiment protocol — version 4

H1 asks whether retained executable skills improve held-out task performance.
H2 asks whether benefit survives fresh processes and conversations with only
approved executable artifacts. H3 needs matched Python arms and is deferred.
No fixture result is evidence for any hypothesis.

Version 4 records broker results with their corresponding call sequence, adds an
independently checked live capability smoke test, and requires a complete matching
SCI isolation proof for smoke, acquisition, resume, held-out, and cold-boot entry
points. Earlier source snapshots remain historical evidence. The Sonnet 5.5
spending proposal is not authorization; smoke consumes part of the acquisition
category if the operator approves that allocation.

Frozen and evolving Clojure arms receive the same initial primitives, model,
observations, tools, recursion, and per-task limits. Both can execute temporary
code. Only the evolving arm can retain approved code between learning tasks.
The deterministic scheduling loop is the same in both arms.

Split definitions are controller-owned. Learning and development cases differ.
Final seeds and outcomes never enter learner mounts. Freeze the artifact library
before final evaluation. Reset task-local memory each episode. Do not return
final scores to the learner. Tuning after final evaluation needs a new split and
experiment record. New seeds test interpolation; explicit larger DAG, chain/fanout,
resource-mix, and fault-density changes test distribution shift.

Promotion is a paired development-panel comparison. Reject safety violations,
any case with lower completion, and any complete case with worse makespan.
Require a strict improvement in completion or aggregate penalized makespan.
Incomplete runs receive horizon plus unfinished-job penalties. Never remove
timeouts or failures from averages. Pin active sessions/episodes to immutable
versions. Promote only at an episode boundary using a compare-and-swap parent.

Report raw cases, count, dispersion, and paired uncertainty. Tasks that share one
learned library are not independent learning runs. Report acquisition and final
evaluation costs separately. Unknown dollars are null. No compute-efficiency
claim without a matched total-budget experiment. Record failed candidates too.

Cold boot exports a whitelist with hashes, dependencies, code/workflows, and
concise API metadata. Exclude conversations, task caches, model session IDs,
retrieval data, test inputs, scores, and narratives. Audit comments, docstrings,
embedded data, and identifiers. A scan alone does not prove no memorization.
Run a contract-compatible parent/fallback ablation. Trace actual invocations.

Commitment means at most one accepted simulator result per job. Retries can
execute work more than once. Do not claim exactly-once execution or model calls.
Safety status starts at implemented and advances only with explicit evidence.

## Version 2 execution details

Acquisition runs three paired learning tasks. Each arm/task receives a fresh
controller, root session, mailbox, context store, and worker set. Both arms can
stage artifacts, request the same development panel, use temporary code, and use
controller-approved code during that task. Only B carries approved executable
artifacts forward. A starts each new task with the initial library. Neither arm
retains transcripts or narrative memory. Alternate arm order across task indices.

The operator's acquisition cap covers both arms. Divide it by twice the learning
panel size. Each task has the same call, token, message, candidate, evaluation,
wall-time, and interpreter limits. Children share that task's allowance. Report
all task ledgers, including failures, rejected candidates, and outstanding charges.
Do not transfer unused allowance to another task. This is equal allocation, not
a claim of equal actual cost or compute efficiency.

Resume preserves completed task records and allowances. A controller crash with
an unfinished task does not trigger a model retry. Keep unknown charges reserved,
score the interrupted task as failed, and continue with the remaining task
allowances. A recorded episode survives a crash after its write. Resume requires
the same source, split, model, worker image, rates, and original total cap.

Final RLM evaluation uses equal six-call task caps. Both arms can replace their
policy temporarily; neither can stage or promote artifacts. Also run fixed FIFO
and estimate baselines. Separately execute the retained policy and compatible
initial policy without inference. This direct removal test prevents a model from
reconstructing the removed skill during the ablation. It does not measure the
causal contribution of every workflow choice. Report workflow invocation records
and analyze that limitation when interpreting a real run.

Development and final records include full replayable episodes, including policy
and pre-execution failures. They are controller evidence, never learner mounts.
Source changes require a new experiment version and fresh held-out splits.

## Version 3 budget enforcement

The event limit in configuration now reaches every policy runner. A task has one
absolute execution deadline. Development episodes, root/child inference, REPL
calls, and the task's final policy execution all use its remaining time. The token
count request cannot reset the inference deadline. A worker uses the smaller of
its own lifetime limit and the remaining task time. No work starts after that
allowance expires. An expression also has the fixed worker execution timeout.

A late policy response cannot dispatch new actions. A wall-budget stop keeps its
partial state and can be replayed from the recorded actions and terminal status.
Unknown provider outcomes retain their reservations. Cleanup and durable failure
recording happen after the execution stop and may extend total observed wall time;
they use separate bounded transport timeouts and do not authorize further inference
or generated-code execution. Each independent direct-code ablation case starts
with an equal fresh allowance. Frozen and evolving agent cases share the same
inference-plus-execution accounting rule.
