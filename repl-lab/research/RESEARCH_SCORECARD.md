# Research scorecard (2026-10-30)

Compiled read-only from recorded plan.json, results.jsonl and report.json across the seven local worktrees; no inference, no Docker, no held-out path opened. Structured rows with the exact source paths: `evidence/scorecard/scorecard.json`. Three doc/data disagreements found here were checked against raw files and corrected or recorded in `UNBLOCK_ACQUISITION.md` and `PILOT1_RESULTS.md` (A1c arm 08 was Sonnet 5.5; D's count error has opposite signs under the two preregistered conventions; sonnet-ten32's $0.47 includes a reserved unknown call).

## 1. Per-suite tables

### Head-to-head v8 Phase B — 49 sealed OOLONG-synth held-out contexts, 4K–128K, 10 repeated, 118 arms (added 2026-11-04, live)

Arms include the repeated trials (n is arms). Suites: synth{4,8,16,32,64,128}-indep-heldout (`828205cc`, `e939980b`, `cfa97d2f`, `c74547bd`, `4bd3438d`, `37446dc0`).

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 128K held-out | 5 | 0.600 | 5/5 | 0.0887 | 0.00 (0 unk) | 20 | 28.0 / 28.0 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 128K held-out | 5 | 0.600 | 5/5 | 0.2320 | 0.00 (0 unk) | 22 | 30.8 / 30.8 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 16K held-out | 15 | 0.717 | 15/15 | 0.2889 | 0.00 (0 unk) | 50 | 23.4 / 23.4 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 16K held-out | 15 | 0.600 | 15/15 | 0.8096 | 0.00 (0 unk) | 63 | 25.5 / 25.5 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 32K held-out | 11 | 0.545 | 11/11 | 0.1281 | 0.00 (0 unk) | 36 | 17.3 / 17.3 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 32K held-out | 11 | 0.727 | 11/11 | 0.5074 | 0.00 (0 unk) | 46 | 24.5 / 24.5 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 4K held-out | 9 | 0.880 | 9/9 | 0.1294 | 0.00 (0 unk) | 24 | 18.1 / 18.1 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 4K held-out | 9 | 0.760 | 9/9 | 0.4339 | 0.00 (0 unk) | 36 | 24.5 / 24.5 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 64K held-out | 10 | 0.601 | 9/10 | 0.2088 | 0.00 (0 unk) | 39 | 22.1 / 22.0 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 64K held-out | 10 | 0.575 | 7/10 | 0.6620 | 0.00 (0 unk) | 43 | 29.4 / 26.3 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | aljure 8K held-out | 9 | 0.778 | 9/9 | 0.1417 | 0.00 (0 unk) | 32 | 22.1 / 22.1 | 2026-11-04 |
| h2h-v8-phase-b run-1 | aljure (repl-lab) | `d6d1137` | `62ac8890` | claude-sonnet-5-5 | prime 8K held-out | 9 | 0.889 | 9/9 | 0.4181 | 0.00 (0 unk) | 35 | 23.5 / 23.5 | 2026-11-04 |

Pre-registered primary (pooled, context-weighted, Aljure − Prime): +0.040, 95% [−0.044, +0.138], 90% [−0.031, +0.121], **inconclusive**; W/T/L 7/35/7 over 49 tasks. Overall means 0.690 against 0.688; Aljure $0.99 against $3.06; p50 17.0 against 23.1 s. Five arms (four Prime, one Aljure, all 64K) failed on the plan's $4.40 per-arm cap (a plan defect, kept as 0 in the primary); diagnostic cap-unaffected pooled difference +0.028, 95% [−0.048, +0.119], inconclusive. See `HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md`. Held-out; no superiority claim.

### Head-to-head v8 pilot 1 — four OOLONG suites in one plan, 28 tasks, 6 repeated, 68 arms (added 2026-11-04, live)

Arms include the repeated trials (n is arms, not tasks). Suites: synth8 = OOLONG-synth 8K unexposed `805f3673`; synth32 = OOLONG-synth 32K dev `b157ee63` (7 of 21); synth128 = OOLONG-synth 128K unexposed `556cb6bc`; pairs32 = OOLONG-Pairs 32K dev `e4f4e52a` (3 of 10).

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | aljure pairs32 | 4 | 0.720 | 4/4 | 0.2146 | 0.00 (0 unk) | 14 | 25.4 / 25.4 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | prime pairs32 | 4 | 0.846 | 4/4 | 0.3376 | 0.00 (0 unk) | 26 | 43.3 / 43.3 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | aljure synth128 | 8 | 0.513 | 8/8 | 0.1444 | 0.00 (0 unk) | 33 | 22.2 / 22.2 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | prime synth128 | 8 | 0.638 | 8/8 | 0.4832 | 0.00 (0 unk) | 49 | 33.0 / 33.0 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | aljure synth32 | 8 | 0.879 | 8/8 | 0.2579 | 0.00 (0 unk) | 35 | 30.4 / 30.4 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | prime synth32 | 8 | 0.888 | 8/8 | 0.5291 | 0.00 (0 unk) | 34 | 25.6 / 25.6 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | aljure synth8 | 14 | 0.861 | 13/14 | 0.3467 | 0.00 (0 unk) | 51 | 22.0 / 22.0 | 2026-11-04 |
| h2h-v8-pilot-1 | aljure (repl-lab) | `ac5b99f` | `bdb21429` | claude-sonnet-5-5 | prime synth8 | 14 | 0.911 | 14/14 | 0.7318 | 0.00 (0 unk) | 58 | 26.8 / 26.8 | 2026-11-04 |

Primary per suite (context-weighted paired difference, Aljure − Prime): synth8 −0.058 inconclusive; synth32 −0.010 equivalent (7 contexts, 6 ties); synth128 −0.083 and pairs32 −0.156 without intervals. Aljure $0.964 against $2.082, p50 22.8 against 25.9 s. One Aljure error (correct text answer rejected). See `HEAD_TO_HEAD_V8_RESULTS.md`. Development evidence; no held-out claim.

### Suite `8f7f4510` — reuse economics, eight cases, three arms, long six-clause rule (added 2026-11-04, live)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reuse-economics run-1 | aljure (repl-lab) | `2873a49` | `ffbbb00f` | claude-sonnet-5-5 | A stateless, long rule | 8 | 1.000 | 8/8 | 0.0835 | 0.00 (0 unk) | 24 | 10.1 / 10.1 | 2026-11-04 |
| reuse-economics run-1 | aljure (repl-lab) | `2873a49` | `ffbbb00f` | claude-sonnet-5-5 | B library, long rule | 8 | 1.000 | 8/8 | 0.0966 | 0.00 (0 unk) | 25 | 12.5 / 12.5 | 2026-11-04 |
| reuse-economics run-1 | aljure (repl-lab) | `2873a49` | `ffbbb00f` | claude-sonnet-5-5 | BN library, summaries withheld, long rule | 8 | 1.000 | 8/8 | 0.1330 | 0.00 (0 unk) | 32 | 17.3 / 17.3 | 2026-11-04 |

