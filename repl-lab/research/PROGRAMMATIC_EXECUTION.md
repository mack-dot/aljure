# Programmatic tool calling, executable learning, and the Prime Pareto challenge

**Status (2026-10-30):** offline implementation and preregistration. No live inference, no Docker
build and no held-out access happened for this document. Pilot 1b (`UNBLOCK_ACQUISITION.md` §8b)
is paused at P run 1, untouched. The acquisition pilot stays frozen and unauthorized.

Commits: `3fec260` (bridge), `16dffc0` (program artifacts), `532a299` (benchmark), this document.
Tests: 203 Clojure (`make test`), 44 Python (`test_python`), all offline.

## 1. Architecture comparison (Phase 1, source-grounded)

| Capability | Aljure before this work | Aljure now | Droid (Script tool) | Prime (pinned `c4c238c`) |
| --- | --- | --- | --- | --- |
| Program calls many tools, results stay out of the model window | None. Worker protocol was one request in, one value out (`worker.clj`); the model reached 5 native tools, one call per turn (`model_protocol.clj` `command-tools`, `disable_parallel_tool_use`). | Yes: `(tool "name" input)` inside SCI; only the program's final value returns (`programs.clj`, `bridge.clj`). | Yes: model-written JavaScript in a sandbox with no file/network/system access; only printed output returns, capped; full results logged for later search. | Yes: `python_repl` over a persistent CPython kernel with `host_request` events; skills callable from code (`research/PRIME_ARCHITECTURE.md`). |
| Bounded loops and conditionals | SCI `loop`/`if`; 10 s per expression, 256 MiB, 64 KB output, container killed whole (`isolation.py`). | Same bounds per compute segment between tool calls; plus operation budgets per program and per task. | "checks and loops run deterministically in code"; 5 min then output so far; ~1 h wait in background. | Kernel wall and memory limits. |
| Durable tool-result references | Design only (`ARTIFACT_PROTOCOL_DESIGN.md`). | Every operation's result hash and bytes are recorded (`:program-op`); results over 60 KB are refused with a "request a smaller slice" error. Handles remain design only. | Full results logged where the model can search them; `writeResult` file. | Files in the session workspace. |
| Controller-mediated side effects | Mailbox and staging only; no approval flow. | Effects are a tool class: need `approval "preapproved"` in the frozen grant and an idempotency key per call; a repeated key is not re-executed; an uncertain outcome is never retried. | Fixed inputs approved before the Script runs; run-time inputs ask when they run (changelog v0.236–0.237). | Native permission rules. |
| Parallel independent operations | None (`future`, `pmap` denied; one provider request in flight). | Sequential by design (requirement 5); the handler is one function, so a batched form can be added once sequential value is measured. | `Promise.all`, batches of 60. | Async `rlm.spawn`, effective concurrency 2. |
| Output aggregation | `aljure-show`, truncation, paged `done`. | Unchanged: a program's value is displayed like a `repl_eval` value. | Printed output capped; status line with wall time. | Printed output. |
| Executable artifact capture and validation | One-argument text classifiers only (`capture.clj`); rule v2; receipts. | Programs are artifacts (`:program` category, declared capabilities); validated on service fixtures through the real bridge; `program-rule-v1`. | Not documented: results persist, programs do not. | Skills and memory are model-edited files; no validation gate. |
| Cross-task program reuse and adaptation | Library preload of functions; `patch`/`compose`. | Programs preload like functions; `parameterize` lifts a pinned literal into a parameter (AST, parent pinned). | Not documented. | Skills (Python packages) and memory notes. |

Droid sources: factory.com/news/frontier-harness (2026-10-29), docs.factory.com/changelog. Its
published numbers are a 15% cost reduction on Opus 5.5 versus direct calling, concentrated in the
12.5% of scripts with six or more tool calls; its direct-call token figures are modeled, not
measured. Anthropic's API feature (`code_execution` + `allowed_callers`) reports −38% billed
input tokens on a 75-tool benchmark with no accuracy change and +8% cost on τ²-bench, with the
note that "sequential single-call workflows do not benefit" and that `allowed_callers` is not a
security boundary. Prime's source is not in this repository; the pinned image is built locally
from `var/upstream/prime-agent`; its programmatic execution is the Python kernel.

## 2. The bridge (Phase 2)

