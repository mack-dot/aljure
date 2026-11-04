# Aljure verification mechanism: results of the development ablation (verification-dev-v1)

**LIVE MODEL RUN, development evidence, run once.** Plan
`135230e46c5c5d2f0de75d491d954d2e4379c8693cd0afde4aaeae4a9b5d1d83`
(protocol `VERIFICATION_DEV_PROTOCOL.md`, source commit `7846f2d` clean), approved
by the owner ("i approve for whenever") and launched through host policy v1 on
2026-11-04. Six arms per task on 20 development comparison and count questions
(24 items with the seeded repeats), 144 arms, Sonnet 5.5 through the Claude
subscription. Raw traces: `var/verification-dev-20261104/run-1`; committed copy:
`evidence/verification-dev-20261104/`. `report.json` is the runner's pre-registered
report; `verification-review.json` is derived afterwards. Nothing in the frozen run
was altered. Written against the owner's goal "Aljure Verification: Complete,
Diagnose, and Improve".

## 1. Frozen experiment completion and integrity

Two segments under one plan. Arms 0–45 ran 16:29:29–16:51:01; the driver then
refused arm 46 on its own 10 GiB disk floor (free disk had fallen to 6.4 GiB
because macOS swap grew to 21 GB under the Docker VM, Chrome and Cursor). No
model call was interrupted. After disk recovered to 21 GB and swap fell under
88%, `--resume` continued arms 46–143 from 17:03:42 to 17:52:07 after a new
preflight and host gate; the first 46 rows were kept byte for byte
(`resumes.jsonl` records the resume at index 46). No completed arm was restarted
and no failed arm was rerun.

Integrity: 144 rows in the plan's order; 571 provider receipts equal 571 recorded
calls; accounting complete on every row, no unknown reservation; gateway cleanup
ok on 144 of 144; 96 SCI workers started (startup 957 / 1,451 / 3,790 ms min /
median / max) and all cleanups confirmed; Docker Desktop session unchanged within
each segment; no orphan container. Known spend $5.29 against the $12 maximum;
the largest single arm spent $0.24 against the $0.60 allowance, so the
reservation-aware cap fix held. Host saturation was severe (swap 79–98%, free
memory down to 27 MB, one-minute load up to 107), so latency figures are
comparative only.

Three arms did not complete; none was excluded:

| Arm | Item | Cause |
| --- | --- | --- |
| 8, A2 (text off) | 2 | the model answered "Answer: 24" in text with no tool call (gold 25, which would have scored 0.75); rejected after the single correction; the Lot 1 failure mode |
| 21, P1 | 4 | Prime spawned subagents (`rlm.spawn`); their concurrent reservations were refused by the $4.93 per-arm cap (one reservation in flight); the children got 429 and the arm ended with a provider error |
| 56, P0 | 10 | the same: `rlm.spawn`, 429, no answer |

