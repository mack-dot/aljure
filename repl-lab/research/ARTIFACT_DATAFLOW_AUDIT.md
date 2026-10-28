# Artifact data-flow audit

Where large values cross a boundary in the current Aljure external-task path:
serialization, copies, recomputation, model context, storage, re-parsing and
transfer between agents. Measurements are **observed** from the A1 run
(`sci-ablation-bounded-64k`, plan `d5038fe2…`, 32K OOLONG-Pairs development
suite, commit `13490b4`) unless marked *estimate*. Source paths are relative to
`repl-lab/`.

## 1. Critical path

```text
paired.py (host)
  └─ public input (context 76,803 chars) ─JSON stdin─► external_task.clj (host JVM)
       ├─ context → controller store (line records)                     [copy 1: ledger]
       ├─ first repl_eval → open worker (supervisor, Docker, JVM, SCI)  [6–11 s cold start]
       │     └─ initialize-context!: 19 chunk evals of 4,096 chars      [copy 2: worker heap]
       │        + prelude + context-lines                               [copy 3: vector of lines]
       ├─ model call (gateway → subscription) ◄── full history each call (cache reads)
       │     └─ tool_use (repl_eval source) ─► broker ─► worker
       │            worker: eval → pr-str value → one reply line ≤ 64 KiB ─► supervisor ─► controller read-edn
       │            controller: tool_result text → history; ledger events (tool-call, tool-result); stdout trace
       └─ done
             ├─ summary: model types the answer (output tokens)
             └─ source (A1 code): evaluate → ONE reply line with the whole answer   ← fails above 64 KiB
                 (fix, uncommitted): [length hash] → paged reads ≤ bound/8 chars → host assembles, checks
answer.txt (host) ─► independent scorer
```

Child sessions (`agent/call`) run the same loop. The child's `done` summary
returns to the parent **as text** in a tool result, so it is copied into the
parent's model context. No session in A1 or in the earlier 32K runs used a
child.

## 2. Boundaries and measurements

| Boundary | What crosses | Observed (A1) | Failure risk |
| --- | --- | --- | --- |
| Context into the worker | 76,803 chars in 19 chunks, then `context-lines` | on every worker start, including restarts; chunk evals take milliseconds | worker restart repeats it |
| Worker start | container, JVM, SCI, readiness probe | **6.1–10.6 s each; 4–5 starts per Aljure arm = 32.6–40.7 s of a 120 s budget** | dominant time cost |
| Model context | history re-sent each call (cached) | Aljure: 9–11 calls, 43.6K–77.2K cache-read and 7.2K–18.7K cache-write tokens per arm. Prime: 5–8 calls, 64K–139K read, 18K–31K write. | cost and latency |
| Tool results into the model | `repl_eval` values | Aljure max 1.5–24.2 KB (bounded previews); Prime `python_repl` max 4.7–30.7 KB | bounded |
| Worker reply line | one EDN line per expression | ≤ 64 KiB by the supervisor; **5, 3 and 4 stops in the first three Aljure arms**, all from final answers | **fatal for large answers (fixed by paging)** |
| Final answer | `done` summary or source | gold sizes 26.5K–156.6K chars (6 of 10 over 64 KiB); Prime delivered 35–140 KB through `/work/answer.txt` | Aljure could not deliver (A1) |
| Ledger | events and state, SQLite | 299–406 KB per Aljure arm; appended messages only since `79a3bd9` | fine at this scale |
| Traces | `stdout.jsonl` (request bodies) | Aljure 0.21–0.24 MB; Prime 0.58–0.99 MB (stream fix applied) | under the 4 MiB bound |
| Child to parent | `done` summary as text | not used | would copy large results into the parent's context |

## 3. Findings

1. **Model context is not the bottleneck for Aljure on these tasks.** The
   bounded surface keeps its tool results small. Aljure reads fewer cached
   tokens per arm than Prime.
2. **The binding boundary was the worker reply for the final answer.** The
   model computed the answers (85–91K chars in case 1), then lost them at the
   64 KiB reply bound and retried until the deadline. One arm submitted "ab"
   after three failures.
3. **Each failure is also a restart.** The definitions are lost and the
   context is re-ingested, at 6–11 s per start. That is about a third of each
   failed arm.
4. **Native Prime already delivers exact answers outside the model**, by
   writing a file that the harness collects. Exact delivery for Aljure is
   therefore **parity**, not an advantage.
5. **No recursion occurred.** Neither harness used children or subagents in
   any 32K run, so no observed cost or failure comes from agent-to-agent
   transfer.

## 4. Not measured (instrumentation gap)

Per-boundary bytes inside the worker (heap use), host CPU time, the time to
serialize and parse each reply, and tokens attributable to each tool result.
Add them through the worker audit and gateway events before claiming savings
at those boundaries.