Mechanism. A request to the worker may carry a grant, `{:allow #{names} :max-ops n}`. Inside that
evaluation, `(tool "name" input)` prints one line `{:tool-request {:seq :name :input}}` on the
worker's only channel and blocks on the reply line, `{:tool-result v}` or `{:tool-error message}`.
The worker gains nothing: it still cannot read, write, connect or spawn (the deny list and the
container are unchanged); it can only ask. The supervisor (`scripts/isolation.py`) is unchanged:
each compute segment between requests keeps its 10 s wall bound, the wait for the controller
counts as idle, and each line keeps its 64 KB bounds. A request without a grant, which is every
request from every existing plan, makes `tool` throw before anything is written.

Controller. `isolation/request!` answers requests through a handler; `programs/operate!` is the
one authorization path for both a program's operations and the direct tools:

1. The tool must be in the registry (`programs/tools`, typed input keys) and in the plan's grant.
2. Budgets: per tool (`max_calls`), per program (`max_ops_per_program`, also enforced in the
   worker), per task (`max_ops_per_task`), per program wall time (`max_program_ms`), programs per
   task. Ceilings bound what a plan may authorize (`programs/ceilings`, `paired.PROGRAM_CEILINGS`).
3. Reads versus effects: an effect needs `approval "preapproved"` in the grant and an
   `:idempotency-key`. The controller keeps the key table: a repeat returns the first result
   without acting (`:deduplicated`); an outcome the service reported as uncertain is recorded and
   never repeated (`:uncertain-not-retried`); a rate-limited effect was not applied and may be
   retried under the same key.
4. Results over 60 KB are refused before they reach the worker (the supervisor would kill it).
5. Every request is an event: `:program-started`, `:program-op` (sequence, name, class,
   input hash, decision, status, error, elapsed, result bytes and hash, acted), `:program-finished`.
   The `:tool-call`/`:tool-result` pair around `program_run` records what the model saw.

Model surface (`aljure_contract.programs`): `program_run {source}` and/or the grant's tools as
direct one-operation tools. Without the switch, tool definitions and the worker protocol are
byte-identical to before. `done` with a direct answer stays available.

What is not built: parallel operations (requirement 6, deferred until sequential value is
measured), result handles, interactive approval (a benchmark run has no human; anything not
preapproved in the frozen plan is denied).

## 3. Code as data (Phase 3)

A program artifact is `(fn [...] body)` of category `:program` whose `:capabilities` are exactly
the tool names its body asks for (`program-library/make-program` refuses dynamic names and unknown
tools); identity is the envelope hash, exact code identity the code hash, and validation and
execution context are separate records naming it. `validate!` runs each case in a fresh service
seeded from its fixture through the real bridge and checks the value, the final collections and
that no operation went outside the declared capabilities. `program-rule-v1`: every case passes on
at least two distinct fixtures. Library versions hold programs with applicability predicates and
receipts as before (`skills.clj`); promotion and rollback are the existing content-addressed
versions. `parameterize` replaces one pinned literal subtree by a new parameter, on code data,
with the parent pinned.

Capture reads recorded `program_run` sources and never evaluates them. Quarantine reasons, each
of which blocks promotion: `:session-data`, `:unresolved`, `:literal-data-set`,
`:embedded-task-data` (a string literal equal to a record id of this task's fixture),
`:dynamic-tool`, `:no-tool-call`, `:too-large`. The known limits of the function capture
(whole-form local-name approximation, reader gensym renaming) are unchanged and still behind
`acquisition.experimental_capture`; program capture inherits the same free-symbol analysis and
is development-only until a live validation pass shows it semantics-preserving.

## 4. Threat model and authorization boundaries

- Unchanged: generated code runs only in the container (`--network none`, read-only, uid 65534,
  no capabilities, memory/pid/output/wall limits, killed whole); nothing is evaluated in the
  controller JVM; gold stays on the controller; a hash is never correctness.
- New boundary: the bridge channel. The worker can emit requests; the controller decides.
  Defense in depth: the worker checks the allow list and the per-program count before writing;
  the controller re-checks everything and is the only party that can act.
- Failure modes: malformed request line → worker error, program fails; handler exception → tool
  error to the program, recorded; oversized reply → refused, recorded; worker killed mid-program
  (wall, memory, output) → worker retired, "definitions are gone" as for `repl_eval`, every
  completed operation stays recorded and the idempotency table survives in the controller;
  controller crash → events are in SQLite up to the last operation; no effect is repeated on
  restart because no restart re-runs a program.
- Not a security boundary: tool descriptions, the model's idempotency keys (a model that changes
  the key re-acts; the budget bounds the damage, and every action is recorded), the synthetic
  service (it is in memory; "real third-party mutations" do not exist in this design).
