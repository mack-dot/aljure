# Selector acquisition v1: implemented, offline controls only

**No live selector inference is authorized or reported.** The acquisition,
independent acceptance, executable export, held-out and cold-boot entry points
use the existing controller, provider adapters, SCI workers, simulator and replay
scorer. No scheduler or scoring rule changed. The old selector gate remains v1;
the stricter rules below are an explicit opt-in v2 gate.

This work follows the [pinned Prime skill audit](PRIME_SKILL_DISCOVERY.md): expose
a compact reviewed inventory, inspect source on demand, distinguish callability
from validation, and promote only through a controller decision. It does not copy
Prime's refinement loop or claim parity with Prime.

## Implemented boundary

`selector-acquisition` stages a model's `select-route/1` analysis artifact through
the native runtime. The independent gate checks the exact staged source against
the recorded provider response and author session. Live acceptance requires the
requested and returned model to be `claude-sonnet-5-5`. Fixture proposals cannot
be promoted. The controller exports an accepted selector only at a terminal
authoring boundary, after final acquisition accounting.

The reviewed initial library contains four independently identified capabilities:

- The prior model-generated policy, with byte-identical source and an explicit
  export-name adapter. It requires numeric CPU and memory fields and ignores
  other resource types. The adapter is a human edit, not a new learned artifact.
- A general resource-fit scheduler. It checks every resource key.
- A dependency ranker. It returns ready jobs in downstream-work order.
- A resource packer. It dispatches an ordered set of jobs onto feasible workers.

The controller owns names, descriptions, interfaces, applicability and limitations.
They are source-reviewed claims bound to verified source hashes, not model-written
claims or formal proofs. Full forms/source remain available through artifact
inspection. All conditions get the same tools and catalog.

The trusted executor supports approved reuse, zero-inference computation, actual
ranker-plus-packer composition, task-local adaptation/synthesis, and a native
recursive child session that produces a task-local policy. Composition loads and
calls both helpers; it does not merely choose one scheduler. Generated programs
run only through SCI. The delegate route currently delegates policy construction;
it is not evidence of learned decomposition into independent subproblems.

Authoring and task execution use separate role instructions. The original
acquisition prompt is not reused as an instruction to synthesize another selector
during a held-out policy task. Both prompt hashes enter the frozen plan.

## New preregistration, not a rerun of the GPU study

The new task specification combines graph shape, dependency depth, memory pressure,
missing memory fields, resource types (`license`, `bandwidth`, `storage`) and faults.
It has three learning, three development, four held-out and four cold-boot profiles.
Every unseen panel includes CPU/memory-only tasks and out-of-contract tasks. Seeds
are independently drawn and frozen in a controller-only file. Models and workers
receive observations; they do not receive actual durations, future faults, seeds,
scorer state or hidden outcomes. No current hidden panel has been generated or run.

There are six comparison conditions: automatic retained reuse, descriptive
model-directed discovery, fresh synthesis, a deterministic applicability guard,
constant ranker-plus-packer composition, and the acquired selector. Cold boot
also removes only the selector and substitutes the applicability guard with the
same approved library. That ablation is a fixed control, not learned behavior.

The constant composition control is necessary. A resource-aware selector must
beat simply composing two useful tools. The fixed guard checks both required
fields and unsupported resource keys, not the literal name `gpu`. The study does
not presume that every exposed route will help or that selection is needed.

V2 acceptance preserves independent replay, zero accepted invariant violations,
and no paired completion/score regression against the simpler controls. It also
requires an advantage over both the guard and constant composition, and lower
projected cost than descriptive discovery. A model that merely restates the
guard does not qualify.

The proposed 100-task amortization horizon is **projected payback**, not measured
efficiency and not 100 assumed successes. The full acquisition USD is retained.
Held-out reports separately divide actual acquisition plus actual evaluation cost
by the number of verified solutions. A zero-success arm has no defined cost per
verified solution. Local compute prices and subscription invoices remain unknown.

## Accounting and failure handling

Every task uses the existing durable root/descendant ledger. A provider wrapper
reserves in a shared phase ledger before native dispatch. Native adapters retain
their per-task reservations. Phase caps sum to the campaign ceiling. Complete
provider receipts reconcile back to their originating ledger, run and session.
Inspection, selection, child calls, generation and development validation count.
Final acceptance charges all acquisition attempts, including rejected candidates,
control evaluations and authoring after development feedback.

The new gate rejects `{}` as an accounting ledger. It requires controller fields,
matching request/result events, complete usage, consistent token totals, matching
spent totals, and no unresolved reservations or overruns. Unknown outcomes retain
reservations and block further phase dispatch. There is no automatic retry.

Startup, code loading, instrumentation, execution and cleanup have distinct
evidence. A healthy worker's explicit code rejection is an algorithm/contract
failure. Tracing failures are controller failures. If tracing fails after a
simulation, its original episode is preserved and does not become a fabricated
zero-completion episode. Transfer writes the full slot list before execution,
stops on infrastructure or unresolved accounting, and retains unattempted slots
in the report and denominator. Unknown costs remain unknown.

## Offline evidence and preserved failures

