# Skill discovery v2: offline controls stopped at startup

**FIXTURE — no new model calls, no selection-performance result.**

The registry and four-condition control runner are implemented. The actual SCI
run stopped on its first task, before any policy loaded. Fifteen slots remain
unattempted. It was not resumed or rerun. There is no evidence yet that descriptions,
deterministic reuse, or a learned selector improve results.

## Implemented and checked

The [Prime audit](PRIME_SKILL_DISCOVERY.md) covers pinned commit
`c4c238ca025e382d96fb5f37e6328ca77fb82ef3`. Its checkout remains clean.
Useful lessons are compact routing descriptions, explicit callable interfaces,
on-demand implementation details, and separate proposal/validation/persistence.
No upstream code was copied or changed.

Aljure now exposes `skills/list`, `skills/describe`, and `policy/select`.
The registry contains names, descriptions, applicability, interfaces, provenance,
version hashes, evidence and limitations. Interfaces/provenance come from verified
artifact envelopes; evidence counts come from a hash-pinned independent diagnostic.
Behavioral descriptions are source-reviewed controller configuration, scoped to an
exact hash. They are not inferred from the model's claims. Unknown hashes receive
only a derived interface description. Metadata never approves executable code.
Only the session's approved dependency closure is selectable. Full code remains
available through `artifact/inspect`.

The source audit identified a real limitation: the retained policy tests only
CPU and memory. New GPU constraints use the existing simulator's resource rules.
Trusted compiled controls verify that those workloads are solvable and invalid
dispatches fail. Actual retained-policy performance on these GPU cases remains
**UNVERIFIED** because execution stopped before reaching them.

Regression suite: **70 tests / 1,496 assertions passed**. Additional control
suite: **2 tests / 29 assertions passed**. The latter covers correct/incorrect
solutions and distinct startup/loading/execution/algorithm failure attribution.
An initial test-double mistake produced five failed assertions; the log is
preserved, and the corrected backend double passed. These tests are not learning
results. Both suites are now part of `make test`.

## Frozen run and exact failure

| Field | Value |
|---|---|
| Source | `d347ba4d823313cf04463a717994deb1eb0c8d51`, clean at freeze |
| Source hash | `d365a07dab1426b5337756e9b04961e689dd0088f6ec03d52ce64ca142778e4c` |
| Run | `var/diagnostics/skill-discovery-v2-controls` |
| Target live model | `claude-sonnet-5-5`; not invoked |
| Actual provider | `fixture-script-v1` |
| Worker | `sha256:508f6f195f8837324f2c52ec87b193eb7fc79334de8948ff300b8585df03b37a` |
| Cases | New seeds 840100–840103; four arms, 16 slots |
| Attempt | `opaque-hash-0`, supervisor PID 18698 |
| New calls/tokens/equivalent spend | **0 / 0 / $0** |

The opaque fixture executed three scripted provider turns: context query,
task-local source installation, and finish. These are not model inference.
It submitted the developer fixture policy; the worker never loaded it.
The first readiness request was `(+ 20 22)`. The supervisor wrote it at
309.501 ms and reported `Worker wall-time limit` at 10,407.044 ms. The container
was still running and `OOMKilled=false`. Cleanup was confirmed at 10,777.421 ms.
Attach exit 137 followed forced cleanup; it does not establish an OOM event.
Total task time was 16.150 seconds. No code-loading or function invocation occurred.

| Condition | Planned | Attempted | Completed | Actual retained calls |
|---|---:|---:|---:|---:|
| Opaque hash | 4 | 1 | 0 | 0 |
| Descriptive discovery | 4 | 0 | 0 | 0 |
| Deterministic reuse | 4 | 0 | 0 | 0 |
| Model-authored selection | 4 | 0 | 0 | 0 |