Outcome by frozen mapping: `reimplementation-regardless-of-length`, summary effect `none`, gate COMPLETE-PENDING-ATTRIBUTION-REVIEW, trace review confirms (0 inspections, 0 artifact calls in 24 attempts); see `REUSE_ECONOMICS_RESULT.md`. Development mechanism test; no superiority claim.

### Suite `7101a245` — causal reuse study, ten cases, four arms (added 2026-11-04, live)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reuse-causal run-1 | aljure (repl-lab) | `ce64874` | `1d5a4db2` | claude-sonnet-5-5 | A stateless | 5 | 1.000 | 5/5 | 0.0525 | 0.00 (0 unk) | 15 | 11.1 / 11.1 | 2026-11-04 |
| reuse-causal run-1 | aljure (repl-lab) | `ce64874` | `1d5a4db2` | claude-sonnet-5-5 | B library | 5 | 1.000 | 5/5 | 0.0526 | 0.00 (0 unk) | 16 | 13.7 / 13.7 | 2026-11-04 |
| reuse-causal run-1 | aljure (repl-lab) | `ce64874` | `1d5a4db2` | claude-sonnet-5-5 | C library, withheld | 5 | 1.000 | 5/5 | 0.0515 | 0.00 (0 unk) | 17 | 13.6 / 13.6 | 2026-11-04 |
| reuse-causal run-1 | aljure (repl-lab) | `ce64874` | `1d5a4db2` | claude-sonnet-5-5 | C0 stateless, withheld | 5 | 0.600 | 5/5 | 0.0619 | 0.00 (0 unk) | 18 | 12.0 / 12.0 | 2026-11-04 |

Outcome by frozen mapping: `reuse-only-when-necessary`, gate COMPLETE-PENDING-ATTRIBUTION-REVIEW, trace review confirms; see `REUSE_CAUSAL_RESULT.md`. Development mechanism test; no superiority claim.

### Suite `b9b18ad0` — Q-SUBSTRATE Experiment A, 20 paired development cases, ten families (added 2026-11-03, live)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| substrate run-1 | aljure (repl-lab) | `087eed28` | `996aa397` | claude-sonnet-5-5 | clojure | 20 | 1.000 | 20/20 | 0.1835 | 0.00 (0 unk) | 58 | 14.9 / 14.9 | 2026-11-03 |
| substrate run-1 | aljure (repl-lab) | `087eed28` | `996aa397` | claude-sonnet-5-5 | python | 20 | 1.000 | 20/20 | 0.1864 | 0.00 (0 unk) | 61 | 15.5 / 15.5 | 2026-11-03 |

Outcome by frozen criteria: inconclusive (paired difference 0, interval [0, 0]); see `Q_SUBSTRATE_RESULTS.md`.

### Suite `456f6acf` — oolong-synth 1-task Opus smoke (negation 415040016)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synth-opus-smoke-one | aljure-sonnet-pair-v7 | `56a3de45` | `a1d0d896` | claude-opus-5-5 | aljure | 1 | 0.000 | 0/1 | 0.1911 | 0.00 (0 unk) | 12 | 70.7 / — | 2026-10-29 04:45Z |
| synth-opus-smoke-one | aljure-sonnet-pair-v7 | `56a3de45` | `a1d0d896` | claude-opus-5-5 | prime | 1 | 1.000 | 1/1 | 0.3324 | 0.00 (0 unk) | 12 | 86.9 / 86.9 | 2026-10-29 04:45Z |
| synth-opus-smoke-one-open | aljure-sonnet-pair-v7 | `f96f0fbd` | `3a0ccea4` | claude-opus-5-5 | aljure | 1 | 1.000 | 1/1 | 0.3830 | 0.00 (0 unk) | 23 | 153.7 / 153.7 | 2026-10-29 05:06Z |
| synth-opus-smoke-one-open | aljure-sonnet-pair-v7 | `f96f0fbd` | `3a0ccea4` | claude-opus-5-5 | prime | 1 | 1.000 | 1/1 | 0.8982 | 0.00 (0 unk) | 32 | 149.2 / 149.2 | 2026-10-29 05:06Z |

### Suite `7b23fbbb` — thesis-pilot trajectory suite, 18 tasks (14 F1 trec_coarse + 4 F2 spam)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A-s101 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.450 | 18/18 | 0.3980 | 0.00 (0 unk) | 71 | 18.8 / 18.8 | 2026-10-29 22:09Z |
| C-s101 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.478 | 18/18 | 0.6959 | 0.00 (0 unk) | 97 | 22.9 / 22.9 | 2026-10-29 22:18Z |
| E-s101 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.415 | 16/18 | 0.6450 | 0.00 (0 unk) | 93 | 27.1 / 26.6 | 2026-10-29 22:27Z |
| A-s202 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.534 | 18/18 | 0.4431 | 0.00 (0 unk) | 81 | 22.6 / 22.6 | 2026-10-29 22:37Z |
| C-s202 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.493 | 17/18 | 0.5980 | 0.00 (0 unk) | 93 | 24.9 / 24.1 | 2026-10-29 22:44Z |
| E-s202 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.486 | 17/18 | 0.5921 | 0.00 (0 unk) | 86 | 21.0 / 19.9 | 2026-10-29 22:53Z |
| A-s303 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.437 | 18/18 | 0.4402 | 0.00 (0 unk) | 82 | 22.8 / 22.8 | 2026-10-29 23:01Z |
| C-s303 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.487 | 15/18 | 0.5977 | 0.00 (0 unk) | 88 | 22.6 / 22.5 | 2026-10-29 23:08Z |
| E-s303 | aljure-thesis-v1 | `6b3c4222` | `795a0140` | claude-sonnet-5-5 | aljure | 18 | 0.423 | 17/18 | 0.6239 | 0.00 (0 unk) | 90 | 25.4 / 25.3 | 2026-10-29 23:17Z |

Plan `795a0140` ran 9 times (A-s101, C-s101, E-s101, A-s202, C-s202, E-s202, A-s303, C-s303, E-s303):
- aljure: mean score per run 0.450, 0.478, 0.415, 0.534, 0.493, 0.486, 0.437, 0.487, 0.423; min–max 0.415–0.534, range 0.120, SD 0.039; cost per run 0.398, 0.696, 0.645, 0.443, 0.598, 0.592, 0.440, 0.598, 0.624

