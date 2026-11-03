# Q-SUBSTRATE Experiment A results: inconclusive at a correctness ceiling

**Live result.** Run 1 of the frozen plan
`996aa3977b85a575245f77b82d7c03725db1fda0b7fe713196f292da0d37a5dd` executed on
2026-11-03 from 17:28:36 to 17:39:16 local time against source commit
`087eed2807e36de0072288a515a9515cc495cbfa`. Protocol: `Q_SUBSTRATE_PROTOCOL.md`
(sha256 `62482d95…`), criteria v1 (`6fe79fa8…`), suite `b9b18ad0…`, model
claude-sonnet-5-5 by subscription, effort medium. The frozen development gate reports
**COMPLETE-PENDING-REVIEW, outcome inconclusive**. The trace review below accepts that
outcome. Raw traces: `var/substrate-20261103/run-1` (1,185 files). Committed copy:
`evidence/q-substrate-experiment-a-20261103/` (omits raw transport bodies and sqlite
stores; `MANIFEST.json` hashes every archived file).

Labels used below: **live** (this run), **fixture** (offline developer solutions through the
real workers, no model), **replay** (archived model programs re-run offline), **proposed**
(not built, not run).

## 1. Identities and commands

| Item | Value |
| --- | --- |
| Source commit | `087eed2807e36de0072288a515a9515cc495cbfa` (clean; source identity `ca905163…`) |
| Plan | `996aa397…`; `authorized false, model_calls 0` at freeze |
| Owner authorization | `run-1/authorization.json` (sha256 `951cfe4b…`), runner pid 74175, 17:28:36 |
| Launch | owner ran `python3 var/host-policy-20261103/run_guarded.py substrate --approve 996aa397…` at 17:28:28 |
| Runner command | `python3 -m benchmark.substrate run --suite var/substrate-20261103/suite --plan var/substrate-20261103/plan.json --out var/substrate-20261103/run-1 --authorize-subscription-plan 996aa397…` |
| Images | SCI `sha256:40f00364…`, Python `sha256:d50e1d20…`, Prime `sha256:f3e30aaa…` (pinned, present before and after every task) |
| Evidence hashes | results.json `63d94ba7…`, report.json `57f167d5…`, analysis.json `149f84ea…`, gate `e87de0fc…`, launcher summary `019cb49b…`, host monitor `de4874dc…` |

## 2. Official gate (live)

Forty attempts: 20 development cases, both arms, every attempt `completed` with complete
accounting, confirmed cleanup and `done` delivery. Both arms answered all 20 cases
correctly under the independent exact scorer. Primary endpoint (paired correctness,
Clojure minus Python): mean 0.0, 95% bootstrap interval [0.0, 0.0], 20 ties. Worker
restarts 0 and 0. By the frozen mapping that is **inconclusive**. It is a ceiling: the
development suite does not separate the arms on correctness, so it cannot establish
superiority or equivalence (the protocol already rules out an equivalence claim).

Spend: $0.1835 Clojure + $0.1864 Python = **$0.37** known model cost, 119 requests of the
480 cap, 0 unknown or unpriced calls, against a $12 ceiling. Wall time 10 min 40 s for
the runner; 10 min 49 s with the host gate and its two probe workers.

## 3. Secondary measures (live)

| Measure | Clojure | Python |
| --- | --- | --- |
| Correct / completed | 20 / 20 | 20 / 20 |
| First program valid | 20 | 20 |
| Evaluations (repl_eval) | 38 | 41 |
| Evaluation errors | 1 | 6 |
| Error classes | unresolved ×1 | name ×4, import ×2 |
| Requests | 58 | 61 |
| Tokens (all kinds) | 171,143 | 171,892 |
| Output tokens | 7,437 | 7,667 |
| First request tokens, median | 2,608 | 2,412 |
| Known cost | $0.1835 | $0.1864 |
| Seconds per task, median (total) | 14.9 (318) | 15.5 (326) |
| Cold evaluation ms, median | 26.9 | 9.2 |
| Warm evaluation ms, median | 53.0 | 13.8 |
| Evaluation ms per task, mean | 123 | 29 |
| Worker startup ms, median / max | 892 / 1,617 | 193 / 300 |
| Source characters per task, mean | 402 | 449 |
| Restarts / OOM / cleanup unconfirmed | 0 / 0 / 0 | 0 / 0 / 0 |

Paired differences (Clojure minus Python, 20 pairs, 95% bootstrap interval, same
resampler and seed as the criteria):

| Measure | Mean difference | Interval | Wins C / P / tie |
| --- | --- | --- | --- |
| Evaluation errors | −0.25 | [−0.45, −0.05] | 0 / 5 / 15 |
| Evaluations | −0.15 | [−0.40, 0.15] | 1 / 5 / 14 |
| Requests | −0.15 | [−0.40, 0.15] | 1 / 5 / 14 |
| Tokens | −37 | [−983, 1,060] | 14 / 6 / 0 |
| Known cost USD | −0.0001 | [−0.0011, 0.0010] | 8 / 12 / 0 |
| Seconds per task | −0.41 | [−3.03, 2.11] | 9 / 11 / 0 |
| Evaluation ms per task | +94.5 | [52.8, 151.5] | 20 / 0 / 0 |
| Cold evaluation ms | +41.7 | [12.4, 94.7] | 18 / 2 / 0 |

Two secondary differences exclude zero. Python made more evaluation errors. SCI
evaluation is slower by about 95 ms per task, which is 0.6% of a 16 s task; model
latency dominates end-to-end time in both arms (about 5 s per request).

