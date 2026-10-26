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
