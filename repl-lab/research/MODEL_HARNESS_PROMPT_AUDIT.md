# Model-visible interface audit: Aljure and native Prime

This document extends `PROMPT_STRUCTURE_COMPARISON.md`, which covers request
sizes, hashes and cache costs, with what each harness tells the model and what
each model used. Sources:
- the request bodies recorded by the gateway for plans `0b6a0451…` (Sonnet)
  and `d6e9b40d…` (Opus);
- `resources/external-tools-assisted.txt` and `src/repl_lab/external_task.clj`;
- the Prime native session logs.

## What each harness says

| Element | Aljure | Prime |
| --- | --- | --- |
| System | Identity line only | Identity line + 29.8K-character harness prompt (skills ~5.8K tokens, continual harness ~1.9K, subagents ~1.5K, core tools ~0.7K, heartbeat, MCP, compaction, goal) |
| Tools | `context_metadata`, `context_query`, `repl_eval` (with the SCI rules), `agent_call`, `done` | `python_repl` (programmatic tools inside the REPL) |
| Completion | "Every response must make exactly one tool call. Text outside a tool call is never executed. Finish by calling done." Task paragraph: "Finish with done: put the exact benchmark answer in summary…". `done` tool: "For the root session the result is the exact final answer." | Task wrapper: "Write only the requested benchmark answer to /work/answer.txt." The run ends on a reply without a tool call. |
| Task text | The official question, verbatim, ending "Give your final answer in the form '…'" | Same question, verbatim |
| Error feedback | Tool errors with a hint. A format rejection: "Call exactly one of the provided tools. Text outside a tool call is never executed; to finish, call done… the task's only formatting correction." | Python tracebacks in the tool result |
| Context access | `external-context` and `context-lines` in SCI; line queries | `/work/context.txt`; Python file I/O and `bash` |
| Delegation | One sentence: "You may delegate a subtask with selected evidence to a child session." | ~1,500 tokens on `rlm.spawn`, collection, messaging and roles |
| Model-specific instructions | none | none |
| Thinking | adaptive, summarized, effort medium (both) | same |
| Compaction and refinement | none | documented (`/compact`, `refine.run()`) |
| Worked examples | none | none in the system prompt |

## What the models actually used

Prime affordances used in its 42 arms (Sonnet and Opus):
- `python_repl` in every arm;
- `rlm.spawn` in **1 arm** (Opus MultiNLI): 6 sub-agents. 5 failed on Prime's own sandbox errors, and 1 contributed a count for 73 of 438 pairs (*corrected 2026-10-29*);
- skills, refinement, compaction, `bash`, MCP and heartbeat: **never**.

So almost all of Prime's 11K-token system prompt was scaffolding these tasks
did not use. Whether its general operating guidance (the core-tools section,
statefulness, printing) helps reasoning cannot be determined without a
Prime-prompt ablation. Prime stays unchanged, so that ablation is out of scope.

Aljure affordances used: `repl_eval` and `done` in every arm, plus
`context_query` occasionally. `agent_call` appeared only in the capped Opus
smoke run (2 children); it was never used in the 21-task runs.

## Text-only completion and Aljure's instructions

| Run | Task type | Aljure arms with a text-only reply |
| --- | --- | --- |
| A1, A1c (OOLONG-Pairs) | long pair lists, built in SCI | 0 of 20 |
| Synth, Sonnet | short answers, "give your final answer in the form …" | 9 of 21 |
| Synth, Opus | same | 4 of 21 (5 replies) |

In 13 of the 14 synth replies the text contained a line in the task's
requested form. The evidence fits a conflict between the task's chat-style
instruction ("Give your final answer in the form 'Label: answer'"), which is
the last thing the model reads, and the harness's rule that only `done`
delivers an answer.
- **It is not specific to Opus**: Sonnet produced more of these replies.
- **The difference under Opus** is that one reply did not recover after the
  correction.

This is an association; it is not established. A test is intervention 3 in
`ADAPTIVE_COMPUTE_ABLATION_PLAN.md`: one general sentence mapping a requested
answer form to `done`'s summary.

## What a smaller general-purpose interface could add

None of these needs Prime's architecture or a larger prompt:
1. **Completion.** State that a requested answer form goes in `done`'s summary.
   About 30 tokens.
2. **Batch judgement.** One sentence about recording per-batch results in SCI
   state (`PRIME_MULTINLI_TRAJECTORY_ANALYSIS.md`), or a prelude tally helper.
3. **Delegation.** Aljure already has `agent_call`. Whether a fuller
   description changes its use is intervention 6; it is not assumed to help.