### Suite `806c5b2b` — reuse-pilot (Pilot 1), 27 tasks (21 F1 trec_coarse + 6 F2 spam)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reuse-S-r1 | aljure-unblock-v1 | `6b7feb9c` | `7f089a8f` | claude-sonnet-5-5 | aljure | 27 | 0.432 | 24/27 | 0.5480 | 0.00 (0 unk) | 116 | 21.8 / 21.8 | 2026-10-30 00:08Z |
| reuse-D-r1 | aljure-unblock-v1 | `6b7feb9c` | `b89df89b` | claude-sonnet-5-5 | aljure | 27 | 0.357 | 22/27 | 0.6397 | 0.00 (0 unk) | 125 | 24.5 / 25.2 | 2026-10-30 00:19Z |
| reuse-P-r1 | aljure-unblock-v1 | `6b7feb9c` | `46d89446` | claude-sonnet-5-5 | aljure | 27 | 0.440 | 24/27 | 0.6970 | 0.00 (0 unk) | 158 | 29.3 / 29.4 | 2026-10-30 00:31Z |
| reuse-S-r2 | aljure-unblock-v1 | `6b7feb9c` | `7f089a8f` | claude-sonnet-5-5 | aljure | 27 | 0.291 | 24/27 | 0.5175 | 0.00 (0 unk) | 110 | 19.4 / 19.1 | 2026-10-30 00:45Z |
| reuse-D-r2 | aljure-unblock-v1 | `6b7feb9c` | `b89df89b` | claude-sonnet-5-5 | aljure | 27 | 0.442 | 26/27 | 0.5660 | 0.00 (0 unk) | 127 | 24.4 / 24.7 | 2026-10-30 00:55Z |
| reuse-P-r2 | aljure-unblock-v1 | `6b7feb9c` | `46d89446` | claude-sonnet-5-5 | aljure | 27 | 0.373 | 25/27 | 0.7431 | 0.00 (0 unk) | 165 | 28.7 / 28.7 | 2026-10-30 01:06Z |

Plan `7f089a8f` ran 2 times (reuse-S-r1, reuse-S-r2):
- aljure: mean score per run 0.432, 0.291; min–max 0.291–0.432, range 0.141, SD 0.099; cost per run 0.548, 0.517

Plan `b89df89b` ran 2 times (reuse-D-r1, reuse-D-r2):
- aljure: mean score per run 0.357, 0.442; min–max 0.357–0.442, range 0.085, SD 0.060; cost per run 0.640, 0.566

Plan `46d89446` ran 2 times (reuse-P-r1, reuse-P-r2):
- aljure: mean score per run 0.440, 0.373; min–max 0.373–0.440, range 0.067, SD 0.048; cost per run 0.697, 0.743

### Suite `90f719a5` — oolong-pairs 8K, 10 tasks (one context)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sonnet-ten-live | aljure-sonnet-pair-v7 | `9cc0812d` | `35778799` | claude-sonnet-5-5 | aljure | 10 | 0.848 | 9/10 | 0.6449 | 0.00 (0 unk) | 70 | 73.2 / 69.7 | 2026-10-28 16:12Z |
| sonnet-ten-live | aljure-sonnet-pair-v7 | `9cc0812d` | `35778799` | claude-sonnet-5-5 | prime | 10 | 0.965 | 10/10 | 0.7173 | 0.00 (0 unk) | 40 | 42.5 / 42.5 | 2026-10-28 16:12Z |
| sonnet-ten-rerun-live | aljure-sonnet-pair-v7 | `87d5fdaa` | `5ef81410` | claude-sonnet-5-5 | aljure | 10 | 0.293 | 3/10 | 0.2228 | 0.00 (0 unk) | 25 | 0.0 / 62.3 | 2026-10-28 16:49Z |
| sonnet-ten-rerun-live | aljure-sonnet-pair-v7 | `87d5fdaa` | `5ef81410` | claude-sonnet-5-5 | prime | 10 | 0.385 | 4/10 | 0.2936 | 0.00 (0 unk) | 16 | 0.0 / 50.9 | 2026-10-28 16:49Z |

### Suite `b157ee63` — oolong-synth 32K dev, 7 independent contexts, 21 tasks

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synth-indep-32k-dev | aljure-sonnet-pair-v7 | `dfd82fbe` | `0b6a0451` | claude-sonnet-5-5 | aljure | 21 | 0.768 | 21/21 | 0.8147 | 0.00 (0 unk) | 95 | 22.1 / 22.1 | 2026-10-29 03:51Z |
| synth-indep-32k-dev | aljure-sonnet-pair-v7 | `dfd82fbe` | `0b6a0451` | claude-sonnet-5-5 | prime | 21 | 0.800 | 20/21 | 1.5901 | 0.00 (0 unk) | 94 | 24.1 / 24.6 | 2026-10-29 03:51Z |
| synth-indep-32k-dev-opus | aljure-sonnet-pair-v7 | `f96f0fbd` | `d6e9b40d` | claude-opus-5-5 | aljure | 21 | 0.770 | 19/21 | 1.7330 | 0.00 (0 unk) | 96 | 25.6 / 22.3 | 2026-10-29 05:11Z |
| synth-indep-32k-dev-opus | aljure-sonnet-pair-v7 | `f96f0fbd` | `d6e9b40d` | claude-opus-5-5 | prime | 21 | 0.919 | 21/21 | 3.8147 | 0.00 (0 unk) | 125 | 29.0 / 29.0 | 2026-10-29 05:11Z |
| contract-ablation-opus-control | aljure-sonnet-pair-v7 | `41b53fac` | `87d8c949` | claude-opus-5-5 | aljure | 21 | 0.853 | 21/21 | 1.7979 | 0.00 (0 unk) | 104 | 24.1 / 24.1 | 2026-10-29 14:25Z |
| contract-ablation-opus-control | aljure-sonnet-pair-v7 | `41b53fac` | `87d8c949` | claude-opus-5-5 | prime | 21 | 0.904 | 21/21 | 3.7374 | 0.00 (0 unk) | 120 | 27.2 / 27.2 | 2026-10-29 14:25Z |
| contract-ablation-opus-f1 | aljure-sonnet-pair-v7 | `41b53fac` | `52f51590` | claude-opus-5-5 | aljure | 21 | 0.876 | 21/21 | 1.6425 | 0.00 (0 unk) | 93 | 30.2 / 30.2 | 2026-10-29 14:47Z |
| contract-ablation-opus-f1 | aljure-sonnet-pair-v7 | `41b53fac` | `52f51590` | claude-opus-5-5 | prime | 21 | 0.898 | 21/21 | 3.9465 | 0.00 (0 unk) | 128 | 33.6 / 33.6 | 2026-10-29 14:47Z |
| contract-ablation-opus-f2 | aljure-sonnet-pair-v7 | `41b53fac` | `b1844732` | claude-opus-5-5 | aljure | 21 | 0.805 | 19/21 | 1.5438 | 0.00 (0 unk) | 91 | 26.3 / 26.3 | 2026-10-29 15:11Z |
| contract-ablation-opus-f2 | aljure-sonnet-pair-v7 | `41b53fac` | `b1844732` | claude-opus-5-5 | prime | 21 | 0.867 | 20/21 | 3.0027 | 0.00 (0 unk) | 95 | 31.6 / 31.2 | 2026-10-29 15:11Z |
| verify-v1-synth21-v1-r1 | aljure-verify-v1 | `8a93ecf7` | `9d16cc1a` | claude-opus-5-5 | aljure | 21 | 0.802 | 20/21 | 2.1960 | 0.00 (0 unk) | 128 | 21.7 / 21.6 | 2026-10-29 20:26Z |
| verify-v1-synth21-v0-r1 | aljure-verify-v1 | `8a93ecf7` | `5fdab5e2` | claude-opus-5-5 | aljure | 21 | 0.865 | 21/21 | 1.6196 | 0.00 (0 unk) | 93 | 22.0 / 22.0 | 2026-10-29 20:39Z |

