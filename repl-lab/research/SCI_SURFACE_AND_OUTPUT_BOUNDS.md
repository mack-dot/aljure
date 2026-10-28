# SCI surface and output bounds: validation and ablation

Motivation: on the fresh OOLONG-Pairs 32K suite (run 2026-10-28, cases 1–5),
every Aljure arm failed on the sandbox, not the task. The model sent several
forms per call, used `Long/parseLong` and `parse-long`, invented helpers, and
printed results over 64 KB. The supervisor then stopped the worker, and every
later call failed until the 12-call budget ran out. Those results stay as
historical evidence (`var/benchmarks/sonnet-ten32-live`, plan `83fecbaa…`).

## 1. Are Prime's 4 MB and Aljure's 64 KB the same boundary? No.

| | Native Prime | Aljure SCI |
| --- | --- | --- |
| Limit | `OUTPUT_LIMIT = 4 MiB` in `benchmark/prime/container.py` caps the native task's whole stdout and stderr stream for the run. The relay also refuses response bodies over 4 MiB. | 64 KiB per expression reply line, enforced by `scripts/isolation.py`. |
| Large tool result | The pinned agent truncates kernel output with a marker (`[... output truncated at N chars ...]`) and the REPL keeps running. `N` is compiled into the Rust binary and could not be recovered from its strings. It is at least 47,784, the largest untruncated tool result in our Prime traces. | The supervisor raises `Worker output limit`, removes the container and loses every definition. |

The material difference is graceful truncation against worker death, not
4 MB against 64 KB.

## 2. Output bound: explicit, proven, 64 KB control preserved

- The bound is read from `REPL_LAB_WORKER_OUTPUT_BYTES` by the supervisor, the
  doctor and the controller's line check. Only 65,536 (the default) and
  1,048,576 are accepted. Each has its own isolation proof
  (`var/isolation-proof.json` and `var/isolation-proof-1048576.json`), and the
  proof records its bound.
- The gate proves the exact boundary at both bounds: a reply line of exactly
  the bound passes, and one byte more stops the worker. The oversized control
  scales to `max(1,000,000, 2 × bound)`: 1,000,000 bytes (unchanged) at 64 KB,
  and 2,097,152 at 1 MB.
- Both bounds: 9/9 negative controls (loop, allocation, oversized result,
  read, write, process, network, evaluator, reader eval). Memory: the
  allocation control still exhausts the 256 MB heap
  (`jvm-heap-exhausted`). CPU and cancellation: the loop control hits the
  per-expression wall limit. Isolation: unchanged container flags. Prime does
  not read the output bound: it uses only the shared container helpers.

## 3. SCI contract (`resources/sci-contract.json`)

The assisted tool description is generated from the contract's rules, so
every advertised behaviour is a contract rule. `repl-lab.sci-contract` runs
every probe through the controller's own source, result and error paths
against the real worker, in raw and bounded modes. It writes a proof that
paired preflight requires (matching the contract, prelude, protocol code,
image and bound). Result: 51/51 at 64 KB and 51/51 at 1 MB.

The check found one design bug before any live use: every result rebound
`last-result`, so paging a truncated value replaced it with the page. A
truncated value is now bound to `full-result`, which paging never changes.

## 4. Assisted surface (opt-in; absent = the unchanged control)

- Several forms per call; the controller reads them with the bounded EDN
  reader. Unreadable code or a reader macro returns the fix before any worker
  is touched.
- A `def` shows its var; every value is bound to `last-result`.
- Helpers loaded on every new worker: `parse-long`, `context-lines` and `page`.
- Error hints for denied functions, unavailable classes and undefined names.
- Bounded results: a value over about 60 KB returns a preview and a truncation
  note, the worker keeps running, and the full value is in `full-result`.

## 5. Failure handling and records

- A worker that stops for any reason other than an expression error is
  retired. The model is told its definitions are gone, and the next call
  starts a fresh worker with the same helpers and context. Final cleanup still
  closes retired workers, and an unconfirmed cleanup still fails the task.
  Proven end to end with real containers (the contract's recovery check: an
  oversized result, a fresh worker, a lost definition reported, and all 8
  events recorded).
- The external task writes events and a result even if the session fails
  after starting. Closing a stopped worker no longer throws.
- The ledger records only what each request appends; full request bodies
  remain in the hashed `stdout.jsonl` trace. Scoring stays independent
  (`benchmark/official.py`).

## 6. Ablation on the 32K development suite (cases 1–10)

Four frozen configurations, each with its own plan and paired run:
`control` (absent settings), `assisted-64k`, `assisted-1m` and `bounded-64k`.
These are development evidence for choosing a configuration. The chosen one
is then frozen again and evaluated separately on a fresh suite.

### Progress (2026-10-28)

- Control, attempt 1 (plan `6ae7e225…`, commit `79a3bd9`): stopped after its
  first arm, with no scores. Aljure started a request 3.2 s before the 120 s
  deadline, the deadline cut it off while connecting, and the unknown outcome
  stopped the pilot by rule. In that arm the 64 KB output limit stopped the
  worker three times; retirement replaced it each time, at 6.5–11 s per cold
  start. The evidence is kept unchanged (`sci-ablation-control`).
- Fix (`40a24bd`, shared gateway, both harnesses): a 10 s dispatch floor
  (requests refused before dispatch are released at zero cost, not unknown)
  and a 60 s in-flight grace (a sent request finishes so its cost is known;
  the task still ends at its deadline).
- Control, attempt 2 (plan `50911e6b…`, commit `40a24bd`): running. An Aljure
  timeout no longer stops the pilot. Aljure has failed or timed out on cases
  1–4 and 6 and scored 0.327 on case 5, while Prime scored 0.84–0.94 (with an
  error on case 5).
- Next, in this order: `bounded-64k`, `assisted-64k`, `assisted-1m`.

Results: pending.
