# Historical performance audit: executable-policy learning to L0–L3

**Type:** read-only audit, 2026-10-29. No code changed. No inference, Docker
or held-out data was used.

**Sources:**
- Run directories: `plan.json`, `report.json`, per-arm controller events and
  gateway receipts in `aljure/repl-lab/var/{runs,evaluations,diagnostics,benchmarks}`,
  `aljure-sonnet-pair-v7/repl-lab/var/benchmarks` and
  `aljure-review-v1/repl-lab/var/benchmarks`.
- Committed summaries in `research/*.md` at `a1c2ce0`.
- Each run is counted once. Some directories exist in two checkouts.

**Units:**
- Cost is API-rate-equivalent through the Claude subscription. Invoices are
  unknown.
- "p50" is the median arm wall time.
- Activation counts Aljure controller tool-call events.
- Every paired plan is a clean checkout (`source.dirty = false`).

Companion memo: `RESEARCH_THESIS_REVIEW.md`.

## 1. Where the emphasis changed

| Commit | Date (local) | Change |
| --- | --- | --- |
| `3b905ff` | 10-26 13:35 | Thesis core. Retention (H1) and cold boot (H2) are the primary hypotheses |
| `213cf96` | 10-26 19:06 | Learning becomes H2. Language becomes H1. A Prime adapter and OOLONG appear as H3 |
| `bb20bb0` | 10-26 19:35 | Operator work order: acquisition, then reuse and cold boot, then learning curves, then *evolving* Aljure against Prime (`research/EXPERIMENT_PROTOCOL.md:9-19`) |
| `f9bf1d0` | 10-26 23:56 | First benchmark-integration commit (OOLONG imports, common Messages adapter) |
| `c474438` | 10-27 00:49 | First frozen Aljure-against-Prime plan |
| **`41a1610`** | 10-27 01:25 | **Last change to any artifact or learning code.** All 22 later live runs use an empty library (`benchmark/paired.py:579`) |
| `a965bd9` | 10-28 11:37 | Native tools. The model-facing surface has no artifact operations (`model_protocol.clj:105-138`) |
| `00390f6` | 10-28 15:45 | Operator brief: Prime comparison is H1 and learning is H3 (`research/STATISTICAL_EVALUATION_PROTOCOL.md:16-18`) |
| `41b53fa`, `9bb4c95`, `f59c0fb` | 10-29 | Semantic benchmark optimization: answer contracts, label, audit and review prompts |
| `51f10c4`, `d441ddf` | 10-29 | Orchestration: asynchronous children, compute-scaling and verification designs |

## 2. Chronological table

**Abbreviations:**
- A = Aljure, P = native Prime (`c4c238ca`), S = Sonnet 5.5, O = Opus 5.5.
- Plan hashes are 8-character prefixes.
- Scorers:
  - `sched`: the frozen simulator, scored by makespan.
  - `pF1`: the Pairs F1 scorer, `1f996086`.
  - `syn`: the OOLONG-synth scorer, `2d2f5ee0`.
- Suites:
  - `p8-1` = `e1491d5e`; `p8-10` = `90f719a5`; `p32-10` = `e4f4e52a`. Each
    Pairs suite uses **one context**.
  - `s32` = `b157ee63`: 7 contexts, 21 tasks.
  - `lc` = `dc164044`: label counts, 5 windows, 11 tasks.

