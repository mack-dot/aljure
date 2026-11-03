# Q-SUBSTRATE Experiment A protocol (development, frozen)

Question A: does a Clojure/SCI substrate enable better agent performance than a
Python substrate under the same Aljure controller? This protocol is the frozen
development version. Its hash is part of the plan; changing this file changes
the plan. Brief: `research/Q_SUBSTRATE_BRIEF.md` Phases 4-5.

## Held constant

Model `claude-sonnet-5-5` through the subscription transport, adaptive
summarized thinking, medium effort; the controller at the frozen commit; the
native tool envelope (`context_metadata`, `context_query`, `repl_eval`,
`agent_call`, `done`, identical schemas); the assisted bounded surface with the
default execution contract (no artifacts, acquisition, programs, verification
levels or skill interface); the same public context and question per case; the
same per-task caps (12 calls, 12,000,000 tokens, $5, 300 s); the same worker
limits (256 MB, 1 CPU, 32 pids, 10 s per expression, 64 KiB output); the same
independent scorer; the same answer rule (`done` summary or source).

## What differs

`execution_language`: `clojure` (SCI worker, `resources/sci-prelude.edn`,
`resources/sci-contract.json` rules) or `python` (Python worker,
`resources/python-prelude.py`, `resources/python-contract.json` rules), and the
three tool descriptions and four instruction terms that name the language
(`research/Q_SUBSTRATE_PHASE2.md`). Prompt overhead differs by under 5%
(checked by the fixture).

## Tasks

`benchmark/substrate_tasks.py`: ten families, two cases each, generated from
seed `q-substrate-dev-2026110302`; synthetic records, sentences, payments,
graphs and expression trees with controller-side gold. The families follow the
brief's list: large collection processing, filtering and aggregation, exact
counting, parsing and normalization, algorithm construction (shortest path),
error recovery (malformed lines), persistent task-local state (three-part
answer), program inspection, symbolic transformation and verified execution
of the transformed program. No official dataset is used; no held-out rows
exist for this run. A held-out split uses a different seed, generated only
under a separate explicit authorization, and its cases are never opened before
that run.

Scoring: exact match after trimming (`substrate_tasks.score`). The fixture's
developer solutions in both languages reproduce every gold value, so the
generator and scorer are checked by two independent implementations.

## Sequence and budget

Every case runs in both arms, 40 attempts; the first arm alternates by case.
Each task is a fresh process, fresh workers, no shared state. Hard ceiling $12
aggregate, $5 per task (the gateway's reservation for one request needs this
much headroom), 480 calls; the runner refuses the next task once the spent
total plus the $5 reserve would exceed $12 (a dispatch stop above $7 spent),
stops on any failure, incomplete accounting or missing safety evidence, and
never retries or resumes. Expected spend is about $0.05 per task, $2 in all.

## Endpoints and frozen criteria (`benchmark/substrate.py` `CRITERIA`)

Primary: the paired difference in correctness, Clojure minus Python, over the
20 cases, with a 95% percentile bootstrap interval (4,000 resamples, seed
2026110302).

- success-clojure: the interval lies above 0 and Clojure's worker restarts are
  not more than Python's.
- success-python: the interval lies below 0 and Python's worker restarts are
  not more than Clojure's.
- inconclusive: the interval includes 0. Twenty paired cases cannot establish
  equivalence; equivalence needs a held-out run of at least 60 paired cases
  with the interval inside [-0.1, 0.1].
- failure (INCOMPLETE): any task not completed with complete safety evidence
  and accounting.

Secondary, reported as distributions per arm: first-attempt program validity,
execution success rate, requests and tokens, known cost, cold and warm
evaluation latency, end-to-end seconds, worker restarts, source characters,
error classes, delivery path. Not measured: worker CPU-seconds and peak memory
(no per-call instrumentation), structural patch correctness through artifact
tools (both arms use `repl_eval` only).

A single development outcome in either direction is not evidence of general
superiority. No prompt or surface change is made after seeing results; a
change means a new plan.

## Gate

`COMPLETE-PENDING-REVIEW` with the outcome pattern, or `INCOMPLETE`. Never
GO. Every trace is reviewed for error classes and delivery path before an
outcome is accepted.