By family (2 cases each; correct C / P, evaluation errors C / P): aggregation 2/2, 0/2;
algorithm 2/2, 0/0; collection 2/2, 0/0; counting 2/2, 0/0; inspection 2/2, 0/0;
parsing 2/2, 1/3; recovery 2/2, 0/1; state 2/2, 0/0; transformation 2/2, 0/0;
verified-execution 2/2, 0/0.

## 4. Trace review: failure categories and attribution (live)

No computational failure and no controller failure occurred in either arm. All seven
evaluation errors are interface errors, each recovered in the next call, costing one
extra request and about $0.003 each:

- Python, 4 cases (aggregation-1, aggregation-2, parsing-2, recovery-2): `NameError: name
  're' is not defined`. The model used `re.` without `import re`. The Clojure surface has
  regular expressions built in; the Python prelude does not pre-import `re`. This is a
  **prelude-assistance** gap, not a language-semantics or familiarity effect.
- Python, 2 cases (parsing-1, parsing-2): `ImportError: Module is outside the computation
  capability set` for `from decimal import Decimal`. The worker's module allow-list omits
  `decimal`. A **surface restriction**.
- Clojure, 1 case (parsing-2): `Could not resolve symbol: Math/round`. SCI without Java
  interop. A **surface restriction**; the Phase 3 hints do not cover it.

Program validity on the first attempt was 20/20 in both arms, so this suite shows no
familiarity gap for Sonnet 5.5 at this difficulty. Execution overhead favors Python
(startup 0.2 s vs 0.9 s; evaluation 29 vs 123 ms per task) but is immaterial to wall
time, cost or correctness here. Every answer went through `done`; no paged answers were
needed. All results come from the **assisted bounded Clojure surface**; nothing here
speaks to native Clojure.

## 5. Host conditions and safety evidence (live)

The run was admitted by host gate `cd2d20f9…` (record `gate-1793744909.json`) with one
warning, host swap at 91%. The swap refusal (`--max-swap 0.9`) was added to the gate at
the owner's recommendation after this launch and did not apply to this run. Over the run
the host monitor took 106 samples: swap 88.7% to 97.8% of 15.4 GB, free memory down to
20 MB, 1-minute load up to 11.2 on 10 CPUs, zero Docker query timeouts, one Desktop
session throughout. Container events: 40 worker creates, 40 starts, 40 exits with code 0,
0 OOM, 0 kills; the 41st destroy is the gate's own probe worker. The other project on
this daemon ran five one-second containers between 17:32:54 and 17:36:33; none was
running at any sample, and the tasks in that window show no anomaly. Sampled worker
memory peaked at 68.5 MB over 61 `docker stats` samples (5 s cadence; not a true peak).
CPU-seconds were not measured. Worker startup stayed under 1.7 s against the 30 s limit
despite the memory pressure.

Supporting records, all offline: Phase 3 replay (`Q_SUBSTRATE_PHASE3.md`, 272 archived
programs, errors 56 to 35) and the two-language fixture (66/66, every gold reproduced by
developer programs in both languages). Neither is a model result.

## 6. Limitations

- Twenty paired cases at a correctness ceiling: no power to detect a substrate effect on
  correctness. The suite was calibrated by developer solutions, not by model difficulty.
- One model, one effort setting, one run, development cases only; no held-out data.
- Assisted bounded Clojure surface only; Python worker's capability set is narrower than
  CPython (no `decimal`, no `re` pre-import), which created most of the Python errors.
- No per-call CPU or peak-memory instrumentation in the supervisor.
- Host memory was saturated throughout; worker timings may be pessimistic for the JVM arm.

## 7. Architecture decision (Phase 5)

Options: A assisted bounded Clojure, B Python, C polyglot selection, D Clojure-native
compositional skills with Python interop. This evidence does not discriminate A from B on
task quality, reliability, latency, tokens or cost at this difficulty. It argues against
building C or D now: nothing observed requires a second substrate per task, and the
long-term objective (create, validate, retain, retrieve, compose, reuse executable
computation) was not exercised by this suite at all. The reuse interface study already
showed the model reimplements rather than reuses (`REUSE_INTERFACE_RESULT.md`, NO-GO);
the frozen causal study (`REUSE_CAUSAL_PROTOCOL.md`, plan `53f2fcb8…`, untouched, needs
its own approval) is the experiment that bears on D, and it remains the next reuse step.

**Smallest discriminating experiment (proposed): Q-SUBSTRATE A2.** A new versioned
protocol, not an edit of this one: (1) close the three surface gaps found here, in both
preludes symmetrically (`import re` in the Python prelude, `decimal` in the allow-list,
a `Math/round` hint or `Math` interop in SCI); (2) a harder generated suite of at least 60
paired cases whose fixture solutions need three or more evaluations and carry state
across calls, so that the ceiling moves; (3) the same frozen criteria, scorer, budgets
and host policy. Expected cost about $1.50 at the observed $0.01 per task. If A2 also
ties, the substrate choice is free with respect to correctness and should be made on the
reuse evidence; if it separates, the per-family error classes will say whether the cause
is semantics, familiarity, prelude or ergonomics, because the surface gaps will have been
removed first.

## 8. Next experiment for a credible advantage

Experiment A has settled that, for short single-answer computations, the substrate does
not change Sonnet's outcome. A statistically credible advantage over Prime (Q-HARNESS,
`Q_SUBSTRATE_BRIEF.md` Phase 6) therefore cannot come from the substrate alone. The order
is: the independent causal reuse study (frozen, $6 ceiling, about $0.25 expected), then A2
only if reuse turns out to depend on the substrate, then the Prime comparison on a
held-out suite with the confounds in `PRIME_PARITY_MATRIX.md` controlled.
