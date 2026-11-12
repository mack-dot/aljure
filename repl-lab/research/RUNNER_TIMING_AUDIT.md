# Paired-runner wall time: where it goes

**Scope:** read-only over completed arms, written while L1 was still running.
- Script: `scripts/runner_timing_audit.py`.
- Evidence: `evidence/runner-timing/timing.json`.
- Clock: the gateway's arm clock (`task_elapsed_ms`, which starts with the arm).
- Model time: the union of request intervals, so overlapping Prime sub-agent requests count once.

## Breakdown

| Run | Plan span | Aljure arms | Prime arms | Model share (A / P) | Before first request, median (A / P) | After last response, median (A / P) | Gaps between arms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Control (21 tasks) | 1,318 s | 622 s | 697 s | 76% / 67% | 3.5 s / 7.4 s | 0.7 s / 1.2 s | 0 s |
| F1 | 1,439 s | 612 s | 827 s | 75% / 69% | 4.7 s / 8.3 s | 0.9 s / 1.4 s | 0 s |
| F2 | 1,329 s | 605 s | 712 s | 74% / 61% | 4.3 s / 9.0 s | 1.1 s / 1.5 s | 11 s |
| L0 (11 count tasks) | 1,653 s | 711 s (43%) | 942 s (57%) | 83% / 71% | 4.8 s / 9.0 s | 1.0 s / 1.5 s | 0 s |

**Components:**
- **Model time dominates:** 61–83% of every arm.
- **Before the first request:** for Aljure, controller JVM start, isolation preflight (about 1.7 s per arm at the normal 0.15 s per Docker query) and context binding. For Prime, native container start.
- **SCI worker start** (about 1.5–1.9 s to ready) overlaps the first model call (prewarm), so it is rarely on the critical path.
- **Between requests:** SCI execution and controller work. For Prime it also includes sub-agent orchestration (151 s in L0, mostly the MultiNLI arms).
- **Fixed overhead per arm pair:** about 15 s, roughly 10% of a plan.
- **Idle time between arms:** about 0. The runner starts the next arm at once.

## Why execution is sequential

1. **Latency is an endpoint.** Concurrent arms would share the host CPU, Docker Desktop's VM and the provider connection, and would change each other's wall time unevenly. Prime's container is pinned to 1 CPU, while Aljure's controller runs on the host.
2. **Stop rules must act before the next arm.** An unknown provider outcome, an isolation refusal, a Docker restart or an unconfirmed cleanup stops the plan. With arms in flight in parallel, the next arm would already be dispatched.
3. **Paired fairness.** The frozen sequence alternates Aljure and Prime per task (A/P, then P/A), so the two arms of a task are adjacent in time.
4. **Docker stalls under load.** Two `docker info` stalls happened today with one worker set at a time. Parallel workers would raise that risk.
5. **The chain runs configurations one after another,** so each frozen plan is isolated and the chain can stop between plans.

## What dominates the cost of this design

**Repeating unchanged Prime in every configuration plan:**
- In L0, Prime arms take 57% of wall time and 70% of cost ($5.85 of $8.32).
- Across L0–L3, three of the four Prime runs only re-measure Prime. That gives Prime's run-to-run spread, which is useful once or twice, not four times.
- Removing them would save about 45 minutes and $17 in this experiment.

## A faster design that keeps fairness

1. **A shared Prime reference block.**
   - Run Prime once or twice per suite as its own frozen plan.
   - Run Aljure-only configuration plans that cite the reference by plan hash.
   - This needs runner support and a protocol change, so it needs its own approval.
   - Saves about 57% of time and 70% of cost per extra configuration.
2. **Interleave configurations within one plan.**
   - Order tasks so every configuration runs each task in a rotating, balanced order (a Latin square).
   - The same total time, but time-of-day drift no longer separates the configurations.
3. **Separate accuracy runs from latency runs.**
   - Accuracy tolerates bounded parallelism: at most 2 concurrent arms, each with pinned resources, and a stop on any `docker info` latency above 1 s.
   - Measure latency in a small, sequential calibration pass.
   - About 2× faster on accuracy work, with no contention in latency numbers.
4. **Trim fixed overhead (minor).** Keep a warm host controller between arms, with fresh isolated workers per arm as now. This saves about 3 s per Aljure arm, which is small next to model time.
5. **The main lever is model time,** which is 61–83% of every arm. Runner changes cannot beat fewer or cheaper model calls.

## Remaining time for this experiment (estimated at 17:14 UTC)

- L1: 19 of 22 arms done after 28 minutes. Prime's arms there average 101 s, against 86 s in L0.
- L2 and L3: about 30–35 minutes each, using L0/L1 arm durations and a 10–30% allowance for audit and review calls in Aljure's arms.
- **Total remaining:** about 65–75 minutes, so done around 18:20–18:30 UTC.
