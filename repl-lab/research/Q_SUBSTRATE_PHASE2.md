# Q-SUBSTRATE Phase 2: the matched Python surface

Date: 2026-11-03. Commits `18864e4` (items 1-3) and `0f067ce` (item 4) on
`codex/executable-learning-recovery-20261102`. No model inference was run.
Brief: `research/Q_SUBSTRATE_BRIEF.md`. Audit and build list:
`research/Q_SUBSTRATE_PHASE0_AUDIT.md` Part 3.

## What exists now

A plan with `execution_language: "python"` runs the Aljure arm on the Python
worker through the same controller, native tools, prompt structure, context
binding, previews, paging and answer delivery as the assisted bounded Clojure
surface. The Clojure surface is byte-for-byte unchanged: its tool definitions,
instructions and proofs did not move (`command_envelope_test.clj`
`python-surface-shares-the-tool-envelope-and-changes-no-clojure-text`, and the
regenerated SCI contract, artifact-path and acquisition proofs, all TESTED).

| Capability | Clojure/SCI | Python (new) | Where |
| --- | --- | --- | --- |
| Native tools | `repl_eval`, `done`, `agent_call`, `context_*` | same names and schemas; three descriptions in Python terms | `model_protocol.clj` `python-descriptions` |
| Instructions | `external-tools-assisted.txt` | `external-tools-python.txt`: the Clojure text with four language terms replaced, nothing else (tested) | `external_task.clj` `instructions` |
| Advertised rules | `resources/sci-contract.json` (7 bounded rules) | `resources/python-contract.json` (6 rules) | `sci-rules` |
| Context binding | `external-context`, `context-lines` | `external_context`, `context_lines` split on `\r?\n` with trailing empties dropped, as `split-lines` does | `initialize-python-context!` |
| Helpers | `sci-prelude.edn` | `python-prelude.py`: `page`, `last_result`, `full_result` | loaded on every new worker |
| Result display | `aljure-show` in the worker | the worker's `show`: printed output, then the final expression's `repr`; `None` and statements show `(no output)` | `python_worker.py` display request |
| Previews | over about 60 KB: preview, `full-result` | same limit, `full_result`; the preview shrinks until its JSON fits | same |
| Errors | hints for denied symbols, classes, ranges | hints for `NameError`, limited imports, the print bound | `python-error-hints` |
| `done` with source | `aljure-answer`, pages of bound/8 UTF-16 units, Clojure `hash` | `aljure_answer`, pages of bound/16 code points (JSON escapes), 31-polynomial checksum over code points | `runtime.clj` done/eval |
| Overflow | bounded: preview, worker kept | preview, worker kept; a print flood over 1 MiB is a recoverable error with a hint | `check-recovery` |
| Isolation gate | gate v2: supervisor hash, same-worker readiness, boundary, 9 negatives | gate v2: supervisor and gate hashes, same-worker readiness, boundary, 9 negatives + session reset | `python_isolation.py`, `validate-python-proof!` |
| Preflight | SCI proof + contract proof | plus `python_readiness`: gate v2 proof, frozen Python image, `python-contract-proof.json` fresh for six sources | `paired.py` |

Prompt overhead is matched: tool JSON 2,976 vs 2,943 characters, instructions
1,947 vs 1,914 (Clojure vs Python), measured through `tool-definitions` and
`instructions` on 2026-11-03.

## What is deliberately not matched

- The Python surface exists only assisted and bounded. The raw Clojure surface
  (the historical control, where an oversized result stops the worker) has no
  Python twin; `sci-settings` and `execution_language` refuse other settings.
- Clojure-only contract levels stay Clojure-only and are refused with Python:
  structured labels, uncertainty audit, targeted review, artifacts, acquisition,
  programs, the inspect-v1 skill interface. The audit's item 5 (a Python tool
  bridge) is not built; Experiment C is out of scope until it is.
- The Python worker's own 64 KiB reply bound fires before the supervisor's, so
  a Python worker is never stopped by output; the gate's `over-bound` check
  records that semantics instead of pretending the SCI one.
- Isolation mechanisms differ (SCI denies symbols; Python removes builtins and
  limits imports, and the container is the boundary). Both gates prove the same
  objectives: no read, write, process, network, evaluator or host-environment
  access; bounded loops, memory and output.

## Evidence

| Check | Result |
| --- | --- |
| `test_python/test_python_worker.py` (host interpreter) | 8 tests |
| `test_python/test_execution_language.py` | 4 tests |
| `test_python/test_python_isolation.py` (fixture supervisors) | 4 tests |
| Clojure tests added | 6 in `command_envelope_test.clj`, 1 in `language_benchmark_test.clj` |
| Full suites | Clojure 210 + 5 tests, 3,162 + 50 assertions; Python 261 tests |
| `var/python-contract-proof.json` | TESTED, 34 of 34 probes, paged delivery (ASCII and astral), overflow recovery, in the real worker |
| `var/python-isolation-proof.json` | TESTED, gate v2, boundary both sides, 9 negatives + reset; startup 456-1,107 ms |
| SCI proofs regenerated after the controller change | contract 76, artifact-path 6, acquisition 7, all TESTED |

Worker image: `sha256:d50e1d20c656d17166cecfdf79e8dba591ff140d432c09be8bd93910e61a8e2d`
(built from `python:3.12.10-slim-bookworm`; the earlier pinned image had
vanished from the local daemon, as the SCI images did before).

## Cross-language checksum vectors

The worker returns `[3, 96354]` for `'abc'` and `[2, 131519]` for `'a😀'`; the
controller's independent implementation returns the same, so a paged Python
answer is checked end to end without sharing code.