Makespan, amortized dollars per verified solution, and relative efficiency are
undefined with zero verified solutions. Local-compute dollars are unknown.
The model-authored arm has only a developer selector stand-in for offline wiring;
no model selector was generated, accepted, or evaluated. No learning claim applies.

## Isolation proof audit: readiness remains blocked

The legacy gate printed `TESTED`, after one positive control and nine negative
attempts. Subsequent read-only audit found an important qualification:
`scripts/isolation.py:280` accepts **any nonzero worker exit** as a negative-test
pass. The positive control runs in a different container. Thus a negative worker
that never becomes ready can be falsely counted as a successful restriction test.

The process and network tests produced no SCI response and ended at the response
deadline. Loop/allocation also have no preceding readiness response, so their
timeouts alone cannot distinguish intended resource enforcement from failed
startup. Other cases have explicit response/output-limit evidence. The gate log
is preserved as what the old checker reported, not as complete isolation proof.

The active `var/isolation-proof.json` was moved, unchanged, to
`var/analysis/skill-discovery-v2/legacy-proof-invalidated.json`. This makes
`require-tested!` refuse subsequent generated-code runs until valid evidence is
restored. The checker itself remains unchanged in the frozen source. It needs a
same-worker positive handshake before each negative request; request-time limits
and cleanup must remain enforced. Do not regenerate or restore the legacy proof
and treat it as readiness. This finding does not demonstrate an isolation escape.

Docker reports 10 CPUs and 8,218,034,176 bytes of VM memory. That does not explain
why this JVM failed to answer within 10 seconds. The precise startup bottleneck
remains unresolved; no limits, image, source or scoring were changed during the run.
No worker container or quarantine marker remained after cleanup.

## Evidence and reproduction

- [Manifest and prompt/config hashes](evidence/skill-discovery-v2/manifest.json).
- [Complete report and unattempted slots](evidence/skill-discovery-v2/report.json).
- [Frozen registry](evidence/skill-discovery-v2/catalog.json).
- [Worker audit](evidence/skill-discovery-v2/repl-lab-fea235f228b3482ebc09850dfd007226.json).
- [Gate audit](evidence/skill-discovery-v2/gate-audit.json),
  [legacy output](evidence/skill-discovery-v2/isolation.log),
  [preserved invalidated proof](evidence/skill-discovery-v2/legacy-proof-invalidated.json).
- [Regression checks](evidence/skill-discovery-v2/regression-tests.log),
  [failed test attempt](evidence/skill-discovery-v2/control-tests.log),
  [corrected tests](evidence/skill-discovery-v2/control-tests-fixed.log).
- [Source/evidence integrity](evidence/skill-discovery-v2/verification.json),
  [recorded-failure replay](evidence/skill-discovery-v2/replay.log),
  [33-file raw archive](evidence/skill-discovery-v2/archive.json).

All **88 frozen source files** still matched at verification. All **1,369 previous
evidence files** remained unchanged. The saved failure independently replays.
The archive contains raw SQLite/session events, candidate source, world definitions,
the manifest, worker diagnostics, and test logs. Archive contents were hash-checked.

Executed command, from `repl-lab/` (historical; do not rerun this sealed path):

```sh
source var/worker.env
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/skill-discovery-v2-controls/workers" \
  make skill-discovery-fixtures OUT=var/diagnostics/skill-discovery-v2-controls
```

The [v2 protocol](SKILL_DISCOVERY_V2.md) separates metadata engineering, fixed
reuse, policy transfer, autonomous reuse and learned routing. A real selector must
beat simpler alternatives on new unseen cases with all acquisition costs included.

**One recommended next experiment:** a versioned, no-inference worker-readiness
diagnostic with a fixed series of fresh containers and a positive handshake in
each negative-test worker. Keep the same image and limits; record startup latency,
per-request outcomes and cleanup. First make the gate reject startup failures,
then identify the startup bottleneck. Do not resume this selection run, authorize
more inference, or start Prime benchmarking on the present evidence.