| # | Date | Run (source; plan) | Objective | Bench, scorer, model | Completed A / P | Accuracy A / P | Cost A / P | p50 s A / P | Aljure activation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10-26 12:45 | `fixture-1793033138728` (before `3b905ff`) | Retention plumbing | sched, fixture | 9/9 | makespan: retained fixture 82.7; serial 209.6; FIFO 91.0; estimate 81.2 | $0 | — | Developer fixture; no model |
| 2 | 10-26 | `smoke-1793049211459` | Live recursion smoke | 12 checks, S | 12/12 checks | — | $0.03 (6 calls) | — | Context query, root and child SCI, child call |
| 3 | 10-26 | `artifact-parity-20261026-serial` (`213cf96` era) | Clojure and Python artifact parity | fixture | passed | cold 4/4 correct per language; fallback 0/4 | $0 | — | Staging, patch, composition (fixture) |
| 4 | 10-26 20:46 | First live (`7126edb`; source `4f5262ff`) | **Acquire and transfer a policy** | sched, S | acquisition 1/3 per arm; held-out frozen 0/8, evolving 5/8; cold frozen 0/8, evolving 3/8; **retained-direct cold 8/8** | **cold makespan 59.5 against 204.1** (direct); equal to the estimate baseline | $1.38 known + $1.18 reserved (139 calls) | — | 4 artifacts, 1 promoted pair; 565 direct invocations; **0 agent retrievals** |
| 5 | 10-26 22:18 | Policy diagnostic v1 (`087939e`) | Repeat transfer with healthy workers | sched, no model | 23/48 attempted; stopped at the readiness rule | healthy pairs 94.2 against 206.5 (−54.4%) | $0 | — | 1,186 retained invocations |
| 6 | 10-27 00:09 | Skill discovery v4 (`bf6c6a8`) | Reuse against adaptation | sched, fixture | 20/20 slots; blind reuse 2/4 | guard = scripted selector | $0 | — | Source inspection 0 |
| 7 | 10-27 01:22 | Selector acquisition (`c8b868b`) | Learned selector | fixture | — | — | $0 | — | No real selector |
| 8 | 10-27 | V1 (plan frozen `c474438`) | First A against P | p8-1, pF1, S | 0/1; P not dispatched | — | $0.005 | — | Receipt rejected (`usage.speed`) |
| 9 | 10-27 | V2 (`a5b71747`) | Repeat | p8-1, S | 0/1; P not dispatched | — | $0.010 + $4.33 reserved | — | Third request unknown |
| 10 | 10-27 | V3 (`7c06c68`) | Repeat | p8-1, S | 0/1 / 1/1 | 0 / 0.968 | $0.086 total | — | `Trailing EDN` |
| 11 | 10-28 | V6 (`2184b10`; `703dbecf`) | Repeat | p8-1, S | 0/1 / 0/1 | 0 / 0 | $0.026 / $0.062 | 30 / 35 | 2 command rejections |
| 12 | 10-28 | V7 (`7b0cfa7`; `9798e89e`) | Source blocks | p8-1, S | 0/1 / 1/1 | 0 / 1.0 | $0.028 / $0.069 | 33 / 39 | Tool-call markup rejected |
| 13 | 10-28 | Native tools (`a965bd9`; `78d14e14`) | Native tool calls | p8-1, S | 1/1 / 1/1 | 1.0 / 0.968 | $0.172 / $0.067 | 103 / 41 | 2 repl, 4 queries |
| 14 | 10-28 | Fair (`1a570af`; `6462f780`) | Caching, `done` source | p8-1, S | 1/1 / 1/1 | 0.968 / 0.968 | $0.051 / $0.065 | 43 / 32 | 3 repl |
| 15 | 10-28 | Ten (`9cc0812`; `35778799`) | 10 cases | p8-10, S | 9/10 / 10/10 | 0.847 / 0.965 | $0.645 / $0.717 | 73 / 43 | 36 repl; 0 children |
| 16 | 10-28 | Ten rerun (`87d5fda`; `5ef81410`) | Ledger fix | p8-10, S | stopped after case 4: 3 / 4 done | (0.293 / 0.385 over 10) | $0.22 / $0.29 | — | — |
| 17 | 10-28 | Ten32 (`1b99ef7`; `83fecbaa`) | 32K | p32-10, S | stopped after case 5: 1 / 4 done | (0.089 / 0.368) | $0.47 / $0.33, incomplete | — | — |
| 18 | 10-28 | SCI control (`79a3bd9`; `6ae7e225`) | Raw surface | p32-10, S | stopped after arm 1 | — | $0.045 | — | — |
| 19 | 10-28 | SCI control-2 (`40a24bd`; `50911e6b`) | Raw surface | p32-10, S | 3/10 / 8/10 | 0.176 / 0.680 | $0.79 / $1.09 | 115 / 55 | 49 repl |
| 20 | 10-28 | A1 (`13490b4`; `d5038fe2`) | Assisted + bounded | p32-10, S | 4/10 / 10/10 | 0.174 / 0.852 | $0.73 / $0.94 | 96 / 64 | 3 infrastructure failures |
| 21 | 10-28 | **A1c** (`dd98108`; `30654ed6`) | Latency, reader syntax | p32-10, S | **10/10 / 10/10** | **0.845 / 0.862** | $0.83 / $0.95 | 34 / 40 | 49 repl; 10 paged deliveries |
| 22 | 10-29 | Synth (`dfd82fb`; `0b6a0451`) | 7 independent contexts | s32, syn, S | 21/21 / 20/21 | 0.768 / 0.800 (inconclusive) | $0.815 / $1.590 | 22 / 24 | 65 repl; 9 rejections |
| 23 | 10-29 | Opus smoke (`56a3de4`; `a1d0d896`) | 12-call cap | 1 task, syn, O | 0/1 / 1/1 | 0 / 1.0 | $0.19 / $0.33 | — | Out of calls |
| 24 | 10-29 | Opus smoke, open (`f96f0fb`; `3a0ccea4`) | Open limits | 1 task, O | 1/1 / 1/1 | 1.0 / 1.0 | $0.38 / $0.90 | 154 / 149 | 2 children |
| 25 | 10-29 | **Synth Opus** (`f96f0fb`; `d6e9b40d`) | Same 21 tasks | s32, O | 19/21 / 21/21 | **0.771 / 0.919 (inferior)** | $1.73 / $3.82 | 26 / 29 | 70 repl; 6 rejections |
| 26 | 10-29 | Contract control (`41b53fa`; `87d8c949`) | Same configuration again | s32, O | 21/21 / 21/21 | 0.853 / 0.904 | $1.80 / $3.74 | 24 / 27 | 3 children |
| 27 | 10-29 | F1 (`52f51590`) | Truncation retry | s32, O | 21/21 / 21/21 | 0.876 / 0.898 | $1.64 / $3.95 | 30 / 34 | **0 retries** |
| 28 | 10-29 | F2 (`b1844732`) | Terminal-text answer | s32, O | 19/21 / 20/21 | 0.805 / 0.866 | $1.54 / $3.00 | 26 / 32 | **0 accepted** |
| 29 | 10-29 | L0 (`40270ba`; `def381f5`) | Baseline | lc, syn, O | 11/11 / 11/11 | 0.363 / 0.474 | $2.47 / $5.85 | 56 / 108 | 4 children |
| 30 | 10-29 | L1 (`240ce694`) | Label prompt + `show-items` | lc, O | 11/11 / 11/11 | 0.273 / 0.388 | $2.68 / $5.86 | 60 / 105 | `show-items` 0/11 |
| 31 | 10-29 | L2 (`51687387`) | + uncertainty audit | lc, O | 11/11 / 10/11 | 0.417 / 0.279 | $2.77 / $4.34 | 95 / 86 | **audit 0/11** |
| 32 | 10-29 | L3 (`20f25624`) | + targeted review | lc, O | stopped after arm 1 (`IsolationPreflightFailed`) | — | $0.57 | — | Not evaluated |

