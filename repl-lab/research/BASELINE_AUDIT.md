# Aljure baseline audit — 2026-10-26

Aljure commit: `3b905ffd70f04e30181d83545086b008c2e2e116`.
The working tree has substantial tracked and untracked changes. The commit alone
does not identify the tested implementation. `experiment/manifest` already records
the real commit, dirty status, exact source-file hashes, and runtime versions.
There is no remaining placeholder commit in that function. Historical manifests
are preserved; they are not rewritten to imply newer source was tested.

This audit covers the local implementation, including work absent from GitHub.
The previous goal turn made progress: a real provider smoke passed and preserved
new evidence. The present turn resumes engineering, with no new inference approval.

## What works

- Deterministic integer-time scheduling, observation filtering, replay, ownership
  checks, and competent fixed FIFO/estimate baselines.
- SQLite compare-and-swap session, mailbox, provider-reservation, and promotion
  records. Parent and descendant model calls share the same budget ledger.
- Content-addressed Clojure artifacts, structural patches, stale-parent refusal,
  paired development comparisons, and controller-owned activation.
- Actual Docker/SCI positive control and nine negative tests for the pinned image.
- **LIVE MODEL RUN:** `var/runs/smoke-1793049211459/report.json`. Twelve checks
  passed: external context, root SCI, real recursive child inference, child SCI,
  and parent consumption. Six provider receipts total 12,455 input and 509 output
  tokens. The $0.03 figure is API-rate equivalent; subscription billing is unknown.

## What has only mock or fixture evidence

Acquisition, accepted skill retention, learned workflow use, sealed evaluation,
cold boot, and artifact removal have developer fixtures. Crash tests use scripted
provider transport. They verify durable bookkeeping, not network exactly-once
behavior. The old retained scheduler's 82.67 ticks versus the estimate baseline's
81.22 ticks is a fixture result and does not support learned superiority.

Baseline commands from this checkout:

```text
make test
48 tests, 751 assertions; 0 failures, 0 errors
python3 -m unittest discover -s test_python -v
37 tests; OK; 68.988 seconds
```

These counts precede the new language-backend tests. Later counts belong in
`PROGRESS.md`. No experimental model has produced an independently promoted
retained skill. No held-out or cold-boot learning benefit has been established.

## Language boundaries and reuse

Reuse the simulator, controller/store, provider reservation protocol, message
transport, trace records, and promotion transaction logic. They do not need a new
scheduler, agent controller, or memory database.

The execution calls in `runtime.clj` previously opened SCI directly. The new
`execution.clj` interface routes those calls to SCI or an isolated Python worker
from `:execution-language`. The existing SCI default is retained. Both workers
use the same Docker supervisor and limits. The Python worker supports real AST
manipulation, compile/exec, higher-order functions, classes, and generated modules.

The follow-up artifact implementation addresses these baseline gaps:

1. `artifact.clj` now supports Python source/AST consistency, fixed exported arity,
   structural patches and shared dependency validation. Python parsing occurs in
   a separate verified syntax worker. Both acquisition fixture arms pass.
2. Executable loading routes through `execution.clj`. Bundle schema 2 supports
   language-specific forms and restores fresh identities. Full cold-boot fixture
   evidence is tracked in `LANGUAGE_ARTIFACTS.md`; the first SCI attempt timed out.
3. `:command-format :json` provides common control commands and instructions with
   language appendices. Legacy EDN remains the default for old experiments. Live
   prompt behavior is still unverified.
4. A controller-owned `:verified-cases` promotion objective complements the old
   scheduling rule. Benchmark-family integration and full four-condition learning
   remain unfinished; adding a rule does not establish learning.

The four-condition learning experiment is not implemented merely because both
execution backends exist.

## Risks to experimental conclusions

- Old hypothesis labels conflict with the new research specification. Old H1 is
  retention; old H2 is cold boot; old H3 is language. New H1 is language, new H2 is
  executable learning, and new H3 is full Aljure versus Prime. Keep old records
  intact and use the new labels only with the research protocol.
- SCI disables user macros and dynamic eval. Python's AST/compile APIs are more
  expressive in some directions. Record this asymmetry; do not present it as
  language-only parity without a bounded equivalent contract.
- Python import restrictions are defense in depth, not a secure interpreter.
  Introspection can defeat them. Isolation relies on the container, no host
  mounts/credentials/network, and enforced resource bounds.
- The current context broker returns small record slices. It does not yet provide
  direct worker-side handles for processing a 128K-token context without routing
  each slice through the model. The existing OOLONG importer is not a live adapter.
- Prime includes child usage in parent aggregates. Counting both double-counts
  inference. Refinement and compaction also need individual accounting.
- Subscription transport adds a CLI layer and cannot establish invoice-level
  parity with native Prime's API provider. Local compute prices are also unknown.
- Four scripted paired cases are engineering checks. No model comparison,
  acquisition-run replication, sealed final result, or learning curve follows.
- Prime's native kernel is not a sandbox. Do not run generated Prime code on the
  host or mount controller answers, credentials, or a Docker socket into it.

The highest-value next work is completing the artifact/JSON fixture validation,
then the isolated native Prime adapter and common provider budget gateway.
