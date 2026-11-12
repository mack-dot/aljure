# Uncertainty review: cost and benefit

## What the levels cost (Aljure, 11 tasks)

| | L0 | L1 | L2 |
| --- | --- | --- | --- |
| Calls | 106 | 112 | 107 |
| Output tokens | 42.8K | 50.3K | 51.2K |
| Cache-read input tokens | 0.94M | 1.18M | 1.36M |
| Cost | $2.47 | $2.68 | $2.77 |
| Wall time (sum of arms) | 711 s | 1,004 s | 941 s |
| p50 / p95 | 56 / 152 s | 60 / 344 s | 95 / 134 s |
| Aljure/Prime cost | 0.42 | 0.46 | 0.64* |

\*Prime failed one arm in L2 and spent less. Against Prime's mean cost per
complete run ($5.85), Aljure's L2 ratio is 0.47.

**Where the extra cost goes:**
- L1 and L2 added +9% and +12% cost, and +18% and +20% output tokens.
- The added text (122 words) is cached, so the extra cost is mostly longer
  reasoning and larger tool results.
- None of it bought an attributable accuracy gain, since the audit was never used.

## What review would cost if it ran

L3 was not evaluated. From the measured cost per call, about $0.023 for Aljure
on these tasks, and the arm sizes:
- **One targeted review turn on a count task:** about +1 call, $0.02–0.05 and 5–15 s.
- **A blinded reviewer child on 24 items:** about +2–3 calls, $0.05–0.10 and 15–30 s.

**Applied to all 11 tasks:**
- about +$0.3–1.1 per run;
- an Aljure/Prime ratio of about 0.47–0.61.

**Applied only where a controller signal fires:** less.

## Value: expected benefit per dollar

| Intervention | Cost | Expected benefit | Confidence |
| --- | --- | --- | --- |
| Answer-format check at `done` | ≈ $0 (one notice turn only when it fires) | Recovers official scores lost to parse failures: 3/33 arms here | High |
| Controller reads per-item evidence and checks invariants | ≈ $0 (an SCI read) | Catches coverage and arithmetic slips. None were observed here | Medium |
| Blinded review of a sample | +$0.05–0.10 per task where used | The Aljure-only excess (formality), possibly. The shared bias, probably not | Low; unmeasured |

## Conclusion

- **The cost advantage is intact** in every completed level: 0.42–0.47 against
  a full Prime run.
- **The cheapest certain gain is answer-format validation,** which is free.
- **Semantic review is worth measuring only as a controller-triggered, blinded
  mechanism.** It needs to be evaluated for its effect on the Aljure-only excess,
  since the shared bias is outside its likely reach.
