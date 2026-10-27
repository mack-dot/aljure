# Progress

## 2026-10-26 — Initial inspection

Read the full attached master prompt. `/Users/mackianni/aljure` was empty.
`git status --short` reported no Git repository. No existing work was discarded.

Commands and evidence:

- `java -version`: Temurin 21.0.2.
- `node --version`: v24.3.0.
- `python3 --version`: 3.10.11.
- `clojure -Sdescribe`: CLI 1.11.3.1463.
- `rg --files ~/.m2/repository`: Clojure 1.11.3, data.json 2.5.0 cached;
  SCI and sqlite-jdbc absent.
- `curl -I --max-time 15 https://repo.maven.apache.org/maven2/org/clojure/clojure/1.12.0/clojure-1.12.0.jar`:
  failed with DNS resolution error (exit 6).
- `docker info --format '{{json .}}'`: failed, daemon socket access denied.

M0 documents and runnable scaffold added. No experimental model calls authorized
or made. No generated candidate source executed. Next: simulator, baselines,
invariant and replay tests; then feasible offline runtime and evidence work.

## M1 — Simulator

Implemented integer-time DAG simulation, heterogeneous capacities/speeds, hidden
actual durations, exogenous failures/recovery, delayed completion delivery,
attempt IDs and generation checks, bounded waits, infeasibility/deadlock/horizon
and event-budget outcomes. Added capacity-aware FIFO and critical-path estimate
baselines, permitted observations, raw action replay and final state hashes.

`make test` initially failed on an unmatched delimiter in `sim.clj:144`.
Fixed the delimiter. Re-ran `make test`: 7 tests, 339 assertions, 0 failures,
0 errors. This includes 30 generated worlds × 2 baseline policies, repeated runs,
per-transition invariant checks, and exact replay. This is tested evidence, not a
proof for arbitrary policies or all possible workloads.

SQLite runtime: Python 3.10.11 / SQLite 3.40.1. Added the storage bridge,
session/mailbox transactions, shared budget ledger, and structural artifact code.
These additions are not yet validated at this point in the log.

## M2–M4 — Offline runtime and evidence work

Added a bounded SCI worker and Docker supervisor, provider interfaces, a scripted
fixture adapter, and an Anthropic HTTP adapter. The worker image contains only its
fixed interpreter code. Generated code never runs in the controller. The Docker
negative suite returns UNVERIFIED (exit 2), because no worker image can be verified.
No real model call or generated-code execution has occurred.

Added durable session identities, parent links, resume/cancel states, peer
messaging, duplicate detection, transactional ack/effects, context handles,
budget reservation/reconciliation, and unknown provider outcomes after restart.
Added structural subtree patches with base/target hashes, immutable artifact
files, independent paired promotion, registry recovery and rollback operations.

`make test` passed at the intermediate runtime checkpoint: 14 tests, 381
assertions, 0 failures, 0 errors. Earlier compiler failures were an extra closing
parenthesis in `controller.clj:125`, extra delimiters in runtime tests, and an
unqualified `ProcessHandle` reference. Each was corrected before the passing run.

`make fixture-demo` created `var/runs/fixture-1793033138728/` with SQLite records,
48 episode EDN records and JSONL traces, a full report, and a whitelist export.
The no-change candidate was rejected. The developer-authored packing fixture and
workflow patch passed the fixed development rule. This is plumbing, not learning.

Measured fixture panel: 9/9 complete in each arm. Mean makespan in virtual ticks:
serial 209.5556; retained fixture 82.6667; FIFO 91.0; estimate baseline 81.2222.
`make replay RUN_ID=fixture-1793033138728` reproduced all 48 final state hashes.
`make cold-boot EXPORT=var/runs/fixture-1793033138728/export` launched a fresh JVM
and wrote `var/evaluations/eval-1793033266635/`. Retained fixture mean remained
82.6667; contract-compatible serial ablation mean was 209.5556. This checks a
fresh process resolving exact trusted fixtures. It does not test isolated SCI
loading or a fresh model conversation, so H2 remains untested.

## M5 — Local dashboard

Added React/TypeScript dashboard and a JSON-driven packager. `npm install
--offline --ignore-scripts --no-audit --no-fund` first failed (ENOTCACHED for scoped
package metadata). `node scripts/bootstrap-dashboard.mjs` then extracted 9 exact
packages from verified npm cache entries without modifying the global cache.
`npm install --package-lock-only --offline --ignore-scripts --no-audit --no-fund`
succeeded. `npm run typecheck` and `npm run build` passed.

`make demo RUN_ID=fixture-1793033138728` built
`dashboard/dist/index.html` from the recorded report and controller events.
The UI labels the run SYNTHETIC FIXTURE and shows the DAG, attempt timeline,
messages, policy input/output records, code/forms, promotion and rejection.
Headless Chrome screenshot attempt exited 134 under the restricted environment.
No screenshot or browser interaction check is claimed. A server-side render
check is being added. No site was registered, published, or deployed.

Next: finish command documentation, strengthen offline integration checks,
audit all milestone gaps, and complete real evaluation wiring where feasible.

## Verified checkpoint — 2026-10-26

Current successful fixture: `var/runs/fixture-1793035647201/`.
All 34 files listed in its source manifest still match their SHA-256 digests.
Source hash: `36bcb8b5131a028518cf969da22e67b8c1e778ed5a745e8b374a3e5d4106de80`.
The whitelist contains 2 artifacts and 1,235 executable payload bytes, plus its
manifest/audit. Per-artifact origin is retained; old session identities are not.

Final commands and observed results for this checkpoint:

```text
make doctor
  offline-ready=true; isolated generated-code execution unavailable
make test
  22 tests, 424 assertions, 0 failures, 0 errors
python3 -m unittest discover -s test_python -v
  4 tests passed, including actual SIGKILL before/after promotion commit and rollback
python3 -m py_compile scripts/clj.py scripts/store.py scripts/isolation.py scripts/demo.py
  exit 0
make fixture-demo
  fixture-1793035647201; one no-change rejection and one approved developer fixture
make replay RUN_ID=fixture-1793035647201
  48 episodes reproduced exactly
make evaluate EXPORT=var/runs/fixture-1793035647201/export PROFILE=heldout
  var/evaluations/eval-1793035917094; 9 retained + 9 fallback cases
make cold-boot EXPORT=var/runs/fixture-1793035647201/export
  fresh JVM; var/evaluations/eval-1793035924742; 9 retained + 9 fallback cases
make demo RUN_ID=fixture-1793035647201
  dashboard/dist/index.html built from the recorded data
cd dashboard && npm run typecheck
  exit 0
cd dashboard && node check-render.mjs ../var/runs/fixture-1793035647201
  rendered=true; 15,176 HTML bytes; 36 comparison cases
make isolation-test
  UNVERIFIED, exit 2; no verified local worker image
make evolve
  refused, exit 2; LIVE=1/model/cap were not supplied; no provider call
```

The final comparison and both fixture evaluations retain the measured means:
serial/fallback 209.5556, retained fixture 82.6667, FIFO 91.0, estimate baseline
81.2222 virtual ticks. All 9 cases complete in each comparison arm. Real LLM calls:
0. Scripted transport calls: 6. No model learning claim is supported.

Additional fixes and tests in this checkpoint:

- Enforce event budgets inside action batches and waits, with replayable limits.
- Bound reader nesting and reject reader-time evaluation/discard syntax. A final
  fixture attempt exposed rejection of valid `#:mvn` dependency maps. That run
  failed with `Reader dispatch denied`; the files were preserved. Added a specific
  namespaced-map regression test and reran successfully.
- Restore exported dependency graphs with consistent fresh hashes and preserve
  developer/model provenance. Verify the resulting artifacts and references.
- Add equal per-case frozen/evolving final orchestration. Frozen tasks can select
  temporary executable policies; a test confirms they do not cross task boundaries.
- Add distinct sealed final and cold-boot splits, source/model/image consistency
  checks, operator cost accounting, and bounded provider-body reads. These live
  paths are not validated against a real provider or SCI worker.
- Expose sanitized development trace handles. Hidden world state/hashes remain
  outside learner context records.

## Remaining work at the previous checkpoint — superseded below

The full learning demonstration is not complete. Preserve these requirements:

1. Finish the live experiment recording path. Development calls currently persist
   bounded learner trace records and controller metrics, but still need complete
   evaluator-only episode files for the general replay command. Failure-only real
   evaluation records also need explicit replay support.
2. Complete the frozen acquisition arm and compare its accounting with evolving
   acquisition. Final paired arms have equal caps and tool access; the current
   `evolve` command only runs the evolving acquisition loop.
3. Normalize real-model reports for the dashboard. The current demo packager/UI
   is verified against fixture reports. Add a recorded budget-exhaustion fixture
   to the presentation path, with clear provenance.
4. Verify SCI positive/negative tests on a machine with Docker access and the
   pinned dependencies. Then verify an actual recursive child model call and the
   end-to-end live path only with explicit credentials, rates, and a spending cap.
5. Run the capped H1/H2 experiment and compatible ablation when authorized.
   Report improvement, regression, or no effect. Browser interaction QA is also
   unverified because headless Chrome exited 134 in this environment.

No goal-complete claim has been made. The next safe work is items 1–3; they do not
require paid calls. The highest-value later experiment is a capped real-model
frozen/evolving comparison with an actually invoked workflow change, followed by
the separate cold-boot panel and fallback ablation.

## 2026-10-26 — Matched acquisition and recording checkpoint

Implemented complete evaluator-only development records, explicit pre-execution
failure replay, recursive task-directory replay, and evaluation artifact copies.
Added one shared acquisition runner for both arms, fresh task stores, equal
non-transferable allowances, approved-code retention only in evolving, per-task
cost aggregation, restart checkpoints, unknown-charge preservation, and final-seal
resume refusal. Added direct code-removal and deterministic baseline paths to live
evaluation. Actual SCI/provider integration remains unverified.

The runtime now retains a completed child's mock SCI worker across resume until
the root task ends. Cancellation/failure releases it. Added strict provider-response
playback with original usage kept separate from zero new charges. Bundle export
now publishes a complete directory atomically. Manifests record Git HEAD and dirty
state; a Git repository now exists at the workspace parent.

Normalized dashboard reports for acquisition and final records, missing costs,
failed cases, and arbitrary recorded arms. Added an actual one-call budget refusal
as an explicitly staged fixture. Added per-arm server-render checks. Initial
parallel render checks shared temporary files and therefore did not independently
validate both reports. Fixed the checker to use a unique directory per invocation
and resolve its paths from its own file. Re-ran the evaluation render independently.

Commands and observed evidence:

- `make test`: 28 tests, 617 assertions, 0 failures, 0 errors.
- `python3 -m unittest discover -s test_python -v`: 7 tests passed, including
  actual process-kill promotion recovery.
- `python3 -m py_compile scripts/clj.py scripts/store.py scripts/isolation.py scripts/demo.py`: passed.
- `npm run typecheck`, `npm run build`: passed in `dashboard/`.
- `make fixture-demo`: latest completed fixture `fixture-1793037849143`.
  All four comparison arms complete 9/9; mean virtual makespans remain serial
  209.5556, retained 82.6667, FIFO 91.0, estimate 81.2222. One additional failure
  is the staged budget test; it is outside the paired performance panel.
  Real model calls 0; scripted transport calls 7, including the budget fixture.
- `make replay RUN_ID=fixture-1793037849143`: 49 episodes reproduced exactly.
- `make evaluate EXPORT=var/runs/fixture-1793037694217/export PROFILE=heldout`:
  `var/evaluations/eval-1793037850098`, 9 retained plus 9 compatible fallback cases.
