# Adaptive harness protocol — current priorities

Status: IMPLEMENTED / UNVERIFIED for the experiment as a whole. The current
language pilot is FIXTURE engineering validation. It is not a preregistered model
result or a sealed held-out experiment. No inference is authorized by this file.

## Current research priority

The operator has restored the original goal: a fixed model should acquire useful
executable computation, change how its harness works, and transfer improvements
to unseen tasks after reset. Clojure is a proposed mechanism. Python is an
ablation. Neither a language-only pilot nor a Prime kernel replacement may block
the first real acquisition/transfer experiment.

Work order: (1) one model-generated candidate and independent decision; (2) actual
reuse, sealed transfer and cold boot with compatible removal; (3) learning curves
and inference cost; (4) evolving Aljure versus native Prime; (5) language ablations.
Preserve the existing backends, evaluator and Prime adapter. Do not add benchmark
families or general orchestration infrastructure before the first live mechanism
test. The external Prime gateway remains necessary for that later comparison.

The current scheduler promotion rule evaluates policy behavior. A policy accepted
under a new workflow hash does not establish that context selection or delegation
improved. Report policy synthesis, workflow changes, actual workflow invocation,
and measured benefit separately. If only the policy improves, call the result
skill acquisition. A harness-efficiency claim needs its own matched workflow
ablation and complete inference accounting.

## Claims and historical labels

Use the new research labels: H1 is the effect of execution language, H2 is the
effect of executable learning/transfer, and H3 is full Aljure versus native Prime.
The scheduling protocol in `EXPERIMENTS.md` used H1 for retention, H2 for cold boot,
and H3 for language. Do not reinterpret historical fields silently.

The language ablation uses one Aljure controller with Python/Clojure and
frozen/evolving retention. The competitive comparison uses native Prime with its
full declared capabilities against the preregistered Aljure condition. These
answer different questions. A Prime Clojure fork is not an available condition.

## Outcome to freeze before final evaluation

Primary outcome: paired held-out verified task success at a fixed total budget.
Failures, timeouts, invalid source, provider errors and aborted attempts remain
in the denominator. An agent's final success claim is never the scorer.

Secondary outcomes: input/output tokens per verified solution, calls, recursion,
repairs, invalid-program rate, context queries, local execution time, artifact
size, accepted artifact invocation, acquisition cost and amortized evaluation
cost. Record uncertainty in local-compute prices and provider billing separately.

Protocol A fixes inference calls and tokens, then measures correctness/time.
Protocol B fixes acquisition plus inference plus attributable local cost. Do not
claim a fixed total economic comparison when local prices or provider charges
are unknown. Diagnostic unbounded development cost is reported separately.

For H2 estimate `(Clojure_evolving - Clojure_frozen) -
(Python_evolving - Python_frozen)` on the primary outcome, with repeated independent
acquisition runs. Resample acquisition runs, then paired tasks within each run,
or use another preregistered hierarchical method. Tasks from one retained library
do not constitute independent learning replications. No significance or win
claim is available from the current scripted pilot.

## Required frozen metadata

Record requested and returned model IDs, endpoint/provider, sampling and thinking,
output limit, cache policy, context window, tool schemas, complete prompt hashes,
capability matrix, source revision and file hashes, task/split hashes, artifact
library hash, container IDs, hardware and allocations, and all provider requests.
Control model settings across root and descendants, refinement and compaction.
Unknown receipt costs remain unknown. Reserve a shared ceiling before dispatch.

The first real paired case and ten-case pilot are engineering data. They may
guide a future protocol, but their scores cannot become that protocol's final
test evidence. Freeze the pilot configuration before calling a provider.

## Execution and contamination controls

Keep learning, development, held-out, cold-boot and distribution-shift splits
separate. Only the fixed controller may validate, promote, score, or consume a
sealed split. Neither agent gets scorer code, future hidden cases, credentials,
or access to source/budget configuration. Never drop failed pairs.

Frozen arms may construct and run task-local functions. Evolving arms may retain
only independently accepted executable artifacts. Before final evaluation,
terminate model conversations, workers and kernels; load an audited executable
bundle and its interface documentation into fresh processes. Exclude transcripts,
cached answers, seed tables and narrative memory. Record actual skill invocations.
Run a contract-compatible artifact ablation on matched unseen inputs.

The current `research/capabilities.json` lists remaining asymmetries. Python AST,
registry, promotion and export now have fixture coverage. Shared JSON commands and
language-specific documentation are implemented. SCI user macros/dynamic eval
remain disabled. Broker calls still orchestrate both languages; the REPL is not
yet the direct orchestration interface. Live parity remains unverified.

The OOLONG scorer/data pins remain in `benchmark/upstream.lock.json`. A local
export importer does not authenticate official dataset origin. No custom task
in the language pilot is called OOLONG.