The two Prime failures are the parity-matrix row 3b interaction (the cap throttles
Prime's asynchronous children) and the first recorded runs in which Prime used
subagents at all. They are cap-affected and kept as 0 in every pre-registered
figure; section 3 gives the diagnostic without them.

## 2. Pre-registered primary endpoint: A1 − A0

Context-weighted mean paired deadline-aware score difference over the 10
development contexts, repeats averaged within (task, harness), 10,000-resample
cluster bootstrap over contexts, δ = 0.05.

| Statistic | Value |
| --- | --- |
| Estimate | **+0.150** (task-weighted +0.150) |
| 95% interval | [0.000, +0.300] |
| 90% interval | [+0.050, +0.250] |
| Decision (campaign rule) | **inconclusive**: the 95% lower bound is exactly 0, not above it |
| Wins / ties / losses, 20 tasks | 3 / 17 / 0 |
| Exact sign test p | 0.25 |
| Paired cost difference | +$0.0145 per task (A1 $0.0327 against A0 $0.0175, 1.9×) |
| Paired agent latency difference | +5.6 s (p50 22.4 against 20.7 s; p95 62.4 against 39.7 s) |
| Tool errors / incomplete arms | A1 2 / 0; A0 1 / 0 |

A1 never lost to A0. Its three wins are two contexts of yahoo-topic and
negation comparison at 32K plus the multinli entailment-against-neutral task,
which it won on both of its trials (A0 lost both). Repeat variance within Aljure
was zero on the four repeated tasks; Prime's baseline flipped on one of them.

Pre-registered GO rule (`VERIFICATION_DEV_PROTOCOL.md` §5): A1 − A0 ≥ 0.10 and
A1's cost per task ≤ 50% of P1's. Both hold (+0.150; 47%), so the rule reads GO.
Section 12 explains why the recommendation is nevertheless ITERATE.

## 3. Secondary comparisons (same statistic; descriptive)

| Contrast | Estimate | 95% interval | W / T / L | Reading |
| --- | --- | --- | --- | --- |
| A2 − A0, text answers off | +0.072 | [−0.056, +0.222] | 2 / 17 / 1 | no evidence the text channel helps; A2 lost one answer outright to the rejection rule |
| A3 − A1, evidence gate | −0.091 | [−0.241, +0.019] | 1 / 17 / 2 | the gate arm trails the plain contract (section 6) |
| P1 − P0, the contract in Prime | **+0.150** | [0.000, +0.300] | 3 / 17 / 0 | the identical lift, on different tasks |
| A0 − P0, base against base | −0.088 | [−0.200, 0.000] | 0 / 17 / 3 | the Phase B gap, reproduced on development data |
| A1 − P1, verified against verified | −0.088 | [−0.225, +0.037] | 1 / 16 / 3 | the gap is unchanged by the contract |
| A1 − P0, best Aljure against baseline Prime (exploratory) | +0.073 | — | 2 / 16 / 2 | at 56% of Prime's cost |
| **(A1 − A0) − (P1 − P0)**, harness-specific part | **0.000** | [−0.200, +0.200] | — | no harness-specific effect detectable |

Diagnostic, not pre-registered, without the two items whose Prime arm was
cap-affected (items 4 and 10, which also carry two of A1's three wins): A1 − A0
+0.100 [0.000, +0.250], P1 − P0 +0.100 [0.000, +0.250], difference-in-differences
again 0.000. The conclusion does not depend on the cap failures.

Exploratory arms against baseline Prime: A1 0.888, A3 0.771, A2 0.781, A0 0.721
against P0 0.815 and P1 0.940 (deadline-aware means over 24 arms each).

## 4. Per-task paired score ledger (A0 A1 A2 A3 P0 P1; `!` = did not complete; repeats are trial 1 of the same task)

```
 1  8K yahoo     Health vs Family&Rel.            1.00 1.00 1.00 1.00 1.00 1.00
 2  8K app_rev   count in date range (gold 25)    0.56 0.56 0.00! 0.75 0.56 0.56
 3 32K yahoo     Computers vs Science             0.00 1.00 1.00 0.00 1.00 1.00
 4 32K multinli  entailment vs neutral            0.00 1.00 0.00 0.00 0.00 0.00!
 5  8K app_rev   April subset comparison          1.00 1.00 1.00 1.00 1.00 1.00
 6  8K imdb      positive before 2024-02-01       0.00 0.00 0.00 0.00 0.00 1.00
 7  8K app_rev   (repeat of 5)                    1.00 1.00 1.00 1.00 1.00 1.00
 8  8K formality informal vs formal               0.00 0.00 0.00 0.00 0.00 1.00
 9 32K negation  April subset comparison          0.75 0.75 0.75 0.75 1.00 1.00
10 32K negation  False before 2022-10-02          0.00 1.00 1.00 1.00 0.00! 1.00
11 32K yahoo     Business vs Family&Rel.          1.00 1.00 1.00 1.00 1.00 1.00
12 32K agnews    Sci/Tech vs World                1.00 1.00 1.00 1.00 1.00 1.00
13 32K agnews    user-subset comparison           1.00 1.00 1.00 1.00 1.00 1.00
14 32K multinli  (repeat of 4)                    0.00 1.00 0.00 0.00 1.00 1.00
15  8K imdb      date-range subset                1.00 1.00 1.00 1.00 1.00 1.00
16  8K imdb      (repeat of 15)                   1.00 1.00 1.00 1.00 1.00 1.00
17  8K negation  False vs True                    1.00 1.00 1.00 1.00 1.00 1.00
18 32K multinli  dates represented 3 times        1.00 1.00 1.00 1.00 1.00 1.00
19  8K yahoo     Entertainment vs Health          1.00 1.00 1.00 1.00 1.00 1.00
20 32K yahoo     (repeat of 11)                   1.00 1.00 1.00 1.00 1.00 1.00
21  8K negation  July subset comparison           1.00 1.00 1.00 1.00 1.00 1.00
22  8K formality dates represented 2 times        1.00 1.00 1.00 1.00 1.00 1.00
23  8K multinli  dates represented 2 times        1.00 1.00 1.00 1.00 1.00 1.00
24  8K multinli  November subset comparison       1.00 1.00 1.00 1.00 1.00 1.00
```

16 of 24 items were six-way perfect. Every decisive item is a semantic
comparison (topic, sentiment, formality, NLI, negation) that needs per-item
judgement; every count question with a machine-checkable property (dates
represented k times, subset counts) was solved by every arm.

## 5. A1 improvement attribution (every task where A1 beat A0)

Reconstructed from both arms' tool-call ledgers. **No A1 arm called
`audit-labels` and none recorded an `:unknown` label; `show-items` was called in
one arm (item 10). No improvement below is attributed to a primitive that was not
invoked.**

| Item | First meaningful divergence | What A1 did that A0 did not | Tokens / calls | Same mechanism in P1? | Class |
| --- | --- | --- | --- | --- | --- |
| 3, yahoo 32K | after the first keyword count (both arms made one) | two further regex refinements, then printed the non-matching questions and read them before deciding; A0 stopped at one count and one list | 1,889 vs 1,554 output tokens; 7 vs 4 calls; $0.039 vs $0.026 | P0 and P1 both correct by one keyword pass; no | **evidence selection** (reads the excluded items), modest cost |
| 4, multinli 32K, trial 0 | the first expression | A0 read the first 1,500 and last 600 characters and answered with no computation; A1 computed a word-overlap proxy over all 440 pairs and answered from the ratio | 797 vs 298 tokens; 3 vs 3 calls; $0.015 vs $0.006 | P1 failed (cap); P0 wrong with 4 calls | **computation** (a proxy, not a label record) |
| 14, the same task, trial 1 | the second expression | A0 counted the literal words "entailment" and "neutral" in the text and answered in prose; A1 paged through all 438 pairs, recorded hand labels as strings in SCI defs, tallied 137 against 156 and answered | 4,922 vs 424 tokens; 9 vs 3 calls; $0.137 vs $0.008 (17×) | P0 and P1 both read and hand-labelled; P1 correct | **verification by exhaustive labelling**, token-dependent |
| 10, negation 32K | after the date split (both arms isolated the 110 "before" items) | A0 printed the 110 items and judged the balance in a text reply; A1 parsed the definitions, paged the items with `show-items`, recorded five index sets of judged-False items as defs, computed 65/110 against 356/569 and answered by `done` | 9,638 vs 3,362 tokens; 12 vs 5 calls; $0.178 vs $0.054 (3.3×) | P1 did the same with a Python dict of 0/1 labels over all 683 items (13 calls, $0.24), correct; P0 spawned children and died on the cap | **verification by exhaustive labelling** with a recorded label structure; the one use of a primitive |

Two of the three A1 wins (items 10 and 14) are the same mechanism: the instruction
made the model label every item, keep the labels in the worker, and count them,
at 3–17 times the baseline cost. The third (item 3) is one more read of the
contested items. P1's three wins (items 6, 8, 10) are the same mechanism on
Prime: it read whole items instead of prefixes, kept an explicit set of labelled
indices and counted (item 8: "74 informal and 70 formal, margin 4"; item 10: a
dict over all 683 items). The mechanism is the instruction, carried out with each
harness's native state, and it costs tokens in proportion to the item count.

Classification over the three A1 improvements: computation 1, evidence selection
1, verification by exhaustive labelling 2 (one task twice); none attributable to
a verification primitive except the paging helper in item 10, which replaced a
`subvec` the model could have written itself.

## 6. A3 failure attribution (evidence gate)

A3 = A1 plus `targeted_review` (the one-time controller notice when the model's
last `audit-labels` report left items open) and its prompt line. **The gate never
fired: zero evidence-gate events in 24 arms**, because no arm ever called
`audit-labels`, so there was never an audit for the controller to check. Every A3
difference from A1 is therefore prompt variation under the extra line, not a gate
decision. Per regression:

| Item | A1 | A3 | What A3 did |
| --- | --- | --- | --- |
| 3 | 1.00 | 0.00 | one keyword pass each way and a 70-item read, then answered; it never refined or reread like A1 |
| 4 | 1.00 | 0.00 | computed the same word-overlap proxy as A1 (after one unmatched-delimiter error) and read it the other way |
| 14 | 1.00 | 0.00 | read 70 of 438 pairs and answered |
| 2 | 0.56 | 0.75 | a count off by one instead of two: ordinary variation |
| 10 | 1.00 | 1.00 | recorded explicit index sets like A1 and was right at 7 calls, $0.085 |

So the gate neither rejected a valid answer, nor triggered a correction, nor
consumed budget, nor prevented a text completion: it was inert. The regression is
within-prompt variation on three semantic items, with A3 spending less than A1
(mean $0.023 against $0.033, p95 51 s against 62 s). Design conclusion: a gate
conditioned on an audit the model never produces is dead code; it adds a prompt
line and no verification.

## 7. Text-channel reliability

Phase B's descriptive gap (text answers 0.50 against computed 0.79) does not
reproduce here. Within A0, text-delivered answers scored 0.737 (14 arms) against
0.700 for `done` answers (10 arms); within A1 0.82 against 0.92; within A3 0.84
against 0.73. The ablation arm A2 (text off) scored +0.072 above A0 with a wide
interval, won items 3 and 10 where A0's text answers were wrong, and lost item 2
outright when its text answer "Answer: 24" was rejected. P1 delivered 8 of 24
answers through its final text, all but one correct. Reading: the channel is a
delivery path, not a cause of weak answers; what predicts a wrong answer is
answering without an item-level tally, whichever channel carries it.

## 8. Token, cost and latency effects

| Arm | Mean | Cost per task | p50 / p95 | Calls | Output tokens | Cost on the 16 perfect items | Cost on the 8 decisive items |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | 0.721 | $0.0175 | 20.7 / 39.7 s | 3.3 | 817 | $0.0151 | $0.0221 |
| A1 | 0.888 | $0.0327 | 22.4 / 62.4 s | 4.1 | 1,466 | $0.0194 (1.3× A0) | $0.0594 (2.7× A0) |
| A2 | 0.781 | $0.0190 | 21.9 / 36.1 s | 3.5 | 907 | $0.0150 | $0.0270 |
| A3 | 0.771 | $0.0232 | 18.8 / 51.0 s | 3.5 | 1,021 | $0.0186 | $0.0324 |
| P0 | 0.815 | $0.0582 | 22.4 / 46.8 s | 4.6 | 1,061 | $0.0503 | $0.0738 |
| P1 | 0.940 | $0.0700 | 23.7 / 80.5 s | 4.7 | 1,417 | $0.0530 | $0.1040 |

The contract costs little where it cannot help (1.3× on the perfect items, mostly
a longer prompt) and 2.7× where it does help, because it makes the model label
every item. Aljure keeps its cost position at every level: A1 is 47% of P1 and 56%
of P0. Latency: A1's p95 rises to 62 s, still under P1's 80 s.

## 9. Evidence of usage of the verification machinery

| Mechanism | Arms that used it |
| --- | --- |
| `show-items` (paged item display) | 1 of 48 verification arms (A1, item 10, 2 calls) |
| `audit-labels` | 0 |
| `:unknown` labels | 0 |
| evidence gate (A3) | 0 events |
| recorded per-item labels in SCI (defs of label strings or index sets) | A1 items 10 and 14; A3 item 10 |
| `index-of`, `user-records` (pilot-2 prelude helpers) | A0 5 calls, A1 1, A2 3, A3 4; `user-records` 2 calls in each arm |
| Prime: explicit label dict or set in the kernel | P1 items 8 and 10; P0 none |

## 10. General against harness-specific improvement

The contract produced the same +0.150 in both harnesses, on different tasks, and
the difference-in-differences is 0.000 with a ±0.20 interval. The mechanism seen
in the traces (label everything, keep the labels, count) is available to any
harness with a persistent state and is exactly what Prime did in its kernel. The
only Aljure-specific element observed was paging through `show-items` once. There
is no evidence in this run of a capability uniquely enabled by Aljure; there is
evidence that Aljure delivers the same instruction-induced gain at about half of
Prime's cost.

## 11. Minimal recommended architecture

Evidence-based, in the owner's order of preference for less machinery:

- **Remove the evidence gate** (`targeted_review`). It never fires without an
  audit, costs a prompt line, and A3 trailed A1.
- **Keep the contract as prompt-only** (A1's text), since the primitives were
  not what moved the result. The prompt should ask for the behaviour the traces
  show working: enumerate the items the question depends on, record one label
  each in the worker, count from the record, and only then answer.
- **Make verification selective, not mandatory.** On the 16 perfect items the
  contract bought nothing and cost 1.3×. The observable condition that separated
  A0's losses from its wins in this run was "the answer was committed without any
  item-level tally in the worker" (items 4, 10 and 14; item 3 is the exception,
  where a tally existed but was a keyword heuristic). A controller check for that
  condition can be deterministic: before accepting a root `done` on a comparison
  or count question, look for an evaluation in the ledger that produced a count
  over a filtered or labelled collection; if none exists, ask once. This is
  candidate B of the goal, and it replaces the dead gate.
- **Deterministic verification only where it is machine-checkable** (candidate
  C): date and user-subset counts were already perfect everywhere; `audit-labels`
  coverage and arithmetic checks are only meaningful once labels are recorded,
  and must never be described as checking label correctness.

## 12. Decision and the proposed next controlled experiment

**Recommendation: ITERATE.** The pre-registered GO rule fires (+0.150 at 47% of
Prime's cost), but three facts argue against spending held-out data now: the
95% interval touches zero on 10 contexts; the gain is general (difference-in-
differences 0.000), so a held-out run would test an instruction, not Aljure; and
the mechanism costs 2.7× on the tasks it helps while 16 of 24 development items
did not need it. The cost advantage survives either way.

Next controlled experiment, development data only, to be frozen for separate
approval (no inference authorized here):

| Arm | Contract | Isolates |
| --- | --- | --- |
| V0 | A0 (text-answer-v2) | baseline |
| V1 | prompt-only: A1's text, SCI helpers absent | the instruction alone |
| V2 | helpers-only: `show-items` and `audit-labels` loaded, no contract text | the primitives alone |
| V3 | selective: V0 plus the deterministic "no tally before done" check, one request | candidate B |
| Q0 / Q1 | Prime base / Prime with V1's text | general against specific, again |

Inputs: a fresh verification development suite (same profiles, next seeded
questions) with the count questions kept as negative controls, 20 tasks, 20%
repeats, 6 arms, about $6, under the reservation-aware cap with a concurrency
allowance so Prime's subagents are not refused (which needs either a higher
per-arm cap or a lower maximum spend; the two cannot both be $12 and $4.93).
Primary: V3 − V0; secondaries V1 − V0, V2 − V0, V1 − V2, and the harness
difference-in-differences. GO to held-out only if V3 or V1 gains ≥ 0.10 with a
95% lower bound above zero and the cost ratio to Prime stays ≤ 0.5.

## Files

- `var/verification-dev-20261104/run-1/`: `plan.json`, `preflight.json`,
  `authorization.json`, `results.jsonl`, `report.json`, `resumes.jsonl`,
  `verification-review.json`; hashes in the evidence manifest.
- Host policy: gates `gate-1793827764.json` (admitted 16:29) and
  `gate-1793829819.json` (admitted the resume 17:03), the six refused gates
  between them (foreign containers; swap), monitors and summaries for both
  segments, `launch_verify_when_clear.sh`, `resume_verify_when_clear.sh`.