- `make replay RUN_ID=eval-1793037850098`: 18 episodes reproduced exactly.
- `node dashboard/check-render.mjs var/evaluations/eval-1793037850098`:
  rendered all 18 cases' two arm views; 15,272 bytes in the default HTML view.
- `make cold-boot EXPORT=var/runs/fixture-1793037849143/export`:
  fresh JVM wrote `var/evaluations/eval-1793038970992`; 9/9 complete in both panels,
  retained mean 82.6667 versus fallback 209.5556. H2 is still untested.
- `make demo RUN_ID=fixture-1793037849143`: local dashboard built from that record.
- `make doctor`: offline ready, no configured immutable worker image.
- `make isolation-test`: UNVERIFIED, exit 2. No negative generated-code test ran.
- `make evolve`: refused, exit 2, without LIVE/model/cap. No provider request.
- `git diff --check`: passed at this checkpoint.

Intermediate test code had a misplaced parenthesis in two lexical scopes; both
were fixed before the passing suite. A dashboard-check command used the wrong
working directory; the checker now handles either project or dashboard cwd.
No existing run was deleted or relabeled as a real model result.

## Continued audit after the user's “keep going” instruction

Found that Docker worker removal status was ignored. Added checked cleanup, a
persistent quarantine marker on failed/uncertain removal, and `make isolation-recover`
for only recorded REPL Lab container names. Added tests for failed removal, timeout,
verified absence, and invalid targets. `python3 -m unittest test_python.test_isolation -v`:
6 tests passed. These are mocked control tests, not actual container isolation tests.

Added worker output serialization checks, a persistent-binding positive control,
stdout/stderr draining at process exit, and enforced/configured limit comparison.
These source changes occurred **after** the fixture checkpoint above. Its source
hash identifies that historical implementation, not the current working tree.
A targeted limits test initially had a shell/Clojure quoting error; the corrected
command uses `(var ...)` and is being checked. Full verification of these latest
changes is pending. No real SCI execution or paid model call has occurred.

Remaining useful local work: finish the worker/provider audit, test the real-provider
adapter through mocked HTTP, inspect runtime subagent orchestration and interruption
behavior, then regenerate and verify a final source-matched fixture. The external
SCI image, actual recursive model call, capped H1/H2 run, and browser interaction QA
remain unverified. The full goal remains active.

## Continued validation results

- `make test`: 34 tests, 657 assertions, 0 failures, 0 errors.
- `python3 -m unittest discover -s test_python -v`: 11 tests passed in 19.093 s.
  The new transport test uses real host pipes and a fixed Python fixture. It does
  not evaluate generated source or substitute for an SCI isolation test.
- Provider-only mocked HTTP suite: 4 tests, 33 assertions, all passed. It checks
  reservation before token counting, actual-usage reconciliation, unknown outcomes,
  model mismatch, no retry, and no HTTP dispatch after budget rejection.
- Nested subagent transport test: 1 test, 5 assertions, all passed. A depth-two
  child sends an acknowledged message to the first subagent without root copying.
- Trusted worker source reader check: 4 top-level forms parsed. SCI execution is
  explicitly not tested by this check.
- `make isolation-recover`: cleanup-confirmed for 0 containers; isolation tests
  still required. No actual container removal was performed.
- Read-only `docker info --format '{{json .}}'` again failed with daemon socket
  access denied. SCI's Maven cache directory is still absent.
- `git diff --check`: passed.

The per-case fixture audit adds a useful limit to the mean comparison: the
estimate-aware baseline ties the retained packing fixture on 6 cases and beats it
on 3. The retained fixture beats that baseline on none of the 9 cases. The three
specified shift cases are all ties. This is a fixture result, not a model-learning
finding or evidence for language superiority. A large gain over serial alone is
an insufficient success criterion for the later experiment.

Final current-source fixture generation is running. Once it finishes, verify its
manifest, replay, cold-boot export, and all dashboard arm views. Then preserve the
exact resulting IDs here. External SCI/provider/browser gates remain unchanged.


## Final source-matched offline checkpoint — 2026-10-26

Latest run: `var/runs/fixture-1793040314818/`.
All 35 source files match the manifest. Source hash:
`b6ae8b871e12503c33674d30f068b45677c6278119e58cfc17aa47ca09eb5393`.
Recorded Git HEAD: `3b905ffd70f04e30181d83545086b008c2e2e116`; dirty=true.
The final UI correction resets the case selector when changing arms.

- `make test`: 35 tests, 664 assertions, 0 failures, 0 errors.
- Added and ran the direct removal/failure-record test afterwards: 1 test,
  6 assertions, 0 failures, 0 errors. No runtime source changed for that test.
- `python3 -m unittest discover -s test_python -v`: 11 tests passed.
- `npm run typecheck`: passed after the final UI correction.
- `make fixture-demo`: produced `fixture-1793040314818`; 36 paired comparison
  cases plus the separate staged budget-exhaustion case. All comparison arms
  complete 9/9, with the previously reported means unchanged.
- `make replay RUN_ID=fixture-1793040314818`: 49 episodes reproduced exactly.
- `make cold-boot EXPORT=var/runs/fixture-1793040314818/export`: fresh JVM wrote
  `var/evaluations/eval-1793040408757`; 9 retained and 9 compatible fallback
  cases completed. Means: 82.6667 and 209.5556 virtual ticks respectively.
- `make demo RUN_ID=fixture-1793040314818`: built the local dashboard from that
  recorded run. No site was registered, published, or deployed.
- A source-manifest assertion confirmed all 35 current source hashes, HEAD,
  and dirty status above. Reader-only parsing found all 4 worker top-level forms;
  that check does not establish SCI compilation or execution.

The paired final-control test now passes: identical normalized libraries produce
identical model inputs, equal usage, and the same simulator final hash. No retained
change therefore gives zero paired score difference in this scripted test.

Outstanding external evidence remains: actual SCI positive/negative tests, actual
provider integration and recursive model calls, a capped H1/H2 run, and browser
interaction QA. No real model has produced a retained skill or changed a harness.
No model benefit has been shown to survive cold boot. The full learning goal is
not marked complete. M6 remains deferred. The highest-value next experiment is
the matched real-model acquisition/final/cold-boot protocol after isolation passes,
with literal/bundle audit and compatible removal, using an explicit operator cap.

Final follow-up checks completed:

- `make replay RUN_ID=eval-1793040408757`: all 18 cold-boot/fallback episode
  records reproduced exactly.
- `node dashboard/check-render.mjs var/runs/fixture-1793040314818`: passed for
  all five arm views, including budget exhaustion; 37 displayed cases and
  21,504 bytes in the default HTML view.
- `node dashboard/check-render.mjs var/evaluations/eval-1793040408757`: passed
  for both arm views; 18 cases and 15,272 bytes in the default HTML view.
- Final `git diff --check`: passed. Changes remain local and uncommitted.

The next executable gate is `make isolation-test` after Docker access and a pinned
worker image are available. Then use the explicit live commands in README with
credentials, verified rates, a pinned model, and positive operator caps. No such
cap or credentials have been supplied in this session. Do not bypass isolation,
substitute host eval, or report scripted tests as real learning. No work was pushed
or deployed, and no paid request was made.

## Goal continuation — budget and persistence audit

Classified the previous goal turn as progress: it changed implementation and
produced verified replay, parity, recovery, and presentation evidence. Re-read the
entire master prompt and inspected the current worktree and acceptance audit.
Added a requirement/evidence map for prompt sections 1–16, the six simulator
invariants, the nine lifecycle steps, cold-boot requirements, and every required
command. Actual SCI/model/browser gates remain open.

The audit found two required budget gaps. Policy runners hard-coded 10,000 events,
and active HTTP/worker operations could outlive the controller's task deadline.
Added `limits.clj`, explicit execution options, one absolute task deadline, bounded
HTTP phases, deadline propagation to the worker supervisor, and monotonic remaining
worker lifetime. Late policy responses cannot dispatch actions. Partial wall-budget
outcomes stay scored and replayable. The configured event limit now reaches
learning, development, final, fixture, and direct-code runners. Experiment version
is now 3; older snapshots remain historical evidence.

Also fixed idle worker lifetime: a completed expression no longer starts another
10-second execution timer while the model thinks. Idle bindings survive until the
shared task/session deadline. A real host-pipe test delays the second request past
the expression timeout and receives both responses. Its process is a fixed Python
fixture, not SCI and not generated code. All generated execution still fails closed
without the verified worker image.

Observed checks:

- `make test`: 41 tests, 689 assertions, 0 failures, 0 errors.
- `python3 -m unittest test_python.test_isolation -v`: 9 tests passed, including
  remaining-deadline and idle transport checks.
- `python3 -m unittest discover -s test_python -v`: the final updated suite passed
  all 13 tests in 15.671 seconds.
- `python3 -m py_compile scripts/isolation.py`: passed.
- `git diff --check`: passed.

Task execution stops at the deadline. Bounded cleanup and durable failure recording
may continue afterwards and are included in observed wall time. This is stated in
the protocol; it does not authorize extra inference or generated-code execution.
A new source-matched fixture completed for version 3. No real provider request,
new infrastructure, publication, or deployment occurred.

## Version 3 checkpoint and Prime/OOLONG readiness review — 2026-10-26

`fixture-1793041669070` completed with the same nine completed cases per comparison
arm and unchanged makespan measurements. All 36 current source files match its
manifest. Source hash:
`e5cd0346cc23650d7b1671233360e50f6d4cefa677c1c988928f8dde48101426`.
Recorded-action replay reproduced all 49 episodes. Fresh-process cold boot wrote
`var/evaluations/eval-1793041900279`, with nine retained and nine fallback cases
complete. Their mean makespans remain 82.6667 and 209.5556 virtual ticks.

`make demo RUN_ID=fixture-1793041669070` rebuilt the local dashboard. Server
rendering passed for all five arm views: 37 displayed cases, 21,504 bytes in the
default view, and explicit SYNTHETIC FIXTURE provenance. Browser interaction QA
remains unverified. Cold-boot replay reproduced all 18 episodes. Its two arm views
also passed server rendering: 18 cases and 15,272 bytes in the default view.
`git diff --check` passed.

The user asked how close this implementation is to a ten-case OOLONG comparison
with Prime Agent. A read-only GitHub check found the implementation on `main`
under `repl-lab/`, including its README. Root-level README/dependency 404 responses
do not show that the repository is empty. The latest local changes remain
uncommitted and were not pushed during this work.

The current application is a scheduling experiment. It has no OOLONG task adapter,
OOLONG scorer, Prime adapter, or `aljure bench` command. The only implemented live
provider is Anthropic Messages. Existing controller ledgers, traces, snapshots,
fresh-task stores, and reports can support a new benchmark integration, but do not
establish cross-harness parity. Zero real paired benchmark cases have run. The
SCI/provider gates still apply to real Aljure execution. The current fixture
retained policy does not beat the estimate baseline; it is developer-authored,
so it provides no evidence of model learning or language superiority.

Prime's official blog reports 0.940 for OOLONG Yahoo at 128k with GPT-5.6 Sol
(high), not an unspecified OOLONG sample. A reproduction needs a pinned protocol
and matching provider settings. Its old `packages/coding-agent/docs/json.md` URL
returned 404 on this check; current repository structure has changed. Pin and
verify the selected Prime release's CLI and all-session usage records before
building the adapter. The OOLONG repository documents an inference entry point;
it does not provide an adapter to this Aljure implementation.

Sources checked: https://github.com/mack-dot/aljure/tree/main/repl-lab,
https://www.primeintellect.ai/blog/prime-agent,
https://github.com/PrimeIntellect-ai/prime-agent,
https://github.com/abertsch72/oolong.