- Proofs: `runtime.clj`, `external_task.clj`, `model_protocol.clj`, `executable.clj`,
  `skills.clj` and the worker image changed, so the isolation, SCI-contract, artifact-path and
  acquisition proofs in this checkout are stale and must be regenerated serially, after Pilot 1b,
  before any live use. A bridge section for the SCI-contract proof (a real-worker version of
  `programs_test`) is the first Docker-bound task.

## 5. Benchmark specification (Phase 4)

`benchmark/service_benchmark.py` generates seeded suites of an in-memory service (issues with
status, priority, assignee, age, parent; users with team). Families, each with a deterministic
expected answer and expected final state: `read` (hundreds of independent reads, paged 50),
`seq` (follow parent links), `cond` (close or reopen by a threshold), `bulk` (update many),
`verify` (update, then re-read and report), `fault` (two targets fail with a 500; report them,
never retry), `rate` (a rate limit every 7th call; retries required), `auth` (deletion is asked;
no tool can delete; the correct answer is `unsupported` and no change), `direct` (no service
access needed; optimum zero operations). Suite seed 1: 18 tasks, 9 families × sizes 120 and 240,
`suite_sha256 ed8142ec…`, scorer sha `5db280dc…` (the generator pins itself).

Scoring: official task success (exact answer after the last `Answer:` marker), correctness of
externally observable effects (final collections equal the expected state; missing and unintended
changes listed separately), model requests, input/output/cache tokens, API-rate-equivalent cost,
wall p50/p95, tool operations executed (ok, failed, denied, deduplicated, uncertain), effects,
controller operation time, direct versus program operations, and the family's optimum operation
count. `service_benchmark.report` reads recorded runs only.

Conditions: A conventional (`config/program-pilot-A.json`: direct tools, no program), B ephemeral
programs (`config/program-pilot-B.json`: `program_run` only), C exact reuse (a pinned library of
validated programs preloaded by applicability), D structural adaptation (C plus `parameterize`
and composition candidates validated before use), E native Prime. E cannot run yet: Prime's
pinned harness has no counterpart of the service tools; parity needs a Prime-side tool adapter
in the relay, which is not built, so every plan here is Aljure-only and says so.

## 6. Reusable-program experiment (Phase 6)

After B shows value: sequential families where a validated program from task k is applicable at
task k+j (same family, new seed), with unfamiliar schemas (renamed fields), changed requirements
(threshold or status changes: adaptation needed), compositions (verify after bulk), incompatible
tasks (`auth`, `direct`) and cold restarts (new process; library only from the pinned version).
Arms: B (ephemeral), C (exact), D (evolving). Evidence required, each from recorded events: the
artifact was captured from an earlier task's `program_run` source (source hash in the receipt);
validated on ≥ 2 fixtures (`program-rule-v1`); invoked on an unseen task (hash-attributed
invocation count); adaptation was necessary (C fails or declines where D's parameterized version
passes); fewer requests or higher success than B on the same tasks; acquisition plus validation
cost below the saving. Prime receives the same sequence with skills and memory enabled once the
adapter exists; until then no claim compares to Prime.

## 7. Projected cost and latency

