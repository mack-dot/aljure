# Contract ablation (control, F1, F2): results

**LIVE MODEL RUNS, development evidence.** On 2026-10-29 the operator approved
three frozen plans, to run through the Claude subscription only. They ran in
order, with no change between runs.

**Common settings:** Opus 5.5, open limits, the 21-task dev suite `b157ee63…`,
clean commit `41b53fa`, and native Prime unchanged.

| Plan | Aljure contract | plan_sha256 | Output |
| --- | --- | --- | --- |
| Control | original | `87d8c949…` | `var/benchmarks/contract-ablation-opus-control` |
| F1 | `truncated_turn_retries: 1` | `52f51590…` | `…-f1` |
| F2 | `terminal_text_answer: true` | `b1844732…` | `…-f2` |

**Evidence:** `evidence/contract-ablation-opus/comparison.json`, from
`scripts/contract_ablation_compare.py`. The criteria were fixed beforehand in
`CONTRACT_FIX_ACCEPTANCE_CRITERIA.md`.

**Billing:** the runs report "API-rate-equivalent subscription usage; no API
credit fallback". The costs below are at API rates.

## Results

| | Control: Aljure | Control: Prime | F1: Aljure | F1: Prime | F2: Aljure | F2: Prime |
| --- | --- | --- | --- | --- | --- | --- |
| Mean score | 0.853 | 0.904 | 0.876 | 0.898 | 0.805 | 0.866 |
| Completed | 21/21 | 21/21 | 21/21 | 21/21 | **19/21** | **20/21** |
| Scores ≥ 0.9 | 16 | 18 | 17 | 16 | 15 | 16 |
| Cost | $1.80 | $3.74 | $1.64 | $3.95 | $1.54 | $3.00 |
| Aljure/Prime cost | 0.48 | | 0.42 | | 0.51 | |
| Model calls | 104 | 120 | 93 | 128 | 91 | 95 |
| Latency p50 / p95 | 24.1 / 58.8 s | 27.2 / 56.4 s | 30.2 / 43.1 s | 33.6 / 67.6 s | 26.3 / 55.0 s | 31.6 / 48.6 s |
| Paired difference (95% cluster bootstrap) | −0.051 [−0.147, 0.000] | | −0.022 [−0.082, +0.016] | | −0.061 [−0.156, 0.000] | |
| Wins / ties / losses | 1 / 17 / 3 | | 1 / 17 / 3 | | 1 / 18 / 2 | |

## What actually triggered

| | Control | F1 | F2 |
| --- | --- | --- | --- |
| Provider responses (Aljure) | 104 | 93 | 91 |
| Truncated turns | 0 | **0** | 0 |
| F1 retries | 0 | **0** | 0 |
| Arms with text-only replies (each got the correction) | 2 → both `done` | 1 → `done` | **3 → 2 `done`, 1 failed** |
| Accepted `FINAL ANSWER` | 0 | 0 | **0** |
| Contract violations (auditor) | 0 | 0 | 0 |

**F1 never fired.** There were 0 truncations in 288 Aljure responses across the
three plans; the overall rate is now about 1 in 840. Every F1 score, cost and
latency difference from the control, including its lower p95, is therefore
run-to-run variation. None of it is an F1 effect. Prime's p95 moved by a similar
amount (56.4 s → 67.6 s).

**F2 fired three times and rescued nothing.** The F2 arm failure is task 1,
`415040036` (negation, gold "more common than"):
1. Response 2: a text-only answer with the correct conclusion. The correction
   offered `done`, or exactly one `FINAL ANSWER:` line.
2. Response 3: Opus used the marker, `FINAL ANSWER: Answer: False is more common
   than True`, which is correct. But it put a paragraph of explanation above it.
3. The strict one-line rule rejected the reply, and the task failed.

**So:**
- **No false completion occurred.**
- **A correct answer was falsely rejected.** Aljure answered this task correctly
  in all three other runs.
- **The other two F2 triggers recovered through `done`.** That is what the
  original correction achieves 6 times in 7 across the four Opus runs.
- **Net effect of F2:** −1 task on this run.

## Two failures that were not the contract

**The isolation gate failed closed on one arm (F2, Aljure, MultiNLI `715070023`):**
- The worker's isolation preflight timed out at `docker info` after 5 s:
  `worker-audit/preflight/c31e…json`.
