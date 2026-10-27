# Skill discovery and selection v2

**Post-run readiness warning:** the first offline attempt stopped before policy
loading. The legacy isolation proof was invalidated after audit found that startup
timeouts can count as negative-test passes. The commands below record the original
protocol; a regenerated legacy proof is not sufficient to authorize another run.
See `SKILL_DISCOVERY_V2_RESULTS.md`. No versioned selection run should be retried.

Supersedes the proposed conditions in `SKILL_SELECTION_V1.md` for the next study.
The old proposal and every earlier sealed result remain unchanged.
**No additional inference is authorized.** The implemented command runs FIXTURE
controls only. It has no live provider path. Sonnet `claude-sonnet-5-5` remains
the proposed live pin; the actual offline provider is `fixture-script-v1`.

## Four conditions

| Condition | Intervention | Offline control |
|---|---|---|
| Opaque hash | Initial library reference is a hash | Script queries observation, synthesizes generic resource-fit policy |
| Descriptive discovery | Initial compact registry, same tools | Script reads registry and details, reuses on CPU/memory and synthesizes for extra resources |
| Deterministic reuse | Controller always selects retained policy | No selector model calls; retained code executes on every case |
| Model-authored selection | Future accepted executable selector routes work | **Developer-authored stand-in only**: reuse, compute then synthesize, or delegate then synthesize |

All arms can query the same contexts, inspect identical code/metadata, use SCI,
call children, select approved code, or make task-local source. The opaque arm
keeps the opaque initial presentation, but gets the same new tool documentation.
It is not a byte-identical replay of the historical agent. The deterministic arm
does not use all tools; its restricted decision rule is the intended intervention.
Offline scripts are wiring controls, not plausible estimates of live behavior.
The generic-resource policy and selector stand-in must never become live hints.

## New workloads and unchanged evaluator

Four public fixture worlds use seeds 840100–840103, sizes 6/7/6/7, layered
dependencies, one fault, and the existing workload generator. The first two
use CPU/memory. The next two additionally require one GPU per job. Workers w0/w2
have two GPUs; the faster w1 has none. The simulator already supports arbitrary
resource keys. Its validation, scores, event budget, and completion rules do not
change. Repeated invalid dispatches remain algorithmic failures, not startup
failures. No extra score rewards a particular route.

This is a deliberate applicability boundary test, not a representative domain
sample. Reuse is reasonable inside the reviewed contract. Adapting or synthesizing
generic resource checks is needed outside it. Cheap deterministic applicability
gating is a strong additional diagnostic baseline for any eventual learned claim;
beating blind reuse alone would be insufficient. This four-case fixture cannot
establish that delegation is worthwhile. Its child route checks plumbing only.

Every task has 6 total parent/child calls, 64,000 tokens, a $0.625 equivalent
ceiling, and 120 seconds including selection and execution. The same unchanged
SCI image and 10-second worker response limit apply. Offline inference costs are
zero; scripted provider turns are counted separately. Selector execution counts
against task time. Rotate arm order by case; use fresh stores, conversations and
workers. Stop on startup/cleanup failure, retain all unattempted slots, no retries.
An actual positive and nine-negative isolation proof remains mandatory.

## Evidence and costs

Freeze source/config/prompt, world hashes, capabilities, image, registry and
selector before execution. Save exact selected code, model/script events, worker
stage diagnostics, and simulator records. Independently replay every episode.
Record metadata exposure, list/detail/source requests, actual successful artifact
calls, selection origin, completion, makespan, invalid actions, tool failures,
parent/child calls, tokens, reservations, and selector overhead separately.
Provider errors and worker failures stay in the attempted denominator with their
own classifications. Healthy paired results are explicitly conditional.

Historical policy acquisition cost is common to all arms: $0.166624 known plus
$0.394712 unresolved reservations for the whole first acquisition (both arms).
Report each divided by verified solutions, separately from new experiment cost.
This deliberately broad allocation is disclosed; it is not a marginal skill price.
Do not treat the unresolved amount as measured spend. Local-compute dollars and
subscription invoices remain unknown. Offline zero-token results cannot support
an inference-efficiency or economic-performance claim.

## Live selector study: proposal only

After separate authorization, use the same pinned Sonnet subscription transport
and settings in every model-driven condition. Pin its actual CLI revision too.
Start with 6 acquisition and 4 development tasks from independent new seeds and
a balanced resource-contract mix. Only the selector arm may acquire a selector;
its cost includes all labels, failed proposals, evaluation and child calls.
The initial approved policy/library and tool surface are equal across arms.
Provide only permitted observations, registry entries, and acquired development
evidence. Allow pure executable selectors to return bounded routes: reuse approved
hash, compute then select, delegate then select, adapt, or synthesize.
Do not give them fixture branch rules, hidden answers, or future workload seeds.

The controller must validate selector source/arity/isolation, output schema,
approved hash membership, route execution limits, and independent development
results. Require no development completion regression or paired makespan regression
against the best simple control, plus a strict reduction in model equivalent cost
versus descriptive model-directed selection. Count selector acquisition too.
This is a new selector acceptance rule, not a change to historical policy promotion.
If no selector qualifies, report rejection; never substitute the fixture selector.

Before model calls, freeze the generator, acceptance rule, independent sealed seeds,
sampling settings, prompts, arm order, rate configuration and all phase caps. Then
freeze accepted code, restart processes/conversations, and evaluate 12 matched unseen
cases with no feedback or tuning. Use at least three independently acquired selectors
before interpreting uncertainty as learning generalization. Add contract-compatible
selector removal and compare to constant reuse and deterministic applicability
gating. Attribute gain separately to policy, metadata, autonomous reuse, and routing.
Success means a validated learned selector beats simpler choices on unseen verified
performance/cost; mere branching, persistence or a changed workflow hash is insufficient.

Acquisition: proposed 12 calls / 64k tokens / $1 equivalent / 300 seconds per task.
Evaluation: unchanged 6 calls / 64k / $0.625 / 120 seconds. These per-task figures
are **not** an approved global cap. A concrete phase/global budget and readiness
review must precede any live run. Live selector acquisition/acceptance and sealed
four-arm orchestration are **not implemented** by the offline control command.

## Commands

From `repl-lab/`:

```sh
python3 scripts/clj.py -e "(require 'repl-lab.skills-test)(clojure.test/run-tests 'repl-lab.skills-test)(shutdown-agents)"
source var/worker.env
make isolation-test
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/skill-discovery-v2-controls/workers" \
  make skill-discovery-fixtures OUT=var/diagnostics/skill-discovery-v2-controls
```

The output path must be new. A failed run is preserved, never retried in place.
`make skill-selection-live` fails with an explicit authorization/implementation
message. It cannot silently run fixtures as a live experiment.