## Provider process-crash audit — 2026-10-26

The preceding goal turn made progress: it completed the version 3 fixture,
fresh-process evaluation, replay, source checks, and benchmark readiness review.
Re-read the full master prompt before this continuation. The original scheduling
H1/H2 goal remains active; the Prime/OOLONG status question did not replace it.

Added a test-only provider crash probe and a Python process test. The test sends
SIGKILL to the actual controller process group at four boundaries, for both root
and child requests: after durable reservation, after scripted dispatch, before
response commit, and after response commit. A fresh JVM then invokes the normal
`recorded-or-new-task!` recovery path. No production runtime source changed.

All eight cases passed. Uncommitted outcomes retain the complete token/dollar
reservation and become unknown. A committed response remains charged exactly
once. Recovery cancels interrupted sessions, records the task as failed, makes no
new provider or policy call, preserves parent links, and writes a checkpoint.
Repeating resume leaves the ledger unchanged. Recorded-action replay reproduces
the failure episode. Unknown responses cannot be played back; committed ones can.
All usage in this test comes from fixed synthetic responses, not real inference.

Exact checks:

- `python3 -m unittest test_python.test_provider_recovery -v`: one test with
  eight process-crash subcases passed in 34.476 seconds.
- `python3 -m py_compile test_python/test_provider_recovery.py`: passed.
- `git diff --check`: passed.
- `make doctor`: controller offline-ready; worker not ready because no local
  immutable worker image ID is configured. Java 21.0.2 and Clojure 1.11.3.
- `docker info --format '{{.ServerVersion}}'`: failed with permission denied on
  `/Users/mackianni/.docker/run/docker.sock`; daemon access is still unavailable.
- A direct loopback listener probe failed with `PermissionError: [Errno 1]
  Operation not permitted`. The new tests therefore use scripted transport;
  they do not claim to validate network failures or the real provider service.

Only tests and documentation changed. The version 3 runtime source snapshot and
fixture results above remain applicable. No model-generated skill, harness change,
or surviving model benefit exists yet. Actual SCI isolation and a capped,
explicitly authorized live learning/evaluation/cold-boot protocol remain necessary.

## Execution access audit — 2026-10-26

The previous turn made concrete progress by adding and passing eight provider
process-crash cases. Re-read the full original goal and inspected the current
acceptance map, worker, supervisor integration, image recipe, and dashboard checks.
No further required offline implementation change was identified in this audit.
The original M2–M4 live requirements and M5 browser interaction check remain open.

Current checks:

- `make isolation-test`: exit 2, UNVERIFIED; no local immutable worker image ID
  is configured. None of the negative SCI cases ran.
- `docker info --format '{{.ServerVersion}}'`: exit 1, Docker socket access denied.
- `node --check dashboard/check-render.mjs`: passed.
- The current runtime source matches all 36 files in the version 3 fixture
  manifest, hash `e5cd0346cc23650d7b1671233360e50f6d4cefa677c1c988928f8dde48101426`.
- Tool discovery found no available local browser automation tool. No site was
  created or published as a workaround for local browser access.

The same execution/access condition remains across the readiness review, provider
crash-test turn, and this turn. The earlier turns made useful offline progress;
this turn reached an impasse. Repeating fixtures cannot establish actual SCI,
provider, recursive-model, acquisition, held-out, or cold-boot model behavior.
The full goal is not achieved.

Requested the missing execution environment and explicit live settings through
the user-input tool: working Docker plus a local pinned worker image; exact
Anthropic model; verified input/output prices; separate acquisition, held-out, and
cold-boot spending caps. Credentials must be configured privately in that
environment. No inference request is authorized by this audit. Resume the live
validation path after these conditions change, starting with `make isolation-test`.

## Requested Sonnet 5.5 sequence — 2026-10-26

The user selected `claude-sonnet-5-5` at $2 per million input tokens and $10 per
million output tokens. Anthropic's official model page confirms both the API ID
and these standard prices. The proposed caps are acquisition $15, held-out $10,
cold boot $10, total $35. The user explicitly withheld spending authorization
until later approval and private credential configuration. No paid call occurred.

Current preflight: Docker context is `desktop-linux`, but its socket remains
permission-denied. No worker image ID or provider credential is configured, and
the pinned SCI jar is not cached. `make isolation-test` returns UNVERIFIED with
exit 2; none of its actual worker cases ran. Requested a Docker-enabled execution
environment through the user-input tool. No permission setting was changed.

Prepared concrete next steps while awaiting access:

- Added `make smoke`. It requires a complete negative-test proof for the same
  worker image before inference. It checks an external context query, root SCI
  transformation, real child call with that selected context, child SCI result,
  parent consumption, final answer, and successful runtime completion. Its
  verifier uses ordered events and provider receipts, not agent claims.
- Smoke preserves a manifest, context, controller ledger, complete broker results,
  generated expressions, report, and known/uncertain usage. It has no learning or
  promotion capability. A successful smoke would not establish skill learning.
- Unified the proof gate across smoke, acquisition, resume, and final/cold
  evaluation. Resume and evaluation previously checked readiness without
  revalidating all negative-test results. Offline tests now cover each entry point.
- Added durable broker results/errors linked to call sequences. Bumped the fixed
  experiment version to 4 and included `.dockerignore` in the source manifest.
- Added an inert spending proposal. Proposed smoke allocation is $1 within the
  $15 acquisition category, leaving $14 for equal frozen/evolving acquisition
  allowances. This allocation remains unapproved; the file enables no execution.
- Added host-terminal Docker setup commands using an official Clojure/JDK 21 tag,
  resolving its immutable digest before build. `.dockerignore` restricts build
  context to worker inputs. Actual build and negative tests remain unverified.

Checks so far:

- Initial `make test` found an extra closing parenthesis in the new smoke test;
  corrected it. Runtime namespaces loaded successfully.
- `make test`: 44 tests, 713 assertions, zero failures and zero errors.
- `make smoke` with no flags: exit 2, paid calls disabled, as required.
- Added a final smoke cleanup-failure rejection check after the full suite;
  targeted smoke tests passed: 3 tests, 26 assertions, zero failures/errors.
- `make fixture-demo`: wrote `fixture-1793043550408`; all four comparison arms
  completed 9/9 synthetic cases with unchanged scheduling measurements.
- Source assertion: all 39 current files match that fixture's version 4 manifest,
  hash `60f0eb2623363acc72eb1b9005222926ffc7650876179f2d88bfb5a089eb3fab`.
- `make demo RUN_ID=fixture-1793043550408`: rebuilt the local recorded dashboard.
  Nothing was published.
- `make replay RUN_ID=fixture-1793043550408`: all 49 recorded episodes reproduced
  exactly; no provider rerun.
- `git diff --check`: passed.

The same model and equal per-task allowances remain required in both conditions.
The next executable gate is still actual Docker/SCI isolation, followed by explicit
cap approval and private credentials, then the live smoke. No fixture result is
being used as evidence of learning. Earlier source snapshots remain historical.

## Local Docker setup request — 2026-10-26

The user asked to set up local Docker. Docker Desktop 4.48.0 is installed at
`/Applications/Docker.app`; its configured executable exists. The Docker client
is 28.5.1 on darwin/arm64, with `desktop-linux` selected. Both the user socket and
the `/var/run/docker.sock` symlink exist. This session still receives `operation
not permitted` when connecting to the socket, so daemon health is unverified.

Attempted `open -a Docker` and opening the full application path. Launch Services
could not launch the app from this session. `docker desktop status` could not
write its host log or retrieve status. No permissions or Docker configuration
were changed; no other containers were stopped or removed.

Added `make worker-setup` backed by `scripts/setup_worker.py`. In a Docker-enabled
host terminal it checks daemon access, pulls the official versioned Clojure/JDK 21
base tag, resolves a repository digest, builds the worker against that digest,
and runs the actual SCI positive control plus all nine negative cases. It archives
an old proof before testing and writes `var/worker.env` only after a complete proof
matches the built image. It writes stage/result metadata to `var/worker-setup.json`.
It contains no model invocation and needs no provider credential.

Observed checks:

- `make worker-setup`: exit 2 at `docker-access`, before pull/build/test. The local
  report records FAILED and the daemon permission error. Actual isolation remains
  UNVERIFIED.
- `python3 -m unittest test_python.test_worker_setup -v`: four mocked control-flow
  tests passed in 0.014 seconds. They cover inaccessible Docker, immutable base
  selection, failed test recovery without stale proof reuse, and incomplete proof
  rejection. They do not establish Docker or SCI behavior.
- `python3 -m py_compile scripts/setup_worker.py`: passed.
- `git diff --check`: passed.

Next user-side action: open Docker Desktop in the Mac host session and run
`cd /Users/mackianni/aljure/repl-lab` followed by `make worker-setup` in Mac Terminal.
The saved result can then be inspected in this shared workspace. Paid caps remain
unapproved, credentials remain private, and no model call has been made.
The setup helper and Make target change the source snapshot; prior fixture
manifests remain historical. The experiment runtime and scoring did not change.

## Actual host Docker/SCI verification — 2026-10-26

The user ran `make worker-setup` in the Mac host terminal and supplied the complete
successful output. Inspected the shared saved files directly. `worker-setup.json`
reports TESTED/complete, Docker server 28.5.1, and zero model calls. Its worker image
matches `isolation-proof.json` and the validated image value in `worker.env`.

- Base: `clojure@sha256:a84f36632b6acd1ff8c127ecaf13745aeaed10a5f444425b57c3de733c3d3640`.
- Worker: `sha256:508f6f195f8837324f2c52ec87b193eb7fc79334de8948ff300b8585df03b37a`.
- Actual SCI positive control passed: two expressions retain `offset` and return
  nil, then 42. This is required before the test script can write TESTED.
- All nine negative results are exactly true: loop, allocation, oversized-result,
  read, write, process, network, evaluator, and reader-eval.
- No isolation-quarantine markers remain. The proof and setup metadata agree.

This satisfies the actual worker test gate for that image within the suite's
bounds. It does not establish real model integration, learned skills, or H1/H2.
Updated current README/acceptance/demo/threat-model statements to reflect this
new evidence; historical failed attempts remain recorded above.

No credentials are available in the assistant process, and this session still
cannot access Docker directly. Live execution must use the Docker-enabled host
terminal unless the execution environment changes. Requested explicit approval
for either the $35 staged plan ($1 smoke, $14 acquisition, $10 held-out, $10 cold
boot) or only the $1 smoke. No approval is inferred from successful Docker setup.
Private credential setup is also required. No paid provider request was made.

## Prime comparison priority and smoke authorization — 2026-10-26

The user affirmed the plan to run one $1 smoke attempt, build the Prime/OOLONG
comparison, then complete one matched pair before expanding to ten. The remaining
spending is on hold. This is not approval to run the former $35 scheduling-only
plan. Updated the inert scope record before any smoke run could start.

The supplied credential display was masked/truncated and is not usable. Did not
copy the displayed token or account metadata into project files. No full provider
credential is available to the assistant process. The operator must configure it
privately in the Docker-enabled host terminal. No additional approval is required
for the already authorized single smoke attempt; no automatic paid retry is allowed.

The worker proof remains verified. Next offline work is the independent benchmark
controller, official OOLONG task/scoring integration, and a pinned Prime adapter.
No head-to-head result exists yet. Benchmark infrastructure will remain outside
the fixed scheduling runtime while the operator can run the smoke command.

## Authorized SPM credential search and external scorer — 2026-10-26

