# Prompt structure: Aljure and native Prime (A1c)

What each harness sent the model, measured from the request bodies the gateway
recorded for both routes at the same point (`gateway-request-intent`), and what
the prompts cost over the whole task. Source: A1c (`sci-ablation-speed-64k`,
plan `30654ed6…`), 10 arms per harness. Script: `scripts/prompt_structure.py`.
Evidence: `evidence/a1c-prompt-structure/prompt-structure.json`.

Token counts per section are **estimates**: each section's share of characters
times the measured input tokens of that call. Totals are measured.

## First request

| Part | Aljure | Prime |
| --- | --- | --- |
| Measured input tokens | 2,612 | 13,145 |
| System | 57 chars: the identity line only | 57 chars identity line + **29,825 chars** harness prompt (~11,300 tokens) |
| Tools | 5: `repl_eval` (1,264 chars), `context_query` (466), `agent_call` (381), `done` (476), `context_metadata` (184); ~1,100 tokens | 1: `python_repl` (740 chars), ~280 tokens |
| Message 1 | Base instructions and SCI rules, 2,344 chars (~925 tokens) | `[harness-digest]`, 2,657 chars (~1,000 tokens); state is empty: "No saved harness entries yet" |
| Message 2 | Task as EDN, ~1,444 chars | Task as text, ~1,520 chars |
| Varies by arm | Task only | Task, and one session-log path in the system prompt |

Prime's 29,825-character system prompt, by section (estimated tokens): Skills
~5,800; Continual Harness ~1,900; Subagents ~1,500; Core tools ~700;
Heartbeat ~340; MCP ~340; Compaction ~200; Goal ~170; header ~210.

## Whole-task cost (10 arms each)

| | Aljure | Prime |
| --- | --- | --- |
| Model calls | 59 | 50 |
| Cache writes (5 min) | 197,555 tokens, $0.494 | 234,984 tokens, $0.587 |
| Cache reads | 348,123 tokens, $0.035 | 653,648 tokens, $0.065 |
| Uncached input | 138 tokens | 120 tokens |
| Output | 30,162 tokens, $0.302 | 29,402 tokens, $0.294 |
| **Total** | **$0.831** | **$0.947** |
| First calls only | $0.139 | $0.231 |

The larger Prime prompt costs about $0.12 over 10 arms: more cache writing on
the first call and about 1.9 times the cache reads on every later call. Output,
the largest cost driver per call, is almost equal. Aljure's 9 extra calls
offset part of its prompt saving.

## Information each harness receives

- **Same task text.** The question appears verbatim in both first requests in
  10 of 10 cases.
- **Context access.** Prime: a file, `/work/context.txt`, and a Python kernel
  with numpy, pandas, `bash` and a writable `/work` (parity matrix rows 2c,
  4). Aljure: `external-context` and `context-lines` in SCI, plus
  `context_metadata` and `context_query`; no filesystem; a 10 s watchdog per
  expression (row 2b).
- **Deadline and budget.** Neither prompt states the 120 s deadline or the
  budget.
- **Memory.** Prime's harness digest was empty and identical in all 10 arms,
  so no information carried over between runs.
- **Answer.** Prime writes `/work/answer.txt`; Aljure calls `done`.
- **Request shape.** Prime streams and marks cache breakpoints on both system
  blocks, the tool and the last message. Aljure does not stream, marks the
  last tool and the last message, and sets `tool_choice` auto with one tool
  call per turn.

Neither harness receives information the other lacks about the data itself.
The differences are in instructions, tools and execution substrate.

## What this does not show

- Which prompt sections change behaviour. In A1c Prime made no skill,
  sub-agent, refine, compaction or bash call, so those sections had no visible
  effect on tool use. Their effect on reasoning is unknown; only an ablation of
  Prime's prompt could show it, and Prime stays unchanged in these
  comparisons.
- That a smaller prompt is more efficient in general, or that the SCI
  substrate explains the result. One context, one run per case.
