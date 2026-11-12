# Head-to-head v8 audit: harness, data and capability state (2026-11-04)

Read-only audit of the paired benchmark harness and the four benchmarks named in
the 2026-11-04 brief (OOLONG-Pairs, OOLONG 8K/32K/128K, OBLIQ-Bench, LongBench
Pro), made before `HEAD_TO_HEAD_V8_PROTOCOL.md` was frozen. No inference, no
held-out data. Companion records: `PRIME_PARITY_MATRIX.md`,
`BENCHMARK_VALIDITY_AUDIT.md`, `BENCHMARK_SUITE_MATRIX.md`,
`HISTORICAL_PERFORMANCE_AUDIT.md`, `RESEARCH_SCORECARD.md`.

## 1. Where the head-to-head stands

22 paired Aljure-against-Prime runs exist (450 arms, $58.6). Every one is a single
run of its plan; no paired plan was ever run twice. The last Sonnet 5.5 runs:

| Run (2026) | Suite | Contexts | Aljure | Prime | Cost A / P | p50 s A / P |
| --- | --- | --- | --- | --- | --- | --- |
| synth-indep-32k-dev, 10-29 | OOLONG-synth 32K, 21 tasks | 7 | 0.768 | 0.800 | $0.815 / $1.590 | 22.1 / 24.1 |
| sci-ablation-speed-64k (A1c), 10-29 | OOLONG-Pairs 32K, 10 tasks | 1 | 0.845 | 0.862 | $0.831 / $0.947 | 34.4 / 39.5 |
| sonnet-ten, 10-28 | OOLONG-Pairs 8K, 10 tasks | 1 | 0.847 | 0.965 | $0.645 / $0.717 | 73.2 / 42.5 |

The only cross-context result is inconclusive (−0.031, 95% interval
[−0.174, +0.111]); its pre-registered development target was met (not inferior,
cheaper, faster). Under Opus 5.5 Aljure was inferior on accuracy in four plans
while costing 42–51% of Prime. Since 10-29 the harness changed in 49 commits
(`0c4c2d5` latency fixes: prewarmed worker 1.15 s, ledger 0.18 s per step; the
Q-SUBSTRATE and reuse work), none of them measured against Prime. The Aljure
failure modes seen live, in order of appearance and fix: text-command markup
(V3–V7, fixed by native tool calls `a965bd9`), worker cold start inside the
expression limit (fixed `1a570af`), ledger parse cost (fixed `0c4c2d5`), raw
SCI output overflow (fixed by the bounded surface), single-reply answer
delivery (fixed by paged delivery).

## 2. Harness capabilities (benchmark/paired.py and companions)

Present and reused unchanged by the v8 driver:

- **Identical settings, enforced.** `gateway.clj` `validate-request!` rejects any
  request whose model, `max_tokens`, thinking or effort differ from the pin, for
  both arms; the response model is checked; `oolong.compare` requires identical
  contract rows. Caveat: `max_tokens` is enforced as an upper bound; both arms
  have sent 32,768 in every recorded run.
- **One transport and ledger.** Both arms go through the same OAuth subscription
  transport, gateway reservation and `account()`; cost is API-rate-equivalent;
  unknown outcomes keep their reservation and stop the run.
- **Interleaved pairs, failures kept.** Both arms of a task run back to back;
  every planned arm must have a row; failures score 0.
- **Isolation.** Both arms in Docker on the same VM with the same create args
  (256 MiB, 1 CPU, 32 PIDs, no network, read-only root). Aljure's controller and
  gateway run on the host (parity row 4, disclosed).
- **Scorers.** Vendored, harness-blind, pinned: Pairs F1 AST-identical to
  Prime's; synth `synth_process_response` primary.
- **Gates.** Docker state before and after each arm, SCI and native isolation
  proofs, relay fixture, credential metadata, host policy v1 (swap, memory,
  images, probe, lock, monitor).

Missing before this audit, added by `benchmark/headtohead.py`:

| Brief requirement | State before | Added |
| --- | --- | --- |
| Randomized arm order, seeds | Deterministic alternation by index; no seed | Seeded, balanced per suite; seeded task order across suites; recomputed at every plan read |
| Repeats across seeds | None; duplicates rejected | Seeded 20% of tasks run twice in fresh sessions; trials averaged within task before pairing |
| Resume without exclusion | None; any stop ends the run; unattempted arms recorded as `error`/`ValueError` | Explicit `not-attempted`; `--resume` continues under the same plan after new gates; `resumes.jsonl` |
| p50/p95 latency, tool failures, timeouts | Only in the offline audit; driver wall time includes Docker probes; tool errors only in `scripts/` heuristics | Per-row agent wall, time to first request, model time, tool calls and errors from both arms' traces, HTTP errors; p50/p95 in the report |
| Paired differences | Mean, W/T/L, sign test; 2,000-resample bootstrap task-weighted | Context-weighted estimate, 10,000-resample cluster bootstrap, 95% and 90% intervals, TOST decision, exact McNemar, paired cost and latency differences, repeat variance |
| Pareto | Specified in `FRONTIER_AND_ROADMAP.md` §5 only | Per suite and harness: (score, cost per task, p50) with dominance flags |
| Multi-suite plan | One suite per plan | One plan binds several pinned suites with per-suite exposure disclosure |
| Launcher | `run_guarded.py` knew substrate, causal, economics | `h2h` entry with `--resume`; plan carries `configs` for the host gate |

