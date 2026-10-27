# Read-only analysis of skill selection

Evidence: LIVE MODEL RUN / HELD-OUT EXPERIMENT traces from the first experiment.
This analysis makes no model requests and does not edit or replay sealed tasks.
It separates observed behavior from explanations that still need an experiment.

## What the agent could see

The first root task says: “Solve this task. You may inspect context, use SCI, call
children, and choose a temporary policy. The library is frozen.” Its
`workflow-result` contains a policy hash and selected job observations. It lists an
external `artifacts` context alongside `jobs`, `workers` and `observation`.

The approved policy is available. `artifact/inspect` can retrieve its source and
interface. `artifact/call` can execute approved dependencies. However, the initial
root task does not show the retained policy's source, a descriptive skill name,
applicability conditions or validation results. Its interface is simply `decide`
with arity 2. Fresh export removes the acquisition trajectory and acceptance
history. The policy hash is an identifier, not a useful skill description.

See [first evolving root request](../var/evaluations/evaluation-1793062969450/sessions/transport/049ec1d0-e344-4e21-9bef-7edb5578600a/request.json),
[base instructions](../resources/base-instructions.txt),
[evaluation intake](../src/repl_lab/evaluation.clj) and
[workflow/broker implementation](../src/repl_lab/runtime.clj).

## Selection and retrieval actually observed

Across both old final phases, no agent used `artifact/inspect`, queried the
`artifacts` context, or invoked `artifact/call`. The eight held-out evolving
agents all selected temporary policies. The four cold evolving agents that
received model responses also selected temporary policies. The remaining four
were blocked by transport preflight and provide no evidence of a selection choice.

The controller executes the retained policy if the root finishes without setting
`temporary-policy`. The prompt does not explain that `done` therefore means
“execute the existing policy” when no replacement was chosen. There is no
`policy/use` by hash: that tool accepts new source only. `artifact/call` returns
one function result, not a persistent scheduler selection. These contracts make
synthesis explicit and default reuse implicit. This is a plausible interface
explanation, **not evidence of the model's private reasoning**.

For held-out `evolving-0`, trace sequences 5 and 10 request context; sequence 15
selects temporary source; sequence 20 finishes. There is no intervening skill
inspection. The model's final summaries describe temporary greedy schedulers.
They do not describe a measured comparison with the approved policy. No evaluation
scores were returned during final evaluation, so the model did not reject that
policy after seeing its held-out failures.

The approved workflow did execute: it expanded initial context and omitted
analyst delegation. That is different evidence from policy reuse. Five evolving
held-out successes and three cold successes ran temporary code. Only the separate
direct controls establish retained-policy invocation and its cold-boot benefit.
Failed agent episode `artifact` fields can incorrectly fall back to the retained
hash; `policy/use` receipts and actual policy-call records are the attribution
sources, not that fallback metadata.

## Measured cost of the selection behavior

Values below charge each model turn according to its returned command. They
include that turn's whole input history; they are not causal estimates of savings
from removing an operation.

| Evolving condition | Completed model calls | Total tokens | Known equivalent | Temporary-policy generation turns | Generation input/output tokens | Generation-turn equivalent |
|---|---:|---:|---:|---:|---:|---:|
| Held-out | 36 | 160,660 | $0.392848 | 9, including one repair | 41,485 / 7,156 | $0.154530 |
| Cold boot | 17 | 74,354 | $0.182988 | 4 | 17,851 / 3,412 | $0.069822 |

The held-out evolving arm also spent $0.146756 on context metadata/queries and
$0.091562 on final `done` turns. Those final inputs included prior generated code.
No artifact-retrieval or artifact-call inference cost occurred because those
operations were never selected. Direct retained-policy controls used zero model
calls, but their execution cost in dollars is unknown. The cold arm's incomplete
transport coverage prevents a clean cross-arm cost comparison.

[Per-task audit](evidence/skill-selection-v1/trace-audit.json) retains initial root
tasks, query handles, selection receipts, request IDs, sequence numbers and
input/output/cost breakdowns. Original raw receipts remain authoritative.

## Interpretation

The current evidence does **not** show that the model compared reuse with synthesis
and found synthesis better. It shows an available but uninspected skill, an opaque
initial reference, an explicit synthesis action, and an undocumented default-use
path. There was no learned selection policy or selection-cost feedback in training.
We cannot distinguish prompt effects, retrieval friction and model preferences
without a controlled experiment.

Policy improvement, process retention, autonomous reuse and harness improvement
remain distinct. The first two have narrow positive evidence. The latter two
remain unproven. A manual “always reuse” rule is a useful control, not learning.
The sole proposed model experiment is [skill-selection-v1](SKILL_SELECTION_V1.md),
which is not authorized or started.
