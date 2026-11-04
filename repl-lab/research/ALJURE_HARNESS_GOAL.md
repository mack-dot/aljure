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

## Where the evidence stands (2026-11-04)

| Item | Status | Evidence |
| --- | --- | --- |
| Command-formatting failures | Fixed by provider-native tool calls | `PRIME_HEAD_TO_HEAD_NATIVE_TOOLS_RESULTS.md`; zero rejected commands since `a965bd9` |
| Answer-delivery failures | Diagnosed; recovery built but not adopted | `OPUS_FINALIZATION_REPAIR.md`, `CONTRACT_ABLATION_RESULTS.md` (F1 −0.022 paired, F2 lost completions) |
| Opus gap to Prime | Classified per task; ablations 3–5 designed, not run live | `OPUS_CAPABILITY_GAP_ANALYSIS.md`, `OPUS_CAPABILITY_ABLATIONS.md` |
| SCI ergonomics | Assisted surface, reader syntax, helpers, hints; cold start remains; range-error hint added today | A1c (0.845 vs 0.862 at equal wall time); `REUSE_CAUSAL_DIAGNOSIS.md` |
| Question A | Live Experiment A (2026-11-03, plan `996aa397…`): 20/20 vs 20/20 correct, inconclusive at a ceiling; Python arm 6 surface errors vs 1, all recovered; SCI +95 ms per task, immaterial. A2 proposed | `Q_SUBSTRATE_RESULTS.md`, `evidence/q-substrate-experiment-a-20261103/` |
| Question B | **Phase B held-out run (2026-11-04, plan `62ac8890…`, $4.05, 49 sealed OOLONG-synth contexts 4K–128K, 118 arms): primary +0.040 [−0.044, +0.138], inconclusive; overall 0.690 vs 0.688; W/T/L 7/35/7; Aljure at 32% of Prime's cost and 6 s faster at p50.** Pilot 1 (plan `bdb21429…`, development, Prime higher on every suite). Five Phase B arms failed on a plan-level per-arm cap defect (kept in the primary; diagnostic without them +0.028, inconclusive). Aljure's text-answer channel delivered 18 of 59 answers at mean 0.50 against 0.79 for computed answers | `HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md`, `HEAD_TO_HEAD_V8_RESULTS.md`, `HEAD_TO_HEAD_V8_READINESS.md`, `evidence/head-to-head-v8-phase-b-20261104/` |
| Executable reuse | Live causal study (2026-11-04, plan `1d5a4db2…`): `reuse-only-when-necessary`. With the rule in the text the model reimplemented 3/3 (0/6 across both studies); with the rule withheld it executed the retained skill once and took the rule from its summary once, both correct where the stateless pair was wrong. Recognition did not fail; the lever is the economics of reuse | `REUSE_CAUSAL_RESULT.md`, `evidence/reuse-causal-20261104/`; `REUSE_INTERFACE_RESULT.md` (NO-GO) |
| Reuse economics | Live run (2026-11-04, plan `ffbbb00f…`, $0.31): `reimplementation-regardless-of-length`, summary effect `none`. With Routing v1 stated as six ordered clauses, B and BN inspected or executed the retained skill in 0/12 eligible tasks (0/18 across three studies with the rule in the text); the model compressed the six clauses to one expression or counted by hand. Withholding summaries changed method, not selection. The long rule was compressible, so reimplementation was never expensive | `REUSE_ECONOMICS_RESULT.md`, `evidence/reuse-economics-20261104/` |

## Next steps in order

1. Reuse with the rule in the text is settled: three studies, 0/18 eligible tasks chose
   the retained skill, and neither interface, nor summary, nor rule length moved it.
   Judge the retained-skill mechanism on necessity cases. The next reuse study, if any,
   is a necessity study with two trials per cell and the summary-withheld arm
   (`REUSE_ECONOMICS_RESULT.md` §7, about $0.40); it needs a new frozen plan and the
   owner's approval of its exact hash.
2. Question A is run (inconclusive at a ceiling). Only if reuse depends on the
   substrate: freeze Q-SUBSTRATE A2 (surface gaps closed, 60+ harder paired
   cases; `Q_SUBSTRATE_RESULTS.md` §7).
3. Question B: Phase B held-out is run (inconclusive at +0.04; cost and latency advantage out of sample). Next, in order: (a) fix the per-arm cap defect (cap = one reservation plus a real allowance) before any further paired run; (b) decide the text-answer channel on evidence: it rescued answers but those averaged 0.50 against 0.79 for computed ones; (c) pilot 2 on the exploratory OBLIQ-math and LongBench Pro dev suites (prepared, not frozen); (d) a second Phase B run only with a new frozen plan, disclosing that the windows were seen once.
