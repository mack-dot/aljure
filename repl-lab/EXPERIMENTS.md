# Experiment protocol — version 1

H1 asks whether retained executable skills improve held-out task performance.
H2 asks whether benefit survives fresh processes and conversations with only
approved executable artifacts. H3 needs matched Python arms and is deferred.
No fixture result is evidence for any hypothesis.

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
