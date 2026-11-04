# Head-to-head v8, Phase B: held-out OOLONG-synth, Aljure against native Prime

Version `head-to-head-v8-phase-b`. Frozen before any model call; the plan hash binds
this file. **Not authorized by this file.** The run needs the owner's approval of the
exact plan hash through `var/host-policy-20261103/run_guarded.py h2h-b --approve <hash>`.
Companions: `HEAD_TO_HEAD_V8_PROTOCOL.md` and `HEAD_TO_HEAD_V8_RESULTS.md` (pilot 1,
"Lot 1", immutable), `HEAD_TO_HEAD_V8_READINESS.md` (what changed since Lot 1,
equivalence evidence, unresolved risks), `STATISTICAL_EVALUATION_PROTOCOL.md`
(analysis rules, unchanged), `PRIME_PARITY_MATRIX.md`.

## 1. Question and claim

Q-HARNESS on held-out data: the mean paired deadline-aware score difference between
the frozen Aljure harness and the pinned native Prime agent, same model, settings,
tasks, budgets and deadline, with Aljure's learning disabled. One run of one frozen
plan. Decision rules are the campaign's (section 5). This is the first held-out
Q-HARNESS evidence; it is not a superiority claim unless the rule says `superior`.

## 2. Arms

| Arm | Fixed by |
| --- | --- |
| aljure: controller at the plan's source commit; provider-native tool calls (`native-tool-v1`, one correction); assisted and bounded 64 KiB SCI surface with the pilot-2 prelude (nil-safe `subs`, `index-of`, `pairs-of`, `user-records`, `selection-audit`); contract `terminal_text_answer: text-answer-v2`; `aljure_contract` has no artifacts, acquisition, programs or skill interface (empty library, learning disabled); SCI image `40f00364…` | `config/head-to-head-v8-phase-b-sonnet.json`, `source`, `runtime_source`, `capabilities` in the plan |
| prime: native Prime commit `c4c238ca…`, classic-store image `f3e30aaa…`, unchanged; under text-answer-v2 its final assistant text is accepted by the identical rule when it wrote no answer file (`benchmark/terminal_text.py`), with provenance recorded | `prime_commit`, `execution_images.prime` |

Identical for both arms, enforced per request by the gateway: `claude-sonnet-5-5`,
adaptive summarized thinking, effort medium, `max_tokens` 32,768, documented rates,
Claude subscription OAuth transport, 16 calls per arm, **$4.40 per arm**, 240 s per
task, 1 MiB request bound, 4 MiB task output bound, one fresh session per arm, the
identical public context and question text. The per-arm cap is one in-flight
reservation ($4.33); it bounds any single arm's spend and admits one provider call
at a time per arm (Prime's asynchronous children were never used in any recorded run;
the cap would throttle them, disclosed).

## 3. Inputs (sealed)

OOLONG-synth test split, revision `81d2f8d9…`, every complete context window that no
harness has ever run, excluding the windows used for development at 8K, 32K and
128K. Prepared sealed by `prepare-official --independent heldout` from the pinned
profiles; gold stays controller-side (mode 0600) and is read only by the scorer at
run time. One question per context, chosen by the pilot seed from the two prepared
per window; the second question is never used.

| Length | Suite | Contexts (datasets) |
| --- | --- | --- |
| 4K | `synth4-indep-heldout` `828205cc…` | 8: metaphors ×2, app_reviews ×2, formality ×2, imdb, negation |
| 8K | `synth8-indep-heldout` `e939980b…` | 7: negation, formality, imdb, app_reviews, yahoo, multinli, metaphors |
| 16K | `synth16-indep-heldout` `cfa97d2f…` | 14: app_reviews, formality, imdb, multinli, negation, yahoo, metaphors ×2 each |
| 32K | `synth32-indep-heldout` `c74547bd…` (sealed 2026-10-29) | 7: negation, formality, imdb, app_reviews, yahoo, multinli, agnews |
| 64K | `synth64-indep-heldout` `4bd3438d…` | 8: agnews, multinli, negation, yahoo ×2 each |
| 128K | `synth128-indep-heldout` `37446dc0…` | 5: negation, yahoo, multinli, agnews ×2 |

49 independent contexts, 49 tasks; a seeded 20% (10 tasks) run twice in fresh
sessions; 59 items, **118 arms**. Windows of one dataset at different lengths share
a source instance pool, so clusters are contexts, and the length strata are reported
as secondary. These inputs are kept apart from the exploratory OBLIQ-Bench and
LongBench Pro suites (`benchmark/exploratory.py`), which never enter this plan.

## 4. Order, repeats, resume, budget

Seeded task order across suites and a balanced seeded arm order within each suite
(seed `2026110408`), as in pilot 1; every planned arm gets a row; only infrastructure
failures stop the run; `--resume` continues under the same hash after new gates.

**Maximum spend $12.** Known model cost is bounded by construction: the driver
refuses the next arm when known spend plus the $4.40 per-arm cap would exceed $12,
so no arm can start that could take known spend past $12; refused arms are recorded
`not-attempted` with failure `BudgetCeiling`. Expected spend is about $5.1
(pilot-1 per-arm costs: Aljure $0.02–0.03, Prime $0.05–0.07 at every length), so the
ceiling is expected to stay far away; if it binds, the recorded arms are still a
seeded random subset of the plan.

## 5. Pre-registered analysis

- **Primary endpoint:** context-weighted mean paired deadline-aware score
  difference, Aljure − Prime, over all 49 held-out contexts pooled across lengths,
  repeats averaged within (task, harness) first; 10,000-resample cluster bootstrap
  over contexts (seed 0); 95% and 90% percentile intervals; δ = 0.05; decision
  superior / inferior / equivalent (90% interval within ±δ) / inconclusive, exactly
  as `STATISTICAL_EVALUATION_PROTOCOL.md` §5. One primary endpoint; no other test
  decides the question.
- **Secondary, descriptive:** the same statistic per length stratum (intervals only
  where a stratum has at least five contexts); wins/ties/losses; exact sign and
  McNemar tests; paired cost and latency differences; completion, timeout,
  infrastructure-failure and tool-error rates; cost per task, per success and per
  score point; latency p50/p95; tokens; repeat variance; answer provenance counts
  (done / file / terminal-text) per harness; Pareto points per length.
- A run with more than 10% infrastructure failures in either arm is reported and
  not interpreted. Arms refused by the budget ceiling are reported as such; the
  primary is computed on the items both arms completed or failed on their own, and
  the number of refused items is stated beside it.
- Power: with σ_c ≈ 0.25 (pilot-1 8K contexts) 49 contexts detect Δ = 0.10 at 80%
  power; an effect of 0.05 is not detectable, so `equivalent` is reachable only if
  the per-context differences are mostly exact ties.

## 6. Commands

```
python3 -m benchmark.headtohead plan --campaign phase-b --out var/h2h-phase-b-20261104/plan.json   # freeze; no inference
python3 -m benchmark.headtohead preflight --plan var/h2h-phase-b-20261104/plan.json
python3 var/host-policy-20261103/run_guarded.py h2h-b --approve <plan_sha256>                        # owner only; paid
python3 var/host-policy-20261103/run_guarded.py h2h-b --approve <plan_sha256> --resume
```

Freeze from a clean committed checkout; any commit outside `var/` voids the plan.
Results go to `HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md`; the gold of every held-out
suite is opened for the first time by the scorer during the run. Evidence is archived
in a separate later commit.