### Suite `dc164044` — oolong-synth label counts dev, 5 windows, 11 tasks

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| review-levels-opus-l0-baseline | aljure-review-v1 | `40270ba3` | `def381f5` | claude-opus-5-5 | aljure | 11 | 0.362 | 11/11 | 2.4708 | 0.00 (0 unk) | 106 | 55.6 / 55.6 | 2026-10-29 16:18Z |
| review-levels-opus-l0-baseline | aljure-review-v1 | `40270ba3` | `def381f5` | claude-opus-5-5 | prime | 11 | 0.474 | 11/11 | 5.8530 | 0.00 (0 unk) | 196 | 107.7 / 107.7 | 2026-10-29 16:18Z |
| review-levels-opus-l1-labels | aljure-review-v1 | `40270ba3` | `240ce694` | claude-opus-5-5 | aljure | 11 | 0.273 | 11/11 | 2.6844 | 0.00 (0 unk) | 112 | 60.2 / 60.2 | 2026-10-29 16:45Z |
| review-levels-opus-l1-labels | aljure-review-v1 | `40270ba3` | `240ce694` | claude-opus-5-5 | prime | 11 | 0.388 | 11/11 | 5.8571 | 0.00 (0 unk) | 207 | 105.2 / 105.2 | 2026-10-29 16:45Z |
| review-levels-opus-l2-audit | aljure-review-v1 | `40270ba3` | `51687387` | claude-opus-5-5 | aljure | 11 | 0.417 | 11/11 | 2.7717 | 0.00 (0 unk) | 107 | 94.8 / 94.8 | 2026-10-29 17:22Z |
| review-levels-opus-l2-audit | aljure-review-v1 | `40270ba3` | `51687387` | claude-opus-5-5 | prime | 11 | 0.279 | 10/11 | 4.3404 | 0.00 (0 unk) | 147 | 85.7 / 101.5 | 2026-10-29 17:22Z |
| review-levels-opus-l3-review | aljure-review-v1 | `40270ba3` | `20f25624` | claude-opus-5-5 | aljure | 11 | 0.000 | 0/11 | 0.5677 | 0.00 (0 unk) | 19 | 0.0 / — | 2026-10-29 18:04Z |
| review-levels-opus-l3-review | aljure-review-v1 | `40270ba3` | `20f25624` | claude-opus-5-5 | prime | 11 | 0.000 | 0/11 | 0.0000 | 0.00 (0 unk) | 0 | 0.0 / — | 2026-10-29 18:04Z |
| verify-v1-counts-v1-r1 | aljure-verify-v1 | `8a93ecf7` | `1612cb67` | claude-opus-5-5 | aljure | 11 | 0.361 | 11/11 | 2.7343 | 0.00 (0 unk) | 133 | 61.3 / 61.3 | 2026-10-29 18:44Z |
| verify-v1-counts-v0-r1 | aljure-verify-v1 | `8a93ecf7` | `e9255963` | claude-opus-5-5 | aljure | 11 | 0.354 | 11/11 | 2.4372 | 0.00 (0 unk) | 110 | 53.2 / 53.2 | 2026-10-29 18:59Z |
| verify-v1-counts-v1-r2 | aljure-verify-v1 | `8a93ecf7` | `1612cb67` | claude-opus-5-5 | aljure | 11 | 0.388 | 10/11 | 2.7085 | 0.00 (0 unk) | 114 | 53.7 / 48.5 | 2026-10-29 19:12Z |
| verify-v1-counts-v0-r2 | aljure-verify-v1 | `8a93ecf7` | `e9255963` | claude-opus-5-5 | aljure | 11 | 0.423 | 11/11 | 2.7970 | 0.00 (0 unk) | 152 | 78.8 / 78.8 | 2026-10-29 19:26Z |
| verify-v1-counts-v1-r3 | aljure-verify-v1 | `8a93ecf7` | `1612cb67` | claude-opus-5-5 | aljure | 11 | 0.437 | 11/11 | 2.6848 | 0.00 (0 unk) | 138 | 88.1 / 88.1 | 2026-10-29 19:48Z |
| verify-v1-counts-v0-r3 | aljure-verify-v1 | `8a93ecf7` | `e9255963` | claude-opus-5-5 | aljure | 11 | 0.479 | 11/11 | 2.9092 | 0.00 (0 unk) | 170 | 58.1 / 58.1 | 2026-10-29 20:10Z |

Plan `1612cb67` ran 3 times (verify-v1-counts-v1-r1, verify-v1-counts-v1-r2, verify-v1-counts-v1-r3):
- aljure: mean score per run 0.361, 0.388, 0.437; min–max 0.361–0.437, range 0.075, SD 0.038; cost per run 2.734, 2.708, 2.685

Plan `e9255963` ran 3 times (verify-v1-counts-v0-r1, verify-v1-counts-v0-r2, verify-v1-counts-v0-r3):
- aljure: mean score per run 0.354, 0.423, 0.479; min–max 0.354–0.479, range 0.125, SD 0.062; cost per run 2.437, 2.797, 2.909

