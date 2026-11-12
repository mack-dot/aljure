# Quality–cost–latency forecast for the Opus interventions

**What this is:** forecasts, not measurements. Every number comes from the recorded
Opus dev run (`d6e9b40d…`) or from rates measured in recorded traces. Ranges are
wide because each task ran once.

## Baseline (Opus, 21 dev tasks)

| | Aljure | Prime |
| --- | --- | --- |
| Mean score | 0.771 | 0.919 |
| Cost | $1.73 ($0.018 per call) | $3.81 ($0.031 per call) |
| Output tokens per arm | 1,332 | 1,598 |
| Latency p50 / p95 | 25.6 s / 46.3 s | 29.0 s / 65.6 s |
| Total wall time | 567 s | 741 s |
| Judged-count tasks (16, 19, 20, 21): cost, output, wall | $0.63, 9.0K, 152 s | $1.48, 13.6K, 223 s |

**Two corrections to reading the −0.149 gap:**
1. **Delivery losses, expected against observed.** In this run, delivery
   failures cost Aljure −0.095. The expected loss per run is smaller:
   - Text-only replies that did not recover: 1 of the 4 Opus arms with such a
     reply (1 of 13 across Sonnet and Opus). That is about 0.3–1.0 lost tasks per run.
   - Truncations: about 1 in 557 responses, at ~96 responses per run, so about 0.17 per run.
   - Together: about **0.02–0.06** of mean score per run.
2. **Prime's exact MultiNLI count is partly chance.** At its measured item
   accuracy, its expected score on that task is about 0.54, not 1.0
   (`MULTINLI_COUNT_FAILURE_ANALYSIS.md`). Prime's expected mean on this suite is
   therefore about 0.90, not 0.919.

## Per intervention

| Intervention | Extra calls | Extra tokens | Verification time | Expected quality (21-task mean) | Timeout risk | Cost change | p50 / p95 effect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. F2, finalization | 0 (reuses the existing correction) | ~60 input tokens on the correction turn | none | **+0.015 to +0.048** | none | ≈ $0 | none |
| 2. F1, truncation retry | 1 per event, ~0.17 per run | one repeated turn per event (~20K cached input, ~400 output) | none | **+0.008** | none (refused near the deadline) | +$0.005 per run | none, except +5 s on the affected task |
| 3. Verification helpers | 0–1 per judgement task | ~140 cached prompt tokens per request; **+0.5–3K output tokens** on tasks that keep a ledger | ms (SCI, in the worker) | **0 to +0.01** under Opus (no structural error seen in Opus MultiNLI) | low | **+$0.12 (count tasks only) to +$0.63 (every task)**, i.e. +7% to +36% | +8–40 s on ledger tasks; p95 rises most |
| 4. + uncertainty review | 0–1 per judgement task | a few hundred output tokens to reread open items | ms | **+0.01 to +0.04** (count bias; MultiNLI alone is about +0.02) | low | +$0.02–0.15 | +5–15 s on review tasks |
| 5. + evidence gate | 1 per firing; 0 otherwise | one turn (~30–60K cached input, ~0.3–1K output) | ms | **0 to +0.02**, beyond 4 | low | +$0.02–0.04 per firing | +5–15 s per firing |

**How the token and latency estimates were made:**
- **Opus output speed:** about 60–70 output tokens per second. Example: the
  truncated imdb turn produced 381 tokens in 5.6 s, over an 18K-token cached input.
- **Ledger size:**
  - Writing labels for 438 items in full costs about 2.6K output tokens.
  - Listing only one label's indices plus the unknowns, as Sonnet Prime did,
    costs about 0.4–0.8K.

## Reaching Prime's accuracy at lower cost: plausible, not shown

A worked example on the observed run:
1. With F1 and F2 rescuing tasks 6 and 7, Aljure's observed mean would be 0.866.
2. Removing the MultiNLI bias raises its expected score on that task to about 0.5.
   That gives an Aljure expectation of about 0.88–0.89.
3. Prime's expectation is about 0.90.
4. The expected gap, about −0.01 to −0.02, is inside run-to-run noise.

The cost at that point:

| Configuration | Expected Aljure cost | Against Prime | Expected total wall time | Against Prime |
| --- | --- | --- | --- | --- |
| F1 + F2 | $1.73 | 45% | ~570 s | 77% |
| + helpers and review, count tasks only | ~$1.9 | ~50% | ~650 s | ~88% |
| + helpers and review on every task | ~$2.4 | ~63% | ~740 s | ~100% |

**Where no configuration dominates:**
- Ledgers on every task cost latency roughly equal to Prime's, for little gain on
  tasks already at 1.0.
- The useful target is **ledgers only where the answer is an exact count, or
  depends on many close judgements**.
- Whether the model limits itself that way is the open question for ablation 3.

## What would falsify the closing hypothesis

The hypothesis is false if, with F1 and F2 on and the chosen verification
configuration, either of the following holds:

1. **Accuracy:**
   - Aljure completes every task, but its paired difference from Prime stays below
     −0.05, with a 95% context-clustered interval below 0;
   - this holds over repeated dev runs and then on the sealed held-out suite.
2. **Cost:** closing the gap needs Aljure's cost or wall time to reach Prime's.

It is also false if the count tasks keep a signed bias after review, across
3 repeats. That would mean the semantic error is not reachable by review.