The user explicitly authorized locating and reusing SPM's existing Claude API
configuration. Read the local SPM policy and current workflow. The workflow uses
`anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` at lines 202, 305, 408, and
511 of `.github/workflows/agent-review.yml`. This is a secret reference, not its
value. Its review model is Opus; the Aljure smoke remains pinned to the requested
Sonnet model. No SPM file or GitHub configuration was changed.

Checked 247 candidate configuration files across 15 local SPM checkouts. Checked
the usual local shell and Claude configuration locations separately. No usable
Anthropic key was found. The assistant process has no configured API key.
Search output contained paths/counts only, not secret values. GitHub's official
Actions secrets REST documentation confirms that read endpoints return metadata
without the secret value. Requested only the path of any separate private copy;
the user can instead enter the key privately in the host terminal. The one-smoke
authorization persists. No additional paid scope is inferred.

Added `benchmark/` outside the frozen scheduling-runtime source paths. It contains
the pinned official OOLONG synthetic scorer and MIT license, a deterministic
local-export importer, checksummed public inputs separated from controller-only
gold records, individual-provider-call accounting, and an independent paired
comparison CLI. Unknown calls retain reservations; unpriced cache usage gives
unknown total cost. Parent aggregate usage is rejected to avoid counting Prime's
child usage twice. Reports include failed outcomes and reject incomplete pairs,
changed inputs, unequal budgets/model settings, changed frozen harness revisions,
and reused provider receipts. Fixtures remain explicitly labeled.

The local-export importer cannot authenticate dataset origin and says so. No
official dataset download or real head-to-head run has occurred. Native live
adapters and their shared spending enforcement remain unimplemented; the package
does not present itself as paid-execution ready. Prime and OOLONG source revisions
and the dataset HEAD obtained by `git ls-remote` are recorded in the lockfile.
Direct Python HTTPS access to Hugging Face failed DNS in this sandbox; no alternate
network route was used to download the dataset.

`python3 -m unittest test_python.test_benchmark -v`: 9 tests passed (0.238 s).
These cover scoring semantics, deterministic hidden-answer preparation, root/child
accounting, uncertainty, complete paired reporting, tampering, settings mismatch,
and receipt reuse. They are software tests, not evidence of model performance.
No smoke report was present when checked. No paid model request was made by the
assistant. The actual Docker/SCI gate remains passed for the previously recorded
image; it has not been bypassed.

Final external-scoring check: 10 tests passed in 0.491 seconds after adding the
known-spend plus unresolved-reservation budget check. `python3 -m benchmark
--help` loads successfully. The vendored scoring function bodies match the pinned
upstream text exactly. `git diff --check` passed. No runtime source in the smoke
manifest was changed by this benchmark work, and no smoke report is present.

## Subscription smoke adapter and host-access boundary — 2026-10-26

The user selected use of their Claude subscription and reported successful
`claude auth login --claudeai` in the host terminal. Official Anthropic guidance
currently supports personal subscription usage through the unmodified CLI/Agent
SDK. The existing Aljure adapter was direct-API-only, so added a separate bounded
subscription transport for the capability smoke. Other paid phases remain held.

Implemented `scripts/claude_subscription.py`, `src/repl_lab/subscription.clj`,
and `make smoke-subscription`. Version 2.1.310 is required. The local binary hash
was `ffb64331bc0ee1b69efb7c2c428bd3ab516bc31b75bf60886b356c97c1c25ffd` and is
pinned in each run's manifest and checked before each call. The helper uses normal
subscription login without reading or copying token values. Its environment
excludes inherited API keys, cloud credentials, endpoint overrides, and preload
hooks. The CLI has no native tools, MCP servers, or custom skills; all generated
Clojure remains with SCI. Each logical model call uses a fresh CLI process with
the explicit controller history. Parent and child share the durable reservation.

Preserved streams include the request, CLI configuration/system prompt, assistant
blocks, partial stream events, final result, and bounded stderr. Official SDK
documentation identifies per-assistant output tokens as placeholders and permits
multiple blocks sharing one message ID. The parser therefore deduplicates the ID,
checks final input/cache totals and stream output totals, and rejects additional
model calls or tool access. CLI and controller failures retain uncertain charges;
known consumption is recorded before a failed response is rejected. No retry is
performed by the controller, and the pinned CLI is configured for zero retries.

The dollar cap is an API-rate-equivalent budget for subscription runs. Actual
subscription charges are unknown, not zero. CLI cost fields and budget thresholds
are estimates and cannot establish an invoice-level spending guarantee. Reports
make this distinction explicit. The added CLI runtime must be controlled in any
eventual Prime comparison. This is capability plumbing, not learning evidence.

Validation:

- `python3 -m unittest test_python.test_claude_subscription -v`: 9 tests passed in
  0.664 s. They include actual pipe/supervisor tests with a local fixture emitter,
  timeout cleanup, auth selection, credential stripping, isolation refusal, and
  output-accounting edge cases. No real model is involved in these tests.
- `make test`: 48 Clojure tests, 751 assertions, zero failures/errors. New tests
  cover shared root/child accounting, unknown outcomes, known failed consumption,
  reservation overruns, and stopping before CLI dispatch on insufficient budget.
- `python3 scripts/claude_subscription.py doctor`: exact CLI version/hash found,
  but `loggedIn:false`, `authMethod:none` from this sandbox; zero model calls.
- `source var/worker.env && make smoke-subscription LIVE=1
  MODEL=claude-sonnet-5-5 MAX_USD=1`: exited 2 at actual isolation preflight,
  `Docker daemon is unavailable or denied`. It did not reach model inference or
  create a smoke run. The existing host SCI proof has not been bypassed.

The user explicitly authorized enabling Docker access in this session. A targeted
escalation request for read-only `docker info` was rejected by the execution
policy: `sandbox_approval:false`. No runtime permission-changing tool is exposed.
The OpenAI Docs skill was used to verify the supported app permission controls.
The user must select an appropriate permission mode in the application before
this agent can request Docker access. No socket permissions, Codex policy files,
or sandbox controls were changed. Host execution remains a supported alternative.

Source changes in this section update the runtime snapshot; a new smoke manifest
will record them. The SCI worker image is unchanged. All live capability, learning,
held-out, cold-boot, and Prime comparison results remain unverified.

## First successful live subscription smoke — 2026-10-26

Full session access resolved the earlier Docker and login blockers. Docker reports
28.5.1. The pinned Claude CLI passes authentication preflight. The existing SCI
proof still matches worker image
`sha256:508f6f195f8837324f2c52ec87b193eb7fc79334de8948ff300b8585df03b37a`.
The gate ran before inference and was not bypassed.

Runs `smoke-1793048656305` and `smoke-1793048953467` stopped at the subscription
weekly quota. Both preserved terminal receipts report `usage_limit_reached`, zero
tokens, and no model usage. Their original reports and ledgers remain unchanged.
Added `failure-diagnosis.json` beside each report with the cause and trace hash.
The adapter currently reports these as generic transport failures and retains
$0.059514 per run. These diagnostics do not release either reservation.

The user then explicitly said "try again". Authentication passed. To keep the
original total $1 allowance, including both unresolved reservations, ran once:

```sh
source var/worker.env
make smoke-subscription LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=0.88
```

Run `var/runs/smoke-1793049211459` passed all 12 checks in 54.095 seconds. The root
queried four external records and wrote Clojure to select the two ready records.
SCI returned their IDs and estimate sum 55. A real child model session received
that selection, wrote separate Clojure, and ran it through SCI to return
`{:count 2 :double-estimate 110}`. The parent consumed that result and returned it.
Both sessions completed. The successful run has no unresolved provider calls.

Recounted all six distinct provider receipts from the saved raw streams offline:
12,455 input tokens, 509 output tokens, zero cache tokens. At $2/M input and $10/M
output, the total is $0.03 API-rate equivalent. Subscription invoice cost remains
unknown. The successful usage plus both earlier retained reservations totals
$0.149028, below the original $1 allowance. Saved `receipt-verification.json`
with per-request counts, provider IDs, trace hashes, report/artifact hashes, and
the check results. This recount made no additional model calls.

All requests, raw streams, generated source, SCI results, context, session events,
and accounting remain in the run directory. Runtime source was unchanged during
the live run. Updated README and acceptance status after it completed.

This is the first real capability result. It establishes external context access,
SCI execution of model-written code, and recursive model use. It does not establish
a retained skill, independent skill acceptance, held-out improvement, cold-boot
transfer, or superiority to Prime/Python. No acquisition or evaluation run started.
The native Prime/Aljure benchmark adapters and shared budget enforcement remain
unfinished; larger experiment spending remains on hold.

## Computational-substrate audit and shared execution foundation — 2026-10-26

Read the original goal attachment and the expanded research specification. This
extends the scheduling goal; it does not authorize more inference. The prior goal
turn was progress: it established a real capability smoke. This turn made zero
provider calls. Aljure HEAD is `3b905ffd70f04e30181d83545086b008c2e2e116`, with
existing uncommitted work preserved. Source manifests already record that commit,
dirty state, runtime versions and exact file hashes. Added benchmark code and the
machine-readable capability matrix to the frozen source set for new runs.

Baseline rerun before the new backend tests:

```text
make test
48 tests, 751 assertions; zero failures/errors
python3 -m unittest discover -s test_python -v
37 tests; OK; 68.988 seconds
```

Cloned Prime to `var/upstream/prime-agent` and checked out detached commit
`c4c238ca025e382d96fb5f37e6328ca77fb82ef3`. Read its AGENTS.md, documentation,
protocol-3 kernel contract, Rust manager/tool/agent-loop boundaries, Python runtime,
recursive host bridge, prompt/skill contracts, harness/refinement code, headless
flags, and descendant accounting. The checkout remains clean. No upstream changes
or external infrastructure were created. Its MIT license remains in the checkout.

Created `research/BASELINE_AUDIT.md`, `PRIME_ARCHITECTURE.md`,
`EXPERIMENT_PROTOCOL.md`, and `capabilities.json`. The actual Prime boundary is
newline-delimited JSON to `python -m rlm.repl`. A Clojure replacement also requires
changes to Python-specific prompts, executable skill references, provisioning,
bootstrap and dill namespace snapshots. It is not a narrow language-only swap at
this pin. Native Prime remains the competitive arm; Aljure's shared controller is
the primary causal language experiment. Prime parent usage includes descendant
attribution, so independently summing both levels would overcount inference.

Implemented `ExecutionBackend` with Clojure and Python records, selected by
`:execution-language`. The existing SCI default, controller, SQLite sessions,
messages, provider budgets, and scheduling implementation remain in use. Python
source runs only in a disposable worker, with AST/compile/exec, classes,
higher-order functions and generated-module support. Both worker types use the
same Docker supervisor and enforced limits. Python artifact promotion and policy
registry operations fail explicitly until the equivalent artifact path exists.

`make python-worker-setup` built from
`python@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`.
Python worker:
`sha256:94b3350439576a7e236b164a2d2c7dba846d239155cd463eb3a14f5ac4e18280`.
Actual positive persistent-binding control and ten negative/reset checks passed.
Evidence: `var/python-isolation-proof.json`, `var/python-worker-setup.json`.
The Python restrictions are not an interpreter security proof; Docker is the
security boundary. `source var/worker.env && python3 scripts/isolation.py test`
also reran the actual SCI positive control and nine negative checks successfully.
Direct test commands now archive an earlier proof before starting, so a failed
rerun cannot reuse it. Neither gate was bypassed.

