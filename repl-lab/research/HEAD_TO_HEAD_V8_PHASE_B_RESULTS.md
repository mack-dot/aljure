# Head-to-head v8, Phase B: results (held-out)

**LIVE MODEL RUN, held-out, run once.** Plan
`62ac8890430e87b04d7e5aea1c7e0d8b3fe5e21424775c1534e03aac5df0b385`
(protocol `HEAD_TO_HEAD_V8_PHASE_B_PROTOCOL.md`, source commit `d6d1137` clean,
SCI image `40f00364…`, Prime `c4c238ca…` / `f3e30aaa…`), approved by the owner and
launched through host policy v1 on 2026-11-04 from 15:07:15 to 15:55:33 local time,
Sonnet 5.5 through the Claude subscription. All 118 arms ran; accounting is
complete; no infrastructure failure, no timeout, no orphan container. The 49
held-out contexts were opened for the first time by the scorer during this run.
Raw traces: `var/h2h-phase-b-20261104/run-1`; committed copy:
`evidence/head-to-head-v8-phase-b-20261104/`. `report.json` is the runner's own
pre-registered report, unmodified; `phase-b-review.json` and `equivalence.json`
are derived afterwards. Lot 1 (pilot 1) is untouched.

## 1. Pre-registered primary endpoint

Context-weighted mean paired deadline-aware score difference, Aljure − Prime, over
all 49 held-out contexts, repeats averaged within (task, harness), 10,000-resample
cluster bootstrap over contexts, δ = 0.05. **Every cap failure (section 4) is kept as
a 0 score, as the protocol requires.**

| Statistic | Value |
| --- | --- |
| Estimate (context-weighted = task-weighted here) | **+0.040** |
| 95% interval | [−0.044, +0.138] |
| 90% interval | [−0.031, +0.121] |
| Decision | **inconclusive** (interval includes 0; 90% interval not within ±0.05) |
| Wins / ties / losses over 49 tasks | 7 / 35 / 7 |
| Exact sign test p | 1.0 |
| McNemar at 0.9 (Aljure-only / Prime-only successes) | 4 / 4, p = 1.0 |
| Items both scored 0 | 8 of 59 |

The held-out evidence does not separate the harnesses on accuracy. It is not
evidence of equivalence either: the interval spans from a 0.04 deficit to a 0.14
advantage.

## 2. Headline, all 118 arms

| | Aljure | Prime |
| --- | --- | --- |
| Deadline-aware mean score | 0.690 | 0.688 |
| Completed / errors | 58 / 1 | 56 / 3 |
| Cost, API-rate-equivalent | **$0.99** | $3.06 |
| Model calls | 201 | 245 |
| Agent latency p50 / p95 | **17.0 s / 35.9 s** | 23.1 s / 38.0 s |
| Tool calls / tool errors | 198 / 3 | 189 / 0 |
| Output tokens | 41,801 | 51,094 |

Total $4.05 against the $5.16 estimate; the $12 ceiling never approached. Paired
cost difference −$0.035 per task; paired latency difference −5.3 s. Aljure cost 32%
of Prime and was faster at p50 and p95 at every length. Repeat variance (10 tasks,
fresh sessions): mean absolute score change 0.20 (Aljure) and 0.18 (Prime), so
single-task differences are noisy.

## 3. Per length (secondary, descriptive)

| Length | Contexts | Aljure | Prime | Difference | 95% interval | W/T/L | Cost per task A / P | p50 A / P |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4K | 8 | 0.880 | 0.760 | +0.135 | [−0.062, +0.416] | 2/5/1 | $0.014 / $0.048 | 16 / 23 s |
| 8K | 7 | 0.778 | 0.889 | −0.071 | [−0.214, 0.0] | 0/6/1 | $0.016 / $0.046 | 20 / 21 s |
| 16K | 14 | 0.717 | 0.600 | +0.125 | [−0.036, +0.339] | 2/11/1 | $0.019 / $0.054 | 20 / 23 s |
| 32K | 7 | 0.545 | 0.727 | −0.143 | [−0.286, 0.0] | 0/5/2 | $0.012 / $0.046 | 15 / 22 s |
| 64K | 8 | 0.601 | 0.575 | +0.079 | [−0.138, +0.375] | 2/5/1 | $0.021 / $0.066 | 20 / 27 s |
| 128K | 5 | 0.600 | 0.600 | 0.000 | degenerate | 1/3/1 | $0.018 / $0.046 | 24 / 28 s |

