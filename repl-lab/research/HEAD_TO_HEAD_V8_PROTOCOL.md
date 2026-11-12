# Head-to-head v8: Aljure against native Prime, development pilot 1

Version `head-to-head-v8-pilot-1`. Frozen before any model call. No live run is
authorized by this file; the run needs the owner's approval of the exact plan
hash through `var/host-policy-20261103/run_guarded.py h2h --approve <hash>`.
Companions: `HEAD_TO_HEAD_V8_AUDIT.md` (harness and data audit of 2026-11-04),
`STATISTICAL_EVALUATION_PROTOCOL.md` (analysis rules, unchanged),
`PRIME_PARITY_MATRIX.md` (disclosed capability differences),
`BENCHMARK_CAMPAIGN_PROTOCOL.md` (phases and claim boundaries).

## 1. Question

Does the current Aljure match or beat the pinned native Prime agent on
correctness, cost, latency and reliability when both run the same model, the same
settings, the same tasks, the same budgets and the same deadline, with Aljure's
learning disabled? This pilot is Phase A (development): it validates the
multi-suite driver, the new 8K and 128K OOLONG-synth inputs, the repeat and
resume mechanics, and the per-suite cost and variance that size the held-out
evaluation. It supports no held-out or superiority claim.

## 2. Arms

| Arm | Harness | Fixed by |
| --- | --- | --- |
| aljure | Aljure controller at the plan's source commit: provider-native tool calls (`native-tool-v1`, one correction per task), assisted and bounded 64 KiB SCI surface, paged answer delivery, prewarmed worker, `aljure_contract {}` (no artifacts, acquisition, programs or skill interface; empty retained library, so learning is disabled), SCI image `40f00364…` | `config/head-to-head-v8-sonnet.json`, `source.sha256`, `runtime_source`, `capabilities` in the plan |
| prime | Native Prime commit `c4c238ca…`, classic-store image `f3e30aaa…`, unchanged; its skills, subagents, refine and compaction stay available | `prime_commit`, `execution_images.prime` |

Identical for both arms, enforced on every request by the gateway: model
`claude-sonnet-5-5`, adaptive summarized thinking, effort medium,
`max_tokens` 32,768, documented rates, the Claude subscription OAuth transport,
16 calls per arm, $12 per arm, 240 s per task, 1 MiB request bound, 4 MiB task
output bound, one fresh session per arm. Both arms get the identical public
context (Prime at `/work/context.txt`, Aljure as the `external-context`
binding) and the identical question text. The deadline is 240 s rather than the
120 s of the October runs because the 128K contexts are new; the change applies
to both arms and is recorded in the plan.

Capability differences that are not removed (`PRIME_PARITY_MATRIX.md`): Prime's
persistent CPython kernel with libraries and a filesystem against Aljure's SCI;
Prime's 29.8K-character harness prompt against Aljure's 1.8K; Aljure's
orchestration on the host against Prime's single 256 MiB container; Aljure's
10 s per-expression limit. The compute-boundary confound (row 4) is disclosed,
not fixed, in this pilot.

## 3. Inputs

All inputs are pinned official data imported through `benchmark/official.py`
from `benchmark/upstream.lock.json`; gold stays controller-side; the agents
never see label-augmented context.

| Suite | Source | Tasks | Independent contexts | Selection rule | Exposure |
| --- | --- | --- | --- | --- | --- |
| synth8 `805f3673…` | OOLONG-synth test split, 8K, windows …010 of negation, formality, imdb, app_reviews, yahoo, multinli (new profile `independent-dev:8192`) | 12 | 6 | all | unexposed |
| synth32 `b157ee63…` | OOLONG-synth test split, 32K, windows …016 (existing dev suite) | 7 | 7 | one per context, seeded | development, run 2026-10-29 by both harnesses |
| synth128 `556cb6bc…` | OOLONG-synth test split, 128K, windows …021 of negation, yahoo, multinli (new profile `independent-dev:131072`) | 6 | 3 | all | unexposed |
| pairs32 `e4f4e52a…` | OOLONG-Pairs 32K validation context (existing ten-task suite) | 3 | 1 | seeded sample of 3 | development, run 2026-10-28/29 three times |

Held-out counterparts are pinned and sealed, not prepared: `independent-heldout:8192`
(windows …009) and `independent-heldout:131072` (windows …022) need shards 5, 7,
10, 15 and 22, which are pinned by size and SHA-256 but not downloaded; the 32K
sealed suite `c74547bd…` is untouched. OOLONG-Pairs has one context per length
and every 8K, 32K and 128K context is already exposed, so Pairs is a development
and regression suite only. Scorers: the vendored OOLONG-synth
`synth_process_response` and the vendored Pairs F1, AST-identical to Prime's
pinned `research-environments` scorer (`python3 -m benchmark audit` reports no
violation).

## 4. Order, repeats, resume

