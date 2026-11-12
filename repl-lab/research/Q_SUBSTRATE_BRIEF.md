# Operator brief (2026-11-03): Prove the Clojure substrate advantage

Verbatim operator brief, recorded so that `/goal` can reference it by path. It
authorizes nothing; every live step needs its own frozen plan and approval.
Companion: `ALJURE_HARNESS_GOAL.md` (end state and priorities).

## Mission

You are the principal research engineer and agent-runtime architect responsible for Aljure.

Our objective is to build a general-purpose agent harness that matches or exceeds Prime's task-solving quality while achieving lower inference cost, lower latency, stronger program verification, and eventually cumulative improvement through reusable executable knowledge.

**Our central architectural hypothesis: Clojure, using SCI and code-as-data, can provide a superior computational substrate for autonomous agents compared with a conventional Python REPL.**

Do not assume this hypothesis is true. Build the system and experiments necessary to prove or falsify it.

The long-term goal is not to clone Prime. It is to build a superior harness by exploiting the properties of structured executable computation.

Operate autonomously through repository analysis, implementation, refactoring where justified, testing, verification, and experimental preparation.

Do not initiate paid model inference without separate approval of an exact frozen experimental plan.

## Phase 0 — Reconcile the actual repository

Inspect the entire local Aljure workspace, all worktrees, relevant branches, committed and uncommitted changes, and historical experimental evidence.

Important known checkpoints include:

- `213cf96` — matched Clojure/Python backend foundation.
- `a965bd9` — provider-native tool integration.
- `79a3bd9` — assisted SCI execution interface.
- `0c4c2d5` — worker startup and ledger performance improvements.
- `3fec260` — programmatic tool bridge.
- `82d82e5` — locally reported reuse-interface experiment result.

The latter may exist only locally. Verify rather than assuming the remote contains it.

Read at minimum:

- `research/LANGUAGE_ARTIFACTS.md`
- `research/EXPERIMENT_PROTOCOL.md`
- `research/STATISTICAL_EVALUATION_PROTOCOL.md`
- `research/PRIME_PARITY_MATRIX.md`
- `research/PRIME_ARCHITECTURE.md`
- `research/SCI_EXECUTION_CONTRACT.md`
- `research/HARNESS_LATENCY.md`
- `research/OPUS_CAPABILITY_GAP_ANALYSIS.md`
- `research/CONTRACT_ABLATION_RESULTS.md`
- `research/PROGRAMMATIC_EXECUTION.md`
- `research/RESEARCH_THESIS_REVIEW.md`
- `research/RESEARCH_SCORECARD.md`

Inspect actual source code, tests, commits, and traces rather than accepting conclusions from documentation without verification.

Preserve all existing work and historical evidence.

Identify the current implementation of:

1. Clojure SCI evaluation.
2. Python evaluation.
3. Common execution backend abstractions.
4. Model-facing tool interfaces.
5. Context delivery and persistent state.
6. Programmatic tool execution.
7. Structural code transformations.
8. Validation, promotion, and artifact retention.
9. Resource limits, isolation, and accounting.
10. Prime benchmark integration.

Produce a capability and parity matrix grounded in code.

## Phase 1 — Establish the true causes of previous underperformance

Investigate the observed gaps in Aljure's previous Prime comparison:

- Model reasoning errors.
- Invalid model-generated code.
- SCI language or capability restrictions.
- Prompt and tool-schema problems.
- Output delivery and finalization errors.
- Worker startup and process overhead.
- Controller or ledger overhead.
- Context access and parsing differences.
- Premature stopping.
- Provider or benchmark failures.
- Genuine deficiencies in algorithms or computational expressiveness.

Reproduce relevant failures offline wherever possible.

Determine which problems have already been fixed, which remain, and which were never established as real causes.

Pay special attention to the earlier model-facing EDN failures, worker restarts, `parse-long` restrictions, 64 KiB output behavior, repeated process startup, and final-answer delivery.

