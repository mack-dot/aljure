# SCI execution contract

The model-facing contract for Aljure's Clojure SCI worker: what is advertised,
how it is verified against the real worker, what happens on failure, and what
remains unverified. Formerly `SCI_SURFACE_AND_OUTPUT_BOUNDS.md`.

Source of truth: `resources/sci-contract.json` (rules and probes) and
`resources/sci-prelude.edn` (helpers). The assisted `repl_eval` description is
generated from those rules, so every advertised behaviour is a contract rule.

## 1. Two surfaces

| | Raw (benchmark control) | Assisted | Assisted + bounded |
| --- | --- | --- | --- |
| Config `aljure_sci` | absent | `surface: assisted, results: raw` | `surface: assisted, results: bounded` |
| Forms per call | exactly one | one or more (wrapped in `do`) | one or more |
| Reader syntax | EDN only | Clojure (`#"..."`, `#(...)`, `'x`, `@x`) | same |
| `def` result | error ("not EDN data") | shows the var name | shows the var name |
| Helpers | none | `parse-long`, `context-lines`, `page`, `last-result` | same, plus `full-result` |
| Unreadable source | worker error | explained before the worker is touched | same |
| Error hints | none | denied function, unavailable class, undefined name | same |
| Result over the output bound | worker stops; definitions lost | worker stops; definitions lost | preview plus truncation note; worker keeps running |

The output bound is 64 KiB per expression by default. 1 MiB is available only by
explicit configuration (`worker_output_bytes`), with its own isolation proof.

## 2. Advertised rules (assisted surface)

Generated from `resources/sci-contract.json`. Each rule is checked by probes in
section 4.

1. Send one or more forms. They run in order, and the last value is the result.
2. A `def` shows its var name, so definitions need no trailing `nil`. The value
   of every result is also bound to `last-result`.
3. Helpers: `(parse-long s)` returns an integer or `nil`; `context-lines` is the
   context as a vector of lines; `(page v offset n)` returns `n` characters of
   `v`'s printed text, starting at `offset`.
4. *(Bounded only.)* A result larger than about 60 KB comes back as a preview
   with a truncation note, and the worker keeps running. Its full value is bound
   to `full-result`, which paging does not change; read the rest with
   `(page full-result offset n)`.
5. *(Raw results only.)* A result over the worker's output bound stops the
   worker and loses its definitions.
6. Clojure reader syntax works: `#"\d+"` (no double escaping), `#(...)`,
   `'x`, `@x` and `#'v`. `#=` and tagged literals such as `#inst` are refused.
   The controller reads the source with Clojure's reader in a safe mode (no
   read-eval, record construction, tagged or conditional reads; nesting
   bounded at 96) and sends plain data to the unchanged worker. A regex
   literal becomes `(re-pattern ...)`. The raw surface keeps EDN.
7. `clojure.string` works, as do String methods such as `(.indexOf s "x")` and
   `Integer/parseInt`. `Long`, `Math` and `Character` do not.
8. `read-string`, `eval`, `slurp`, `spit` and printing (`println`, `pr-str`) are
   denied; build text with `str` and `clojure.string`.