Added a working offline language runner and independent Python re-scorer. The
pilot has two developer fixture families: external-record aggregation and
structural transformation of an affine-program IR. Separate evaluator inputs,
known-correct, known-wrong and malformed solutions check scoring. Root/child agents
use the existing broker and durable ledger. Reports preserve source, events,
scoring inputs/outputs, image limits, runtime metadata, usage and source/trace
hashes. Python independently checks affine semantics using exact coefficients;
the Clojure checker evaluates programs on specified inputs. These are small
engineering fixtures, not official OOLONG data or model-generated learning.

Exact command evidence:

```text
source var/worker.env
source var/python-worker.env
make language-parity OUT=var/benchmarks/language-parity-20261026
passed: persistent bindings, structural changes, execution, errors, repair, reset

make benchmark-pilot OUT=var/benchmarks/language-pilot-20261026
FAILED: one known-correct SCI aggregate control terminated without a result

python3 -m benchmark language-compare --run var/benchmarks/language-pilot-20261026
exit 2: Pilot gate failed; retain failure evidence

make benchmark-pilot OUT=var/benchmarks/language-pilot-20261026-diagnostics
passed: 4 paired cases, 8 task executions, 80 evaluator task cases

make benchmark-compare RUN=var/benchmarks/language-pilot-20261026-diagnostics
FIXTURE: Clojure 4/4, Python 4/4, difference 0; model calls 0

make prime-doctor
exit 2: source pin verified and clean; native adapter/container/gateway missing
```

The first failed pilot is preserved. Its eight task executions scored correctly,
but the failed positive control invalidated the overall gate. The first worker
failure lacked stderr in its evaluator record; its cause remains unresolved.
Docker's bounded historical event query was inconclusive and is saved alongside
that run. Added EOF supervisor diagnostics to evaluator failures and a regression
test. The comparison now refuses any failed pilot/control even if task rows pass.
The diagnostic rerun retained the same worker/resource limits and passed every
control and task. This does not erase the first infrastructure failure or establish
reliability across arbitrary workloads. No retry or inference charge was hidden.

The successful run recorded 56 scripted provider responses and zero model tokens
or model dollars. Local compute cost is unknown. `comparison.json` preserves the
independent result and source-report hash. A final `docker ps --all --filter
name=repl-lab-` found no remaining workers. No model produced a retained skill,
no skill was independently promoted, and no held-out/cold-boot benefit was tested.

Validation after the backend changes:

- Full Clojure suite: 51 tests, 1,362 assertions, zero failures/errors. Log:
  `var/language-foundation-clojure-tests.log`.
- Full Python suite: 40 tests passed in 81.763 s. Log:
  `var/language-foundation-python-tests.log`.
- After the diagnostic/report-gate correction: focused Clojure suite passed
  4 tests / 613 assertions; focused Python language suite passed 4 tests in 0.009 s.
- `git diff --check` passed. The early namespace delimiter error was corrected
  before the parity and pilot runs. No failed experiment record was overwritten.

Remaining: neutral live model instructions/wire contract; equivalent Python AST
artifact validation, promotion, reuse/composition and export; native Prime build,
isolated adapter and shared budget gateway; official OOLONG data provenance and
live adapters; broader structural/compositional task families; full four-condition
learning, sealed evaluation, cold boot/ablation/shift, replication and research
report. Live make targets return explicit unimplemented errors. This foundation
does not complete the full research goal. New inference needs a separate explicit
operator authorization after these prerequisites are reviewable.

## Shared Python artifacts and neutral model commands — 2026-10-26

Continued the existing goal. No new inference was authorized or dispatched.
Preserved the dirty working tree and the earlier failed pilot. No changes were
made to the pinned Prime checkout or any production application.

Implemented Python source/AST artifacts using a separate syntax-only container.
The parser compiles syntax but never executes module statements. It cannot share
the learner's Python namespace. The registry now validates exported arity,
source/forms agreement, dependency language and export-name conflicts. Added
brokered subtree inspection, stale-checked structural patches, and approved
export calls in fresh workers. Calls to merely staged artifacts are refused.
The existing controller owns promotion; a new explicit verified-case objective
supports non-scheduling fixtures without changing the default scheduling rule.

Executable loaders now select Python or SCI. Bundle schema 2 preserves AST/forms
and minimal interfaces, with compatibility for schema 1. Fresh restoration remaps
dependency hashes and creates new envelopes. Python docstrings and encoded
literals are included in the inspection audit. Rehashed extra narrative fields
are rejected by the bundle loader. This is not a proof against memorization.

Added selectable JSON model commands, common instructions and separate language
appendices. The language pilot uses this format. Existing EDN runs retain their
original contract. Python uses JSON AST paths/replacements; Clojure uses EDN
strings inside JSON to preserve symbols and list/vector distinctions. The shared
broker, providers, sessions, messages and budgets remain in use.

Rebuilt the Python worker after adding syntax operations. Image:
`sha256:a1a4367a74b602545ac95b4494f92aaef49120f7d40f160017dad43fd9064fd7`.
`python3 scripts/setup_python_worker.py` passed the actual persistent positive
control and all ten negative/reset checks. Log:
`var/python-artifact-worker-setup.log`. The prior image's proof is archived.
The SCI worker and its isolation limits were unchanged.

Validation completed so far:

```text
make test
57 tests, 1,393 assertions; 0 failures, 0 errors
log: var/artifact-foundation-clojure-tests.log

python3 -m unittest discover -s test_python
41 tests; OK; 164.637 seconds
log: var/artifact-foundation-python-tests.log

focused repl-lab.model-protocol-test, after dependency-conflict checks were added
6 tests, 32 assertions; 0 failures, 0 errors
```

Early compile checks found a delimiter error in the new bundle audit and test
file, and a missing ProcessHandle import in the fixture driver. These were fixed.
Two focused assertions initially expected an unescaped slash in JSON text; the
protocol round trip was correct. The checks now compare decoded operation values.
These failures were development checks, not live model or benchmark outcomes.

`make artifact-parity OUT=var/benchmarks/artifact-parity-20261026` passed both
languages' staging, patching, dependency composition, independent development
checks, promotion, approved invocation, frozen retention refusal and task-local
execution checks. It then failed in the Clojure cold process before a controller
was created: `Worker wall-time limit`. Its exact log is
`var/benchmarks/artifact-parity-20261026/clojure/cold-process.log`. The full test
suites and a large Docker image pull/unpack were running concurrently. Contention
is plausible but is not a confirmed cause. No isolation limit was raised.

A new fresh-JVM diagnostic used the same exported Clojure library and unchanged
limits. It passed all four transfer inputs, failed all four compatible fallback
inputs as expected, and recorded an approved export invocation in a fresh scripted
conversation. Evidence remains under the original run's `clojure/cold-diagnostic`.
This diagnostic does not change the first run's failed status. The complete
artifact fixture is being rerun serially in a new output directory.

The pinned Prime CI specifies Rust 1.98.1. Pulled its build image without inference:
`rust@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e`.
The native Prime binary/container, adapter and trusted inference gateway are still
unfinished. A downloaded compiler image is not a passing Prime runtime test.

Technical limits and API differences are recorded in
`research/LANGUAGE_ARTIFACTS.md`. Repeated isolated Python syntax checks add local
overhead; the verbose AST also reaches the bounded wire limit sooner for some
programs. Neither effect may be presented as a Clojure research advantage.

The full serial artifact run completed successfully:

```text
make artifact-parity OUT=var/benchmarks/artifact-parity-20261026-serial
FIXTURE; all gates passed for Clojure and Python; model calls 0

python3 -m benchmark artifact-compare --run var/benchmarks/artifact-parity-20261026-serial
independent checks passed; fresh-process retained outputs 4/4 in each language;
compatible fallback outputs 0/4 in each language
```

Both languages used new JVMs, new workers and fresh scripted conversations for
the transfer controls. `independent-comparison.json` records the raw-report digest,
arithmetic checks, paired development acceptance, export-file hash checks and
actual invocation evidence. These inputs were not used for development, but they
remain developer fixtures. There is no model-generated skill or learning claim.
The first failed cold attempt remains preserved and is not relabeled successful.

Added an independent artifact comparison CLI and two Python scorer rejection tests.
The focused Python artifact/language suites passed six tests. A trace-export
regression test caught that generic keyword serialization could omit an operation's
namespace. New controller JSONL exports preserve full names such as `artifact/call`.
Historical logs and authoritative EDN/SQLite records were not rewritten. The final
focused Clojure protocol suite passed seven tests with 33 assertions. These are
focused counts after the earlier full-suite run, not a claimed new full-suite count.

The new common-JSON language pilot also passed:

```text
make benchmark-pilot OUT=var/benchmarks/language-pilot-20261026-json
4 paired FIXTURE tasks, 8 executions, 80 evaluator task cases; model calls 0

python3 -m benchmark language-compare --run var/benchmarks/language-pilot-20261026-json
Clojure 4/4, Python 4/4, paired difference 0; independent scorer agrees
```

The pilot used common JSON instructions plus language appendices, recorded prompt
digests, and preserved full operation names in new JSONL traces. All positive,
known-wrong and malformed-program controls passed. Cleanup inspection found no
remaining REPL Lab containers. The unchanged Prime checkout remains clean at its
pinned commit. No new inference or billed cost was incurred.

Started the next offline phase: `scripts/setup_prime.py` builds an archived clean
copy of the pinned upstream source inside Docker. It preserves source and license
files, uses Prime's committed Rust/runtime locks, installs bundled native skills,
and records the exact image. The checkout itself is not modified. A successful
build is labeled BUILT / UNVERIFIED until native execution and isolation tests
pass. No provider credentials enter the build context. Native adapter work is
continuing; no Prime comparison is claimed.

## Native Prime adapter — actual offline integration, 2026-10-26

Built pinned Prime `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` with its release
profile. The unmodified binary reports `0.10.1`. The source checkout remains clean.
The initial image passed isolation controls but its first headless fixture failed:
Prime refused its kernel because the default scientific Python packages were
missing. Its scripted final message still said the task was complete; the
independent artifact check rejected it. Evidence:
`var/benchmarks/prime-native-20261026` and `var/prime-native-fixture.log`.

Inspected `DEFAULT_RLM_EXTRA_PACKAGES` in pinned upstream source and installed the
full set. Added a hash-locked package file constrained by the upstream runtime
lock. Bundled skills remain installed. Rust build layers were reused without any
source changes. The corrected image is
`sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
Build record: `var/prime-builds/1793054423155041000.json`. Log:
`var/prime-native-build-packages.log`. The image records its installed packages.

Added actual native negative controls for loops, allocation, oversized output,
host reads, root writes, network, evaluator access, reset and process count. All
nine passed for the corrected image, plus the file/arithmetic/no-credential
positive control. The proof is `var/prime-isolation-proof.json`; prior proofs are
archived. Docker settings are inspected for every container. No gate was bypassed.

Artifact collection exposed a separate issue: Docker cp omitted tmpfs contents.
The fixed collector streams a tar archive from inside the live container mount
namespace while a bounded bootstrap holds it open. It never restores symlinks or
loads dill. An actual marker-file control passed. The supervisor bounds stdin,
both output streams, elapsed time and archive size, and removes the entire
container through the existing quarantine-aware cleanup. Four focused supervisor
tests passed, including a process that never reads stdin and an output flood.

The corrected headless integration passed. Prime's original Rust loop and real
Python kernel read the exact eight records from the successful Aljure JSON pilot's
`aggregate-0` task. All three fixture arms returned ready IDs `node-3`, `node-5`,
`node-6`, `node-7` and total 78. The independent aggregate scorer verified the file;
assistant prose was ignored. This is **FIXTURE**, with no model inference or
learning claim. Native faux-provider token estimates are explicitly not treated
as provider measurements or compared against Aljure's zero-token fixture counters.

```text
source var/prime-worker.env
make prime-isolation-test
TESTED; all nine controls true; model calls 0

