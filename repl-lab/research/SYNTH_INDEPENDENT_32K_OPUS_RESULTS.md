# OOLONG-synth independent contexts, 32K (dev): Opus 5.5 results

**LIVE MODEL RUN, development evidence.**
- **Plan:** `d6e9b40d…` (commit `f96f0fb`). The operator approved it and it ran on 2026-10-29.
- **Arms:** all 42 ran, and cost accounting is complete.
- **Tasks:** the same 21 dev tasks as the Sonnet run (`SYNTH_INDEPENDENT_32K_RESULTS.md`).
- **What changed from the Sonnet run:**
  - the model: `claude-opus-5-5`, with rates verified against its official overview page;
  - the per-task limits, opened because Prime's own benchmark sources state no call cap or deadline:
    - 1,000 calls per arm and 1,000 Aljure steps per session;
    - a 900 s safety deadline;
    - 4 MiB requests, 64 MiB task output, and $100 per arm.
- **Evidence:** `evidence/synth-indep-32k-dev-opus/` (run report sha256 `f2cba0c7…`).

## Smoke tests (one pair, negation task 415040016)

| Plan | Limits | Aljure | Prime | Result |
| --- | --- | --- | --- | --- |
| `a1d0d896…` | 12 calls, 120 s | out of calls after 12 (root plus 2 child sessions) | 1.0, 12 calls, 86.9 s | **failed** criterion 1; the full run was not started ($0.52) |
| `3a0ccea4…` | opened | 1.0, 23 calls, 154 s | 1.0, 32 calls, 149 s | **passed** all three criteria ($1.28) |

## Primary endpoint (7 contexts, 21 tasks)

| | Aljure | Prime |
| --- | --- | --- |
| Deadline-aware mean score | **0.771** | **0.919** |
| Tasks with score ≥ 0.9 | 15 | 18 |
| Completed with an answer | 19 / 21 | 21 / 21 |

- **Paired difference** (Aljure − Prime, each context weighted equally): **−0.149**.
  - 95% cluster bootstrap interval (10,000 resamples, seed 0): [−0.271, −0.048].
  - 90% interval: [−0.240, −0.057].
- **Aljure's wins, ties and losses:** 1, 16, 4.
- **Decision under the protocol: inferior.** The upper bound is below 0 and the estimate is at most −0.05.
- **Sensitivity check:** excluding the provider-truncated turn (imdb task 1) gives −0.101, with a 95% interval of [−0.209, −0.009]. That is still inferior.
- **The preregistered target is not met.** Aljure is cheaper and faster, but it is not comparable on accuracy.

## Secondary endpoints

| | Aljure | Prime |
| --- | --- | --- |
| Total wall time | 567 s | 741 s |
| Latency p50 / p95 | 25.6 s / 46.3 s | 29.0 s / 65.6 s |
| Longest arm | 48 s | 91 s |
| Model calls, total / most in one arm | 96 / 8 | 125 / 26 |
| API-rate-equivalent cost | $1.73 | $3.81 |

The opened limits did not bind: no arm came near 900 s. The old 12-call cap would have bound one Prime arm (multinli count, 26 calls), and that arm is the one task Prime won by spending.

## Where Aljure lost

| Task | Aljure | Prime | Cause |
| --- | --- | --- | --- |
| formality: least common label in a date range | 0 (no answer) | 1 | Opus wrote its answer as text twice instead of calling `done`. Aljure never executes text and allows one correction, so the arm failed. Prime's harness takes a final text reply as the end of the run (parity matrix row 5). |
| imdb: label comparison | 0 (no answer) | 1 | The provider returned `stop_reason: tool_use` with only thinking blocks, the second reading "This part of the response was interrupted before it finished." Aljure classes this as an uncorrectable incomplete turn. |
| multinli: count of one label | 0.08 | 1.00 | Prime spent 26 calls and got the exact count. *Corrected; see the note below.* Its root labelled 365 of the 438 pairs itself in four pages and kept a per-page count in Python state. It started 6 sub-agents (the only sub-agent use in Prime's 21 arms). One of them, `nli2`, labelled pairs 146–218 and reported 22, which the root added. Aljure used 8 calls and was off by 9. |
| agnews: count of one label | 0.18 | 0.56 | Labelling accuracy over 341 articles; both counts were off. |
| agnews: count of one label (Aljure won) | **0.75** | 0.56 | Aljure was off by 1, Prime by 2. |

Two of the four losses are answer-delivery failures, not wrong answers. On the 19 tasks where Aljure delivered an answer, it scored 0.852 on average. Prime scored 0.919 over all 21 tasks.

## Sonnet and Opus on the same tasks

| | Aljure (Sonnet → Opus) | Prime (Sonnet → Opus) |
| --- | --- | --- |
| Mean score | 0.768 → 0.771 | 0.800 → 0.919 |
| Completed | 21 → 19 | 20 → 21 |
| Cost | $0.81 → $1.73 | $1.59 → $3.81 |

- **Prime gained from Opus; Aljure did not.**
- **Aljure's reasoning did improve.** It fixed the formality task it missed under Sonnet, and on agnews it scored 0.75 against 0.02.
- **Two new contract failures cancelled that gain.** One text-only answer did not recover after the correction, and one turn came back truncated. *Corrected:* Opus does not answer in text more often. Sonnet had text-only replies in 9 arms, Opus in 4 (see the note below).

## Limits and next steps

- **Scope:** one run per task over 7 contexts. These are dev tasks; the sealed held-out suite was not used.
- **Fixes to test** (each is a harness change that needs its own frozen plan; confirm on the held-out suite):
  1. **Truncated turns.** Treat a provider turn with `stop_reason: tool_use` and no tool block as a provider fault: retry it once, outside the model's correction allowance.
  2. **Text-only answers.** Decide whether a final text-only reply after the correction may count as the answer, as Prime's harness already does. This is a disclosed change to Aljure's answer contract.
  3. **Count tasks.** Investigated in `MULTINLI_COUNT_FAILURE_ANALYSIS.md`. Delegation was not the mechanism; the original wording here was wrong.

## Corrections (2026-10-29)

Two statements in this document were wrong. No score changes.

1. **Prime's exact MultiNLI count.** This document said one sub-agent produced it.
   The traces show the root did most of the work, plus one sub-agent's partial count:
   - The root spawned 6 sub-agents.
   - 2 failed with "Connection error"; 3 exited without replying after their Python kernel failed to start.
   - `nli2` labelled pairs 146–218 and messaged back "Contradictions: 22".
   - The root labelled the other 365 pairs itself in four pages. It kept per-page counts in Python state:
     `C=[36]`, `C.append(11+22)`, `C.append(28)`, `C.append(32)`, then wrote `sum(C)` = 129.

   Sources:
   - the root session `var/benchmarks/synth-indep-32k-dev-opus/30-prime/native/sessions/01a1861e-b9cb-75b5-ad29-dfa6d321a8d0.jsonl`: the `rlm_child_failure` and `rlm_child_terminal_notice` messages, the `agent_message` from `nli2`, and the `python_repl` calls;
   - the child's label file `.../30-prime/native/chunks/l2.txt`.

   Details: `MULTINLI_COUNT_FAILURE_ANALYSIS.md`.
2. **Text-only replies.** This document said Opus answers in text more often. It does not:
   - Sonnet Aljure: text-only replies in 9 arms.
   - Opus Aljure: 5 replies in 4 arms.

   The difference under Opus is that one reply did not recover after the correction.
   Source: `evidence/contract-audit/baseline.json` (response classes per run, from the raw provider bodies).
