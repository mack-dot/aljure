# Prime's MultiNLI success: trajectory analysis

**Task:** `oolong-synth-test-32768-715070023`. Count the sentence pairs labelled
`contradiction` among 438 MultiNLI pairs. The gold answer is 129.

| Arm | Answer | Score |
| --- | --- | --- |
| Opus Prime | 129 | 1.00 |
| Opus Aljure | 120 | 0.08 |
| Sonnet Prime | (far off) | 0.01 |
| Sonnet Aljure | (far off) | 0.00 |

The analysis is read-only over the recorded native session files, sub-agent
session files, chunk files and Aljure's event log, from plans `d6e9b40d…` and
`0b6a0451…`.

## What Prime did

The **root session** took 10 assistant turns and 3,616 output tokens. It ran
these steps:

1. Read `context.txt`; printed the first 3,000 and last 1,500 characters.
2. Split the 438 pairs into 6 chunk files and called `rlm.spawn` 6 times in a
   loop. Each worker's task was: "classify each line yourself (read carefully,
   no code heuristics) … reply to parent with the count of contradictions."
3. Wrote "Six workers are labeling the chunks; waiting for results." Then
   checked for the workers' label files and found none (`[]`).
4. **Read the pairs itself instead**, in 4 pages of about 110 pairs.
5. **Recorded a count after each page.** On reading pages 1–3 it saved
   `C = [36]`, then `C.append(33)`, then `C.append(28)`, each in the call that
   printed the next page. It added `C.append(32)` after page 4.
6. Wrote `Answer: 129` (36 + 33 + 28 + 32) to `/work/answer.txt`.

The **six sub-agents** took 19 turns between them. *Corrected 2026-10-29:*
an earlier version said no sub-agent result reached the answer, and that was wrong.
- `nli2` labelled pairs 146–218 and messaged back "Contradictions: 22".
- The root's page-2 entry was `C.append(11+22)`: its own 11 for pairs 110–145 and 219, plus that 22.
- The other five sub-agents failed: two with connection errors, three with Python-kernel start failures.

See `MULTINLI_COUNT_FAILURE_ANALYSIS.md`, which supersedes this document's conclusions.

There was **no independent verification**: the root did not recount, compare
against the workers, or check the per-page counts.

## What Aljure did

Aljure took 8 calls and 2,756 output tokens:

1. Looked at the start and the end of the context.
2. Defined the list of 438 pairs and a `show` helper. Read 80 pairs.
3. Read the rest in 4 more pages: 85, 85, 90 and 98 pairs.
4. Called `done` with `Answer: 120`. The final call (715 output tokens) gave
   one count from everything it had read.

It **kept no running count**: no number was saved after any page.

## Which mechanism made the difference

| Candidate | Evidence | Verdict |
| --- | --- | --- |
| Recursive delegation | One sub-agent's count (22, for 73 pairs) was added in. The other five failed. | **A minor contributor**: one sub-agent covered 17% of the pairs and was exact only because one false positive cancelled one false negative (*corrected*). |
| More inference | Root: 10 turns, 3.6K output tokens. Aljure: 8 calls, 2.8K. Both read every pair. | **Not established.** The difference is small and both covered all items. |
| A different algorithm | Prime counted each page while it was fresh and saved the count in program state. Aljure counted once, across all 438 pairs. | **Most likely cause.** |
| Better initial instructions | Prime's prompt does not tell it to tally per batch. | **Unknown.** Prime's prompt may favour keeping state, but nothing shows it. |
| Verification | Neither harness verified. | **Not the cause.** |
| Task-specific behaviour | Running tallies appear in this one arm only. They are absent from Prime's AG News counts, which still scored 0.56, 0.56 and 0.18. | **Not a general Prime behaviour.** |

One instance cannot separate "a different algorithm" from chance. Opus Prime
could have counted 129 in one pass on another run.

## Controls that would separate the mechanisms

Each control is an Aljure-only change. Native Prime stays the reference. Each
runs on the four large exact-count tasks in the dev suite (16, 19, 20, 21),
plus the three yahoo comparisons as a check for side effects on other task
types. Each is repeated 3 times, because count scores are noisy.

| Control | Change | Separates |
| --- | --- | --- |
| A. More inference | `effort: high` instead of medium; nothing else changes. | inference volume |
| B. Instructions | One general sentence in the base prompt: "When you judge many items by reading them, record each batch's result in SCI before reading the next batch." | instruction-induced algorithm |
| C. Algorithm, imposed | A prelude helper `(tally! label n)` and a page helper that shows the next unread batch and the running totals, with no instruction to use them. | whether the affordance alone changes behaviour |
| D. Delegation | The base prompt invites `agent_call` for batch labelling; the child budget is shared, as now. | recursion |
| E. Verification | After an answer, one extra turn asks the model to recheck one batch and reconcile. | verification and correction |

Falsification: if B or C does not raise the count scores above the control
by at least the noise band (estimated from the 3 repeats), the running-tally
explanation is not supported.