make prime-fixture OUT=var/benchmarks/prime-native-20261026-resource-manifest RUN=var/benchmarks/language-pilot-20261026-json
FIXTURE; passed; native exit 0; independent answer verified; model calls 0

python3 -m unittest discover -s test_python
47 tests; OK; 75.157 seconds
log: var/native-adapter-python-tests.log

python3 -m benchmark prime-doctor
source pin true, native isolation true, fixture receipt true;
exit 2 for live gateway and validated retention export still missing
```

One metadata initializer used an incorrect local source path before its native
process started. Its log and attempt directory remain preserved. The correction
and the final resource-manifest run passed. Current native records include Aljure
and Prime revisions, dirty status, adapter/evaluator source hashes, prompt digest,
image and actual limits, raw events, native state archive, answer and file hashes.
The source-matched receipt is `var/prime-adapter-proof.json`. `git diff --check`
passed and final Docker inspection found no remaining REPL Lab containers.

Important limits: Prime's Rust controller shares the 256 MiB/one-CPU/32-PID ceiling
with its kernels, while Aljure's controller runs outside its worker caps. Prime has
an additional 8 MiB workspace. Its watchdog bounds the whole task, not individual
expressions. These differences are explicit; strict economic or execution parity
is not established. Full descendants, refinement, compaction, provider retries,
native executable-only export and a trusted global-budget gateway remain open.
The four-condition language learning runner and official OOLONG live integration
also remain unfinished. No real model has created an independently accepted skill
or demonstrated unseen-task improvement after reset in this work.

## Gateway accounting and native recursion — 2026-10-26 checkpoint

Added `gateway.clj`, which reuses the existing controller and SQLite CAS ledger.
It reserves one global budget before each injected transport request. Requests
from all configured routes share the cap. It retains uncertain reservations,
stops automatic retries after an uncertain outcome, reconciles model mismatches
before stopping, rejects duplicate provider receipts, and handles cumulative SSE
usage and separate cache-write durations. Gateway session IDs identify requests;
native agent ancestry is not yet verified. This is a tested accounting core, not
a connected live gateway. No HTTP listener or production transport is enabled.

The full Clojure suite passed **66 tests / 1458 assertions**, with no failures or
errors (`clojure -M:test -e ''`; the main test runner ignores the extra arguments).
Later narrow bounds/normalization changes receive a focused rerun. The preserved
accounting fixture at `var/benchmarks/gateway-20261026` passed with two successful
scripted receipts and one interrupted response. Its reservation survived reopen,
and a retry did not reach the transport. All model-call counts are zero. Logs and
the durable SQLite ledger, raw request/response events and normalized receipts
remain in `var/`. This is **FIXTURE**, not provider billing or learning evidence.

Native Prime's real child kernel selected external context, computed the aggregate,
sent a message, and returned its result to the parent. The independent answer
check passed at `var/benchmarks/prime-recursive-20261026-transcripts`. Both original
session transcripts and their usage rows are preserved. The first recursive attempt
at `var/benchmarks/prime-recursive-20261026` failed an incorrect expectation that
the faux path emits child-usage attribution rows. Further source inspection identified the actual cause in `print_rlm.rs:627`: the
daemonless host omits child usage attribution. `rlm_usage_store: None` selects a
default store in `runtime_wiring.rs`; it does not disable it. The revised check
verifies child execution, message delivery and distinct transcript usage;
it explicitly leaves native billing aggregation unverified. The failed attempt
remains preserved. Three focused transcript-accounting tests passed, including an
aggregate that must not be counted twice.

The native fixture and shared gateway core are still separate. Connecting a
bounded transport through disposable isolation, checking real provider-path
descendants/refinement/compaction/retries, and validating native retention export
remain required before a live Prime comparison. No additional inference was run.

### Published checkpoint and normal HTTP provider test

At the user's explicit request, committed and pushed accumulated work to
`origin/main` as `213cf96d9f028c711336636f56cc5db32996758b`. A scan of 119 candidate
files found no credential-pattern hits. Ignored local evidence, environment files,
build outputs and upstream checkouts were excluded. Staged whitespace checks
passed except the unchanged vendored OOLONG scorer's original trailing space;
its official source body was preserved.

The focused gateway rerun passed **7 tests / 61 assertions** after narrow bounds
and receipt-format changes (`var/gateway-focused-tests.log`). An independent
Python checker reconciled the gateway fixture: two complete receipts, one unknown,
known synthetic cost $0.000172 and a retained $0.005 reservation. Total cost stays
null while the outcome is unknown. Cache duration rates now have independent checks.

Added a no-network, no-credential local HTTP fixture for Prime's actual Anthropic
transport. `var/benchmarks/prime-http-20261026` passed independent answer and
root/child/message checks. Four scripted responses supplied 4,000 input and 80
output tokens; native transcripts recorded 0 input and 80 output. The report keeps
this discrepancy. Source inspection confirmed that the pinned streaming parser
reads initial counters from the wrong object level. Missing parent attribution
comes from the daemonless host; a null optional store selects a default store and
is not the cause. The earlier checkpoint explanation has been corrected.

`make gateway-native-replay OUT=var/benchmarks/gateway-native-replay-20261026 RUN=var/benchmarks/prime-http-20261026`
passed with all 4,080 scripted tokens accounted for and no remaining reservations.
It estimated $0.0088 at fixture rates. This is recorded scripted transport playback,
not a connected gateway or actual spending. The next focused Python run passed
**19 tests** in 0.589 seconds (`var/gateway-expanded-python-tests.log`). See
`research/GATEWAY_ACCOUNTING.md` for the remaining transport boundary. Docker
inspection found no REPL Lab containers. Live execution remains disabled.

### Latest operator direction: mechanism before comparison expansion

The operator restored adaptive harness learning as the primary question. Preserve
Python as an ablation and Prime as the later competitor. Do not expand the proposed
20-case language pilot or general gateway machinery before the first real
acquisition/transfer result. `research/EXPERIMENT_PROTOCOL.md` now records that
priority and separates policy synthesis from proven orchestration improvement.
Prime readiness is no longer a prerequisite for an Aljure-only learning run;
explicit spending approval still is. The $35 acquisition/held-out/cold-boot
proposal remains unapproved; only the earlier $1 smoke was authorized.

Before that steering arrived, the host-only stdio gateway bridge passed two actual
process tests, including SIGKILL while a provider response was pending. Recovery
preserved the reservation. Five bounded native-supervisor tests passed, including
a duplex input/output exchange. Files: `gateway_stdio.clj`, `line_process.py`,
`test_gateway_bridge.py`; log `var/gateway-bridge-tests.log` (2 tests, 8.223 seconds).
These are tested primitives, not a connected native gateway. Further native bridge
integration is deferred to the first Prime comparison. The later checkpoint
`5aa1c00789c71ad230de8563a7758bab5fa3cde2` is confirmed on remote `main`.

### Reuse the configured login for the first learning run

Read-only preflight confirmed the SCI image still has its actual nine-case proof
and the existing Claude Code 2.1.310 login is ready. No direct API key is configured
in this process. No secret was read into logs and no inference was requested.

Connected the existing subscription adapter to the existing acquisition, resume,
held-out and cold-boot entry points. This is a narrow provider selection change;
the scheduler, controller, promotion rule and evaluator remain intact. Learning
records carry an explicit subscription scope. All root and child reservations
remain in the same task ledger. Phase caps still use equal nontransferable task
allowances. The transport retains its $1 per-request reservation ceiling, exact
model/rates/output limits, no-retry behavior and actual SCI gate. Evaluation trace
paths now accept the controlled `var/evaluations` root and reject traversal.

Model/provider/rates and the CLI digest must match across acquisition, resume and
evaluation. Reports label subscription values as standard-rate equivalents and
leave invoiced amounts unknown. Direct API selection remains available. Existing
smoke commands retain their at-most-$1 gate. New inference remains unauthorized.

The focused Clojure provider/isolation tests and actual fake-CLI pipe tests passed;
exact summaries are preserved in `var/learning-provider-tests.log` and
`var/learning-subscription-python-tests.log`. These are FIXTURE tests. The concrete
existing-command protocol and proposed $15/$10/$10 caps are in
`research/FIRST_MECHANISM_RUN.md`. No extra benchmark family or agent controller
was added. Explicit authorization for those caps remains pending. The subsequent
actual-worker rehearsal below adds a readiness requirement.

### Actual-worker acquisition rehearsal: controller timing failure

With inference disabled, ran the existing acquisition path with developer-authored
policy/workflow responses and real isolated SCI execution. The first attempt,
`var/benchmarks/mechanism-rehearsal-20261026`, exhausted the unchanged 120-second
task limit after five development episodes, before any provider call. Frozen task
0 remains a recorded failure. Stopped the partial evolving task after this diagnosis;
the process exited 143 and the remaining stopped worker was removed through the
existing cleanup function. Original evidence is preserved. This is **FIXTURE**.

Profiling a separate SQLite copy found 2,079,123 characters of trace context in the
main controller record. Reading it took 6,076 ms; three identity transactions took
6,378, 6,268 and 6,165 ms. The original failed database was not modified. Profile
log: `var/mechanism-profile-20261026-fixed-driver.log`.

Development trace records now use immutable, content-addressed entries in the
same SQLite database. The main controller stores small descriptors. Approved
context queries retain the same filtering, selection and output limits. Reads
verify content hashes and counts; an interrupted publication cannot expose an
unpublished block. No task or isolation limit changed.

Focused validation: **26 tests / 305 assertions; zero failures or errors** in
`var/context-block-tests.log`. Command:

```sh
python3 scripts/clj.py -e "(require 'repl-lab.runtime-test 'repl-lab.experiment-test) (let [r (clojure.test/run-tests 'repl-lab.runtime-test 'repl-lab.experiment-test)] (shutdown-agents) (System/exit (if (zero? (+ (:fail r) (:error r))) 0 1)))"
```

The new actual-worker rehearsal at
`var/benchmarks/mechanism-rehearsal-blocks-20261026` completed successfully with
the same development panel, 120-second task limits and scripted proposals:

- Four acquisition tasks completed. The controller accepted one policy/workflow
  candidate in each first task. Frozen retention was cleared; evolving retention
  carried to the next task. Candidate-validation tasks took 109.057 and 109.342
  seconds. The next tasks took 53.125 and 58.638 seconds. All 36 development
  episodes and four task episodes completed through real SCI workers.
- A separate JVM loaded the export and ran three new paired cases, including
  larger fanout and independent workloads. All six episodes completed. The report
  confirms a different process ID. Both fresh scripted conversations used the same
  budgets. Reports, source hashes, original driver and event/episode traces remain
  under that directory, with cold results in `cold/`.
- Twelve synthetic provider receipts during acquisition used zero model tokens
  and zero dollars. There were **zero real model calls**. The authored code is a
  developer fixture; neither promotion nor its fresh-process benefit establishes
  learning, a Clojure advantage or a Prime result.

Commands and terminal logs:

```sh
source var/worker.env
python3 scripts/clj.py -i var/mechanism-rehearsal.clj -e '(mechanism-rehearsal/acquire!)'
python3 scripts/clj.py -i var/mechanism-rehearsal.clj -e '(mechanism-rehearsal/cold!)'
```

Both exited 0. Logs: `var/mechanism-rehearsal-blocks-acquisition.log` and
`var/mechanism-rehearsal-blocks-cold.log`. The first failed attempt remains separate.

Only about 11 seconds remained for inference in a candidate-validation task.
Before any live acquisition, declared a 300-second acquisition task cap for both
arms. The evaluator keeps 120 seconds per task. SCI remains at 10 seconds per
expression and 120 seconds per worker session, with the same actual isolation
gate. Model-call, token and dollar limits remain unchanged. This change applies
to future live acquisition; it does not rewrite the successful 120-second fixture.
The real model-generated improvement and the $15/$10/$10 approval remain pending.

After the declared acquisition-time change, the focused subscription suite passed
**5 tests / 44 assertions**, zero failures or errors
(`var/context-block-subscription-tests.log`). An independent Python report check
confirmed all four acquisition tasks, all six cold episodes, actual policy calls,
two approvals, distinct process IDs, zero invariant violations, zero model tokens
and no unresolved reservations. Docker inspection found no remaining workers.
No broader performance claim follows from these fixture checks.

Preserved all 82 executed source files in `executed-source.zip` beside the report.
Every file matches its recorded source hash; this archive contains the source
before the subsequent live-only task-time change. Archive SHA-256:
`82bd23897469977935229ec76dc81ea2dfe107875ac9233ad1a10c6d11daf55b`.
Seven changed tracked files passed the credential-pattern scan; local evidence
and environment files remain ignored. Whitespace checks passed.

### Learner contract audit before real acquisition

The previous goal turn made concrete progress and was pushed as
`0cabe9702c207832c97570785c9f23f2e066ddaf`; remote `main` matched that hash. The next
audit found that `resources/base-instructions.txt`, used by live EDN acquisition,
did not advertise the existing inspect, subtree, patch or approved-call operations.
It also omitted the exact workflow submission interface and parent/dependency rule.

Completed that API contract. It now explains context transfer into SCI, session
bindings, shared descendant budgets, structural patch hashes, staged versus
approved code, independent promotion after sessions finish, and final-library
freezing. Examples contain no scheduling solution or claimed learned skill.
The same prompt serves both acquisition arms. No broker capability or acceptance
condition was added, and the JSON comparison protocol retains its existing scope.

Static contract validation passed: **17 command examples cover all 16 broker
operations**, with exact keys. The workflow example passed the real artifact
validator after substituting actual fixture hashes. Evidence is **FIXTURE**;
model-call count is zero. Prompt SHA-256:
`8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005`.
Command: `python3 scripts/clj.py -i var/learning-prompt-audit.clj -e nil`.
Log: `var/learning-prompt-contract-audit-fixed-driver.log`, exit 0. The earlier
one-line audit command failed to parse before running; its log remains at
`var/learning-prompt-contract-audit.log`. This was a driver error, not an API pass.

Corrected `research/FIRST_MECHANISM_RUN.md` to use the existing conservative
allocation in `config/live-proposal.edn`: reserve the full earlier $1 smoke cap,
then allow $14 new acquisition, $10 held-out and $10 cold boot. This keeps the
entire proposal within $35, including uncertain smoke reservations. All remain
standard API-rate equivalents for the subscription; actual billing is unknown.
New acquisition and transfer spending still lack explicit approval.

The next required action is real-model acquisition under those approved caps.
Further comparison infrastructure is outside the operator's current priority.
There is still no model-created retained skill, independently accepted model
workflow, or demonstrated model-learned cold-boot benefit.

Also corrected stale README statements that limited subscription support to the
smoke and made Prime integration a prerequisite for acquisition. The actual source
supports the documented learning provider selection. Five changed files passed
the credential-pattern scan and whitespace check. The only model-facing change
in this checkpoint is the prompt contract; its real-model effectiveness is
IMPLEMENTED / UNVERIFIED. The pending spending approval has now remained the same
blocking condition across at least three consecutive goal turns. With the
requested first-run preparation complete, further progress on the prioritized
mechanism requires that approval; no additional inference was dispatched.

### First real experiment request: current preflight, no inference

The operator explicitly requested a fresh readiness check and a separate approval
request. This request does not authorize model calls. The baseline was clean at
`3a5d517a858aef384caa3fb2f43e09be9cce9462`. Preflight evidence is preserved under
`var/preflight/first-live-20261027T003144Z`; the published metadata is
`research/FIRST_LIVE_PREFLIGHT.json`. All 82 executed source-file hashes remained
unchanged through the checks. No simulator, acceptance rule, scorer or hidden
split changed. No actual learning or final split was generated or consumed.

`make doctor` passed before and after. Read-only subscription doctor confirmed
Claude Max authentication and the pinned 2.1.310 binary digest. No worker or
experimental JVM was found before the checks; no worker container or supervisor
remained afterward. The focused subscription accounting suite passed **5 tests /
44 assertions**, and the fake-CLI transport suite passed **10 tests**. Neither
suite calls a real model.

The first `make isolation-test` failed its positive control. The underlying cause
is unconfirmed because that test only returned a generic positive-control error.
An identical diagnostic control returned both expected values in 9.943 seconds.
The unchanged full suite then passed its positive control and all nine negative
cases. Both attempts and diagnostics are preserved. No worker limits, image or
gate changed. Startup timing remains a reliability limitation; the initial
failure is not relabeled as a pass.

The existing `live/development-panel!` executed all six known fixture cases in
real SCI workers in **54.440 seconds**, within the 300-second acquisition deadline.
All cases completed with zero accepted invariant violations. The local driver
used only the initial library, not a proposed winning fixture. The final-phase
configurations retain 120-second task deadlines and six shared model calls.
There were zero new model calls, zero model tokens and no new reservations.

Read-only integrity checks validated 20 stored artifact envelopes, both exported
artifacts, ten SQLite databases and all 82 archived source hashes. The earlier
failed acquisition and successful rehearsal remain intact. Two earlier quota
failures retain $0.059514 each in uncertain reservations. Combined with $0.03
known smoke usage, $0.149028 remains accounted for within the separate $1 smoke
allowance; those reservations were neither erased nor reallocated.

Created `research/FIRST_LIVE_RESULTS.md` with an explicit NOT RUN status, baseline
identifiers, proposed phase configurations, preflight failures and passes, raw
evidence links, and exact commands. Live candidate counts, acceptance, performance,
inference use, held-out transfer and ablation remain unmeasured. Outcome A–D and
the follow-up experiment will be assigned only from actual model-run evidence.
The only next required input is separate explicit approval for the proposed
$14/$10/$10 new allowances plus the earlier $1 smoke allocation.

### Explicit authorization for the first real experiment

The operator replied "yes rip it" to the exact model/provider/cap request.
Recorded at 2026-10-27T00:46:45Z. This authorizes one acquisition ($14), held-out
($10), and cold-boot ($10) experiment using the existing Claude subscription,
`claude-sonnet-5-5`, and $2/M input / $10/M output equivalents. The earlier $1
smoke allocation remains reserved, keeping the total ceiling at $35. This does
not authorize extra experiments, silent retries or changes to scoring or limits.
Read-only worker/login checks still pass; the recorded actual SCI proof matches
the pinned image. No leftover workers were found. Record this authorization before
the acquisition source snapshot, then freeze all experiment source through the
three phases. Results are pending; no success claim follows from approval.

### First real experiment completed — 2026-10-27 UTC

Authorized source `7126edb7e29c0d9431acb52f395057bb274b68c5`; all 82 frozen source
hashes matched after acquisition, held-out and cold boot. No source, scorer,
promotion, model or limit changes. No sealed reruns or inference retries.

- Acquisition `model-1793062055972`: four real model artifacts, one accepted pair,
  one rejected pair; 1/3 learning tasks completed per arm. Cleanup quarantine
  blocked later tasks. Existing recovery plus unchanged nine-case isolation suite
  passed before held-out. Three old-policy development worker failures inflated
  promotion gain; they are not evidence of algorithmic improvement.
- Held-out `evaluation-1793062969450`: frozen 0/8, evolving 5/8, retained direct
  policy 1/8, original direct policy 6/8. Evolving successes used temporary code.
  Both fixed host baselines completed 8/8; they bypass Docker/SCI startup.
- Cold `evaluation-1793064236328`: new JVMs/conversations; frozen 0/8, evolving
  3/8. Direct retained and removal controls both completed 8/8. Retained mean
  makespan 59.5 versus original 204.125; 565 retained invocations. Retained matches
  estimate baseline on every cold case. This supports limited policy transfer,
  not demonstrated harness improvement or a general competitive result.
- Installed Claude CLI changed from 2.1.310 to 2.1.311 during cold boot. The pin
  rejected later dispatch; no version/model switch or retry occurred.
- 139 completed receipts reconciled: 518,373 input / 34,335 output tokens,
  $1.380096 equivalent known usage. $1.184326 remains reserved across 18 uncertain
  requests. All phase caps held. Earlier smoke retains its full $1 allocation.
  Subscription invoices/local compute prices remain unknown.

Exact commands, raw evidence, all failures and source identifiers are in
`research/FIRST_LIVE_RESULTS.md`. Read-only cause analysis and the sole proposed
next experiment, `policy-runtime-diagnostic-v1`, are in
`research/FIRST_LIVE_POSTMORTEM.md`. No diagnostic or Prime run was started.
Final cleanup found no worker containers, experiment JVMs or quarantine markers.

Post-run read-only verification: `python3 scripts/clj.py -i
var/experiments/first-live-20261027T004645Z/replay-records.clj -e nil` passed
54 acquisition + 48 held-out + 48 cold recorded-action replays. Restored policy
forms match exactly; bundle envelope/payload hashes verified. An earlier direct
CLI replay invocation rejected the path; a later inline command had a missing
parenthesis. Both failed verification attempts are preserved. Neither reran a
model or generated policy. The saved verification script then completed cleanly.

### No-inference diagnostic and skill-selection audit — 2026-10-27 UTC

User authorized the proposed fixed-policy diagnostic, read-only selection analysis,
and a proposal only for a future four-condition selection study. No new inference.

Source `087939ef23c55190ed9c8321e33fdd96d8ae99a8` froze opt-in supervisor diagnostics
and the versioned direct-policy runner. Limits/image/simulator/scorer/policy forms
were unchanged. Both policies get the same readiness control before code loading.
`python3 -m unittest discover -s test_python -p test_isolation.py -v`: 10 passed.
Namespace/48-slot plan/12-world checks passed. Actual `make isolation-test` passed
its positive control and all nine negative cases with the pinned SCI image.

Commands (from `repl-lab/`, after `source var/worker.env`):

```sh
python3 scripts/clj.py -m repl-lab.policy-diagnostic prepare var/diagnostics/policy-runtime-diagnostic-v1-20261027
export REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/policy-runtime-diagnostic-v1-20261027/workers"
make isolation-test
python3 scripts/clj.py -m repl-lab.policy-diagnostic run var/diagnostics/policy-runtime-diagnostic-v1-20261027
```

Result: STOPPED—UNHEALTHY after 23/48 attempted episodes, no retries. Eleven healthy
pairs completed; retained/original mean makespan 94.182/206.545 ticks (54.40% lower
conditionally). Attempt `retained-11-r0` timed out on `(+ 20 22)` before policy load
or invocation. The supervisor recorded a 10-second response timeout, a running
non-OOM container before removal, and successful cleanup. No code-loading,
post-load execution or terminal algorithmic failures occurred in completed pairs.
The reversed-order repetition was not reached. Twenty-five slots remain explicitly
unattempted, not silently dropped or scored as successful.

All 23 recorded episodes replayed to their final hashes; 83 diagnostic source
files and 1,212 prior experiment files matched. Model calls/tokens/equivalent cost:
zero. Local-compute dollars remain unknown. No containers or quarantine remain.
The raw run and compact evidence include all worlds, order, policy hashes, stage
errors, worker state, traces, unattempted slots and archive hashes.

Read-only old-trace analysis found no artifact inspection, artifact-context query
or explicit artifact call. Evolving agents used temporary policies in all eight
held-out tasks and all four cold tasks that reached the model. Nine held-out
synthesis turns cost $0.154530 equivalent; this is descriptive accounting, not an
estimate of causal savings. The prompt exposes a policy hash but not its meaning;
`policy/use` takes new source, and default reuse through `done` is undocumented.

Reports: `research/POLICY_RUNTIME_DIAGNOSTIC_V1_RESULTS.md`,
`research/SKILL_REUSE_ANALYSIS.md`, `research/SKILL_SELECTION_V1.md`.
The proposed selector study is not started. Automatic reuse is explicitly a manual
control. Learned selection requires model authorship, independent acceptance,
actual route/invocation evidence and unseen-task benefit with acquisition cost.
Next prerequisite: repeatable healthy worker startup, without weakening isolation.
### Approved skill discovery v2 — implementation and offline preflight

Read Prime's pinned `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` skill discovery,
callable Python modules, progressive disclosure, and refine plan/apply/persist
boundary. Read-only audit: `research/PRIME_SKILL_DISCOVERY.md`; no upstream edits.

Added controller-reviewed skill descriptors tied to immutable version hashes,
derived interfaces/provenance and hash-checked diagnostic evidence. Added compact
list/detail tools and explicit approved-policy selection. Staged source cannot
select or approve itself. Full code remains on demand. Legacy prompts, simulator,
policy scoring, and promotion thresholds remain unchanged.

`skill-discovery-v2` is a separate four-condition **FIXTURE** control: opaque hash,
descriptive discovery, deterministic reuse, and a developer-authored selector
stand-in. New CPU/memory and GPU workloads use the existing simulator. The live
selector path remains unimplemented and unauthorized. No inference has occurred.

Preflight: `make test` passed 70 tests / 1,496 assertions; two additional discovery
control tests passed 29 assertions. The first control-test attempt failed because
protocol methods need a backend test double; its log is preserved. The corrected
tests verify startup/loading/execution/algorithm attribution. Actual positive SCI
control and all nine negative isolation cases passed with the existing image.
Final offline run evidence will be recorded separately below.
### Skill discovery v2 result and gate qualification

Frozen source `d347ba4d823313cf04463a717994deb1eb0c8d51`; actual SCI offline run
`var/diagnostics/skill-discovery-v2-controls` stopped after 1/16 slots. First
readiness expression timed out before loading. Zero actual policy/selector calls;
15 unattempted slots preserved. No retry or new inference. Report:
`research/SKILL_DISCOVERY_V2_RESULTS.md`. All 88 source hashes and 1,369 previous
evidence files matched; recorded failure replay and raw archive verification passed.

Correction to the preflight statement below: the legacy gate *reported* all nine
negative cases passed. The subsequent audit found process/network workers timed
out without a SCI response. The checker treats any nonzero exit as a pass and
does not prove startup in each negative worker. The active proof was preserved
and invalidated; generated-code readiness is now blocked. No evidence of an escape,
but the reported gate pass is insufficient. Same-worker positive controls and a
separate startup diagnostic are the next prerequisite. Limits and sealed results
were not changed.
### Strict readiness repair and v3 offline continuation

SCI negative tests now require a same-worker positive handshake before the negative
request. They distinguish denial, allocation failure and output/time enforcement;
startup failures fail the gate. Proof v2 pins supervisor source and readiness for
all nine workers. Clojure and subscription proof readers reject legacy/stale proof.
11 supervisor tests, 10 subscription tests, and 7 targeted Clojure tests / 82
assertions passed. A selector-test syntax error was corrected before execution;
its failed log is preserved. No provider requests occurred.

Three original and three startup-profile fresh-container probes all answered.
The derivative image has the identical root filesystem and only adds JVM C1-only
tiering. Same limits; no moved deadline. Its strict positive + all nine negative
checks passed with per-worker readiness. Image:
`sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
`var/worker.env` now selects this tested profile; original image/env evidence remains.