Per task at Sonnet 5.5 rates, from Pilot 1 and 1b costs (about $0.04 per request-heavy task):
A about 10–40 requests per effect-heavy task (one per operation) → $0.08–$0.30; B 2–4 requests →
$0.03–$0.06; the pilot's 18 tasks × 2 runs × 2 arms ≈ $8–$14, capped at $5 per task and $90 per
run. The per-task cap is a ceiling, not an expectation: the gateway reserves the whole declared
1M context at the highest rate plus maximum output before every call (about $4.33), so a cap
below that admits no call at all (the first relay fixture on a $3 cap stopped with "Global provider
budget exhausted" before any request). Pilot 1b used the same $5 per-task cap. Latency: B adds controller operation time (sub-millisecond per in-memory operation) and
removes one model round trip per operation. These are projections, not measurements.

## 8. Pilot plan and GO/NO-GO (Phase 7)

Configs: `config/program-pilot-A.json`, `config/program-pilot-B.json` (Sonnet, subscription only,
no API-key fallback, Aljure-only, 18 tasks, two runs each preregistered). The plans are frozen
on suite `var/official/service-sim-s1` (`suite_sha256 ed8142ec…`, scorer `5db280dc…`) at the
clean commit `0c44178308ad9660cd4003fedba681305e76768a`. (A first freeze at `14c7571`, hashes
`1ce6d25b…` and `5ff64da6…`, was authorized and run: A run 1 failed on all 18 tasks before any
model call, because the task delivers its service fixture JSON-decoded with every key keywordized
and the loader rejected that shape. Spend $0. The failed run is kept as
`program-A-r1-failed-fixture-shape-20261101`; the fix and a report fix are in `0c44178`, with
offline tests for both.) A frozen plan binds the digest of every
tracked file, so the hashes are recorded here in the following commit and in
`research/evidence/program-pilot-freeze/` (`index.json` lists every file's SHA-256). Live runs
must execute from a checkout at the freeze commit, as Pilot 1b did; preflight at that commit was
`ready: true` for both plans with zero model calls. The suite is not tracked; a run checkout
regenerates it byte-identically (verified) with
`python3 -m benchmark.service_benchmark suite --out var/official/service-sim-s1 --seed 1 --per-family 2`.

| Plan | `plan_sha256` | SCI image | Prime image (unused, Aljure-only) |
| --- | --- | --- | --- |
| A, direct tools only | `9090d1c3f0c34fe2dda8c2d2b4a979af436d9a29a8c876dcd897099479e670f6` | `sha256:40f00364…c233f` | `sha256:f3e30aaa…446ad` |
| B, `program_run` only | `c67f6ab9b21fb87634a0b87e59e10e8885708a7059cf52bbc20052d79abbe888` | `sha256:40f00364…c233f` | `sha256:f3e30aaa…446ad` |

Both plans are `authorized: false`. The relay fixture (scripted transport control, zero inference)
passed its 15 checks on this image pair for the plans' shared transport contract
(`relay-fixture-report.json`). Two defects surfaced while freezing and are fixed in the freeze
commit: a task without a service fixture used to fail at start when the grant listed service
tools (now those tools are dropped from that task's grant and from its advertised tool list,
`programs/narrow`), and a per-task cap of $3 admitted no call (section 7). The worker image `40f00364…` is the first build that carries
`worker/src/repl_lab/bridge.clj`. Proofs regenerated on it, all `TESTED`: isolation (9 negative
cases), SCI contract, artifact path, acquisition, and the new bridge proof
(`python3 scripts/clj.py -m repl-lab.bridge-proof`, `var/bridge-proof.json`, 16 probes against the
real worker: grant, allow set, per-evaluation limit, refusal and handler-failure delivery, oversized
input and result, a 12 s tool wait that is not compute, a post-tool infinite loop that still ends
the worker, grant cleared after evaluation, no filesystem). The image is archived outside Docker
at `var/sci-image-recovery/bridge-40f00364/` with its SHA-256, so an image prune cannot erase this
plan identity (see `PILOT1B_INTERRUPTION.md` for why that matters). Frozen copies of the plans,
preflight outputs and proofs are in `research/evidence/program-pilot-freeze/`.

Running either plan needs the operator's authorization of the exact hash above
(`paired-run --authorize-subscription-plan <hash>`), one plan at a time, no other Docker-bound job
in parallel.

Preregistered decision on seed 1, two runs per arm, families pooled and reported separately:

- GO for programmatic execution if B's success and effects-correct rates are each within 0.05 of
  A's (or higher) **and** B's model requests are ≤ 0.5 × A's on the operation-heavy families
  (`read`, `cond`, `bulk`, `verify`, `fault`, `rate`) **and** B's cost per task is ≤ 0.75 × A's,
  with the per-run spread reported beside every mean.
- NO-GO if B loses more than 0.05 success or effects correctness on any family, or shows more
  unintended changes than A, or its request reduction comes only from `direct` and `auth`.
- Phase 6 starts only after GO. Nothing here is a win until measured live and reproduced.

**Outcome (2026-11-01, `PROGRAM_PILOT_RESULTS.md`): NO-GO under this rule.** Four runs completed
(72 rows, $1.29, accounting complete, zero unknown outcomes). B matched or beat A on success
(0.92 vs 0.81), final-state correctness (1.00 vs 0.94), requests on the operation-heavy families
(0.22×) and cost per task (0.26×), but one `fault` observation in B scored 0 on an answer-format
miss with a correct final state, which is a 0.25 family loss against the 0.05 tolerance. The rule
stands; the results document records the miss, a bulk answer-key defect in the generator and the
recommended next step (a second suite version with answer normalization defined before freeze).

## 9. What was not claimed

The bridge works end to end against the real isolated SCI worker (bridge proof, 16 probes) and
against the real controller with a fake worker over pipes (offline tests). No model has used it.
No request, token, cost or latency number in this document is a measurement. The benchmark is scripted
fixtures; it validates mechanisms and scoring, not value.
