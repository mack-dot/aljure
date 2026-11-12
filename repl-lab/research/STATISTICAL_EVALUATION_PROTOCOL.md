# Statistical evaluation protocol

Pre-registered analysis rules for the campaign questions. Fix these before any
Phase B (frozen) data is collected. `benchmark/audit.py` (`paired_statistics`)
implements the descriptive and cluster rules. Changing a rule after seeing
held-out data voids the held-out claim.

## Question labels

This repository has already used H1–H3 twice with different meanings
(`EXPERIMENTS.md`; `research/EXPERIMENT_PROTOCOL.md`). The campaign therefore
uses names:

| Campaign label | Brief | `EXPERIMENT_PROTOCOL.md` | Question |
| --- | --- | --- | --- |
| **Q-HARNESS** | H1 | H3 | Full Aljure vs native Prime, same model, tasks and budgets |
| **Q-SUBSTRATE** | H2 | H1 | SCI vs Python under one controller |
| **Q-LEARNING** | H3 | H2 | Verified executable artifacts vs none, unverified or automatically selected |

## 1. Units, clusters and independence

- **Observation:** one task, run once by each arm, under one frozen plan.
- **Cluster:** one independent context (`context_window_id` within a benchmark
  and context length). Questions sharing a context are correlated, and every
  inference is resampled at the cluster level. Different context lengths of
  OOLONG-Pairs are different windows over the same question source: treat them
  as separate clusters, and note that they share a distribution.
- **Minimum clusters:** none for a descriptive report, 5 for any interval, and
  10 for a primary Phase B inference (section 5).

## 2. Task score (deadline-aware)

Each arm-task gets one score in [0, 1]:

| Outcome | Score |
| --- | --- |
| Completed before the deadline, answer recorded | official scorer value |
| Timeout, harness error, missing or unparseable answer, budget exhausted | 0 |
| Infrastructure failure (section 3) | 0 in the primary analysis; excluded pair-wise in a sensitivity analysis |

Ties are differences of exactly 0. There is no tie-breaking.

## 3. Infrastructure failures (mechanical classification)

A failure counts as infrastructure only when its recorded failure code is one
of: `DockerNotReady`, `DockerRestartedDuringArm`, `ProviderOutcomeUnknown`
(after the in-flight grace), `GatewayCleanupFailure`, and a host or relay
crash before the first model call. `NativeCompletionMissing` with reason
`output-limit` was a harness defect for runs before `178bfc3`. The pre-fix runs
are development evidence only. A plan with more than 10% infrastructure
failures in either arm is reported, but not used for a claim.

## 4. Primary endpoints

| Question | Primary endpoint |
| --- | --- |
| Q-HARNESS | Mean paired deadline-aware score difference, Aljure − Prime |
| Q-SUBSTRATE | Mean paired deadline-aware score difference, SCI − Python (same controller) |
| Q-LEARNING | Mean held-out verified-completion difference, validated retention (C) − no memory (A), resampled by acquisition run |

## 5. Estimation and decision rules

- **Estimator:** mean of paired differences, with each context weighted equally
  (average within the context, then across contexts). Also report the
  task-weighted mean.
- **Interval:** cluster bootstrap over contexts, 10,000 resamples, seed 0,
  95% percentile interval.
- **Minimum meaningful difference:** δ = 0.05 score.
- **Decisions** (two-sided, α = 0.05):
  - *superior* if the lower bound is above 0 and the estimate is at least δ;
  - *inferior* if the upper bound is below 0 and the estimate is at most −δ;
  - *equivalent* **only** if the 90% interval lies within ±δ (two one-sided
    tests);
  - *inconclusive* otherwise.

  A non-significant difference is **never** reported as equivalence.
- **Multiplicity:** one primary endpoint per question. Secondary endpoints are
  descriptive, or Holm-adjusted when tested.
- **Distributions:** always report the per-context and per-task differences,
  the per-arm score histograms and the wins, ties and losses, not only means.

## 6. Secondary endpoints

- Completion rate; timeout rate; infrastructure-failure rate.
- Cost per success (total API-rate-equivalent USD over all arms, divided by
  tasks with completed score ≥ 0.9) and cost per score point.
- Latency p50 and p95, including startup; model calls; input, output and cache
  tokens.
- Tool reliability: expression or tool errors per call, first-try execution
  success, worker restarts.
- Resources: host and container CPU-seconds and peak memory, when measured.
  The compute-boundary difference is in `PRIME_PARITY_MATRIX.md` row 4.

## 7. Variance, order and stability

- **Order:** alternating arm order per task (already implemented) and a fixed
  task order, both recorded in the plan.
- **Run-to-run variance:** the model is stochastic. On 8K task 1, Prime scored
  0.968–1.0 over five runs. A Phase B plan includes a repeat of 20% of tasks
  (fresh sessions) to estimate within-task variance. Repeats are averaged within
  the task before clustering.
- **Stability gates** before and during each arm: the Docker gate (no pending
  restart, images present, stable session); a 1-minute load average below 8 on
  this 10-core host at arm start (record it; pause and resume between arms if
  it is exceeded); record competing containers. Latency comparisons are
  reported only for arms that passed the gate.

## 8. Scorers

- **OOLONG-Pairs:** the vendored functions are AST-identical to Prime's pinned
  `research-environments` scorer (`benchmark audit`, scorer equivalence).
- **OOLONG-synth:** **primary** is the original OOLONG `synth_process_response`
  (benchmark authors' implementation, vendored). **Sensitivity** is Prime's
  `research-environments` `score()`. They disagree on verbose answers without a
  colon (8/88 probes), so report both, and list each task where they differ.
- Other suites: the official scorer, pinned by commit and hash, with a gold
  self-test before use (`benchmark audit` pattern).

## 9. Sample size (planning estimates)

For a cluster design, the needed number of contexts is approximately
n ≈ (z₀.₉₇₅ + z₀.₈₀)² · σ_c² / Δ². Here σ_c is the standard deviation of the
context-level mean difference and Δ is the effect to detect.

The existing data has one context, so σ_c is not estimable. Within-context task
differences had a standard deviation of about 0.1 (8K) and about 0.4 (32K,
control). Planning values:

| Δ to detect | σ_c = 0.15 | σ_c = 0.25 |
| --- | --- | --- |
| 0.15 | 8 contexts | 22 contexts |
| 0.10 | 18 contexts | 49 contexts |
| 0.05 | 71 contexts | 196 contexts |

**Plan for 60 independent contexts, one question each, in Phase B**
(LongBench Pro; Δ ≈ 0.10 at σ_c ≈ 0.25 needs about 49). Update σ_c from the
Phase A pilot before freezing Phase B. OOLONG cannot reach this: there are at
most 16 synth windows per length, and one Pairs context per length
(`BENCHMARK_SUITE_MATRIX.md`).

## 10. Economics (Q-LEARNING)

Net benefit after N reuses = N × (cost per solved task without memory − cost
per solved task with memory) − (acquisition cost + validation cost). Report
the break-even N with its interval, counting failed acquisitions. A retained
artifact counts as reused only when a trace shows it executed (artifact or
workflow invocation events), not when it is merely present.