The corrected **controls-v3 is FIXTURE**. Seven policy slots plus one selector
invocation used fresh SCI workers. Six policy slots completed. The expected
retained-policy test with missing memory and an added resource failed with a
code rejection after healthy startup/loading. Composition, scripted adaptation
and the scripted recursive child route completed on that same task.

Both composed helpers actually ran: 29 invocations each in the CPU case and 18
each in the mixed case. The retained policy ran 29 times in the CPU case and once
before the expected contract exception in the mixed case. These counts do not
establish that selection improves performance.

The two earlier controls failed because of new tracing code:

1. V1 returned a SCI Var from instrumentation definitions. The worker correctly
   rejected an unreadable result. These are controller loading failures.
2. V2 used `@selector-invocations`, which its EDN source reader does not support.
   The final tracing read failed after policy execution. Its historical wrapper
   replaced the episode with `execution-failure`. Those old zero-completion rows
   are unreliable policy evidence. The raw records remain unchanged and annotated
   here; no algorithmic conclusion is drawn from them.

V3 uses explicit `deref`, EDN-returning definitions and preserved episodes on
tracing failure. The focused tests exercise the exact EDN snippets and verify that
tracing failure preserves a completed episode. Each control version had four
**scripted provider turns**, zero real model calls, zero tokens and zero inference
USD. None created or accepted a real model-authored selector.

Evidence: [archive inventory and hashes](evidence/selector-acquisition-v1/archives.json),
[v1 manifest](evidence/selector-acquisition-v1/v1-manifest.edn),
[v2 manifest](evidence/selector-acquisition-v1/v2-manifest.edn),
[v3 manifest](evidence/selector-acquisition-v1/v3-manifest.edn),
[v3 control report](evidence/selector-acquisition-v1/v3-controls.edn).
The three compressed raw archives contain 171 files. All 24 SQLite integrity
checks passed. Each run includes its exact source-file hash manifest; failed
intermediate source revisions were not committed as separate source snapshots.

The final targeted run passed **11 tests / 137 assertions**, including the old v1
gate tests. [Test output](evidence/selector-acquisition-v1/targeted-tests.log).
The new namespace is included in the normal test runner. The full project suite
was not repeated in this worktree while the separate Prime run was active.
Exact targeted command:

```sh
python3 scripts/clj.py -e "(require 'repl-lab.selector-acquisition-test 'repl-lab.selector-gate-test) (let [r (clojure.test/run-tests 'repl-lab.selector-acquisition-test 'repl-lab.selector-gate-test)] (shutdown-agents) (System/exit (+ (:fail r) (:error r))))"
```

V3 source hash: `1db3756042dc8e0b59d51c69fbf1deb93765672a236b1e6b90f997c05210641e`.
Base Git revision: `56f67c32249cb66384577f2fdc371e10f9383263`, with local changes.
Worker: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
The final revision also separates authoring/task prompts; those prompt changes
have unit coverage, not provider validation. The v3 source hash is not relabeled
as the final source revision.

## Commands and current blockers

From `repl-lab/`, an offline engineering control uses a **new** output directory:

```sh
source var/worker.env
python3 scripts/clj.py -m repl-lab.selector-acquisition controls var/selector-new-control
python3 scripts/clj.py -m repl-lab.selector-acquisition plan var/selector-plan-v1
python3 scripts/clj.py -m repl-lab.selector-acquisition preflight var/selector-plan-v1
```

The config is a proposal, not authorization: $24 acquisition, $15 held-out, $18
cold boot, $57 API-rate-equivalent maximum; six calls/$1/120 seconds per task;
12 authoring calls/$2/300 seconds; at most two development evaluations. The shared
phase cap can stop a second evaluation. No unused task allowance transfers. These
amounts do not reuse either the old $35 learning authorization or the independent
$24 Prime comparison authorization.

**Live selector execution is blocked.** The historical subscription adapter pins
Claude Code 2.1.310; the installed version is 2.1.311. Its preflight correctly fails.
This change does not alter that pin or silently use the new external OAuth gateway.
A separately versioned provider contract and explicit authorization of a frozen
selector plan are required before any new selector inference.

After that prerequisite and explicit approval, commands require `LIVE=1`,
`MODEL=claude-sonnet-5-5`, `INFERENCE_PROVIDER=claude-subscription`, `MAX_USD=57`,
and `SELECTOR_APPROVED_PLAN=<exact frozen plan hash>`. Credentials remain private.
Run `acquire`, then `heldout`, then `coldboot`, each as a separate invocation of
`python3 scripts/clj.py -m repl-lab.selector-acquisition <command> var/selector-plan-v1`.
Held-out/cold-boot refuse a changed source, image or bundle, require an accepted
selector, and require a process distinct from acquisition. They create fresh
model conversations and workers. No transcript is placed in the executable bundle.

The live authoring/acceptance path, real transfer, and real acquisition-inclusive
savings remain **IMPLEMENTED / UNVERIFIED**. The small panel is a mechanism pilot,
not statistical proof. Cold bundle restoration is unit-tested; a complete live
fresh-process transfer campaign has not run.

The principal research risk is that the constant composition or deterministic
guard already solves this distribution. That is a useful negative result, not a
reason to weaken the controls. The next selector experiment should use the frozen
mixed-contract panel with all five simple controls after the provider contract
and separate authorization are in place. It must not delay the independent Prime
comparison.