V4 and V5 were frozen but not run (isolation and image blockers).

**Inference totals:**
- Live learning (rows 2 and 4): about $1.4 known plus $1.3 reserved.
- Paired benchmark runs (rows 11–32, from reports): **$58.6**. Aljure
  $20.6, Prime $37.9, 450 arms.
- Artifact operations in all paired Aljure arms (225 planned): **0**. The
  library hash in every arm is sha256(`[]`).
- 0 of 176 finished Aljure arms answered without running code. The context is
  outside the window by design.

## 3. What each change was

**(1) Transport and runtime reliability.** This class is the largest source
of measured Aljure gains.
- Worker startup:
  - first-live held-out direct runs lost 7/8 to `Worker terminated without result`;
  - the diagnostic isolated a 10 s readiness timeout;
  - prewarm and AOT (`0c4c2d5`) cut cold start from 6–15 s to 1.15 s
    (`research/HARNESS_LATENCY.md`).
- Gateway receipts (V1), unknown transport outcomes (V2), the Keychain, and
  Docker image loss (V4–V6).
- Ledger parsing: 560 ms became 53 ms per read (`87d5fda`). The case-5
  timeout in row 15 came from this.
- Paged delivery (`274e225`) and the deadline dispatch floor (`40a24bd`).
- Rows 20 → 21: on the same suite, Aljure moved from 4/10 and 0.174 to 10/10
  and 0.845. Prime moved from 0.852 to 0.862. One run each, so the shares of
  runtime and of reader syntax (`4cf04c0`) cannot be separated.

