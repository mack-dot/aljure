# Benchmark validity audit (Aljure vs native Prime)

**Read-only audit and offline checks, 2026-10-28, at `178bfc3` on
`claude/sonnet-pair-v7`. No inference was run for this audit.** This file also
covers the `BENCHMARK_PRECHECK.md` deliverable of issue #1.

Run `python3 -m benchmark audit --out var/audit/<name>.json` to reproduce the
mechanical checks (`benchmark/audit.py`, tests in `test_python/test_audit.py`).
Related: `PRIME_PARITY_MATRIX.md`, `SCI_EXECUTION_CONTRACT.md`,
`STATISTICAL_EVALUATION_PROTOCOL.md`, `BENCHMARK_CAMPAIGN_PROTOCOL.md`.

## 1. Local state

- **Branch and remote.** `claude/sonnet-pair-v7` is pushed to `origin`. Commits
  after `29f0f61` are local.
- **Active experiments.** None. The SCI ablation's `bounded-64k` plan was frozen
  (`62b3fb23…`) but **not run**, because this brief stops paid inference.
  `assisted-64k` and `assisted-1m` were never frozen.
- **Proofs.** The clean execution checkout (`~/aljure-sonnet-pair-v7`) holds the
  proofs for `40a24bd`. `178bfc3` changed `scripts/isolation.py` (the
  per-language readiness probe), so both SCI isolation proofs and the native
  Prime proof must be regenerated before the next live run. Prime's gate
  digest includes that file.
- **Missing image.** The Python worker image (`sha256:a1a4367a…`) is absent from
  the local Docker store, so the Python backend cannot run until it is rebuilt.

## 2. Evidence inventory

Every recorded paired run, re-scored independently from its stored answers.
`reproduced` means scores, means, wins/ties/losses, the results hash and the
scorer hash all match the saved report.

| Run | Suite (contexts) | Aljure interface | Aljure mean | Prime mean | W/T/L | Accounting | Reproduced |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sonnet-pair-v6-live | pairs 8K, 1 task (1) | EDN text | 0 | 0 | 0/1/0 | complete | yes |
| sonnet-pair-v7-live | pairs 8K, 1 (1) | EDN + source block | 0 | 1.0 | 0/0/1 | complete | yes |
| sonnet-pair-native-tools-live | pairs 8K, 1 (1) | native tools | 1.0 | 0.968 | 1/0/0 | complete | yes |
| sonnet-pair-fair-live | pairs 8K, 1 (1) | + caching, done source | 0.968 | 0.968 | 0/1/0 | complete | yes |
| sonnet-ten-live | pairs 8K, 10 (1) | same | 0.847 | 0.965 | 2/3/5 | complete | yes |
| sonnet-ten-rerun-live | pairs 8K, 10 (1) | + ledger fix | 0.293 | 0.385 | 1/7/2 | complete; stopped after case 4 | yes |
| sonnet-ten32-live | pairs 32K, 10 (1) | same | 0.089 | 0.368 | 0/6/4 | **incomplete**; stopped after case 5 | yes |
| sci-ablation-control | pairs 32K, 10 (1) | raw SCI surface | 0 | 0 | 0/10/0 | **incomplete**; stopped after arm 1 | yes |
| sci-ablation-control-2 | pairs 32K, 10 (1) | raw SCI surface | 0.176 | 0.680 | 2/0/8 | complete | yes |
| sci-ablation-bounded-64k (A1) | pairs 32K, 10 (1) | assisted + bounded | 0.174 | 0.852 | 1/0/9 | complete; 3 Aljure infrastructure failures | — (added after this audit) |

**Every paired comparison so far uses one OOLONG context.** No run supports a
cross-context estimate (section 4). The 8K first case was reused in six runs.
The 8K and 32K ten-task suites were used to find and fix defects, so they are
**development evidence**, not held-out evidence.

