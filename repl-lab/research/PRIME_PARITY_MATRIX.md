# Prime parity matrix

Pinned native Prime: commit `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, image
`f3e30aaa…`. Local checkout `var/upstream/prime-agent` is clean at that commit.
Aljure: `178bfc3`. The facts come from a read-only audit of the Prime source and
image, our adapter, and the request bodies of the 32K runs
(`sci-ablation-control-2`, `sonnet-ten32-live`). Prime-side line references are
to the pinned Prime repository (`P:`).

**Type:** **A** = legitimate architectural difference (keep it and disclose it);
**C** = implementation confound (fix it or control for it); **?** = unverified.

| # | Dimension | Native Prime | Aljure | Type | Notes / evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Model, thinking, effort, `max_tokens` | `claude-sonnet-5-5`; adaptive thinking (summarized); effort medium; 32768; streaming | Same values; non-streaming; `tool_choice` auto, one call per turn | parity | The gateway enforces the pinned settings for both arms (`gateway.clj` `validate-request!`). |
| 1b | Thinking in history | Signed thinking blocks kept | Kept unchanged when present. Adaptive thinking sends no thinking block on some turns. | parity | Verified in the `00-aljure` request bodies. An audit claim that Aljure drops them was checked and **refuted**. |
| 1c | Context overflow handling | Auto-compaction starts at 95% of the 1M window | None | **C** | The relay and gateway reject request bodies over 1 MiB (about 250–300K tokens) first, so Prime's compaction can never trigger and a long run fails instead (`gateway.clj:63`; `relay_bootstrap.py`; `P:crates/pa-core/src/session_engine/compaction.rs`). |
| 2 | Per-call output | 65,536 **characters** per stream (`DEFAULT_MAX_OUTPUT_CHARS`, `P:crates/pa-core/src/kernel/shared.rs:14`). Truncates head and tail with a marker; the kernel keeps running. | Raw surface: 65,536 **bytes** per expression, and overflow stops the worker and loses its definitions. Bounded surface: about a 60 KB preview, and the worker survives. | **C** (raw) | Similar size, opposite failure behaviour. The bounded surface removes the confound. |
| 2b | Per-call timeout | None (watchdog off in print mode) | 10 s per expression; 30 s worker startup | A | Disclosed. Aljure's sandbox bound. |
| 2c | Libraries and state | Persistent CPython 3.12 with numpy, pandas, scipy, bs4, lxml and pillow; `bash()` with grep, awk and sed; `/work` filesystem | SCI: `clojure.core`, `clojure.string`, String methods, `Integer`; no filesystem, process or network | A | This is the substrate difference. Q-SUBSTRATE tests it. |
| 3 | Subagents, refine, compaction, messaging | Available (`rlm.spawn` asynchronous, depth 2) | Synchronous `agent_call` children | A | **Unused in both 32K runs** (0 spawn, refine, compact or bash calls). |
| 3b | Concurrency under the reservation rule | Nominally 8; effectively **2**: each reservation holds $4.33 against a $12 cap | Children are synchronous | **C** (latent) | Would throttle only Prime's asynchronous children. |
| 4 | Compute boundary | Agent loop, relay, kernel and children share **one** container: 256 MiB, 1 CPU, 32 pids, 8 MiB `/work` with exec allowed | Controller and gateway run on the **host**. Each SCI session gets its own 256 MiB, 1-CPU container. | **C** | Aljure's orchestration has more CPU and memory. Disclose it, or move Aljure's controller into a bounded container for Q-HARNESS. |
| 4b | Time | Same 120 s kill. The first request comes at 5.3–8.0 s (container and agent start). Kernel warm; about 1 s of harness time between model calls. | Same 120 s. In A1, 6–15 s per cold SCI worker and 1.6–3.8 s of harness time between model calls (ledger process starts). Since `0c4c2d5`: worker prewarmed during the first model call, cold start 1.15 s, ledger 0.18 s per step; relay fixture 5.8 s against Prime's 13.6 s. | A | Startup is inside the budget for both. Report it separately. `HARNESS_LATENCY.md`. |
| 4c | Task-output bound (4 MiB) | Counted request bodies **plus every native JSON event**. `message_update` events, each repeating the partial message, were about 70% of the stream and killed 2/10 arms. | Counts request bodies only (0.11–0.33 MB per arm) | **C → fixed** | `178bfc3` keeps a marker for `message_update`. The killed streams would fall to 1.37 MB and 1.24 MB. |
| 5 | Final answer | The model writes `/work/answer.txt`; the run ends on a reply with no tool call. Files are collected only after the completion event, so a killed arm loses an answer it already wrote. | `done` with a summary, or SCI `source` that evaluates to a string; one tool call per response | A | Both are killed at 120 s; neither prompt states the deadline. |
| 6 | Prompt | About 29.8K characters of Prime harness prompt (skills, subagents, refine, MCP), one `python_repl` tool schema; about 12.5K input tokens on the first call | About 1.8K characters of instructions plus the task map; 5 tool schemas; about 6.8K first-call tokens | A | The model sees each harness's own prompt. |
| 7 | Adapter changes to Prime | Custom provider entry, explicit `maxTokens`; print/JSON mode (daemonless, so `rlm.create_session` and the watchdog are off); OAuth identity; relay limits (1 MiB request, 4 MiB response, 120 s); fresh `/work`; uid 65534; no network | — | disclosed | Unverified: whether Prime retries the relay's 429 replies. |

## Required before a Q-HARNESS claim

1. Run the relay fixture after `178bfc3`; confirm Prime's stream bound now
   measures output.
2. Choose and disclose the compute boundary (row 4). Preferably run Aljure's
   controller inside a matched container, or report host CPU-seconds for both.
3. Use the bounded SCI surface, or disclose raw-mode worker death (row 2).
4. Keep rows 2b, 2c, 3, 5 and 6 as disclosed architectural differences. Do not
   remove Prime features to match Aljure.
5. Record whether Prime used subagents, refine or compaction in each arm. So far
   it never has.
