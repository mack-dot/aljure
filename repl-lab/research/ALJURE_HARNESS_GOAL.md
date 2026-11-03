# Aljure goal: a better agent harness than Prime, on a Clojure substrate

Set by the operator on 2026-11-03. This file states the goal, the two research
questions that decide it, the priority order, and where the evidence stands.
It authorizes nothing. Each experiment keeps its own frozen protocol.

## End state

> Aljure is a general-purpose agent harness that uses structured executable
> computation to achieve comparable or better task quality with fewer model
> calls, stronger verification, and reusable computational knowledge.

Clojure is the computational substrate because code is data: programs can be
parsed into forms, transformed, hashed, validated, composed and executed in a
restricted interpreter. That is a possible advantage for agents that construct,
inspect, transform, verify and reuse programs. It is not automatically a better
execution environment than Python, and it is weaker for numerical work. Python
stays available as an optional capability for NumPy, pandas and similar
workloads; Clojure owns orchestration and program representation.

The substrate supports four execution strategies, chosen per task by the
controller, which also applies budgets, manages context and recovery, and
preserves evidence:

1. Direct reasoning: the model answers without computation.
2. Structured computation: one Clojure program does several operations without
   extra model round trips.
3. Verified reuse: the model runs a previously approved program.
4. Structural adaptation: the model modifies an approved program and validates
   the new version.

## The biggest risk is the model, not the interpreter

Earlier benchmarks showed answer-delivery failures, unsupported-function
errors, command-formatting mistakes and unnecessary retries. A superior
substrate does not matter if the model cannot operate it efficiently. The
first-class engineering objective is therefore:

> Make Clojure as easy for the model to use as Python, while retaining the
> advantages of structured executable data.

That means a small predictable API, well-designed tool schemas, concise error
recovery, bounded outputs, convenient collection processing and robust
finalization. Not a large collection of agent-specific prompts.

## Two research questions, kept separate

**Question A. Does the Clojure substrate outperform the Python substrate?**
Hold the controller, model, task, budget, tool permissions and evaluation
protocol constant. Compare matched Clojure and Python execution backends.
Measure quality, generated-code validity, execution latency, memory, tool
errors, program transformations and verification overhead.

**Question B. Does the complete Aljure harness outperform Prime?** Compare full
systems under identical model settings and comparable capabilities on
independent tasks. This is what users experience.

If Aljure wins B without A, the cause could be context management,
programmatic batching or another harness feature rather than Clojure. The
separation is what makes a substrate claim possible.

## Priority order

1. SCI ergonomics and reliability: remove language and tool-interface
   friction so stronger models can exploit the runtime.
2. Programmatic execution and batching: build on the measured reduction in
   model round trips; benchmark the total cost of programs, not interpreter
   speed.
3. Persistent computational state: structured context, artifacts, validation,
   versioning and restart recovery, efficient and dependable.
4. Autonomous reuse and adaptation: a differentiator once selection and
   measurable utility are established.
5. Full Prime competition: quality, cost, latency and long-horizon efficiency
   on independent benchmarks.

Aljure is not a pure learning experiment. Learning is one capability inside a
competitive execution system.

## Where the evidence stands (2026-11-03)

| Item | Status | Evidence |
| --- | --- | --- |
| Command-formatting failures | Fixed by provider-native tool calls | `PRIME_HEAD_TO_HEAD_NATIVE_TOOLS_RESULTS.md`; zero rejected commands since `a965bd9` |
| Answer-delivery failures | Diagnosed; recovery built but not adopted | `OPUS_FINALIZATION_REPAIR.md`, `CONTRACT_ABLATION_RESULTS.md` (F1 −0.022 paired, F2 lost completions) |
| Opus gap to Prime | Classified per task; ablations 3–5 designed, not run live | `OPUS_CAPABILITY_GAP_ANALYSIS.md`, `OPUS_CAPABILITY_ABLATIONS.md` |
| SCI ergonomics | Assisted surface, reader syntax, helpers, hints; cold start remains; range-error hint added today | A1c (0.845 vs 0.862 at equal wall time); `REUSE_CAUSAL_DIAGNOSIS.md` |
| Question A | Scaffold only: backend switch, Python worker, JSON envelope fixtures for two families; no model has run it; the native tool path has no Python tool | `LANGUAGE_ARTIFACTS.md`, `language_benchmark.clj` |
| Question B | Several paired Sonnet and Opus runs on development suites; no independent benchmark yet | `PRIME_PARITY_MATRIX.md` lists the confounds to control first |
| Executable reuse | Interface works; the model reimplements when the rule is in the text | `REUSE_INTERFACE_RESULT.md` (NO-GO), `REUSE_CAUSAL_PROTOCOL.md` (frozen, awaiting approval) |

## Next steps in order

1. Run the frozen causal reuse protocol if approved (about $0.25). It settles
   whether reuse is a selection problem or an incentive problem before any
   further reuse engineering.
2. Add a Python evaluation tool to the native tool envelope and a matched task
   suite, then freeze a Question A plan.
3. Control the Question B confounds in `PRIME_PARITY_MATRIX.md` (compute
   boundary, bounded surface, output bound) before an independent benchmark.
