# Program pilot results: A (direct tools) vs B (program_run), seed 1, two runs each

Official outcome under the preregistered rule in `PROGRAMMATIC_EXECUTION.md` section 8:
**NO-GO**. One criterion fails: the `fault` family loses 0.25 success in B (one miss in four
observations) against the 0.05 tolerance. Every other criterion passes, most by a wide margin.
The failing observation is an answer-format miss with a correct final state (details below).
The rule is applied as written; nothing here re-scores, re-runs or excludes a result.

## Provenance

| Item | Value |
| --- | --- |
| Freeze commit (execution source) | `0c44178308ad9660cd4003fedba681305e76768a`, run from a clean checkout at that commit |
| Plan A (direct one-operation tools) | `9090d1c3f0c34fe2dda8c2d2b4a979af436d9a29a8c876dcd897099479e670f6` |
| Plan B (`program_run` only) | `c67f6ab9b21fb87634a0b87e59e10e8885708a7059cf52bbc20052d79abbe888` |
| Suite | `var/official/service-sim-s1`, `suite_sha256 ed8142ec…`, 18 tasks (9 families × 2 sizes), scorer `5db280dc…` |
| Model and transport | Sonnet 5.5, Claude subscription transport, API-key fallback disabled |
| Images | SCI `sha256:40f00364…`, Prime `sha256:f3e30aaa…` (unused: Aljure-only plans) |
| Order run | A run 1 → B run 1 → A run 2 → B run 2, serial, one Docker-bound job at a time |
| Rows | 72 (4 runs × 18), accounting complete, 0 unknown provider outcomes, 0 stop signals |
| Spend | $1.29 known, $0 unknown reservations (ceiling $5 per task, $90 per plan) |
| Analysis | `scripts/program_pilot_compare.py` on recorded evidence; zero model calls |
| Evidence | `research/evidence/program-pilot-results/` (per-task answers, events, service state, usage receipts, reports, preflights, run script and logs; `index.json` lists every file's SHA-256) |

A first attempt at the earlier freeze `14c7571` failed on all 18 tasks of A run 1 before any
model call (fixture shape, see `PROGRAMMATIC_EXECUTION.md` section 8); spend $0; kept as
`runs/program-A-r1-failed-fixture-shape-20261101`. The pilot proper is the four runs above.

Readiness gate before committing to the first full run: task 00 of A run 1 loaded its fixture,
made two model requests and completed in 27 s. The script paused once between A run 1 and B run 1
when host free disk fell under the 6 GB floor (an unrelated process), and resumed from B run 1
without re-running anything.

## Pooled results (2 runs per arm; per-run values beside each mean)

| Metric | A direct tools | A per run | B program_run | B per run |
| --- | --- | --- | --- | --- |
| Success (official answer score) | 0.81 | 0.78 / 0.83 | 0.92 | 0.94 / 0.89 |
| Final state correct | 0.94 | 0.94 / 0.94 | 1.00 | 1.00 / 1.00 |
| Tasks not completed | 2 | 1 / 1 | 0 | 0 / 0 |
| Unintended changes | 0 | 0 / 0 | 0 | 0 / 0 |
| Model requests per task | 11.1 | 11.1 / 11.1 | 2.7 | 2.6 / 2.8 |
| Uncached input tokens per task | 24 | 24 / 24 | 7 | 7 / 8 |
| Cache-read input tokens per task | 67,841 | 67,866 / 67,816 | 6,839 | 6,366 / 7,312 |
| Output tokens per task | 1,296 | 1,300 / 1,292 | 310 | 297 / 323 |
| Inference cost per task (USD) | 0.028 | 0.028 / 0.028 | 0.0075 | 0.0073 / 0.0078 |
| Inference cost total (USD) | 1.02 | 0.51 / 0.51 | 0.27 | 0.13 / 0.14 |
| Latency p50 (s) | 38.3 | 45.6 / 24.2 | 25.0 | 37.3 / 19.3 |
| Latency p95 (s) | 147.0 | 171.1 / 113.2 | 70.0 | 74.9 / 26.9 |
| Tool operations per task | 10.1 | 10.1 / 10.1 | 12.7 | 12.3 / 13.0 |
| Failed operations per task (scripted faults) | 0.22 | 0.22 / 0.22 | 0.31 | 0.28 / 0.33 |
| Deduplicated operations | 0 | 0 / 0 | 0 | 0 / 0 |
| Programs per task | 0 | – | 1.42 | 1.33 / 1.50 |
| Programs that errored (model recovered in-task) | 0 | – | 4 | 1 / 3 |
| Controller time in operations per task (ms) | 75 | 109 / 40 | 83 | 132 / 33 |

Ratios B/A: model requests on the operation-heavy families 0.22; cost per task 0.26.

## By family (pooled; B−A is the per-task paired difference, min..max across the 4 pairs)

| Family | A success | B success | A state | B state | A requests | B requests | A cost | B cost | A p50/p95 s | B p50/p95 s | B−A success | B−A requests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| read | 1.00 | 1.00 | 1.00 | 1.00 | 2.0 | 2.0 | 0.0069 | 0.0069 | 25.7 / 44.3 | 27.4 / 34.7 | 0.00 (0..0) | 0 (0..0) |
| seq | 1.00 | 1.00 | 1.00 | 1.00 | 7.0 | 2.0 | 0.0108 | 0.0053 | 33.6 / 48.0 | 28.7 / 59.6 | 0.00 (0..0) | −5 (−5..−5) |
| cond | 0.75 | 1.00 | 1.00 | 1.00 | 22.5 | 6.2 | 0.0519 | 0.0146 | 83.8 / 151.7 | 50.1 / 87.8 | +0.25 (0..+1) | −16.2 (−25..−8) |
| bulk | 0.00 | 0.50 | 1.00 | 1.00 | 15.0 | 3.0 | 0.0370 | 0.0082 | 54.2 / 91.4 | 34.8 / 51.0 | +0.50 (0..+1) | −12.0 (−18..−6) |
| verify | 0.50 | 1.00 | 0.50 | 1.00 | 35.0 | 3.8 | 0.1030 | 0.0109 | 132.4 / 207.7 | 43.3 / 70.3 | +0.50 (0..+1) | −31.2 (−37..−27) |
| fault | 1.00 | 0.75 | 1.00 | 1.00 | 14.5 | 3.2 | 0.0345 | 0.0096 | 53.4 / 84.6 | 28.1 / 40.7 | −0.25 (−1..0) | −11.2 (−17..−6) |
| rate | 1.00 | 1.00 | 1.00 | 1.00 | 2.0 | 2.0 | 0.0048 | 0.0053 | 19.5 / 36.8 | 23.3 / 26.9 | 0.00 (0..0) | 0 (0..0) |
| auth | 1.00 | 1.00 | 1.00 | 1.00 | 1.0 | 1.0 | 0.0034 | 0.0035 | 15.9 / 25.6 | 23.2 / 26.1 | 0.00 (0..0) | 0 (0..0) |
| direct | 1.00 | 1.00 | 1.00 | 1.00 | 1.0 | 1.0 | 0.0032 | 0.0031 | 27.0 / 31.1 | 16.1 / 19.8 | 0.00 (0..0) | 0 (0..0) |

Each family has 2 tasks × 2 runs = 4 observations per arm. One miss moves a family's success
by 0.25.

## The preregistered rule, criterion by criterion

| Criterion | Result |
| --- | --- |
| B success within 0.05 of A (or higher) | pass (0.92 vs 0.81) |
| B final-state correctness within 0.05 of A (or higher) | pass (1.00 vs 0.94) |
| B model requests ≤ 0.5 × A on read, cond, bulk, verify, fault, rate | pass (0.22 ×) |
| B cost per task ≤ 0.75 × A | pass (0.26 ×) |
| No family loses more than 0.05 success or state correctness | **fail**: fault success 0.75 vs 1.00 |
| B has no more unintended changes than A | pass (0 vs 0) |
| Request reduction comes from operation-heavy families, not only direct/auth | pass (direct and auth are unchanged at 1 request) |

**Verdict: NO-GO**, as the rule is written.

## What the failing observation is

B run 2, task `service-sim-1-fault-1-240`: the program set the priorities, did not retry the two
scripted failures, and left the final state exactly as expected (state correct). The model's
answer was `i177,i80`; the sealed answer is `i177, i80`. The frozen scorer matches the normalized
answer text exactly, and the missing space scores 0. The other three fault observations in B and
all four in A scored 1. The scoring protocol is not changed here. A reader who treats this as a
format miss rather than a task failure will read the B/A comparison as a GO on every criterion;
that reading is not the official result and is stated here only so that the next suite version
can define answer normalization before it is frozen.

## Other observations recorded for the next benchmark version (not applied here)

- **Bulk answer key.** The generator's expected answer for the bulk family counts every open
  issue assigned to the user (11 and 30), while its expected state changes only the issues not
  already at the target priority (7 and 19) and the question asks for "the number of issues you
  updated". Both arms, in every run, produced the exact expected state. A's answers (7, 19) match
  the state change count; B answered 11 and 19. Bulk success therefore measures how the model
  resolved an ambiguous count, not whether the work was done. Both arms' bulk state correctness
  is 1.00.
- **A's two failures** are the same task, `service-sim-1-verify-1-240`, in both runs: one
  operation per model turn needs more than the frozen 40 calls per task on the largest verify
  task (40 calls, 40 operations, then "Global provider budget exhausted"). B finishes that task in
  3–4 requests. The cap is part of the frozen plan and binds A as preregistered.
- **B's errored programs** (4 across 36 tasks) were all recovered within the task by a second
  program: a wrong collection name, an unresolved symbol, and similar first-attempt mistakes. They
  are counted in B's operations and cost.
- **Latency.** B's p50 is lower on every operation-heavy family and its p95 is 2–3× lower on
  cond, bulk, verify and fault. The remaining time is dominated by model round trips, not by the
  controller: controller time in operations is under 0.15 s per task in both arms.
- **The pinned scorer module's run report** resolves a task directory from the usage receipt's
  parent, which in the live layout is the `gateway/` subdirectory, so its event-derived fields
  (requests, operations, state) read as zero. The scorer file is pinned by hash in the suite, so
  the comparison script resolves the task directory itself; answer and state scoring are the
  scorer's own functions and are unchanged. Fix the module in the next suite version.

## What this does and does not show

- Within this synthetic benchmark, at this seed and size, programmatic execution (B) matched or
  improved task success and final-state correctness on every family but one observation, while
  using about a fifth of the model requests, a tenth of the cache-read input tokens, a quarter of
  the output tokens and a quarter of the inference cost of one-operation-per-turn tools (A).
- The official rule still returns NO-GO on the family-tolerance criterion, which at four
  observations per family cannot absorb a single miss of any kind. That is a property of the
  rule as preregistered, and the rule stands for this pilot.
- No Prime arm ran. No claim about Prime follows from this pilot. Nothing here measures reuse,
  learning or adaptation (Phase 6 stays unstarted).
- The benchmark is scripted fixtures with an in-memory service; it validates mechanisms and
  scoring, not value on real services.

## Decision on the Prime adapter (deliverable 8, GO/NO-GO for Phase 6 and a Prime arm E)

Official: **NO-GO** under the preregistered rule. Recommended next step, for separate approval:
freeze a second suite version (seed 2) with answer normalization and the bulk key defined before
the freeze, keep the same rule, and re-run A and B at the same size. If that returns GO, the Prime
adapter work (arm E) and the Phase 6 reuse experiment start; if not, programmatic execution stays
a development result.
