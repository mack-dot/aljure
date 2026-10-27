# skill-selection-v1 — proposed, not authorized or run

Question: can Aljure acquire an executable selector that chooses when to reuse an
approved skill, without losing verified task performance or spending more than
reuse saves? This is separate from learning a scheduling policy.

No model call, selector training or Prime comparison is authorized by this file.
The current no-inference diagnostic stopped at its readiness gate. Healthy,
repeatable isolated execution is a prerequisite for this future experiment.
No existing sealed task is reused, retuned or relabeled.

## Minimal intervention and four conditions

Keep the scheduler, accepted policy, scorer, controller, provider, context broker,
SCI image/limits and task inputs fixed. Freeze a new source/manifest version.
Use a small explicit selection contract, not a new agent framework: choose an
approved policy by hash or request task-local synthesis. Record the chosen route,
then the artifact hash actually loaded and every invocation. Do not infer reuse
from a final message or a fallback report field.

| Condition | Selection rule | What it tests |
|---|---|---|
| A: automatic retained skill | Controller always executes the approved retained policy; no model selection call | Manual reuse control; explicitly not learning |
| B: model-directed selection | Current agent loop chooses approved reuse or temporary synthesis | Autonomous choice with access to retained computation |
| C: no retained skill | Same agent loop, tools and prompt, but the acquired skill is absent; only the original control policy is available | Cost and performance without retained knowledge |
| D: learned selector | A model-authored, independently accepted pure selector chooses reuse, the original control, or synthesis | Learned allocation of computation |

For B/C/D, use the same neutral interface documentation, context selection and
artifact catalog format. B retains model-directed selection but does **not**
reproduce the old ambiguous prompt byte for byte. This declared version change
removes the old visibility confound. Do not attribute a B-versus-old-trace gain to
learning. No extra fifth prompt condition is part of this minimal pilot.

The catalog states each available skill's hash, interface, allowed inputs and
bounded development validation summary. Full source remains equally retrievable.
No condition receives hidden outcomes, final seeds, cached answers or a preferred
route. C's missing acquired skill is the intended ablation; give it the original
policy under the same interface. Freeze a common context query and disable the
old automatic analyst delegation in every arm. Optional child calls remain
available to the common agent loop and share its task budget.

A and D may use zero model calls on an evaluation task. Equal budgets are ceilings,
not a requirement to waste the same amount of inference. Do not fill unused calls
or transfer unused task allowances.

## Acquiring the selector

Use six new acquisition tasks and four separate development tasks. Give the model
permitted observations and measured development outcomes/costs for alternative
routes. It may propose `select(features, catalog) -> route`; features must derive
only from information available before solving the task. Disallow seed IDs,
case hashes, hidden durations/future faults, answer tables and stored transcripts.

All route-label generation, including model-directed counterfactual calls used
for selector training, is charged to D's acquisition ledger. There is no free
oracle. If the cap prevents completion, preserve that outcome.

The selector must be model-authored code with an exact source, structural form,
content hash and authoring-session provenance. Developers must not write a reuse
preference and label it learned. The fixed controller validates syntax, allowed
routes, isolation, metadata integrity and development behavior. No selector can
change promotion, accounting or scoring.

Freeze the acceptance rule before acquisition: no development completion
regression versus automatic reuse; no paired completed-case makespan regression;
strict reduction in development inference cost versus model-directed selection.
This is a limited pilot rule, not proof of generalization. Record rejection and
all costs even if no selector qualifies. If none qualifies, D is “no accepted
selector”; do not silently replace it with a hand-coded or best-observed rule.

Freeze the accepted selector and terminate the training processes/conversations.
Load only approved selector/policy code and the common interface documentation.
Evaluate new tasks with fresh processes. The selector cannot learn from final
outcomes or update during evaluation.

