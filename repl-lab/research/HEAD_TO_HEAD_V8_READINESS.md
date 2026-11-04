# Head-to-head v8: Phase B readiness report (2026-11-04)

Status: **frozen and ready, not launched.** Pilot 2 preparation per the owner's
2026-11-04 brief. The Phase B plan hash is in `var/h2h-phase-b-20261104/plan.json`
and in the launch message; it is not written here because this file is part of the
frozen source. Lot 1 (pilot 1) is immutable: `evidence/head-to-head-v8-20261104/`
and `HEAD_TO_HEAD_V8_RESULTS.md` were not touched or rescored.

## 1. What changed from Lot 1, exactly

Lot 1 ran at source commit `ac5b99f` with `config/head-to-head-v8-sonnet.json`.
Phase B runs at the commit that freezes its plan with
`config/head-to-head-v8-phase-b-sonnet.json`. Every difference:

| Area | Lot 1 | Phase B | Where |
| --- | --- | --- | --- |
| Aljure answer contract | `aljure_contract {}`: a root text reply with no tool call is rejected; one correction; a second text reply ends the session (one correct answer lost in Lot 1) | `terminal_text_answer: "text-answer-v2"`: a root text-only reply is accepted iff exactly one trimmed line starts with `FINAL ANSWER:`, `Answer:` or `Label:` and no other line contains a marker; the answer is that line; otherwise the Lot 1 correction path runs unchanged. Provenance (`version`, `correction-used`, `lines`, response hash) is recorded in the ledger and the result row | `src/repl_lab/model_protocol.clj` `terminal-text-answer-v2`, `runtime.clj`, `external_task.clj`; tests `test/repl_lab/terminal_text_test.clj` (6 tests: acceptance, 13 rejection cases, provenance, v1 unchanged, off unchanged) |
| Prime answer semantics | `/work/answer.txt` only | `/work/answer.txt`; if absent and the run completed, the final assistant text under the identical rule (`benchmark/terminal_text.py`), written to `answer.txt` with provenance `origin: prime-final-assistant-text`. Lot 1 Prime arms wrote the file in 34 of 34, so the rule is expected never to fire; it exists so both arms have the same output semantics | `benchmark/headtohead.py` `answer_provenance`; tests `test_python/test_headtohead.py` (cross-language cases identical to the Clojure test) |
| SCI prelude (assisted surface) | bounded `subs`; `.indexOf` on a vector refused with a generic hint | nil-safe `subs`; `index-of`; `pairs-of` (deterministic pair list from ids); `user-records`; `selection-audit` (which selected users match a predicate and which matching users were not selected); a hint for `.indexOf` on collections; contract rules and 7 new probes | `resources/sci-prelude.edn`, `resources/sci-contract.json` (version 2, 51 probes), `model_protocol.clj` hints; SCI contract proof regenerated through the real worker (106 probe results, all passed) |
| Per-arm cap and ceiling | $12 per arm; $816 reservation ceiling | $4.40 per arm (one in-flight reservation); **$12 maximum known spend** enforced before every arm; refused arms recorded `not-attempted` / `BudgetCeiling` | `benchmark/headtohead.py` run loop; plan `budget.stop_rule` |
| Inputs | 28 development and unexposed tasks across 4 suites, 16 contexts | 49 sealed held-out contexts across 6 lengths, one question each | `HEAD_TO_HEAD_V8_PHASE_B_PROTOCOL.md` §3; new lockfile profiles `independent-heldout:{4096,8192,16384,65536,131072}`; shards 0, 1, 2, 5, 7, 10, 15, 22, 30 pinned and verified |
| Primary endpoint | per suite | pooled over all 49 contexts, context-weighted, 10k cluster bootstrap, δ 0.05 | plan `analysis.primary`; report `primary_pooled` |
| Driver | one campaign | campaigns `pilot-1` and `phase-b`; pilot-1's plan still reproduces byte for byte (`test_headtohead`) | `benchmark/headtohead.py` `CAMPAIGNS` |
| Prime arm | commit `c4c238ca…`, image `f3e30aaa…` | unchanged | plan `prime_commit`, `execution_images.prime` |
| Model and settings | Sonnet 5.5, adaptive summarized, medium, 32,768, 16 calls, 240 s | unchanged | config; gateway `validate-request!` |

Not changed and not rescored: Lot 1's rows, report and archive. Lot 1 and Phase B are
different inputs and a different Aljure contract; no number is carried across.

## 2. Equivalence of the two arms (observed and declared)

`python3 -m benchmark.equivalence --out var/h2h-20261104/run-1` over Lot 1's 34
item pairs (all that exist): every pair's two arms received the identical public
input (same context bytes and question; sha256 per pair) and every provider request
of both arms carried `claude-sonnet-5-5`, `max_tokens` 32768, adaptive summarized
thinking, effort medium and no sampling parameters, read from the gateway's
request-intent ledger written before dispatch. 34 of 34 pairs equivalent, zero
mismatches. The same check runs on Phase B's run directory after the run.

