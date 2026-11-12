# External artifact interface audit

This audit starts from commit `e6d17fee98bb40ad9119ca0f3b15533f5b76ad67`.
The original six-task result remains **NO-GO**, with 0/3 eligible unseen tasks
invoking the retained artifact. No original result or threshold is changed.

The extraction verifies all 189 files in the original result index. The index
SHA-256 is `f88d2a60e82d33fcff3ea76645915470b146bb3932475fd085f611e3b34ce353`.
The new extraction is in `evidence/reuse-interface-audit-20261102`. It preserves
each first provider request, observable tool calls and results, applicability
decisions, preload records, and model-visible errors. It excludes assistant
reasoning. `scripts/reuse_interface_audit.py` reproduces the extraction.

## What the model actually saw

Each eligible task received exactly five native tools: `context_metadata`,
`context_query`, `repl_eval`, `agent_call`, and `done`. The task message said:

> Controller-validated functions already defined in your SCI worker. Using them is optional.

The only listed export was `route-hold-rules`, with arity 1 and this summary:

> Routing rules: blocked=yes→hold; age_minutes>=60→expedite; attempts>=3→retry; else hold. For records with blocked/age_minutes/attempts fields.

The export name sounds narrower than its behavior. The summary does describe all
three labels. The message gives no source, hash, argument example, validation
scope, predicate source, or documented inspection operation. It does not explain
that the function accepts one Instance text string. The controller checked the
predicate and preloaded the export on all three tasks. The model did not see
that check's full details or the 36-record validation receipt.

The base instructions encourage inspection and computation through SCI. The
worker has `external-context`, `context-lines`, regex and string helpers. This
makes fresh counting code short. Reuse is optional. The benchmark scores the
final answer, not reuse, in the model-visible instructions. The frozen external
acceptance rule separately requires reuse. These facts make selection incentives
a plausible contributor, but do not establish that they caused a missed reuse.

## Why source failed

Task 4 submitted:

```clojure
(count context-lines) (take 5 context-lines) (source route-hold-rules)
```

`source` is not defined in this SCI worker. The adapter does not load the Clojure
REPL inspection macro or expose a source registry inside SCI. The verified forms
are preloaded by the controller. They are not file-backed Clojure definitions
with a supported REPL source lookup. Enabling filesystem access, `require`, or
host reflection would be the wrong repair.

The model received this exact error text:

> Worker rejected expression: Could not resolve symbol: source. It is not defined in this worker; definitions from a stopped worker are gone. The repl_eval description lists what is available.

That hint gives no inspection alternative. Its reference to lost definitions is
not evidence that the retained function disappeared. The unresolved symbol is
`source`, not `route-hold-rules`.

The broader runtime has `skills/list`, `skills/describe`, `artifact/inspect`, and
`artifact/call`. The frozen provider-native tool schema exposes none of them.
The native command parser rejects an unknown tool name. The general registry is
also the task output directory, not the separate retained library. Merely naming
the internal operations in a prompt would not connect the retained artifacts to
those operations. There was no documented, supported source-inspection route in
the external interface. Var metadata is not a substitute for verified source.

Direct invocation **was** possible through `repl_eval`, because the function was
preloaded. Thus the defect was not an absolute lack of execution capability.
It was missing inspection, incomplete invocation guidance, and no explicit
authorized artifact-call tool in this adapter.

## Three separate traces

| Task | Observed path | What the evidence supports |
| --- | --- | --- |
| 3: retry count | Read the first 600 context characters; wrote inline retry logic; returned `Answer: 17`. Three requests, no tool error. | No observable inspection or invocation attempt. Discoverability, applicability uncertainty, and selection remain competing explanations. |
| 4: hold count | Attempted `source`; received unresolved-symbol error; read context; wrote inline hold logic; returned `Answer: 51`. Four requests. | The model noticed the retained function and tried to inspect it. Strong evidence of inspection friction on this task. It does not prove that successful inspection would have led to reuse. |
| 5: expedite count | Read the first 600 context characters; wrote inline expedite logic; returned `Answer: 18`. Three requests, no tool error. | No observable inspection or invocation attempt. The cause remains uncertain. |

All three answers were correct. The retained code hash was
`4a2419a7e967b76d4510d79c28a8c6578990cf8f902ef539c08900b236f46236`.
No task recorded an invocation of it. The library pin was
`f273cf89770402469f31d549a51c7c25a5d955940706b202565fdd3adc5b2c88`.
The full six-task run cost $0.0812073 in API-rate-equivalent usage, including
$0.025166 for acquisition. These are historical measurements, not repair results.

## Repair boundary

`aljure_contract.skill_interface = "inspect-v1"` enables an external adapter
view of the existing verified library. It creates no new skill store, promotion
policy, or source-execution engine. With the switch absent, the baseline tools,
inventory, error feedback, acquisition behavior and execution path remain unchanged.

The inventory gives approved artifact hashes, names, arities, optional direct
call syntax and admission status. `artifact_inspect` reads canonical verified
source, the applicability source, provenance and the existing validation receipt.
Task 4's supported equivalent is `artifact_inspect` with the hash from inventory.
Its default section is `function`; `section: "applicability"` reads the predicate.
Each page is at most 4096 string characters. The serialized response is capped
at 32768 UTF-8 bytes. Unknown hashes, paths, extra fields and invalid page bounds
fail closed. Inspection reads the controller snapshot; it neither evaluates
source nor accepts a model-supplied filesystem path.

Approved artifacts refused by current applicability remain inspectable. They
are not callable. Quarantined, rejected, unknown-status and corrupt artifacts do
not enter the view. Verified dependencies can be inspected but do not receive an
independent invocation grant unless admitted as exports.

`artifact_call` maps to the existing `artifact/call` operation and
`executable/invoke!` isolated execution path. Its target must belong to this
task's admitted export set. The controller records the immutable artifact hash,
code hash and originating tool-call sequence. Arity checks, dependency checks,
language checks, sandbox limits and task deadlines remain in force. Arguments
are data, not executable source. Existing preloaded calls through `repl_eval`
remain available and retain their existing invocation instrumentation.

No task name, artifact hash, routing rule or expected answer occurs in the
general-purpose repair. Experiment fixtures and the frozen input library contain
their own concrete data, as required for reproducibility.

Summaries remain explicitly model-authored. A passed predicate and past
validation are described as limited evidence. The adapter neither applies the
artifact automatically nor tells the model to prefer reuse. Source inspection
does not count as reuse. Copying inspected code into a new function does not
count as retained-artifact invocation.

## Limits and next evidence

The repair changes inventory, inspection, explicit invocation, and error guidance
together. The next A/B test can measure the combined interface effect. It cannot
separate those components or prove which caused tasks 3 and 5. The retained
artifact was learned live, but its use in the next experiment is conditional on
that fixed acquisition. No new acquisition or promotion will occur in the A/B.

Scripted tests establish that the route works. They cannot establish autonomous
selection. A new, explicitly approved live development run is still required.
The protocol is `REUSE_INTERFACE_PROTOCOL.md`. The original NO-GO result remains
valid for the original interface and does not prove that the model cannot reuse
an executable artifact through a complete interface.