## 3. Fairness checklist (brief §3)

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Same model, provider, effort, sampling, context limit | **Verified on the wire.** Both arms send `claude-sonnet-5-5`, adaptive thinking (summarized), effort medium and `max_tokens` 32768 through one subscription gateway, which enforces the pinned settings. Aljure is non-streaming and Prime streams. | `gateway.clj` `validate-request!`; request bodies in `stdout.jsonl` |
| 2 | Authentic pinned Prime | **Verified.** Commit `c4c238ca…` is built into image `f3e30aaa…`. The local checkout is clean at that commit. The adapter changes are listed in `PRIME_PARITY_MATRIX.md`. | `benchmark/prime/container.py`; Prime isolation proof (10/10) |
| 3 | Identical tasks and data; independent scoring | **Verified.** Both arms receive the same public input from one manifest. Scores are recomputed from stored answers by the pinned scorer, and all 9 runs reproduce. | `benchmark audit` |
| 4 | Equal time, token and USD ceilings | **Verified**, with a caveat. Both arms have 120 s, 12 calls, 12M tokens and $12 per arm. The conservative per-call reservation ($4.33) allows at most 2 concurrent requests, which would only throttle Prime's asynchronous children (unused so far). | `paired.gateway_config`; `gateway.clj` `reservation` |
| 5 | Complete accounting of all calls | **Verified** for root, child, compaction and refinement calls on one gateway ledger per arm. Since `40a24bd`, a request cut off at the deadline is recorded at its real cost, or released before dispatch, not left unknown. Two historical runs have incomplete accounting (unknown outcomes). | `gateway_client.py`; usage receipts |
| 6 | Comparable CPU, memory, process and startup accounting | **Not equivalent (confound).** Prime's whole agent loop, relay, Python kernel and children share one 256 MiB, 1-CPU container. Aljure's controller and gateway run on the host, and each SCI session gets its own 256 MiB, 1-CPU container. Startup counts toward the 120 s for both arms, but is measured differently. | `PRIME_PARITY_MATRIX.md` rows 4–4b |
| 7 | Equivalent deadlines and final-answer rules | **Mostly.** Both arms are killed at 120 s, and the gateway's floor and grace apply to both. Prime answers by writing `/work/answer.txt`, which is collected only after its completion event, so a killed arm loses an answer it already wrote. Aljure answers through `done`. Neither prompt states the deadline. | `paired.py`; `external_task.clj` |
| 8 | Capability differences documented | **Now documented** in `PRIME_PARITY_MATRIX.md`. `research/capabilities.json` and the `CAPABILITIES` text had drifted. | — |
| 9 | No leaked gold or scoring metadata | **Verified.** Public files carry no gold fields or gold text, and the arms receive only public input. One copy of `pairs-one` had a 0755 controller directory (its answers file was 0600). Corrected. | `benchmark audit` (suites) |
| 10 | No contamination through memory or artifacts | **Verified for the paired runs.** Every arm starts a fresh session; Aljure runs with learning off, one library state and a new controller store per arm; Prime gets a fresh `/work`. Model-side memory of earlier runs of the same public case cannot be ruled out. | results `fresh_session`, `learning_library_sha256` |
| 11 | Worker crashes handled; incomplete runs preserved | **Fixed in this branch.** Fixes cover worker retirement, safe close, events written after a failure, the cleanup race and the deadline cut-off. Every historical run is preserved unchanged. | commits `5bc996d`, `1b99ef7`, `40a24bd`, `79a3bd9` |
| 12 | Reproducible task selection | **Verified.** First-n selection in pinned upstream order, with hash-checked manifests. The selection cannot yet take **one task per independent context** (needed for section 4). | `benchmark/official.py` |

## 4. Statistical validity of existing evidence

All nine runs have **one independent context**, so a cross-context interval
cannot be estimated. Within one context, the strongest observed difference
(control-2: Aljure − Prime = −0.504, 2 wins, 8 losses) gives an exact sign test
of p = 0.11 over correlated questions. **No existing measurement supports a
claim of superiority, inferiority or equivalence between the harnesses.**

Run-to-run variance is material. On 8K task 1, Prime scored 0.968, 1.0, 0.968,
1.0 and 0.968 across runs. On 32K task 1 it scored 0.898 and 0.857.

## 5. Defects found by this audit

| Defect | Effect | Status |
| --- | --- | --- |
| Prime adapter forwarded every native `message_update` event (each repeats the whole partial message) | Filled the 4 MiB task-output bound; killed 2/10 Prime arms in the latest 32K run (≈70% of their stream) | **Fixed** `178bfc3` (marker kept; final message in `message_end`); needs a relay-fixture run before use |
| Supervisor readiness probe was EDN for both languages | Python worker would fail readiness since `1a570af` | **Fixed** `178bfc3`; unverified live (image missing) |
| Python isolation proof is not bound to the supervisor hash, has no boundary tests, accepts any non-zero exit | Python backend gate weaker than SCI gate | Open |
| OOLONG-synth: our scorer (original OOLONG) and Prime's environment scorer disagree on long answers without a colon (8/88 probes) | Different results for verbose answers | Open: pre-register the primary scorer (statistical protocol) |
| Learning promotion gain sums scores, so infrastructure failures inflate it (recorded gain 37,630) | Invalid acceptance evidence | Open (`EXECUTABLE_LEARNING_EXPERIMENT.md`) |
| Prime's auto-compaction cannot trigger: requests over 1 MiB are rejected first | Prime's long-run behaviour disabled | Open (documented confound) |
| Docker Desktop image-store switch removes "pinned" images | Runs blocked; Python image currently missing | Mitigated by the Docker gate; Python image open |
| `research/capabilities.json` and the `CAPABILITIES` text are stale | Documentation drift | Superseded by `PRIME_PARITY_MATRIX.md` |

## 6. Implemented, tested, unverified

| Area | Implemented | Offline tests | Live-verified |
| --- | --- | --- | --- |
| Native-tool command interface | yes | yes | yes (8K, 32K) |
| Assisted SCI surface, bounded results | yes | 51/51 real-worker contract checks at each bound | **no live model use yet** |
| 1 MB output bound | yes | isolation 9/9 and exact boundary | no |
| Worker retirement and recovery | yes | real broker and container check | yes (control runs) |
| Deadline floor and in-flight grace | yes | yes | yes (control-2 complete) |
| Python backend under one controller | partial | fixture only | **no** |
| Executable learning (A–D arms) | partial (A, C) | fixture | one acquisition run (n=1) |
| Independent-context selection | no | — | — |
| Other suites (LongCoT, LongBench Pro, ManyIH, tool suites) | no | — | — |