Known accounting and parity gaps that remain (disclosed, not fixed): declared
rather than observed `model_config` rows; streaming Prime against non-streaming
Aljure; Prime's retry behaviour on relay 429 unverified; Prime's own usage
counters untrusted (the gateway ledger is the source of truth).

## 3. Benchmark data

| Benchmark | On disk | Importer and scorer | Exposure | Verdict for v8 |
| --- | --- | --- | --- | --- |
| OOLONG-Pairs | 8K and 32K contexts and gold (pinned); 128K context used by Aljure-only pilots | `prepare-official --suite oolong-pairs`; vendored Prime F1 | One context per length; 8K exposed 6+ times, 32K 3 times, 128K in Pilot 1/1b. **No unexposed Pairs context at 8K, 32K or 128K.** | Development and regression only (pairs32, 3 tasks in pilot 1). 64K+ contexts could be downloaded as new one-context suites; low value for inference (one context each). |
| OOLONG-synth 8K | Test windows …009/…010 of 7 datasets in pinned shards; agnews absent | New profiles `independent-dev:8192` (…010, 12 tasks, 6 contexts) and `independent-heldout:8192` (…009; shards 7, 10, 15 pinned, not downloaded) | Never run by any harness | **Pilot 1 (unexposed) plus a sealed held-out** |
| OOLONG-synth 32K | Dev suite `b157ee63` (7 windows …016) and sealed held-out `c74547bd` (…017) | Existing | Dev run by both harnesses 10-29 and four Opus plans; held-out untouched | Pilot 1 regression anchor (7 tasks); held-out reserved for Phase B |
| OOLONG-synth 128K | negation 40021/40022, yahoo 50021/50022, multinli 70021/70022 partly in pinned shards | New profiles `independent-dev:131072` (…021, 6 tasks, 3 contexts) and `independent-heldout:131072` (…022; shards 5, 22 pinned, not downloaded) | Never run | **Pilot 1 (unexposed; Prime's blog row is "OOLONG yahoo 128k")** |
| LongBench Pro | Absent | None; plan in `BENCHMARK_CAMPAIGN_PROTOCOL.md` §6 step 3: HF `caskcsg/LongBench-Pro` @ `4996884d`, 531.5 MB JSON, port `modules/evaluation.py` metrics without T4 | Never opened | Pilot 2 after an offline importer and scorer port; first held-out suite (484 independent English contexts) |
| OBLIQ-Bench | Absent; zero mentions in the repo before this audit | None. Data: HF `dianetc/OBLIQ-Bench` (CC BY 4.0), five retrieval tasks; Prime's row is "OBLIQ-Bench (math), long ranking, nDCG@10" on the Math Meta-Program subset (151 queries, 3,508 documents, about 316 characters each, 13.5 gold positives per query). Prime's environment is not in its public `research-environments` repository. | Never opened | Pilot 2 with our own task framing (whole corpus as context, ranked top-10 ids per query, nDCG@10 on gold qrels with `per_query_excluded_ids`); disclosed as not Prime's port |

The `acquisition` proofs in `var/` concern executable-learning skill acquisition,
not benchmark data; data integrity is the lockfile's size and SHA-256 per
artifact plus `validate_provenance`.

## 4. Capability mismatches to state before any comparison

From `PRIME_PARITY_MATRIX.md`, unchanged: substrate (CPython with libraries and
files against SCI), harness prompt size, compute boundary (host controller
against one container), per-expression timeout (10 s against none), per-call
output handling (bounded surface against character truncation), context
overflow (Prime's compaction cannot trigger under the 1 MiB request bound),
subagents and refine (available to Prime, unused so far). Pilot 1 keeps all of
them and records whether Prime used spawn, refine or compaction per arm.

## 5. What this audit changes in the plan of record

- Pilot 1 (`HEAD_TO_HEAD_V8_PROTOCOL.md`): 28 tasks over four OOLONG suites,
  68 arms, about $5.5, seeded order and repeats, Sonnet 5.5 first.
- Pilot 2 (not frozen): OBLIQ-Bench math and LongBench Pro development
  contexts after their importers pass offline checks.
- Phase B (not frozen): sealed held-out suites at 8K, 32K and 128K plus the
  LongBench Pro held-out split, sized from pilot 1's per-suite variance.
- Opus 5.5 is evaluated separately after Sonnet, under the same frozen inputs.