Do not attribute a model failure to Clojure merely because the failing harness used Clojure.

Deliver a ranked root-cause analysis supported by specific files, commits, tests, and observed traces.

## Phase 2 — Finish the common execution architecture

Use the existing `ExecutionBackend` abstraction in `execution.clj`.

The architecture should preserve one shared controller while allowing selectable Clojure and Python computational substrates.

Avoid creating separate agent frameworks.

Required common capabilities:

- Persistent task-local execution state.
- Model-generated program execution.
- Structured input and output.
- Bounded result delivery.
- Context access.
- Explicit resource and operation budgets.
- Error feedback and recovery.
- Deterministic computation.
- Authorized programmatic tool calls.
- Program identity and provenance.
- Structural transformations.
- Validation and cold-restart execution.

Inspect the Python backend's unsupported `run-program!` path.

Implement equivalent capability-bearing programmatic execution only where necessary for the experiments, with the same controller-side authorization, effect restrictions, budgets, and audit semantics as SCI.

Do not silently weaken either language's isolation guarantees to obtain parity.

Security controls should achieve equivalent objectives, even if their implementation mechanisms differ.

Use the smallest reusable abstractions possible.

## Phase 3 — Make SCI an excellent model-facing interpreter

We are committed to giving Clojure its best reasonable chance to succeed.

Improve ergonomics without sacrificing isolation.

Investigate and address:

- Familiar, clearly documented Clojure syntax.
- Useful standard collection operations.
- String parsing, filtering, grouping, mapping, and reduction.
- Numeric operations and deterministic counting.
- Multiple expressions in one invocation.
- Persistent bindings.
- Compact, actionable execution errors.
- Large result paging and bounded output.
- Safe access to context records.
- Structural program inspection and manipulation.
- Batch execution of authorized tools.
- Reliable recovery and final-answer submission.

Reuse the existing assisted SCI surface and prelude instead of inventing another incompatible interface.

Reduce unnecessary instructions, model round trips, and serialization.

Preserve the meaningful security boundary between generated computation and the trusted controller.

Do not add arbitrary JVM interop, filesystem access, network access, or unrestricted evaluation merely to match Python.

If an essential capability requires such authority, expose it through an explicit, separately authorized controller-mediated tool.

Measure before and after changes.

## Phase 4 — Run Q-SUBSTRATE as a real scientific experiment

The primary question is:

**Does a Clojure/SCI substrate enable better agent performance than a Python substrate under the same Aljure controller?**

Build a matched experiment using the existing language benchmark framework.

### Experiment A — Controlled computational substrate

Hold constant:

- Foundation model and model settings.
- Controller implementation.
- Public task information.
- Task difficulty and datasets.
- Evaluation and scoring.
- Call, token, dollar, and wall-clock budgets.
- Available external operations.
- Isolation objectives.
- CPU and memory allocations.
- Final-answer requirements.
- Restart and artifact-persistence conditions.

Change the execution backend and the necessary language-specific source instructions.

Use equivalent, idiomatic APIs rather than forcing identical syntax.

Include tasks involving:

1. Large collection processing.
2. Structured filtering and aggregation.
3. Exact counting and numerical computation.
4. Parsing and normalization.
5. Algorithm construction.
6. Error recovery.
7. Persistent task-local state.
8. Program inspection.
9. AST or symbolic transformations.
10. Verified execution of transformed programs.

Use actual model-generated programs, not just scripted fixtures.

Measure:

- Independently verified task success.
- First-attempt program validity.
- Successful execution rate.
- Model requests and tokens.
- Inference cost.
- Execution latency, warm and cold.
- End-to-end latency.
- CPU-seconds and peak memory.
- Worker failures and restarts.
- Source-code size and transformation complexity.
- Structural patch correctness.
- Validation overhead.

Report the entire distribution, not only averages.

### Experiment B — Idiomatic substrate strengths

