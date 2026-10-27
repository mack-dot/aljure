# Model-to-runtime command envelope v1

**IMPLEMENTED / OFFLINE TESTED. Live behavior is unverified.** This repair changes
Aljure's external response boundary and its formatting-error path. It adds no
reasoning strategy, execution capability, scheduler or learning mechanism. V3
remains sealed. New inference requires separate approval of a frozen V4 plan.

## What V3 actually returned

The third provider response ended with a map naming `:op :repl/eval`. Its source
proposed building a `rows` vector from `external-context`, extracting user IDs and
question text, and returning the row count. Before that map, the response included
Markdown and `<invoke>` fragments naming `repl/eval`, `context/query` and `x`.
The final map is the apparent intended command. The complete response does not
establish unambiguous intent, so that fragment must not execute.

[Read-only inspection](evidence/command-envelope-v1/v3-response-inspection.json)
records exact offsets, text and hashes. This extraction is forensic only; no
runtime path extracts it and no generated code was executed during inspection.
Original response SHA-256:
`94ceaf057076832a0a16d61ff34813bf5fa859c64ff74bc84a1dce32a3aac557`.
Exact text SHA-256:
`a8172ea55d76f365dab8dd453e24dc97dc9a6fda1d8df2f7b40121bc59c55930`.
The adversarial test uses this exact text, without its unrelated thinking block.

## Explicit response contract

The external adapter now selects `single-edn-map-v1`. The provider still uses the
existing text response path. It does not request native provider tool calls.
There is no automatic switch between text and tool-use formats.

1. The provider turn must end with `end_turn` and contain exactly one text block.
   Thinking blocks stay separate and never become commands. Tool-use blocks,
   multiple text blocks and disagreement between normalized text and content fail.
2. Text must contain one complete EDN map with only whitespace outside it. The
   parser never removes markup, extracts a map, joins blocks or repairs syntax.
3. The map must have one keyword `:op` and exactly that operation's existing fields.
   Duplicate keys, unknown operations and conflicting commands fail. Executable
   source must be a string; bindings must be a map; final summary must be a string.
4. The existing 32 KiB response and nesting bounds apply. Unsafe reader dispatch,
   tagged data and comments outside strings are rejected. Safe EDN data retains
   sets and nested namespaced maps. Source strings remain opaque to this parser.
5. Valid commands still pass through the existing broker, capability checks,
   deadlines and isolated SCI execution. The model cannot authorize itself.

The original base prompt remains unchanged. The new explicit contract is appended
from [external-command-v1.txt](../resources/external-command-v1.txt). Historical
JSON and EDN experiments retain their original contracts; only the external
adapter opts into this version.

## Bounded correction, not command repair

| Failure | Result |
| --- | --- |
| Markup/fences/prefix instead of a map, malformed EDN, comments, trailing non-command text | Reject all bytes; permit at most one fresh model response |
| Two top-level command maps, duplicate keys, unknown/invalid schema | Reject and stop the session |
| Oversize/deep input, unsafe reader syntax | Reject and stop the session |
| Mixed/split content, incomplete/truncated/refused turn, adapter text disagreement | Reject and stop the session |
| Provider interruption, unknown usage, budget or deadline failure | Existing failure path; never a formatting correction |

A correction is a new complete response, not approval of a rejected fragment.
The controller sends fixed feedback with the rejection category and `executed
false`. It does not send a guessed command or add invalid output to assistant
history. Exact rejected bytes, provider identity and hashes remain in evidence.

One durable `command-corrections-issued` counter covers the entire task, including
children and resumed sessions. Success does not reset it. The next request uses
the ordinary provider, pre-dispatch reservation, shared call/token/dollar caps and
remaining deadline. If those checks deny dispatch, no correction call occurs.
No new time, money or call allowance is created. The existing 64-turn guard also
counts correction turns. A second formatting failure stops its session.

## Verification and limits

The adversarial controls cover trailing text, markup, multiple/conflicting maps,
malformed maps, duplicate keys, unsafe readers, excessive size/depth, split or
mixed content blocks, truncation and field-type mismatches. They check that source
strings are not interpreted by the parser. Integration tests cover the exact V3
response, zero rejected-fragment execution, charged correction calls, exhausted
budgets, root/child/resume sharing and conservative unknown reservations.

The actual-container relay now deliberately supplies a fenced, incorrect final
command. Aljure must reject it, make one accounted correction, then execute the
trusted context fixture in SCI and in a child. Prime's existing native Python,
child, manual compaction/refinement and signed-thinking controls are unchanged.
Two new relay checks are mandatory at preflight. Scripted corrected output is
**FIXTURE**, not proof that a live model will correct itself.

Full regressions passed: **96 Clojure tests / 1,804 assertions** and **106 Python
tests**. [Validation](evidence/command-envelope-v1/validation.json) preserves the
commands and logs, including an initial stale test mock that was corrected.

**Current integration blocker:** two fresh SCI gate attempts failed. The first
worker missed readiness. In the instrumented second attempt, the allocation
probe timed out without OOM evidence and the later read-test worker failed Docker
preflight. Three intermediate positive controls passed, but do not establish
isolation. The source of this latency remains unknown. The supervisor, image and
limits were not changed. The new actual-container relay has therefore not run.
[Failed gates and startup evidence](evidence/command-envelope-v1/isolation-blocker.json).
V4 must remain blocked until the actual isolation and revised relay checks pass.

This change does not prove better reasoning or Clojure performance. Rejecting
unsafe output is required even when it lowers completion. The new prompt adds
input tokens, and correction consumes inference. Both costs must be included.
A real model may still fail or generate valid but incorrect code.

The proposed V4 diagnostic target uses Prime's exact V3 values: F1 at least
`0.967741935483871`, with equivalent inference cost below `$0.0663848`, including
all corrections and descendants. These are diagnostic targets, not a claim or a
new spending cap. The live pair must also compare against its contemporaneous
Prime arm. Its unchanged maximum remains $12 per arm / $24 total, subject to new
approval. Reusing this public case is engineering recovery, not held-out evidence.