Declared identical by the frozen plan for both arms: 16 calls, $4.40, 12,000,000
tokens, 240 s, 1 MiB request bound, 4 MiB task output bound; one fresh session;
the same scorer on `answer.txt`, blind to harness; the same answer rule
(text-answer-v2) on both sides. Container limits are the same create arguments
(256 MiB, 1 CPU, 32 PIDs, no network, read-only root; Prime adds an 8 MiB `/work`).

Disclosed, not equalized (`PRIME_PARITY_MATRIX.md`): Aljure's controller and
gateway run on the host outside the container; Prime streams, Aljure does not;
each harness sees its own prompt and tool schemas; Prime's per-call output
truncation against Aljure's bounded surface and 10 s per-expression limit; Prime's
subagents, refine and compaction remain available (never used in any recorded run).
The relay fixture (scripted responses through real containers, 15 of 15 checks,
zero model calls) is regenerated for the Phase B transport contract before preflight.

## 3. Exploratory benchmarks (pilot 2 inputs, not in Phase B)

| Suite | State | Validation |
| --- | --- | --- |
| OBLIQ-Bench math (`obliq-math-dev` 10 queries, `obliq-math-heldout` 141, one shared corpus of 3,508 problems, 1.26 MB context) | prepared, sealed split by seed | lockfile pins HF `dianetc/OBLIQ-Bench` @ `4ebee29f` (CC BY 4.0), five files by size and sha256; corpus ids unique; every qrels and excluded id in the corpus; all 151 queries judged (13.5 gold positives each, grade 2); scorer nDCG@10 with per-query exclusions and pooled sensitivity; 4 tests |
| LongBench Pro (`longbench-pro-dev` 10 contexts, `longbench-pro-heldout` 60 = 20 per length at 8k/16k/32k, English, T4 excluded, `question_thinking` pre-registered) | prepared, sealed split by seed | pins HF `caskcsg/LongBench-Pro` @ `4996884d` (Apache-2.0), 531,535,940 bytes, sha256 verified; 345 eligible rows over 252 contexts; metrics re-implemented (the evaluation code repository has no LICENSE, so nothing is vendored) and held to the pinned upstream functions on a probe set by executing the upstream pure functions beside the port; NDCG re-implements trec_eval `ndcg_cut`; 4 tests |

These suites are never referenced by the Phase B plan, config or profiles.

## 4. Unresolved validity risks

1. **Cross-length correlation.** Windows of one dataset at different lengths share
   a source instance pool. The primary treats each context as an independent
   cluster, which is slightly anti-conservative. Mitigation: the per-length strata
   are reported; a dataset-level sensitivity has only 7 clusters and is not run.
2. **The 32K sealed suite was sampled from the pinned rows of each window**, which
   for three windows were a subset of the window's 25 questions. The sample is not
   answer-conditioned; it is less random than the other lengths. Disclosed.
3. **Budget ceiling.** If known spend reaches $7.60 the run stops; the recorded
   items are a seeded random subset and power drops. Expected spend is $5.2.
4. **Prelude helpers untested live.** The contract proof shows they work; whether
   the model uses `selection-audit` or `pairs-of` is unknown until a run.
5. **Prime terminal-text acceptance is an adapter addition** that Prime did not
   need in Lot 1. If it fires, the provenance says so; it never changes a file
   answer.
6. **Host saturation.** Lot 1 ran at 82–97% swap; latency figures are comparative
   only. Phase B needs about an hour; the credential gate requires more than one
   hour left at launch.
7. **Exploratory risks** (pilot 2, not Phase B): OBLIQ has one corpus, so every
   query is one cluster and no cross-context interval is possible; the 1.26 MB
   context has never been delivered live; our OBLIQ framing is not Prime's; the
   LongBench Pro code license is unverified (metrics re-implemented, T4 excluded).
8. **Decision reach.** 49 contexts detect Δ = 0.10; `equivalent` requires the 90%
   interval within ±0.05, reachable only with mostly exact ties.

## 5. Readiness checklist

- Tests: Clojure 219 tests / 3,228 assertions pass (6 new terminal-text tests);
  Python 96 tests pass (new: terminal text cross-language, provenance, campaigns,
  exploratory scorers and splits, lock pins).
- Proofs at the frozen commit: SCI isolation (image `40f00364…`, 64 KiB), SCI
  contract (regenerated for the new prelude and contract), native Prime isolation,
  subscription relay (regenerated for the Phase B transport contract).
- `python3 -m benchmark audit`: no violations.
- Plan frozen from a clean commit; preflight ready with zero model calls; host
  launcher dry run (gate, monitor, no runner) passed.
- Launch, when approved: `python3 var/host-policy-20261103/run_guarded.py h2h-b --approve <hash>`.
