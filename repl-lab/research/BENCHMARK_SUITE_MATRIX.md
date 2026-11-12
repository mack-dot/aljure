# Benchmark suite matrix

Candidate official suites for the campaign. Facts are from a read-only source
audit (2026-10-28); context counts marked ✓ were recounted locally from
downloaded metadata. "Prime result" is the Prime Agent blog table
(primeintellect.ai/blog/prime-agent, Aug 2026). It uses other models at high
reasoning, gives no task counts or seeds, and says its tech report
(arXiv 2608.23552) has no uncertainty intervals. **Never compare our Sonnet 5.5
scores with those numbers.**

| Suite | Official source and pin | License | Size | Independent contexts | Scorer | Prime result (Opus 5, Prime vs Claude Code) | Implementation | Fit and biases |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A1. OOLONG-Pairs** | HF `mit-oasys/oolong-pairs` @ `d1e1522b`; contexts from `oolongbench/oolong-synth` @ `81d2f8d9` | MIT | 20 questions × 11 lengths (1K–1M) | **1 per length** (one `trec_coarse` validation window) | Pair F1, vendored, AST-identical to Prime's `research-environments` @ `ba10ef5a` ✓ | .929 vs .922 (length unstated) | importer (first 1 or 10), scorer, audit: **done** | Development and regression only. The 20 questions are correlated. The upstream loader relies on file order (window 8 at 128K); pin both revisions. |
| **A2. OOLONG-synth** | HF `oolongbench/oolong-synth` @ `81d2f8d9`; scorer `abertsch72/oolong` @ `0bb7eabe` | MIT | 1,300 validation (spam, trec_coarse) + 5,200 test (8 datasets) | ✓ validation: 2 windows per dataset and length; ✓ test: mostly 2, **16 windows at 32K**. `context_window_id` is not unique across lengths, and windows share a source instance pool. | Original OOLONG `synth_process_response` (primary); Prime's `score()` disagrees on verbose answers (8/88 probes) | yahoo 128K: .900 vs .920 (not reproducible from the public config: the default split is validation, and yahoo is test-only) | importer pinned for 32K/128K negation (first 1 or 10): **partial** | Too few independent contexts for a primary claim. Use as a clustered secondary suite (≤ 16 per length) or as a Q-LEARNING task family, where the dataset shift is useful. |
| A3. OOLONG-real | HF `oolongbench/oolong-real` | MIT | 4,903 validation questions over 91 windows | ✗ The windows come from 42 episodes, and one episode appears in up to 31 windows. | OOLONG scorer | — | none | Heavy overlap; low independence. Not recommended. |
| **C. LongBench Pro** | HF `caskcsg/LongBench-Pro` @ `4996884d` (one 531.5 MB JSON); code `caskcsg/longcontext/LongBench-Pro` (license unverified) | Apache-2.0 (dataset) | 1,500 rows (750 English) | ✓ **English without T4: 690 rows over 484 contexts**: 8k 85, 16k 83, 32k 84, 64k 78, 128k 80, 256k 74. At most 8 questions share a context. | Official `modules/evaluation.py` + `utils.py`: NDCG, pairwise accuracy, accuracy, F1, SubEM (T4 needs ROUGE-L plus an embedding model) | English: .804 vs .790 | **none** | **Recommended first held-out suite.** Natural long contexts, many independent, deterministic scoring without T4. Lengths are counted in Qwen tokens. The official protocol is 3 runs; there are thinking and non-thinking prompts (pre-register one). Prime's own port is English without T4, the same subset. |
| B. LongCoT-Mini | `LongHorizonReasoning/longcot` (HEAD `fb96494`; `easy` split) | MIT | 507 problems (chemistry, CS, logic, math, chess) | every problem self-contained | `longcot.verify` (optional judge fallback for math and chemistry) | .722 vs .558 | none | The benchmark measures reasoning "without external tools"; a code-executing harness changes the task. Prime's environment pins a commit before upstream gold fixes (`75f3dc1`), drops 21 math IDs and adds a local fallback. Use the post-fix commit and disclose. |
| D. ManyIH (Coding / IF) | HF `jhu-clsp/ManyIH-Bench` @ `117d69a3`; code `JHU-CLSP/ManyIH` | MIT | Coding 427; IF 426 | Coding: 427 distinct MBPP problems; IF: 408 distinct system prompts | Coding: unit tests and style checks (all-or-nothing); IF: code checks plus an LLM judge (defaults to the evaluated model) | Coding .536 vs .522; IF .225 vs .175 | none | Short inputs (median about 2–4K characters), not long-context. Coding is cheap per independent item with a programmatic scorer, and fits Q-SUBSTRATE. No public Prime environment, so Prime's variant is unverified. |
| E. EmulatorBench | not public (cited as unpublished) | — | "16 emulator reconstructions" | — | — | .047* vs .062* | none | **Cannot be independently verified.** Excluded. |
| E′. Terminal-Bench 2.0 | arXiv 2601.11868; Prime environment `terminal_bench_2` (`research-environments` @ `e221a651`) | per task | 89 tasks, one container each | 89 | hidden Harbor verifiers | not in the blog table | none | Tool-heavy and independently verified, but needs a container per task. Set `ignore-timeouts false` for a faithful comparison. A newer version exists; pin 2.0. |
| **F. Executable-learning transfer** | in-house design on official task families (`EXECUTABLE_LEARNING_EXPERIMENT.md`) | — | about 28 tasks per run × 3 runs per arm | limited by OOLONG windows; use the dataset shift as a feature | official scorers plus invocation-trace evidence | — | arms A and C exist; B, invalidation and the reuse measures are missing | Aljure-only (no Prime counterpart). Primary test of the learning hypothesis. |

## Selection rules (pre-register)

- One question per independent context for primary analyses, chosen by a
  seeded shuffle of context hashes (seed recorded in the manifest), stratified
  by length. Never conditioned on answers or on earlier results.
- Separate development contexts (pilot, ablations) from held-out contexts
  **before** the first run, and record the split in the manifest.
- Use the official scorer, pinned by commit and hash, with a gold self-test
  (`python3 -m benchmark audit`) before use.