V3 predeclares 20 new offline slots, including the fixed applicability guard.
`research/SKILL_DISCOVERY_V3.md` records the protocol and limitations. Selector
development gate exists with independent replay, ledger checks, receipt matching,
hidden-data exclusion and fixture accept/reject tests; no real selector was authored
or accepted. The external Prime/OOLONG integration proceeds in a separate worktree
and is not gated on completion of the selector research track.
### V3 cleanup stop and v4 fixture regression

V3 source `b35a228` ran 12/20 slots: both ordinary cases passed in all five arms.
First GPU blind reuse exhausted its event budget with 4,999 rejected capacity
checks. Temporary adaptation completed at 42 ticks, then Docker rm timed out.
The worker had exited; later independent inspection confirmed absence. The run
stopped on quarantine and is preserved with eight unattempted slots. Raw episode
cleanup attribution was incomplete because the old Clojure closer ignored the
supervisor's cleanup failure. Worker audit/stderr are the authoritative correction.

Repaired bounded absence verification after rm timeout; unsuccessful/positive
daemon queries still quarantine. Cleanup failures now propagate through a distinct
exit status. Verified-completion counts exclude cleanup failures. Twelve Python
supervisor tests and six Clojure tests / 63 assertions passed. The actual strict
positive plus all nine same-worker negatives passed again. V4 is a newly frozen
regression run on the same public fixtures; original evidence and scoring stay
unchanged. See `research/SKILL_DISCOVERY_V4.md`.
### V4 complete: 20 offline controls, no infrastructure failures

