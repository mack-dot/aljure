# Thesis pilot (A/C/E, Sonnet): final result

**Plan:** `795a0140f316e83ca3bb55c181f37f2cfda5cc7868f952ebe62cca486b311e39`, approved and run
unchanged on 2026-10-29 in `/Users/mackianni/aljure-thesis-v1` (source `6b3c422`).
Protocol: `THESIS_PILOT_PROTOCOL.md`. Evidence: `evidence/thesis-pilot-results/`.

**Result: UNINFORMATIVE, not negative** (protocol §7). No artifact was promoted, so activation was
0%. The thesis was not tested.

## What happened

- **Run integrity:** all nine trajectories completed, each phase in its own process. There was no
  stop, no unknown provider outcome and no isolation refusal. Spend was $5.03 API-rate-equivalent
  (cap $40). There were 162 task runs.
- **Proposals:** **0 proposals in 100 offered turns** (C 50, E 50). 8 more turns were not offered
  because the task recorded no answer. Every decline was a bare `skip_proposal`, with about 27
  output tokens and no thinking.
- **Promotions:** none. The new-record endpoint scored 0 tasks, because no library existed.

| Arm | F1 mean score | F1 fully correct | F2 mean score | Cost, all tasks | Proposal-turn cost |
| --- | --- | --- | --- | --- | --- |
| A | 0.489 | 18 / 42 | 0.421 | $1.28 | — |
| C | 0.526 | 20 / 42 | 0.345 | $1.89 | $0.59 |
| E | 0.492 | 19 / 42 | 0.265 | $1.86 | $0.60 |

- **Score differences between arms are noise.** No arm had any retained state, so C and E were
  arm A plus a declined turn. F2 differences are not negative transfer, because nothing was
  transferred.
- **Break-even:** none, because C and E only added cost.
- **Delivery:** 8 tasks, all in C or E, recorded no answer: the model replied in text twice, and
  the one formatting correction did not help. Arm A had 0 such tasks (8/108 against 0/54; Fisher
  p ≈ 0.05). No mechanism is known; this is a hypothesis to check, not a finding. Arm A also
  produced text-only replies (20 tasks), but each recovered after the correction.

## What it established

- The optional, no-penalty proposal turn does not produce acquisition with Sonnet.
  `UNBLOCK_ACQUISITION.md` diagnoses why and replaces it.
- The trajectory machinery ran end to end on live tasks: pins carried forward, the cold restart,
  the spend cap, acquisition accounting and the new-record step.