- The SCI worker was refused, no provider call was made (0 receipts), and the
  arm was recorded as an error.
- **This should have stopped the chain** under the operator's instruction. The
  runner treats a per-arm infrastructure failure as a failed arm and continues,
  and the progress monitor's filter did not match it. The remaining 10 F2 arms
  ran after it, and their gates passed.
- Isolation was not weakened: the gate refused to start the worker.
- **The other 125 arms:** no failed worker preflights; every exit code was the
  normal cleanup −9.

**Prime failed the same MultiNLI task in F2, by its own delivery:**
- Its root started 6 sub-agents and replied "Six labelers are running; waiting
  for results."
- The run then ended without writing an answer, which is Prime's equivalent of a
  text-only finalization failure.

## Run-to-run variation

The reference is four Opus runs with Prime identical in every one: the earlier
run `d6e9b40d`, then control, F1 and F2.

| | d6e9b40d | Control | F1 | F2 | SD of run means | Range |
| --- | --- | --- | --- | --- | --- | --- |
| Prime mean | 0.919 | 0.904 | 0.898 | 0.866 | 0.022 | 0.053 |
| Aljure mean | 0.771 | 0.853 | 0.876 | 0.805 | 0.047 | 0.106 |
| Paired difference | −0.149 | −0.051 | −0.022 | −0.061 | 0.055 | 0.127 |

**How to read the spread:**
- **Prime's spread is a lower bound for Aljure's, not a measure of it.** Aljure's
  is about twice as large, and most of it comes from delivery failures:
  2 in `d6e9b40d`, and 1 in F2 caused by F2 itself.
- **Delivery failures alone move a run's mean by 0.048 per task.**
- **With the delivery-free runs (control and F1)**, Aljure's mean is 0.853–0.876,
  and its paired difference is −0.051 and −0.022. Both 95% intervals reach 0.

**Count errors over the four runs** (`—` = no answer):

| Task (gold) | Aljure | Prime |
| --- | --- | --- |
| MultiNLI (129) | −9, −3, −3, — | 0, −5, −2, — |
| AG News 024 (171) | +1, −4, −3, −3 | −2, 0, −1, −1 |
| AG News 025 (40) | +6, +5, +4, +2 | +2, +2, +2, +2 |
| AG News 026 (16) | +6, +6, +5, +6 | +6, +6, +5, +7 |

**What the count errors show:**
- **Prime's exact 129 did not recur** (0, −5, −2, then a failure). That supports
  the earlier estimate that it was partly chance.
- **Aljure's count error is consistently larger**: mean absolute 4.4 across 15
  answered cases, against Prime's 2.9 over the same 15.
- **On 026 both harnesses make the same error.**

## Against the preregistered criteria

| Criterion | Result |
| --- | --- |
| **A. Contract integrity** | **Held.** All 62 Aljure arms with model traffic are conformant, with 0 violations and no retries or terminal answers outside their switch. One arm is unauditable: zero calls, the isolation gate failing closed, explained above. The rule says an unauditable arm fails A "until explained", and this one is explained |
| **B. F1** | **Not triggered.** No truncation occurred, and no F1 failure. F1 rests on the offline proof |
| **C. F2** | **Not fixed.** 3 triggers; 1 unrecovered, caused by F2's own one-line rule |
| **D. Regressions** | F1: none attributable, since it never fired. F2: −1 task (task 1) |
| **Verdict** | **Not "fixed without compromising the contract"**: F2 failed C. The contract itself held |

## Decision

| Fix | Decision | Reason |
| --- | --- | --- |
| **F1** | **Retain, on its own** | No live trigger in about 290 responses, no regression, no cost. Offline proof that it rescues the recorded truncation. It is a safety net, not a measured gain |
| **F2 as built** | **Reject** | Its only live effect was to reject a correct, marked answer. The original correction recovered 6 of 7 text-only arms under Opus |
| **F1 + F2 combined** | **No** | F2 is rejected |
| **F2b**: accept only a final line `FINAL ANSWER: …` after the instruction; text above it is allowed but never used | **Not adopted; needs its own test** | It would have accepted this reply. It loosens a safety rule, so it needs offline adversarial tests and its own plan. Low priority: text-only failures are about 1 in 7 triggered arms, and triggers about 2–4 per run |

**For the review evaluation:** base contract = F1 only. The text-only correction
stays the original one.