Source `bf6c6a8881c8a20983393e7f593b1245f46a6e9e` completed all 20 slots.
All 25 workers started and confirmed cleanup. Blind reuse completed 2/4 and failed
both GPU cases algorithmically. Opaque scripted synthesis completed 4/4 (mean31.5
ticks); descriptive discovery, scripted selector and fixed applicability guard
all completed 4/4 (mean29.0). The fixed checker matched the stand-in and used fewer
scripted turns. No learned-selector or harness-improvement claim follows.

8,918 actual SCI policy calls; 50 root + one child scripted turns; zero new real
model calls/tokens/inference spend. Discovery exposure/read/use is separately
recorded. Full regression: 75 Clojure tests/1,554 assertions and 59 Python tests.
All 20 SQLite checks and 32 recorded v3/v4 replays passed. Source/evidence hashes
and raw archives verified. Report: `research/SKILL_DISCOVERY_V4_RESULTS.md`.

External native Prime/OOLONG integration remains a separate parallel track. Its
official imports/scorers and common gateway are under offline validation. Native
provider compatibility requires an API transport; the current text-only subscription
adapter cannot be advertised as native Anthropic tool/stream parity. No switch in
billing or new inference is authorized. Later external Docker timeouts are preserved
separately and do not rewrite v4 results or establish broad runtime reliability.

## 2026-10-27 — External integration merged; first pair frozen

Merged the separate Prime/OOLONG implementation through `ac34a0f`. Pinned official
OOLONG and OOLONG-Pairs imports, official independent scorers, an asynchronous
common gateway and native/SCI adapters are connected. Root and descendant requests
reserve before dispatch. Cumulative streaming counters reconcile without double
counting. Unknown outcomes retain reservations and stop later dispatch. API HTTP
work has a killable process deadline; localhost Content-Length/chunked and slow-
drip controls passed. Recovery preserves LIVE/FIXTURE evidence categories.

Read-only Anthropic documentation review found that Sonnet 5.5 rejects disabled
thinking. The new external proposal pins adaptive/summarized medium, the documented
1M context bound, and current cache rates. Supported native configuration pins
housekeeping to the same effort without editing Prime. No previous experiment's
model settings or accounting changed. No API credential was read for inference.

Strict native gate v3 passed its nine original controls plus a non-OOM kill-
rejection control. Same-worker state distinguishes OOM from SIGKILL. Earlier
insufficient/failed gate evidence remains preserved. Relay v5 passed root/child,
signature, tool and accounting checks but failed to trigger automatic housekeeping.
Pinned Prime reads initial input usage from the wrong JSON level for that stream;
its native count was zero while the external gateway recorded 995,000 fixture
tokens. Relay v6 used supported manual `/compact` and `/refine` commands only in
the control. All nine checks passed: five Aljure and six Prime scripted requests.
Actual automatic triggering and provider signature validation remain unverified.

Final merged checks:

```text
make test
Ran 75 tests containing 1554 assertions. 0 failures, 0 errors.
python3 -m unittest discover -s test_python -v
Ran 83 tests in 83.379s. OK.
```

Logs, failed controls, exact proofs and trace archives are linked from
`research/EXTERNAL_COMPARISON_V1.md`. These checks made zero model calls.

The first live protocol is now frozen in the separate clean integration checkout
at `ac34a0f03b22623f211710875dee01dd36643156`, preserving Track A while Track B
develops independently. It selects official unused Pairs task
`oolong-pairs-validation-8192-1`, with a proposed $12 per arm/$24 API ceiling.
Plan SHA-256: `39c383fb51f77f1c7806a0c8816409a45eb94ca124ce52e83bd162d40d5af5dc`.
Read-only preflight returned ready with both current isolation proofs and relay
attestation. No live score exists. The separate ten-case OOLONG-synth follow-up is
also frozen; its disjoint allowances imply an unapproved $240 ceiling and its ten
questions share one context. Neither plan inherits the earlier subscription
authorization. See `research/PRIME_HEAD_TO_HEAD_V1_RESULTS.md`.

Track B now proceeds in its own worktree to connect real selector authoring and
trusted route execution to the existing gate. It will use new capability mixtures,
independent development/held-out cases, and strong fixed controls. The completed
v4 public fixtures remain unchanged. No new inference is authorized in either track.

### First-pair approval and subscription steering

The operator replied “i approve” to the exact $24 API-pair request. Approval is
recorded separately from the immutable proposal. No API key is present in the
session or the previously authorized SPM private env configurations; no key values
were printed or written into artifacts. No model request was attempted.

The operator then asked “i cant use my sub?” Read-only checks confirmed the current
Claude Max login. The old adapter correctly rejects the changed CLI version
2.1.311 against its historical 2.1.310 pin. Pinned native Prime already has a
Pro/Max OAuth implementation. A separate worktree now connects those existing
native semantics to the common host-only gateway. The frozen API checkout, prior
learning evidence and old CLI pin remain unchanged. Native subscription requests
still need their own validated, frozen protocol; Track B inference remains
unauthorized. No new provider call has occurred.

### Native subscription comparison frozen — zero new inference

The pinned Prime OAuth path is now connected to the same accounted host gateway
as Aljure. Native workers receive a fake sentinel only. The real Keychain/file
credential stays on the host; redirects, expiry and API fallback fail closed.
The existing API checkout and approval remain unchanged.

The focused transport suite passed 16 tests in 12.580 seconds. The actual native
OAuth relay passed all ten checks with five scripted Aljure requests and six
scripted native requests (root, child, manual compaction and refinement). SCI
execution, signed thinking, protocol headers, accounting and cleanup passed.
These are FIXTURE results, not real account or benchmark validation. Raw evidence
and source provenance are preserved under research/evidence/subscription-gateway-v1/.

The dedicated subscription checkout is frozen at a72b8c0200302cc8dfd4e904d4f8c23370ab2fcb.
One-case plan: 92a6f0cf5de31273e69bc140d5124219442663bfc1e581234bc7a0bd9ff804a4.
Read-only preflight is ready with no blockers. Proposed caps are $12 per arm,
$24 total API-rate-equivalent through Claude subscription OAuth; Sonnet 5.5,
scorer, task and failure rules remain fixed. This new transport plan awaits
operator approval and a fresh valid credential at dispatch. Ten-case and selector
inference are excluded. No new model call or API charge has occurred.