`done` takes either `summary` (text) or `source` (forms evaluated in the
session's worker, whose last value must be a string). An answer built in SCI is
never truncated. A failed answer expression is an ordinary tool error, and the
session continues.

## 3. Failure semantics

- **Expression error** (`Worker rejected expression: …`): the worker stays
  alive. The model gets the message plus a hint (assisted).
- **Worker stopped** (output bound, deadline, closed stream): the worker is
  retired. The model is told its definitions are gone, and the next call starts
  a fresh worker with the same helpers and context. Final cleanup still closes
  retired workers. An unconfirmed cleanup (supervisor exit 3) still fails the
  task.
- **Startup**: the supervisor sends its own readiness probe, in the worker's
  wire format, under a separate 30 s bound. No expression's 10 s clock starts
  before the worker is ready.
- **Records**: events and a result are written even if the session fails after
  starting.

## 4. Verification

`python3 scripts/clj.py -m repl-lab.sci-contract` runs every probe through the
controller's own source, result and error paths against the real isolated
worker, in raw and bounded modes. It then runs an end-to-end recovery check
through the real broker, ledger and containers: an oversized result, a fresh
worker, a lost definition reported, and every event recorded. The proof
(`var/sci-contract-proof*.json`) records the contract, prelude and protocol
digests, the image and the bound. Paired preflight refuses the assisted surface
without a current proof.

| Check | 64 KiB | 1 MiB |
| --- | --- | --- |
| SCI contract probes, recovery and answer delivery | 69/69 | 69/69 |
| Isolation negative controls (loop, allocation, oversized result, read, write, process, network, evaluator, reader eval) | 9/9 | 9/9 |
| Exact output boundary (reply equal to the bound passes; one byte more stops the worker) | pass | pass |
| Oversized control | 1,000,000 bytes, refused | 2,097,152 bytes, refused |

The verifier found one design defect before any live use: every result rebound
`last-result`, so paging a truncated value replaced it with the page. Truncated
values now go to `full-result`.

## 5. Output bounds compared with Prime

Prime's `python_repl` truncates each output stream at 65,536 **characters**
(`DEFAULT_MAX_OUTPUT_CHARS`, `P:crates/pa-core/src/kernel/shared.rs:14`),
keeping the head and tail with a marker, and its kernel keeps running. Prime's
separate 4 MiB limit (`benchmark/prime/container.py`) caps the whole native
task stream, not a tool call. The per-call sizes are similar. The material
difference is graceful truncation against worker death, which the bounded
surface removes. See `PRIME_PARITY_MATRIX.md` rows 2 and 4c.

## 6. Unverified

- **Model-generated execution success with the assisted surface.** One live
  run (A1, one context) used it, before paging, the speed work and reader
  syntax. Measure first-try expression success, errors per call, worker
  restarts and calls to an answer again on the next run.
- Whether the model uses reader syntax when told it works, and whether that
  removes the escaping errors seen in A1.
- Whether a model reads the truncation note and pages (as opposed to
  re-printing).
- A Python counterpart of this contract (needed for Q-SUBSTRATE).
- SCI behaviour under memory pressure from large `full-result` values, close to
  the 160 MiB JVM heap.

## 7. Ablation progress (32K development suite)

- Control, attempt 1 (`6ae7e225…`): stopped after one arm on a deadline
  cut-off (unknown outcome). Kept unchanged.
- Fix `40a24bd`: a 10 s dispatch floor and a 60 s in-flight grace in the shared
  gateway.
- Control, attempt 2 (`50911e6b…`): complete. Aljure (raw surface) 0.176 mean,
  3/10 completed; Prime 0.680 mean, 8/10 completed (2 killed by the adapter's
  stream bound, since fixed). One context; development evidence only.
- `bounded-64k` (`62b3fb23…`): frozen at `40a24bd`, never run.
- **A1** (`d5038fe2…`, commit `13490b4`): the assisted and bounded surface
  against Prime with the stream fix. Accounting complete; Prime completed 10/10
  (no adapter kills). Aljure mean 0.174 and Prime 0.852 (1 win, 9 losses).
  Attribution per case:

  | Cause | Cases | Aljure | Prime |
  | --- | --- | --- | --- |
  | Final answer larger than one 64 KiB reply (gold 70K–157K chars): the model computed it, but `done source` returned it in one reply, the worker stopped, and the retries ran out | 1, 2, 3, 7 | 0, 0, 0 ("ab"), 0 | 0.71–0.98 |
  | Fair contests (answers under 64 KiB, or delivered) | 4, 5, 6 | 0.889, 0.714, 0.139 (under-selected: 10K of 134K) | 0.803, 0.930, 0.763 |
  | Worker cleanup unconfirmed at load average 21 (the container was in fact gone); quarantine failed the next arms with no model call | 8, 9, 10 | 0, 0, 0 | 0.75–0.86 |

  On the fair contests, the assisted surface worked: there were no sandbox-rule
  errors that stopped an arm, and one reader macro was explained before reaching
  the worker. The result was one win and two losses. Infrastructure failures
  (cases 8–10) exceed the protocol's 10% line, so A1 is development evidence
  only.
- **Fixes after A1** (offline; not yet live):
  - paged answer delivery, with `[length hash]`, pages of at most bound/8,
    host length and hash checks, and an `answer-delivered` event;
  - cleanup confirmation retried under load (10 s commands and up to 3 absence
    checks, still requiring a successful daemon query);
  - the controller waits up to 60 s for the supervisor.
- **Fixes after the A1 analysis** (offline; see `HARNESS_LATENCY.md`):
  - commit `0c4c2d5`: one long-lived ledger process with a revision-checked
    cache; an AOT-compiled worker image with a CDS archive (`58550c92…`,
    cold start 5.7 s → 1.15 s); the root worker prewarmed during the first
    model call. Isolation 9/9 with boundaries at both bounds;
  - commit `4cf04c0`: Clojure reader syntax on the assisted surface.
- **Counterfactual replay of A1** (`repl-lab.replay`, no model calls): the
  model's recorded commands, re-run through today's broker and a real worker.
  The fair cases reproduce exactly (4: 0.889, 5: 0.714, 6: 0.139). With paged
  delivery, cases 1, 2, 3, 7 and 8 would score 0.814, 0.802, 0.875, 0.649 and
  0.718 against Prime's 0.984, 0.971, 0.943, 0.711 and 0.753. Mean over cases
  1–8: Aljure about 0.70, Prime about 0.86. This replays the same model code;
  it does not predict new model behaviour.
