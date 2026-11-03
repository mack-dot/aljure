# Frozen development A/B: external artifact interface

Version: `reuse-interface-development-v1`. No live run is authorized by this file.
Approval must name the newly generated exact plan hash. Earlier approval applied
only to the completed six-task experiment. No held-out inputs are used or opened.

## Question and arms

Does the repaired external interface permit model-initiated, source-attributed
invocation of a retained, live-learned artifact on unseen development tasks?

A is the unchanged e6d17fe model-visible baseline. B adds only
`aljure_contract.skill_interface: "inspect-v1"`. Both execute from the same new
source commit, with an offline request-parity proof for A against frozen tasks
3–5. Both use the exact same immutable library acquired in the prior live run.
The existing acquisition pipeline is regression-tested but disabled in this A/B.
No reward, instruction to prefer reuse, automatic application, skill renaming,
artifact editing, or task-specific interface logic is added.

## Inputs and schedule

Five new synthetic development cases: three Routing v1 counts (retry, hold,
expedite; 40, 48 and 56 records), one incompatible parity case (20 records), and
one Routing v2 case (48 records). Routing v2 changes semantics while retaining
familiar field names. The original predicate can admit it; the model must check
current rules and decline the old classifier. Its correct hold count differs
from the old classifier's count by construction.

`benchmark/reuse_interface.py` generates all cases with seed 2026110202. Routing
feature tuples and record texts are disjoint from every earlier six-task record
and validation-panel record, and from each other. Parity codes use a separate
range. These are development cases in known families, not independent held-out
generalization. The gold stays on the controller. The external runner receives
only the selected public task and context.

Ten attempts, paired on the same five cases. Order is A/B, B/A, A/B, B/A, A/B.
Each attempt starts a new JVM, conversation and isolated worker. No session,
trajectory text, model response or task-local code passes between attempts. Only
the fixed retained library persists. The old acquisition process has exited.
No retries, replacements, resumption, additional seeds, or edits after outcomes.
Every failed and unattempted case stays in the denominator. Provider-side prompt
caching may affect cost; cache usage is recorded, and it conveys no conversation
state. Order imbalance and the small sample remain limitations.

## Frozen endpoints and acceptance

Primary: fraction of the three eligible unseen tasks, by arm, with at least one
successful model-initiated invocation attributed to an approved code hash loaded
before the task. Two supported paths count: the controller's `artifact_call`
event, or the existing preloaded function invocation log attached to a model
tool call. Loading, listing, inspection, copied source, controller applicability
checks and scripted fixture calls do not count. Review the original tool source
and return trace for actual task-data use, copying and counter manipulation.
The automatic report is provisional until that attribution review completes.

Secondary: exact answer accuracy; all request costs including inspections,
errors, children and cache charges; unknown reservations; cost per successful
task; wall latency per task and arm total; tool failures; correct reuse tasks
per dollar; invocation counts and returns; negative transfer. Report raw paired
outcomes, not only aggregate percentages. Local compute dollar cost and actual
subscription invoices are unknown and must be stated as such.

Negative transfer controls: parity must refuse execution of the inapplicable
artifact and remain correct. Routing v2 must remain correct without invoking the
old classifier. Record inspection, attempted calls, actual calls, and incorrect
answers separately. An unauthorized call rejected by the controller does not
count as an execution; it remains a tool/selection failure.

Development GO requires all ten attempts complete with exact accounting and
cleanup evidence; all five repaired-arm answers correct; at least one of its
three eligible tasks with valid source-attributed reuse and a correct answer;
and neither negative control with a retained-classifier execution. An unresolved
attribution audit prevents GO. Cost must stay within the hard aggregate cap.
Report any baseline reuse and all regressions. Equal results are not evidence of
improvement. This sample is too small to establish statistical superiority;
even three favorable discordant pairs yield two-sided exact McNemar p=0.25.
No superiority claim or tuning against these outcomes is permitted. A larger
study needs a separate preregistered protocol and approval.

## Cost and safety

Same pinned Sonnet 5.5 subscription transport, adaptive thinking, medium effort,
rates, images and task limits as the original minimal run. No API fallback.
At most 12 requests per task, 120 across ten tasks, 32768 output tokens per
request, 300 seconds per task, and $5 per-task API-rate-equivalent ceiling.
The entire A/B has a **$6 hard aggregate equivalent ceiling**. Before starting
each task, known cost plus unknown reservations must leave the full $5 task
allowance. Thus the run stops before a new task if prior cost exceeds $1. It
does not allocate or authorize $50. All requests use the existing bounded gateway.

Report new A/B expenditure once. Also show each arm's standalone total with the
same $0.025166 historical acquisition overhead, clearly labeled. Do not count
that historical overhead twice in actual new spending. Preserve per-call usage
receipts and verify unique call/provider IDs. If an outcome is unknown, retain
its reservation, stop and do not claim complete cost accounting.

Before live execution: verify frozen source and protocol hashes, all public and
controller input hashes, library bytes, both execution-image IDs, current sandbox
and artifact-path proofs, acquisition regression proof, subscription relay proof,
and the new full-path interface fixture. Require at least 6 GiB free disk before
each task. Refuse a pending Docker restart. Stop on infrastructure, cleanup,
accounting or source-integrity failures. Final-task failures still invalidate
the acceptance gate. Ordinary task errors remain in the record under the same
per-task caps. Do not repeat a paid attempt after a runner crash.

Freeze from a clean committed checkout. The plan pins its source file map,
runtime file map, generated input suite, library, config pair, schedule, budget,
protocol and model contract. Archive preflight and offline failures separately.
No live transport is instantiated by prepare, plan, preflight or fixture commands.

Commands are `python3 -m benchmark.reuse_interface prepare|plan|preflight|run`.
The run command requires `--authorize-subscription-plan <exact-new-plan-hash>`
after explicit user approval. The source checkout and generated suite are kept
separate from the final evidence-archive commit so that archiving cannot change
the approved execution source.