**(2) Model-facing interface.**
- EDN envelopes failed in rows 10–12. Native tools then gave 1.0 (row 13).
- Plain-text string results (`87d5fda`) and the assisted surface (`79a3bd9`).
- Contract F1 never triggered. F2 lowered completion to 19/21.
- The L1 and L2 prompts had no attributable effect. Their helpers were not
  used (`research/REVIEW_ABLATION_DECISION.md:12-13`).

**(3) Evidence for reusable executable computation.** This exists **only in
the scheduling domain, rows 1–7**.
- One model-authored policy transferred after a cold restart: 8/8, −70.9%
  makespan against the serial control.
- The diagnostic repeated the effect: −54.4% on 11 healthy pairs.
- It **tied** a fixed heuristic, so the policy is not a new capability.
- The agent never retrieved it (`research/SKILL_REUSE_ANALYSIS.md:28`).
- Nothing was ever patched structurally.
- Rows 8–32 contain no evidence on this question, because the library was
  empty.

**(4) Evidence for semantic reasoning improvement.** None is attributable.
- Rows 25 and 26 have the same configuration but give Aljure 0.771 and 0.853.
  Prime gives 0.919 and 0.904. Run-to-run variance is about 0.08.
- In L0–L2, Prime alone moved 0.474 → 0.388 → 0.279. Its MAE moved 6.0 →
  8.6 → 11.8 (`research/CONTROLLER_VERIFICATION_DESIGN.md:28`).
- The Opus gap (row 25) is half delivery failures. Count bias is shared with
  Prime (r = 0.865).
- A1c replay: arms with rules followed by model review scored higher than
  rules-only arms. This is observational, on one context
  (`research/REVIEW_REPLAY_ABLATION.md`).

**(5) Results that cannot be compared:**
- Scheduling (rows 1–7) against OOLONG (rows 8–32): different domain,
  scorer and question.
- `p8-1`, `p8-10` and `p32-10` each have **one context**. Six runs reused the
  8K case 1. These suites are development evidence
  (`research/BENCHMARK_VALIDITY_AUDIT.md` §2, §4).
- Sonnet rows against Opus rows.
- The 12-call and 120 s limits against the open limits from `f96f0fb`
  (1,000 calls, 900 s).
- The `pF1` scorer against the `syn` scorer. The `lc` suite against `s32`.
- Stopped plans (rows 16–18, 32) have partial denominators.
- Harness contracts changed between rows 10–21: EDN → source block → native
  tools, and raw → assisted → bounded SCI.

## 4. Verdict on the code-as-data hypothesis

**Insufficiently tested.** It is neither disproven nor improved since 10-26.
- The only live test was one acquisition trajectory. Each arm completed only
  1 of 3 acquisition tasks.
- That test gave a positive transfer by direct execution, against a weak
  control. The transferred policy only equals a fixed heuristic.
- Agent-level reuse, structural transformation and cumulative improvement
  were never observed. They were never given a chance on a benchmark task.
- All later accuracy and cost changes come from reliability, interface and
  noise. Their cause is not accumulated computation.

## 5. The single smallest next experiment

Use the prequential A, C, E design from `RESEARCH_THESIS_REVIEW.md` §5.

**Step 0 (zero inference, first):**
- Replay the recorded A1c rule functions and parsers on other development
  `trec_coarse` windows, against item gold.
- If retained rules cannot decide a useful share of unseen items at high
  precision, the accuracy route is falsified at no cost.

**MF (live):**
- **Arms:** stateless (A), exact cache (C), and validated artifacts with
  structural improvement (E). The controller loads and applies the artifacts.
- **Sequence:** 20 tasks: 16 compatible and 4 incompatible. A cold restart
  after task 10.
- **Size:** 3 trajectories, Sonnet, 180 task runs.
- **Cost:** about $10–15, cap $40.
- **Endpoints:** activation and cost per verified solution, with acquisition
  included. No Prime arm.

The result is the first direct test of cumulative executable knowledge since
row 4.
