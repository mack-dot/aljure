# Structured state (L1): evaluation

**Question:** does recording item-level labels in SCI improve accuracy, on its own,
without additional review?

## What L1 changed

L1 appended 58 words to the system prompt and loaded `show-items` into SCI. The text:
- record one label per item in SCI, as a map, and compute the answer from it;
- use `show-items` to page whole items.

Tools, limits and all other text were identical to L0 (`config-difference.json`).

## What happened

| | L0 | L1 |
| --- | --- | --- |
| Arms with per-item state in SCI | 4/11 | 6/11 |
| `show-items` used | — | 0/11 |
| Mean absolute error | 12.5 | 9.9 |
| Better / tie / worse, by task | | 4 / 3 / 4 |
| 95% interval of the change (5 window clusters) | | [−11.7, +3.8] |
| Cost | $2.47 | $2.68 (+9%) |
| p95 latency | 152 s | 344 s (one long arm) |

**Notes:**
- The per-item state in L1 is the model's own pattern: an atom holding an index
  set. It is not the described map. The baseline already uses it in 4/11 arms.
- The judgements recorded carry identity (index) and label membership only.
  They have no uncertainty, provenance or revision state, because the frozen
  design did not ask for them.

## Answers

1. **Does structured state improve accuracy independently of review?**
   - Not shown.
   - The interval includes zero, and the change (−2.6) is smaller than Prime's
     run-to-run swing (5.3).
   - The model already externalizes per-item state in many arms without being told.
2. **Is the state usable?** Yes.
   - In 22 of 33 arms across L0–L2, the per-item decisions sit in SCI, and their
     totals match the answer or its complement.
   - A controller could read them at `done` without asking the model. That is
     the basis of the controller-owned verification design.

**Verdict: INVESTIGATE.** Do not retain L1's prompt text, which shows no measurable
effect and costs +9%. The underlying insight is retained: the evidence is usually
already in SCI.