- 28 tasks; a seeded 20% (6 tasks) run twice in fresh sessions; 34 items, 68 arms.
- Task order: one seeded shuffle across suites (interleaved).
- Arm order: within each suite exactly half the items run Aljure first; the
  assignment is seeded. The two arms of an item run back to back.
- Seed `2026110405`, recorded in the plan; the sequence is recomputed and
  compared at every read of the plan.
- Every planned arm gets a row. A timeout, error or missing answer scores 0 and
  does not stop the run. Only infrastructure failures stop it
  (`DockerNotReady`, `DockerRestartedDuringArm`, `ProviderOutcomeUnknown`,
  `IsolationPreflightFailed`, `GatewayCleanupFailure`, `IncompleteAccounting`);
  the remaining arms are recorded `not-attempted`, and `--resume` continues from
  the first such arm under the same plan hash after a new preflight and host gate.
  Nothing is excluded or re-run silently; resumes are logged in `resumes.jsonl`.

## 5. Measures per arm

Status (`completed`, `timeout`, `error`, `not-attempted`) and failure code;
official score; API-rate-equivalent cost with complete accounting; model
calls; input, output, cache-read and cache-creation tokens; agent wall time
(`execution.json`), driver wall time, time to first model request, model
request time; tool calls and tool errors (Aljure: tool results whose status is
not ok, plus command rejections; Prime: `toolResult` with `isError`, a
non-ok status or a traceback, plus assistant stop errors); HTTP errors;
cleanup confirmation; Docker state before and after.

## 6. Pre-registered analysis (per suite; `research/STATISTICAL_EVALUATION_PROTOCOL.md`)

- **Primary:** context-weighted mean paired deadline-aware score difference,
  Aljure minus Prime, repeats averaged within (task, harness) first; 10,000-resample
  cluster bootstrap over contexts, seed 0; 95% and 90% percentile intervals;
  decision superior / inferior / equivalent (90% interval within ±0.05) /
  inconclusive. Suites with fewer than 5 contexts (synth128, pairs32) report no
  interval. Suites are never pooled for the primary.
- **Secondary, descriptive:** task-weighted mean difference, wins/ties/losses,
  exact sign test, exact McNemar on success at 0.9, paired cost and latency
  differences, completion, timeout, infrastructure-failure and tool-error rates,
  cost per task, per success and per score point, latency p50/p95 (agent and
  driver), tokens, repeat variance (mean absolute score change between trials).
- **Pareto:** per suite and harness, the point (mean score, cost per task,
  agent p50 latency) with dominance flags. Single-run points; the spread comes
  from the repeated tasks only.
- **Failure attribution:** every non-completed arm by status and failure code,
  with tool-error counts; the trace review names the mechanism per failed arm.
- No claim from this pilot beyond "the harness works end to end on these
  lengths" and the per-suite cost and variance estimates. A suite with more than
  10% infrastructure failures in either arm is reported and not interpreted.

## 7. Cost and safety

| Item | Value |
| --- | --- |
| Arms | 68 |
| Expected spend | about $5.5 API-rate-equivalent (range $3.9–9.9; per-arm priors: synth8 $0.035/$0.060, synth32 $0.039/$0.076, synth128 $0.12/$0.20 guessed, pairs32 $0.083/$0.095, Aljure/Prime) |
| Hard caps | $12 per arm; 16 calls per arm; $816 reservation ceiling; aggregate reserve refused when spend plus $12 would exceed it |
| Deadline | 240 s per arm; 10 GiB disk floor; host gate (swap, memory, Docker session, pinned images, SCI probe, credential ≥ 1 h) |
| Data | development suites only; no held-out suite is opened |

Billing is the Claude subscription; the invoice is unknown. The gateway reserves
the full context bound per call, which throttles Prime's asynchronous children
(parity row 3b); Prime has not used them in any recorded run.

## 8. Commands

```
python3 -m benchmark.headtohead plan --out var/h2h-20261104/plan.json      # freeze; no inference
python3 -m benchmark.headtohead preflight --plan var/h2h-20261104/plan.json
python3 var/host-policy-20261103/run_guarded.py h2h --approve <plan_sha256>  # owner only; paid
python3 var/host-policy-20261103/run_guarded.py h2h --approve <plan_sha256> --resume
python3 -m benchmark.headtohead report --out var/h2h-20261104/run-1
```

Freeze from a clean committed checkout; any commit outside `var/` voids the
plan. Results go to `HEAD_TO_HEAD_V8_RESULTS.md`; evidence is archived in a
separate later commit.

## 9. After the pilot (not frozen here)

Pilot 2 adds OBLIQ-Bench (Math Meta-Program subset: 151 queries over 3,508
documents, nDCG@10 on gold qrels with per-query exclusions; our own task
framing, since Prime's environment is not public) and LongBench Pro (English
without T4; 10 development contexts) once their importers and scorers pass
offline checks. Phase B is the held-out evaluation on the sealed suites and the
LongBench Pro held-out split, sized from this pilot's per-suite variance.