### Suite `e1491d5e` — oolong-pairs 8K, 1 task (validation case 1; one context)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sonnet-pair-v6-live | aljure-sonnet-pair-v6 | `2184b102` | `703dbecf` | claude-sonnet-5-5 | aljure | 1 | 0.000 | 0/1 | 0.0263 | 0.00 (0 unk) | 4 | 29.6 / — | 2026-10-28 14:23Z |
| sonnet-pair-v6-live | aljure-sonnet-pair-v6 | `2184b102` | `703dbecf` | claude-sonnet-5-5 | prime | 1 | 0.000 | 0/1 | 0.0615 | 0.00 (0 unk) | 4 | 35.3 / — | 2026-10-28 14:23Z |
| sonnet-pair-v7-live | aljure-sonnet-pair-v7 | `7b0cfa7c` | `9798e89e` | claude-sonnet-5-5 | aljure | 1 | 0.000 | 0/1 | 0.0284 | 0.00 (0 unk) | 4 | 32.8 / — | 2026-10-28 15:13Z |
| sonnet-pair-v7-live | aljure-sonnet-pair-v7 | `7b0cfa7c` | `9798e89e` | claude-sonnet-5-5 | prime | 1 | 1.000 | 1/1 | 0.0690 | 0.00 (0 unk) | 4 | 38.5 / 38.5 | 2026-10-28 15:13Z |
| sonnet-pair-native-tools-live | aljure-sonnet-pair-v7 | `a965bd96` | `78d14e14` | claude-sonnet-5-5 | aljure | 1 | 1.000 | 1/1 | 0.1722 | 0.00 (0 unk) | 7 | 102.7 / 102.7 | 2026-10-28 15:39Z |
| sonnet-pair-native-tools-live | aljure-sonnet-pair-v7 | `a965bd96` | `78d14e14` | claude-sonnet-5-5 | prime | 1 | 0.968 | 1/1 | 0.0669 | 0.00 (0 unk) | 4 | 41.2 / 41.2 | 2026-10-28 15:39Z |
| sonnet-pair-fair-live | aljure-sonnet-pair-v7 | `1a570afe` | `6462f780` | claude-sonnet-5-5 | aljure | 1 | 0.968 | 1/1 | 0.0510 | 0.00 (0 unk) | 6 | 43.2 / 43.2 | 2026-10-28 16:04Z |
| sonnet-pair-fair-live | aljure-sonnet-pair-v7 | `1a570afe` | `6462f780` | claude-sonnet-5-5 | prime | 1 | 0.968 | 1/1 | 0.0645 | 0.00 (0 unk) | 4 | 32.0 / 32.0 | 2026-10-28 16:04Z |

### Suite `e4f4e52a` — oolong-pairs 32K, 10 tasks (one context)

| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sonnet-ten32-live | aljure-sonnet-pair-v7 | `1b99ef76` | `83fecbaa` | claude-sonnet-5-5 | aljure | 10 | 0.089 | 1/10 | 0.3652 | 4.33 (1 unk) | 58 | 31.8 / 95.9 | 2026-10-28 17:03Z |
| sonnet-ten32-live | aljure-sonnet-pair-v7 | `1b99ef76` | `83fecbaa` | claude-sonnet-5-5 | prime | 10 | 0.368 | 4/10 | 0.3326 | 0.00 (0 unk) | 18 | 0.0 / 55.5 | 2026-10-28 17:03Z |
| sci-ablation-control | aljure-sonnet-pair-v7 | `79a3bd91` | `6ae7e225` | claude-sonnet-5-5 | aljure | 10 | 0.000 | 0/10 | 0.0000 | 4.33 (1 unk) | 10 | 0.0 / — | 2026-10-28 18:24Z |
| sci-ablation-control | aljure-sonnet-pair-v7 | `79a3bd91` | `6ae7e225` | claude-sonnet-5-5 | prime | 10 | 0.000 | 0/10 | 0.0000 | 0.00 (0 unk) | 0 | 0.0 / — | 2026-10-28 18:24Z |
| sci-ablation-control-2 | aljure-sonnet-pair-v7 | `40a24bd9` | `50911e6b` | claude-sonnet-5-5 | aljure | 10 | 0.176 | 3/10 | 0.7927 | 0.00 (0 unk) | 102 | 115.4 / 76.3 | 2026-10-28 18:54Z |
| sci-ablation-control-2 | aljure-sonnet-pair-v7 | `40a24bd9` | `50911e6b` | claude-sonnet-5-5 | prime | 10 | 0.680 | 8/10 | 1.0864 | 0.00 (0 unk) | 54 | 55.0 / 49.9 | 2026-10-28 18:54Z |
| sci-ablation-bounded-64k | aljure-sonnet-pair-v7 | `13490b4b` | `d5038fe2` | claude-sonnet-5-5 | aljure | 10 | 0.174 | 4/10 | 0.7333 | 0.00 (0 unk) | 60 | 95.5 / 88.2 | 2026-10-28 20:00Z |
| sci-ablation-bounded-64k | aljure-sonnet-pair-v7 | `13490b4b` | `d5038fe2` | claude-sonnet-5-5 | prime | 10 | 0.852 | 10/10 | 0.9351 | 0.00 (0 unk) | 60 | 63.5 / 63.5 | 2026-10-28 20:00Z |
| sci-ablation-speed-64k | aljure-sonnet-pair-v7 | `dd981088` | `30654ed6` | claude-sonnet-5-5 | aljure | 10 | 0.845 | 10/10 | 0.8306 | 0.00 (0 unk) | 59 | 34.4 / 34.4 | 2026-10-29 02:24Z |
| sci-ablation-speed-64k | aljure-sonnet-pair-v7 | `dd981088` | `30654ed6` | claude-sonnet-5-5 | prime | 10 | 0.862 | 10/10 | 0.9471 | 0.00 (0 unk) | 50 | 39.5 / 39.5 | 2026-10-29 02:24Z |

### Notes on the repeated plans (run-variance evidence)

**Thesis pilot, plan `795a0140` (suite `7b23fbbb`, Sonnet).** One plan hash covers 3 arms × 3 seeded task orders, so the nine runs are not nine repeats of one condition. Per arm (3 trajectories each, 18 tasks):

| Arm | Mean score per trajectory (s101, s202, s303) | Range | F1 pooled (42 tasks) | F2 pooled (12) | Cost all tasks | No-answer tasks |
| --- | --- | --- | --- | --- | --- | --- |
| A stateless | 0.450, 0.534, 0.437 | 0.097 | 0.489 | 0.421 | $1.28 | 0 |
| C exact cache | 0.478, 0.493, 0.487 | 0.015 | 0.526 | 0.345 | $1.89 (incl. $0.59 proposal turns) | 4 |
| E validated artifacts | 0.415, 0.486, 0.423 | 0.071 | 0.492 | 0.265 | $1.86 (incl. $0.61 proposal turns) | 4 |