No stratum is decided. The 128K "equivalent" flag in `report.json` is a degenerate
interval from five contexts whose two non-ties are partial credits of 0.00002 and
0.013; it is not a finding. The 64K stratum carries four of the five cap failures.
The 32K deficit is the one stratum where every non-tie went against Aljure; rounds
16 and 50 are traced in section 6.

## 4. Plan defect: the $4.40 per-arm cap, and the diagnostic comparison

The plan set `usd_per_arm` to $4.40 to bound a single arm's spend under the $12
ceiling. The gateway reserves the full context bound, $4.33, on every call and
releases it on the receipt, so a new call is refused once an arm's known spend
exceeds about $0.07. Pilot 1's $12 cap never bound; this one did, on the arms whose
calls carry the most tokens:

| Arm | Length | Harness | Mechanism |
| --- | --- | --- | --- |
| 9, 47, 66, 95 | 64K | Prime | gateway refused the next reservation; the relay returned 429; Prime's loop ended with a provider error and no answer file |
| 67 | 64K | Aljure | controller refused the eighth call: "Global provider budget exhausted" |

The cap was identical for both arms but not symmetric in effect: Prime's calls
cost more, so it hit the cap four times to Aljure's one. Classification is
mechanical (`host-policy/review_phase_b.py`: the controller's budget message, or a
429 in Prime's session log). Both arms' known spend stayed under the ceiling, which
the cap was for; the cap was simply set below one reservation plus a working
allowance. Nothing was altered during or after the run.

**Official endpoint (section 1) keeps all five as 0.** **Diagnostic, not
pre-registered:** the same analysis over the 47 contexts where neither arm was
cap-affected gives +0.028, 95% [−0.048, +0.119], 90% [−0.037, +0.103],
inconclusive, W/T/L 5/36/6. The conclusion does not change.

Round-by-round reconciliation against the raw score records
(`phase-b-review.json`, ties are differences of exactly 0): official W/T/L over the
59 items including repeats is 8/44/7. Round 5 (64K, Prime cap error) is a +0.00002
Aljure "win" by the letter of the rule, Aljure's text answer having earned the
synth scorer's partial credit; round 24 is +0.013 in the same way; round 34 is an
Aljure cap error (−0.75); round 48 an Aljure 1.0 against a Prime cap error. The
four rounds are cap-affected as the owner noted, and round 5 is a tie in every
sense but the frozen rule's.

Fix for any later paired run: `usd_per_arm` = one reservation plus an allowance
(for example $4.93, an effective $0.60 per arm) with the ceiling rule unchanged
(refuse when spend plus `usd_per_arm` would exceed $12). Not applied to this run.

## 5. What the text-answer channel did

Aljure delivered 18 of 59 answers through `text-answer-v2`, 15 of them on the first
reply with no correction. Those answers averaged **0.50**; answers delivered by a
`done` call averaged **0.79**. Two of the three Aljure tool errors (a vector cast
at 128K, an arity error at 32K) were followed by a text answer scoring 0. The
channel rescued answers the Lot 1 contract would have rejected, but the model
reaches for it when it has stopped computing, so its answers are weaker on average.
Prime's final-text rule never fired (56 file answers, 3 cap errors). Aljure made 3
command rejections (all corrected) and used `user-records` in 17 arms and
`index-of` in 3; `pairs-of` and `selection-audit` were not used (no Pairs tasks).

## 6. Root cause of rounds 16 and 50 (32K, Aljure 0 against Prime 1)

**Round 16, yahoo window 50017: "is Entertainment & Music more, less or the same
frequency as Health?" (gold: more common).** Both arms read the same 414
questions. Both began with keyword regexes: Aljure's first count gave 43 against 30
(which would have been right); Prime's gave 38 against 34. The first meaningful
divergence is what each did next. Prime wrote "Too close; read them", printed every
matching question and judged each by hand, and answered correctly. Aljure re-tuned
its regexes (dropping tv, show, game, video from the entertainment list and adding
period, body, eye, hair, exercise to the health list), got 27 against 45, trusted
the second count and answered wrong. Classification: **verification**. Retrieval
was identical; the computation was a heuristic in both arms; Prime escalated to
reading and judging, Aljure stopped at a re-tuned heuristic. Not a controller
effect: no rejection, no error, three evaluations, a `done` answer.

**Round 50, multinli window 70017: "among December instances, is contradiction
more, less or the same frequency as neutral?" (gold: less common).** Both arms
extracted exactly the same 26 December pairs in one expression. Neither computed
further; both labelled the pairs by reading. Prime tallied explicitly ("about 9
contradiction and about 10 or more neutral") and answered correctly; Aljure answered
in one shot after the read, with no tally recorded, and answered wrong.
Classification: **verification of a semantic judgement**. Retrieval identical;
computation absent in both; Prime verbalized a count, Aljure did not. The model's
NLI labelling is noisy in both studies; the harness difference is that Prime's
prompt and kernel habit produced an explicit tally.

Both losses are of one kind: Aljure accepted a cheaper judgement (a heuristic
count, a one-shot read) where Prime spent one more step verifying. This matches
pilot 1's Pairs losses (user-set selection) and is the mechanism behind Aljure's
lower cost: fewer steps. The repository's verification helpers (`structured_labels`,
`uncertainty_audit`, off in this plan) target exactly this and are the next
candidate for a frozen comparison.

## 7. Host and isolation record

Gate `gate-1793822830.json` admitted the run at 86.6% swap with two warnings (free
memory under 512 MB; load above CPU count), credential 4.8 h from expiry; the
watcher script waited 16 minutes for swap to fall below 88%. During the run (403
samples at 5 s): swap 80.4% to 96.7% of a swap file macOS grew from 8 to 11 GB, free
memory 57 MB to 2.3 GB, one-minute load 7.4 to 44.3, Docker Desktop session
unchanged. Docker events: 118 containers created and destroyed (two restarts of
the SCI prewarm), 59 SCI workers exited 0, 59 Prime containers killed at cleanup
(the adapter's normal stop), no OOM kill. SCI startup 717 / 1,081 / 2,277 ms (min /
median / max), 59 cleanups confirmed, gateway cleanup ok 118 of 118. Equivalence
check (`benchmark.equivalence`): 59 of 59 item pairs received identical public
inputs and identical per-request model settings.

## 8. Limitations

- One run of one plan; repeat variance 0.18–0.20 per task.
- The cap defect removed five arms; both views (official, diagnostic) are given.
- Cross-length windows of one dataset share a source pool (readiness report, risk 1).
- The host ran at 80–97% swap; latencies are comparative only.
- The 32K sealed suite's sample came from partially pinned rows for three windows.
- The held-out windows have now been seen once by both harnesses; a second run on
  them is a repeat, not held-out.

## 9. Recommendations

1. **Fix the cap before any paired run** (section 4). Zero cost; removes the only
   plan-caused failure mode.
2. **Make the text channel earn its answers.** Keep `text-answer-v2` for delivery,
   but when the root's last evaluation errored or no `done`/`source` computation
   preceded the text, request one verification step before accepting (one
   correction already exists; this is a bounded second). Expected effect: the 18
   text answers at 0.50 are the largest addressable loss in this run.
3. **Spend one verification step where Prime does.** The two 32K losses and the
   Pairs losses share a mechanism: a cheaper judgement accepted without a check.
   Freeze a paired comparison of `uncertainty_audit` on the development suites
   before touching held-out data again.
4. **Keep the cost and latency position** (32% of Prime, 6 s faster at p50 on
   held-out data). It is now replicated out of sample.
5. **Pilot 2** (OBLIQ-Bench math, LongBench Pro dev contexts) is prepared and
   unfrozen; freeze it as its own campaign after items 1 and 2.
