# Q-SUBSTRATE Phase 3: SCI ergonomics, measured on recorded model programs

Date: 2026-11-03. No model inference. Brief: `research/Q_SUBSTRATE_BRIEF.md`
Phase 3 ("measure before and after changes").

## The measurement

`repl-lab.surface-replay` re-runs every model-written SCI program that a
recorded Aljure arm under `var/` kept together with its public context: 196
arms, 272 `repl_eval`/`done` calls from the ten-case live runs, the SCI
ablations, the learning and reuse pilots. Each call runs in its recorded order
through today's broker on a fresh real worker over the arm's own context, and
its recorded outcome is compared with today's. It measures what the current
surface does with yesterday's programs; it predicts no new model behaviour and
cannot see whether a hint would have helped the model.

Evidence: `research/evidence/q-substrate-phase3-20261103/` (both replay
records without sources, and the contract proof after the change).

| | Recorded (historical surfaces) | Current surface before Phase 3 | After Phase 3 |
| --- | --- | --- | --- |
| Calls | 272 | 272 | 272 |
| Errors | 96 | 56 | 35 |
| Fixed relative to the record | | 41 | 62 |
| Regressions | | 1 | 1 |

The one regression is a reuse-interface arm whose program called a preloaded
library function; the replay carries no library. Not a surface regression.

Errors by class under the current surface, before and after:

| Class | Before | After | Treatment |
| --- | --- | --- | --- |
| `subs` range past the string's end | 21 | 0 | prelude `subs` bounded like a slice; `clojure.core/subs` still reachable |
| context tool called from code (`context_query`, `context_query_dummy`, ...) | 15 | 15 | hint: tools are not callable; `external-context` and `context-lines` are bound |
| character where a string is needed | 4 | 3 (+1 now reported as `count not supported`) | hint naming `context-lines` and `(str c)` |
| `Long/parseLong` | 4 | 4 | existing hint (`parse-long`) |
| `println`/`pr-str` "is not allowed!" | 3 | 3 | the denied-function hint now matches this message form too |
| reader errors (unbalanced source) | 3 | 3 | existing "not readable" explanation |
| nil called as a function, `cond` arity, string as number | 4 | 5 | hint for the nil call; the others are program errors |
| `source` of a retained function | 1 | 1 | existing skill-interface hint |

The 41 errors that the current surface had already fixed before this phase
were the raw-surface classes: one form per request (8), reader failures of the
raw `done` splice (28 of 31), `parse-long` (4), and a lost definition after an
overflow restart (1).

## Changes (F1-F5), all surface-level

No new authority was added: no JVM interop, filesystem, network or evaluation.
`Math`, `Character` and `Long` stay unavailable; the corpus shows no `Math` or
`Character` call, and `Long/parseLong` has a hint.

- F1 `resources/sci-prelude.edn`: `subs` bounded to the string.
- F2-F5 `model_protocol.clj` error hints: character-cast, context tool from
  code, "is not allowed!", nil called as a function; the range hint now says
  `subs` is bounded and points `subvec`/`nth` at `count`.
- `resources/sci-contract.json`: the helpers rule states the bounded `subs`;
  eight probes prove the new behaviour and every new hint in the real worker.

Proofs after the change: SCI contract 92 of 92 (was 76), Python contract 34 of
34 regenerated (its digest covers `model_protocol.clj`); artifact-path and
acquisition proofs unaffected (their sources did not change). Tests: Clojure
212 + 5 (3,186 + 50 assertions), Python 261.

## Prompt cost

Tool JSON 2,976 → 3,054 characters and instructions 1,947 → 2,025 for the
Clojure surface (one rule sentence longer); the Python surface is unchanged.

## Still open from the brief's Phase 3 list

- Final-answer submission: unchanged. The historical F1/F2 results stand
  (`CONTRACT_ABLATION_RESULTS.md`); both Q-SUBSTRATE arms share the same
  delivery path, so it is not a substrate confounder.
- Batch execution of authorized tools exists for Clojure only (`program_run`);
  Experiment C needs the Python bridge first.
- Cold start: 1.15 s offline (`HARNESS_LATENCY.md`), two `docker info` calls per
  start remain.
