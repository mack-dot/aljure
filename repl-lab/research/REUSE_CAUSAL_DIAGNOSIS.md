# Why the model reimplemented instead of reusing: diagnosis of run 3

Read-only analysis of the ten retained traces of the reuse-interface A/B
(`REUSE_INTERFACE_RESULT.md`, commit `82d82e5`, raw run
`var/reuse-interface-20261103/run-3`). The NO-GO and its scoring are unchanged.
Observations come from recorded provider requests and responses. Hypotheses
are marked as such. Nothing here infers intent from an absent tool call.

## Observations

**The model knew the library existed and judged it applicable.** Adaptive
thinking emitted zero thinking tokens on all 34 responses, so no hidden
reasoning exists. Four responses carried visible text:

| Task | Arm | Text before the tool call |
| --- | --- | --- |
| reuse-dev-1 | repaired | "Rules match; compute." |
| reuse-dev-2 | repaired | "Rules match; compute directly." |
| reuse-dev-5 | baseline | "The v2 rules apply, so the provided function doesn't. Hold means blocked is not yes and age is under 30." |
| reuse-dev-5 | repaired | "Rules v2 differ from the artifact. Count: blocked=no and age<30." |

The model compared the task rules with the inventory summary, found them to
match on eligible tasks and to differ on the Routing v2 control, and in every
case wrote fresh code. On the one baseline task that touched the function, it
probed `(route-hold-rules (first context-lines))`, received `nil` (the first
line is the header), and abandoned it.

**The first action differed by arm, deterministically.** All five repaired
tasks opened with the same 78-token call
`(subs (apply str (interpose "\n" (take 15 context-lines))) 0 3000)`, which
failed on texts of 1535 to 1546 characters. No baseline task used that form;
three of five opened with `(subs (str external-context) 0 600)`. The number
3000 does not occur in any prompt; the only number present is the inspection
page limit 4096. The two arms' first requests differ only in the two added
tool schemas and the inventory text (2344 against 3181 first-call prompt
tokens, 837 more). Hypothesis: the longer, more structured prompt shifted the
model's opening read; whether length or structure did it is not identifiable
from two prompts.

**The artifact's contract was understandable but incomplete.** The inventory
gave name, arity, hash, summary, `(route-hold-rules arg1)`, admission and the
tool text. It did not say the argument is one record line, nor what a
non-record input returns. The nil probe was the direct consequence: the model
had to discover the contract by execution, and the first experiment returned
nothing. The applicability predicate itself requires the task text to contain
the fragment `age_minutes>=60 means expedite`, so the retained artifact can
only be admitted on tasks that already restate its rule.

**Reimplementation had a rational cost advantage.** On every eligible task the
rule text was in the context and restated in the inventory summary. The inline
solution was one expression of about 160 output tokens and one request. Reuse
by name would have been about as short, but the model had no stated argument
contract; reuse by `artifact_call` is one record per request. Any inspection
costs one extra request (about $0.003). With the rules in hand, the expected
value of inspection or invocation was zero and the cost positive.

**No implementation or provenance defect was found.** All 34 provider
requests were valid tool calls. The inventory and tools were present in every
repaired request. The admitted hash, code hash and library pin matched the
frozen suite. The one baseline invocation was attributed to the correct code
hash with the correct call sequence. Cleanup and isolation evidence were
complete. The only model-visible errors were the four range errors above.

## Root-cause statement and confidence

1. Absence of economic incentive is the dominant explanation. High confidence:
   the model stated the rules matched and computed anyway, on tasks where the
   rules were in the text.
2. Discovery was not the failure. High confidence for exposure (inventory in
   every request) and understanding (the visible comparisons). The model never
   called `artifact_inspect`, so inspection usability remains untested live.
3. Selection failure cannot be separated from (1) on these tasks. The causal
   protocol's necessity arm exists to separate them.
4. The `subs` range error is a prompt-induced change of first action, not an
   interface defect. Moderate confidence on the mechanism; the general hint
   added in this commit removes the retry cost without a benchmark-specific
   instruction.

## What changed in response

- `executable.clj`: the invocation log counts nil returns, so a probe can be
  told apart from a useful execution by executable evidence.
- `model_protocol.clj`: a range error now names the documented `page` helper.
- `benchmark/reuse_causal.py`: attribution levels, prompt and tool-schema
  measurement, the four-arm protocol and the frozen outcome mapping.