Allow each language to use its genuine architectural strengths.

Clojure:
- Canonical symbolic program representations.
- Immutable data.
- Structural patching and composition.
- Validated executable artifacts.
- Controlled persistent computation.

Python:
- Idiomatic Python computation.
- AST manipulation.
- Appropriate standard-library capabilities.
- Equivalent structured program interfaces.
- Matched artifact and validation mechanisms.

Keep comparable resource budgets, task information, security objectives, and evaluation criteria.

Document capability differences rather than disguising them.

Determine whether Clojure's structural advantages outweigh Python's greater familiarity and ecosystem advantages.

### Experiment C — Programmatic tool execution

Compare matched Clojure and Python programs running multiple authorized tool operations within one model invocation.

Measure:

- Model round-trip reduction.
- Tool throughput.
- Correctness of side effects.
- Idempotency and uncertainty handling.
- Authorization enforcement.
- Model cost.
- Execution cost.
- Latency.
- Error recovery.

Preserve the already observed Aljure direct-tools versus programmatic-tools result as historical evidence, not proof of language superiority.

### Experiment D — Verified executable learning

Only after basic substrate parity is demonstrated, test whether either backend provides an advantage in:

- Model-authored skill acquisition.
- Independent validation.
- Structural modification.
- Composition.
- Artifact retention.
- Cold-restart execution.
- Voluntary reuse.
- Amortized future-task cost.

Keep the controller, acquisition rules, tasks, and independent scorer equivalent across languages.

Separate the effect of execution language from the effect of retaining learned artifacts.

The primary learning comparison must include acquisition and validation costs.

## Phase 5 — Design statistically defensible evaluation

Use independently selected development and held-out tasks.

Prefer multiple independent task contexts and repeated runs, rather than many correlated questions from one context.

Use the existing preregistered statistical protocol where applicable.

Report:

- Paired quality differences.
- Confidence intervals.
- Completion and failure rates.
- Total cost per verified solution.
- Latency distributions.
- Per-language source validity.
- Run-to-run variance.
- Meaningful resource asymmetries.

Define success, failure, equivalence, and inconclusiveness before the live evaluation.

A single Clojure win is not evidence of general superiority.

A non-significant difference is not evidence of equivalence.

Keep diagnostic development tasks out of the final held-out claim.

No benchmark-specific prompt changes after seeing held-out outcomes.

## Phase 6 — Evaluate against Prime independently

Once the substrate study produces a credible result, prepare a separate complete-harness evaluation against pinned native Prime.

This is Q-HARNESS, not Q-SUBSTRATE.

Preserve Prime's native capabilities. Do not remove them to manufacture parity.

Match models, task distributions, accounting, deadlines, and resource budgets wherever possible.

Disclose architectural differences that cannot reasonably be equalized.

Evaluate both ordinary single-task performance and long-horizon sequences involving repeated or reusable computation.

Targets:

- Aljure quality ≥ Prime.
- Aljure inference cost ≤ 50% of Prime.
- Aljure median and tail latency ≤ Prime.
- Comparable or better execution reliability.
- No weaker security or evidence guarantees.
- Improved cumulative cost-quality performance through retained computation.

These are targets, not claims.

Determine whether any observed advantage actually comes from Clojure, controller design, programmatic batching, context handling, executable learning, or another cause.

Do not conflate them.

## Phase 7 — Architectural discipline

Before adding substantial infrastructure, answer:

1. Which measured limitation does this component address?
2. Can the existing architecture implement it more simply?
3. Does the component add a model round trip?
4. Does it increase context or prompt overhead?
5. Does it enlarge the security boundary?
6. Can its benefit be measured independently?
7. Can it be removed if the experiment fails?

Favor small, understandable, efficient systems.

Avoid speculative multi-agent frameworks, additional memory databases, unnecessary background services, and duplicate program representations.

Do not recreate Prime's complete architecture as the default strategy.