A model-generated constant reuse selector can count as acquired software, but
not evidence of learning **when** reuse is appropriate. That stronger claim needs
meaningful route variation, verified benefit over constant reuse, and transfer to
unseen inputs. If all workloads favor retained reuse, report the selector problem
as uninformative or constant reuse as the best measured strategy. Do not hand-pick
cases after observing which condition wins.

## Workloads, parity and prospective caps

Before any model calls, generate and hash independent acquisition/development/
held-out manifests using the existing workload generator. Use 12 held-out worlds
with preregistered variation in graph structure, job count, faults and resource
mix. Check disjointness against every old split and diagnostic world. Publish the
profile/seed-generation rule before outcomes; keep final cases inaccessible to
agents. Use identical worlds for all four arms and rotate their order.

Pin requested and returned `claude-sonnet-5-5`, one immutable validated CLI binary,
Claude subscription transport, the same sampling/thinking settings, 2,048 output
tokens, disabled cache and the same model-facing tools. Record prompt differences
and hashes. A transport/model mismatch fails closed. No model substitution.

Prospective evaluation limits for **every** arm: six root/descendant calls,
64,000 tokens, $0.625 API-rate equivalent and 120 seconds per task. The selector's
own execution consumes the same worker/task allowance. A synthesis route invokes
the same downstream agent implementation and model configuration in B/C/D.
All retries, repairs, children, refinement and compaction must reserve from the
same ledger before dispatch.

Prospective acquisition allowance: at most six tasks, 12 calls, 64,000 tokens,
300 seconds and $1 equivalent per task. Expose the same acquisition allowance to
all conditions, but A/B/C remain fixed by definition; unused acquisition allowance
cannot increase their evaluation allowance. D's selector acquisition is charged
in full. The proposed ceiling is therefore $6 acquisition + $7.50 evaluation per
arm, $54 across four arms; most of A's allowance should remain unused. These are
**unapproved ceilings, not spending authority or predicted invoices**. Any further
replication needs its own budget. Use $2/M input and $10/M output for equivalence;
report actual billing separately as unknown when using subscription transport.

One acquisition trajectory and 12 held-out worlds form an exploratory pilot.
Do not claim a statistically established learning advantage. Repeated independent
selector acquisition would require a separately authorized follow-up.

## Metrics and claim boundaries

For every planned/attempted task record:

- Independently verified completion, simulated makespan, penalized score, failures
  by startup/loading/execution/algorithm stage and actual resource-limit outcomes.
- Root/child calls, input/output/cache tokens, unknown reservations and known
  equivalent cost. Count selector acquisition, catalog/inspection prompts,
  selection, repairs and synthesis. Separately include the historical retained-policy
  acquisition cost for A/B/D (known and uncertain amounts), without presenting it
  as new spending. C has no acquired library; developer effort remains unpriced.
  Report amortized acquisition-plus-evaluation
  cost over all planned tasks and per verified completion; undefined ratios stay
  undefined when no task completes.
- Selected route; selector, policy and dependency hashes; actual invocation counts;
  task-local code and repairs; retrieval operations and selection latency.
- Local execution wall/resource measurements. Total economic dollars remain
  unknown unless a local-compute price is frozen before the run. Keep inference
  equivalent and local measurements separate; do not label inference alone total cost.

Primary outcome: paired verified completion under matched limits. Secondary:
completed-pair makespan, tokens/calls/cost per verified solution, and actual reuse.
All failures stay in the overall denominator. Healthy-pair analyses are separately
labeled and cannot erase infrastructure losses.

Maintain four separate evidence statements: **policy improvement**, **fresh-process
retention**, **autonomous skill reuse**, and **harness improvement**. A tests the
first two and provides a manual control. B can demonstrate autonomous reuse only
through actual selection/invocation. D supports harness learning only if a
model-generated, independently accepted selector improves unseen verified
performance or amortized inference efficiency beyond the relevant controls.
Persisting a selector, selecting a hash, or beating the old opaque prompt is not
sufficient.