Source: the nine `report.json` files and `/Users/mackianni/aljure-thesis-v1/repl-lab/var/thesis-pilot/logs/report.json` (`arms`, `trajectories`). The arms carried no retained state (0 proposals, 0 promotions; every E/C case has `promotion: "no-proposal"` and activation `no-applicable-artifact`), so the between-arm differences are the run-to-run spread of one stateless configuration: F1 0.489 to 0.526, F2 0.265 to 0.421.

**Pilot 1, suite `806c5b2b` (Sonnet), each plan run twice.** The official suite mean mixes F1 (21 trec tasks) and F2 (6 spam tasks). F1/F2 split per run, from `/Users/mackianni/aljure/repl-lab/research/evidence/pilot1-results/pilot1-detail.json` (per-task rows; the F1 means over both runs equal `pilot1-compare-fixed.json`):

| Plan (arm) | Run 1 F1 / F2 | Run 2 F1 / F2 | F1 range between identical runs | F1 pooled |
| --- | --- | --- | --- | --- |
| `7f089a8f` S stateless | 0.404 / 0.530 | 0.226 / 0.520 | **0.178** | 0.315 |
| `b89df89b` D seeded library, model-directed | 0.290 / 0.594 | 0.359 / 0.734 | 0.069 | 0.324 |
| `46d89446` P library + controller-supplied labels | 0.417 / 0.521 | 0.336 / 0.500 | 0.081 | 0.377 |

The within-plan F1 spread for S (0.178) is three times the preregistered P − S effect (+0.061, 95% CI −0.020 to +0.162). On the whole 27-task suite, S scored 0.432 then 0.291 (range 0.141).

**Answer-format A/B, suite `dc164044` (Opus), each plan run three times, Aljure only.** V0 `e9255963`: 0.354, 0.423, 0.479 (range 0.125, SD 0.062). V1 `1612cb67`: 0.361, 0.388, 0.437 (range 0.075). The notice under test fired 0 times in 54 V1 arms (`ANSWER_FORMAT_VERIFICATION_RESULTS.md:16`), so both triples are repeats of the same behaviour: the 11-task count suite moves by about 0.12 between identical runs.

**Same configuration, different plan hash (Opus, suite `b157ee63`).** `synth-indep-32k-dev-opus` (`d6e9b40d`, commit `f96f0fbd`) and `contract-ablation-opus-control` (`87d8c949`, commit `41b53fac`) are described as the same configuration (`HISTORICAL_PERFORMANCE_AUDIT.md:136`). Aljure 0.771 → 0.853; Prime 0.919 → 0.904. The commits differ, so this is UNVERIFIED as a pure repeat; the doc treats it as run variance of about 0.08.

**Prime alone on one plan family.** Prime ran unchanged (`c4c238ca`) in L0, L1 and L2 on suite `dc164044`: 0.474, 0.388, 0.279 (one Prime arm failed in L2). On the 1-task 8K suite Prime scored 0.968, 1.0, 0.968, 0.968 across V3, V7, native-tools and fair.