Python interoperability can remain an optional capability inside an Aljure harness. That does not invalidate Clojure as the primary controller and artifact language, but cross-language execution must be attributed accurately.

## Phase 8 — Verification and safety

Run offline tests before any live inference.

Include:

- Clojure and Python regression suites.
- Real isolated-worker tests.
- Interpreter capability and denial checks.
- Tool authorization and effect checks.
- Exact resource-boundary tests.
- Cross-language semantic fixtures.
- Source transformation and stale-parent tests.
- Crash and cleanup recovery.
- Artifact identity and provenance verification.
- Independent scorer validation.

Protect local resources.

Never run unrestricted Docker pruning or destructive cleanup.

Do not kill unrelated workers or alter other projects.

Preserve pinned images and evidence archives.

Use conservative execution concurrency, preflight resource checks, and explicit abort conditions.

Maintain clean separation between source changes, frozen experimental plans, and historical results.

## Phase 9 — Claim gate

Implement a minimal evidence-backed claim report if one is not already available.

Distinguish:

- Implemented.
- Offline tested.
- Live model demonstrated.
- Independently benchmarked.
- Statistically supported to held-out tasks.

Every claim must identify its exact source, model, benchmark, plan, and evidence.

A failed experiment is still a valid research result.

Never reinterpret or change historical NO-GO conclusions.

## Phase 10 — Execution and approval boundaries

Execute the following autonomously:

1. Repository and commit audit.
2. Root-cause investigation.
3. Controlled architecture repairs.
4. Offline benchmark implementation.
5. Unit and integration tests.
6. Isolation and security validation.
7. Measurement instrumentation.
8. Documentation and evidence reports.
9. Reproducible experiment preparation.
10. Frozen plan generation and preflight.

Make incremental, reviewable commits in an isolated worktree. Preserve existing work.

Do not merge into shared branches without authorization.

**Do not initiate paid model inference or access sealed held-out evaluation data without explicit authorization.**

Before requesting approval, provide the exact commit, experiment plan hash, model, task count, estimated cost, hard cost ceiling, resource limits, and frozen acceptance criteria.

Do not treat previous approvals as permission for new experiments.

Continue independent offline engineering when a live step is blocked.

## Required final deliverables

- **A. Root-cause report.** Where Aljure previously underperformed, which issues were caused by SCI, which by harness engineering, and which remain unproven, with exact code and commit history.
- **B. Substrate parity matrix.** Actual Clojure/Python capabilities, missing parity, resource guarantees, and test coverage.
- **C. Implemented corrections.** Code changes, regression tests, performance measurements, and remaining limitations.
- **D. Q-SUBSTRATE experiment.** A reproducible matched-language experiment with independent scoring, meaningful tasks, complete accounting, and explicit uncertainty.
- **E. Prime frontier roadmap.** The smallest changes with the highest expected impact on Aljure's quality, cost, latency, and reliability; experimentally supported priorities distinguished from hypotheses.
- **F. Experimental authorization package.** Freeze the best next live experiment after all offline checks succeed. Stop at the approval boundary with the exact plan hash and requested authorization.

## Definition of success

A successful project does not merely demonstrate that SCI can run Clojure programs. It establishes whether Clojure enables a measurably better computational environment for agents, and whether those advantages improve the performance of a complete agent harness.

The ideal result is a system that solves difficult tasks reliably, uses fewer model calls, executes computation efficiently, represents programs structurally, validates and transforms its own executable work, retains useful computation across tasks, exploits previously acquired computation when beneficial, and outperforms competitive harnesses under fair independent evaluation.

If Clojure is superior in certain dimensions and inferior in others, quantify those tradeoffs and design around them.

**Do not optimize for confirming the Clojure hypothesis. Optimize for discovering and building the best possible agent runtime.**

Start with the full audit. Then execute the highest-value safe engineering work, complete offline verification, and prepare the first genuine Q-SUBSTRATE experiment for approval.