**Paired-campaign totals, deduplicated:** 22 paired runs, 450 arms, Aljure $20.47 + Prime $37.95 = $58.41 by `model_cost_usd` (the doc's $58.6 / $20.6 / $37.9 at `HISTORICAL_PERFORMANCE_AUDIT.md:92-93` uses `known_model_cost_usd`, which differs only on `sonnet-ten32-live`, see section 4). 23 Aljure-only runs (verify, thesis pilot, Pilot 1): $28.83.

## 2. Reproducible vs single-run: each claimed Aljure-vs-Prime advantage

"Several runs" below means several recorded runs of the same suite and model that show the same direction. No Aljure-vs-Prime claim in the repository rests on repeated runs of one plan hash: no paired plan was ever run twice.

| # | Claim (doc:line) | Quoted numbers | Recorded data | Rests on |
| --- | --- | --- | --- | --- |
| 1 | Aljure cheaper than Prime on the 21-task synth suite, Sonnet: "Aljure's cost (51% of Prime's) and wall time (89% of Prime's) are both lower" (`SYNTH_INDEPENDENT_32K_RESULTS.md:41`); "Aljure was cheaper in all 7 contexts and faster in 6" (`:71-72`) | $0.815 vs $1.590; 501 s vs 564 s | `synth-indep-32k-dev/report.json`: $0.8147 vs $1.5901; wall 501 s vs 564 s; grouping cases by context (first digit of the task id, 7 groups of 3): Aljure cost lower in 7/7, wall lower in 6/7 (context 2, imdb, 67 s vs 57 s is the exception). Verified | **One run** (plan `0b6a0451`) |
| 2 | Cost advantage persists under Opus on the same suite: "Aljure is cheaper and faster, but it is not comparable on accuracy" (`SYNTH_INDEPENDENT_32K_OPUS_RESULTS.md:36`); Aljure/Prime cost 0.48, 0.42, 0.51 (`CONTRACT_ABLATION_RESULTS.md:31`) | $1.73 vs $3.81; $1.80/$3.74, $1.64/$3.95, $1.54/$3.00 | Four Opus paired runs on suite `b157ee63`: Aljure cost 45%, 48%, 42%, 51% of Prime; p50 wall lower for Aljure in all four (25.6/29.0, 24.1/27.2, 30.2/33.6, 26.3/31.6 s) | **Several runs, same direction** (4 plans, 1 run each). This is the best-replicated advantage in the repository. It is a cost/latency claim, not an accuracy claim: Aljure scored below Prime in all four (0.771/0.919, 0.853/0.904, 0.876/0.898, 0.805/0.867) |
| 3 | Cost advantage on the label-count suite: Aljure/Prime cost 0.42, 0.46, 0.64 (`REVIEW_ABLATION_RESULTS.md:54`) | $2.47/$5.85, $2.68/$5.86, $2.77/$4.34 | Matches `review-levels-opus-l0..l2/report.json` | **Three runs, same direction**, different Aljure prompts (L0–L2), Prime unchanged. Accuracy: Aljure below Prime in L0 and L1 (0.362/0.474, 0.273/0.388), above in L2 (0.417/0.279, where one Prime arm failed) |
| 4 | Accuracy "not inferior" to Prime on the synth suite, Sonnet: "Preregistered target: met" (`SYNTH_INDEPENDENT_32K_RESULTS.md:38`) | 0.768 vs 0.800; paired −0.031, 95% CI [−0.174, +0.111]; W/T/L 1/15/5 | `report.json`: mean 0.7685 vs 0.7999; `mean_paired_difference_aljure_minus_prime` recorded; W/T/L as stated | **One run.** The doc itself calls the decision "inconclusive" (`:22`). Under Opus the same suite was "inferior" (−0.149, CI [−0.271, −0.048], `SYNTH_INDEPENDENT_32K_OPUS_RESULTS.md:30-34`) |
| 5 | Aljure won on one 8K Pairs case with native tools: "Aljure F1 1.0, native Prime F1 0.968" (`PRIME_HEAD_TO_HEAD_NATIVE_TOOLS_RESULTS.md:3-4`) | 1.0 vs 0.968; $0.1722 vs $0.0669 | Matches `sonnet-pair-native-tools-live/report.json` | **One run, one task.** The doc says it "is not evidence that Aljure is better" (`:42`) and Aljure cost 2.6× |
| 6 | Tie with lower cost after fairness fixes: "Aljure cost 21% less and took 35% longer" (`PRIME_HEAD_TO_HEAD_FAIR_RESULTS.md:3-4`) | 0.968 both; $0.0510 vs $0.0645; 43.2 vs 32.0 s | Matches `sonnet-pair-fair-live/report.json` | **One run, one task** |
| 7 | Aljure within 0.02 of Prime on the 32K Pairs suite after latency work: A1c 0.845 / 0.862, 10/10 both (`HISTORICAL_PERFORMANCE_AUDIT.md:75`) | 0.845 vs 0.862; $0.83 vs $0.95 | Matches `sci-ablation-speed-64k/report.json` (0.8454 / 0.8619; $0.8306 / $0.9471) | **One run.** The three earlier runs on this suite had Aljure at 0.089, 0.176, 0.174 against Prime 0.368, 0.680, 0.852, with different Aljure code each time |
| 8 | Aljure gained more from Opus than Prime on 18 shared tasks (`SONNET_OPUS_PAIRED_DECOMPOSITION.md:105`) | derived from runs `0b6a0451` and `d6e9b40d` | Both single runs; the decomposition is post hoc | **One run per model** |
| 9 | Controller/accounting design advantages: "Aljure better" on hard budgets (`ELASTIC_ARCHITECTURE_GAP_ANALYSIS.md:51`, `:78`) | — | Source-code comparison, no run | Not a measured result |

Claims in the docs that go the other way (Prime ahead) and are also single-run: `PRIME_HEAD_TO_HEAD_TEN_RESULTS.md:3-4` (0.847 vs 0.965, 2/3/5), `SYNTH_INDEPENDENT_32K_OPUS_RESULTS.md:34` ("inferior"), and `BENCHMARK_VALIDITY_AUDIT.md:70-74` ("No existing measurement supports a claim of superiority, inferiority or equivalence between the harnesses").

## 3. Five layers of evidence

### (a) Stateless harness performance vs Prime

Best current evidence: the four Opus paired runs on suite `b157ee63` (7 independent contexts, 21 tasks), all with the empty library and learning off (`learning_claim: false`, `learning_library_sha256` = sha256 of `[]` in every paired arm; `HISTORICAL_PERFORMANCE_AUDIT.md:94-95`).
- Accuracy: Aljure below Prime in every paired Opus run (−0.149, −0.051, −0.022, −0.061 by the docs' cluster bootstrap; only the first interval excludes 0). Sonnet, one run: −0.031, inconclusive.
- Completion: Aljure 19–21/21, Prime 20–21/21. Aljure's non-completions are text-only final replies that `done` never received (`SYNTH_INDEPENDENT_32K_OPUS_RESULTS.md:54`; `CONTRACT_ABLATION_RESULTS.md:54-60`).
- Cost and latency: Aljure at 42–51% of Prime's cost and lower p50 wall in all four Opus runs and in the Sonnet run (table, suite `b157ee63`).
- Label-count suite `dc164044` (Opus): Aljure 0.362, 0.273, 0.417 vs Prime 0.474, 0.388, 0.279; cost 42–64% of Prime's.
- Pairs suites (`e1491d5e`, `90f719a5`, `e4f4e52a`): one context each, development evidence; the latest runs tie or trail Prime by 0.02–0.12.
Sources: rows in section 1; `research/SYNTH_INDEPENDENT_32K*_RESULTS.md`, `CONTRACT_ABLATION_RESULTS.md`, `REVIEW_ABLATION_RESULTS.md`.
Status: cost/latency advantage replicated across runs (never across repeats of one plan); accuracy parity not shown, inferiority shown once (Opus, one run).

### (b) Acquisition (proposal / capture)

- **Live model proposals on benchmark tasks: 0 of 100 offered turns** (thesis pilot, arms C and E, 50 each; `THESIS_PILOT_RESULTS.md:15-18`). Recorded: every C/E case in `thesis-pilot/logs/report.json` has `promotion: "no-proposal"`; `new_record_endpoint.pooled.F1.tasks = 0`. Proposal turns cost $0.59 (C) and $0.61 (E) for nothing.
- **Offline capture feasibility** (zero model calls, `UNBLOCK_ACQUISITION.md:44-54`): 118 of 162 A/C/E tasks have an eligible capture candidate; 51 tasks (31%) have one passing the promotion rule's candidate part. Not tested live: Pilot 2 (plan `d16f383e`) is frozen and unrun (`PILOT1_RESULTS.md:112-145`).
- **Seeded library** (the only "acquired" artifact in the OOLONG domain): A1c arm 08's rule set, wrapped by a developer adapter, approved offline by rule v2 (492/975 panel records decided, 99.0% correct; `UNBLOCK_ACQUISITION.md:112-115`). Step 0 replay: 48–60% of never-seen items at 98.2–99.7% precision on three windows (`STEP0_RULE_TRANSFER.md:45-51`, evidence `research/evidence/step0/`). This is transfer of model-written code, selected and adapted by hand, not model-driven acquisition.
- **Scheduling domain, 10-26** (`FIRST_LIVE_RESULTS.md:69-80`, `var/runs/model-1793062055972/report.json`): one live acquisition run, 4 artifacts, 1 pair promoted, each arm completing 1/3 acquisition tasks; $0.167 spent + $0.395 reserved (`costs.acquisition` in `var/evaluations/evaluation-1793064236328/report.json`).
Status: model-initiated acquisition on benchmark tasks has never happened. The one live acquisition is in the scheduling domain, once.

### (c) Artifact execution (verified invocation in SCI)

- **Real-worker proof, zero model calls:** `artifact-path-proof.json` in `aljure-thesis-v1` and `aljure-unblock-v1` (`predicate-accepts`, `predicate-refuses`, `preloaded-call` returning `"HUM"`, `invocations-by-code-hash`, `drain-clears`, all `passed: true`).
- **Live, Pilot 1** (`pilot1-detail.json`, 162 task rows; `agent/events.jsonl` per arm has `artifact-library-loaded`, `artifact-applicability`, `artifact-preloaded`, `artifact-invocations` events): library preloaded in 42/42 F1 tasks per arm in D and P; refused on 12/12 F2 (spam) tasks in each; `artifact-invocations` events: 32 in `reuse-D-r1`, 21 in `reuse-P-r1`. D: the model named and called the seeded function in 28/42 F1 tasks, 262,713 recorded calls (median 9,472 per invoking task). P: controller-bound `library-labels` read by the model in 38/42 tasks, 115,674 controller invocations.
- **Scheduling domain, 10-26:** retained policy executed directly by the controller after a cold restart, 8/8 complete, 565 invocations, makespan 59.5 vs 204.125 original (`FIRST_LIVE_RESULTS.md:117-122`; `evaluation-1793064236328/report.json conditions`: estimate 59.5, FIFO 65.875 — so the retained policy only tied the fixed estimate heuristic). Diagnostic replication: 94.2 vs 206.5 on 11 healthy pairs (`POLICY_RUNTIME_DIAGNOSTIC_V1_RESULTS.md:62-63`), no model calls.
Status: execution of retained code inside the isolated worker is proven offline and observed live, with hash-attributed invocation records. Reliable.

### (d) Semantic integration (did artifact output reach the answer, and help)

- **Value reached the answer** (Pilot 1, `pilot1-detail.json`): D 8/42 F1 tasks delivered the value the function returned; P 6/42 delivered a value derived from `library-labels`. The preregistered `eligible-reuse` metric recorded **0** in every arm because the model computes in SCI and then types `Answer: N` (`PILOT1_RESULTS.md:41-44`).
- **Did it help**, preregistered rule (`pilot1-compare-fixed.json`, `decision`): `library_useful_when_supplied: false`; P − S F1 score +0.061 (CI −0.020, +0.162) at 1.52× cost; count log-error 0.252 vs 0.281; D − S +0.009 (CI −0.104, +0.159). `no_negative_transfer: true` (F2 spam: S 0.525, D 0.664, P 0.510; library refused 12/12).
- Exploratory subgroup (6 count tasks whose label the library decides): log-error 0.267 → 0.144 (D) and 0.180 (P) (`PILOT1_RESULTS.md:81-83`); 2 runs, not preregistered.
- The within-plan S spread (F1 0.404 vs 0.226) is larger than any between-arm difference, so none of the Pilot 1 differences are separable from run variance at this scale.
- Scheduling domain: the evolving agent never retrieved the retained policy (0 `artifact/inspect`, 0 `artifact/call`; `SKILL_REUSE_ANALYSIS.md:28-33`).
Status: output reaches the answer in a minority of tasks (8/42 D, 6/42 P); no measurable quality or cost benefit under the preregistered rule.

### (e) Cumulative learning

**None yet.** No run has ever carried a model-acquired artifact from one benchmark task into a later one. The thesis pilot promoted nothing (0 proposals). Pilot 1 used a hand-seeded, fixed library (no growth; `versions: []` in every trajectory). Pilot 2 (acquisition during ordinary work) is frozen and unrun. Structural transformation by a model (patch/compose) has never occurred live (`RESEARCH_THESIS_REVIEW.md:104`, `:156`). All 22 paired Aljure-vs-Prime runs used the empty library. There is no learning-curve, break-even or second-version evidence (`thesis-pilot/logs/report.json break_even_position`: all null).

## 4. Where docs and recorded data disagree

1. **`sonnet-ten32-live` Aljure cost.** `HISTORICAL_PERFORMANCE_AUDIT.md:71` says "$0.47 / $0.33, incomplete". `report.json` sums `model_cost_usd` to $0.3652 (one case has `model_cost_usd: null`), `known_model_cost_usd` to $0.469, `reserved_unknown_usd` $4.33, `unknown_calls` 1, `accounting_complete: false`. The doc's figure is the known cost; the tables above use `model_cost_usd`. Both are stated in `scorecard.json`.
2. **Campaign total.** Doc $58.6 (A $20.6, P $37.9) vs computed $58.41 (A $20.47, P $37.95). The gap is item 1.
3. **A1c model and commit.** `STEP0_RULE_TRANSFER.md:12` says the A1c rules came from "Sonnet, run `sci-ablation-speed-64k`, commit `41b53fa`". The run's `plan.json` records `source.commit dd981088…` and model `claude-sonnet-5-5`. `UNBLOCK_ACQUISITION.md:68` and `:83` call the same arm "A1c (Opus) arm 08" / "(Opus, model-authored …)". The recorded data says **Sonnet**; the Opus attribution in `UNBLOCK_ACQUISITION.md` is contradicted by `plan.json config.model`. The `41b53fa` commit may be the replay-script commit; UNVERIFIED.
4. **Pilot 1 count log-error for D.** `PILOT1_RESULTS.md:66` table gives mean log-error S 0.281, D 0.244 (D better), but `:36` and `pilot1-compare-fixed.json` give the paired D − S difference as **+0.055** (D worse, CI −0.107, +0.180). The arm-level means and the paired per-task difference point in opposite directions. The compare script's worst-error substitution for missing counts may explain it; UNVERIFIED.
5. **Thesis pilot "8 no-answer tasks … Fisher p ≈ 0.05".** Recorded statuses: C 1+3 errors, E 2+1+1 errors = 8, A 0. Matches. The `trajectories` report counts only 4 E cases as `no-answer` activation (the other 4 are C cases); consistent.
6. **"Cheaper in all 7 contexts and faster in 6"** (`SYNTH_INDEPENDENT_32K_RESULTS.md:71-72`): verified from `report.json` (7 contexts × 3 tasks; imdb is the one context where Prime was faster, 57 s vs 67 s).
7. **Review ablation L2 cost ratio 0.64** (`REVIEW_ABLATION_RESULTS.md:54`): recorded $2.7717 / $4.3404 = 0.64. Matches, but Prime's L2 cost is low because one Prime arm errored (10/11), as the doc notes.
8. **Thesis pilot and Pilot 1 totals** ($5.03; $3.71), review ablation ($24.5), answer-format ($8.14 / $8.13 / $1.62 / $2.20), contract ablation, synth runs: all match `report.json` to the cent.

Everything in the docs that I checked against `report.json` matched except items 1–4. Also verified: every paired arm's `learning_library_sha256` is `4f53cda1…` = sha256(`[]`) (checked on `synth-indep-32k-dev/results.jsonl`), as `HISTORICAL_PERFORMANCE_AUDIT.md:95` states.

## 5. Files

- `scorecard.md` (this file), `scorecard.json` (45 unique runs; fields `source_files.report/plan/results/date`, `duplicate_copies`), `tables.md`, `runs_raw.json` (all 55 directories before dedup), `build.py`, `extract.py`.
- All under `/private/tmp/claude-501/-Users-mackianni-aljure/c38a9871-7faa-4e4f-9fa1-5586b6e02c5c/scratchpad/scorecard/`.
