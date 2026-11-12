# Q-SUBSTRATE Phase 0 and 1: repository reconciliation and ranked root causes

Read-only audit on 2026-11-03 at HEAD `a28332e`, branch
`codex/executable-learning-recovery-20261102`. Code claims were read from the
files named; run claims come from the result records named. Spot-checked
against `git branch -r --contains`, the worktree list and the cited lines.
Nothing here changes a historical result. Brief: `Q_SUBSTRATE_BRIEF.md`.

## Part 0. Repository state

| Checkpoint | Subject | On a remote branch? |
| --- | --- | --- |
| `213cf96` | Matched language backends and isolated Prime benchmark foundation | origin/main, sonnet-pair-v7, thesis-v1 |
| `a965bd9` | Commands as provider-native tool calls | sonnet-pair-v7, thesis-v1 |
| `79a3bd9` | Assisted SCI surface, bounded results, proven bounds | sonnet-pair-v7, thesis-v1 |
| `0c4c2d5` | One ledger process, AOT worker, prewarm | thesis-v1 only |
| `3fec260` | Programmatic tool bridge | thesis-v1 only |
| `82d82e5` | Reuse interface A/B result: NO-GO | **local only** |
| `f95ac9c`, `eabf466`, `a28332e` | Causal protocol, goal record, brief | **local only** |

The current branch has no upstream. Everything from `82d82e5` onward exists
only on this machine. The tree is clean. Eighteen worktrees exist; the
`aljure-opus-followup` and `aljure-sonnet-pair-v2..v5` checkouts named in the
research docs no longer exist on disk, only their branches. The reuse-interface
and causal evidence under `research/evidence/` is committed; raw runs stay
under `var/` and are not pushed anywhere.

## Part 1. Substrate parity matrix, grounded in code

`ExecutionBackend` (`src/repl_lab/execution.clj:5-11`) has four methods:
`open!`, `evaluate!`, `run-program!`, `close!`. The Clojure record delegates
all four to `isolation.clj`. The Python record shares `evaluate!` and `close!`,
adds `require-tested! :python` on open, and throws on `run-program!`
(`execution.clj:42`, the only explicit unsupported throw).

| Capability | Clojure/SCI | Python | Parity |
| --- | --- | --- | --- |
| Container limits | 256 MB, 1 CPU, 32 pids, no network, read-only, 8 MB tmpfs (`scripts/isolation.py:18-20,158-163`) | Same supervisor (`scripts/python_isolation.py:69`) | equal |
| Per-expression timeout, startup bound, session lifetime | 10 s / 30 s / 120 s (`isolation.py:19,304,242-249`) | Same | equal |
| Output bound | 64 KiB or 1 MiB with its own proof; raw overflow kills the worker (`isolation.clj:15-24,98`) | 64 KiB hard-coded; overflow is a recoverable error (`worker/src/repl_lab/python_worker.py:17,134-135`) | reversed semantics |
| Printed output | Denied (`worker/src/repl_lab/worker.clj:11`) | Captured to 8 KiB then dropped: the controller returns only the value (`isolation.clj:136`) | Python prints are lost |
| Source validation | Bounded EDN reader, no read-eval, nesting ≤ 96 (`model_protocol.clj:242-258`) | `ast.parse` then exec; trailing expression is the value (`python_worker.py:111-117`) | different, both bounded |
| Denied surface | eval, require, slurp, future, print… (`worker.clj:6-11`) | open/input/exit removed; 13 importable modules; the file says "not a sandbox" (`python_worker.py:3-4,15-23`) | container is the real boundary for Python |
| Persistence | SCI context, keyword bindings (`worker.clj:24-28`) | `scope` dict (`python_worker.py:112,123`) | equal |
| Isolation proof | Gate v2: supervisor hash, startup, boundary, output bytes, 9 negatives (`isolation.clj:45-56`) | 9 negatives, session reset, image match only (`execution.clj:13-27`) | Python proof weaker |
| Assisted surface | `parse-long`, `page`, `last-result`, `full-result`, previews, error hints, `context-lines` (`resources/sci-prelude.edn`, `model_protocol.clj:189-192,292-310`, `external_task.clj:83`) | none | Clojure only |
| Worker retire/prewarm | shared (`runtime.clj:48-57,97-109`) | same code, never triggered by overflow; benchmark passes no prewarm | nominal |
| Context access | `context_query`, `context_metadata`, `external-context` bound by Clojure source (`external_task.clj:75-86`) | query broker only | Clojure only |
| `done` with source, paged delivery | `runtime.clj:90,121-142` | summary only | Clojure only |
| Native tool envelope | Clojure descriptions hard-coded (`model_protocol.clj:117-139,200-208`); external tasks force it (`external_task.clj:289`) | no Python descriptions; no config selects Python | **Clojure only** |
| JSON text envelope | `resources/model-common.txt` + `model-clojure.txt` | `model-python.txt` | equal (legacy path) |
| `program_run`, tool bridge | `worker/src/repl_lab/bridge.clj:29-57`, `programs.clj:205-225` | throws; worker rejects `tools` (`python_worker.py:106-107`) | **Clojure only** |
| Direct `tool/call` | never touches the worker (`programs.clj:227-234`) | would work, untested | nominal |
| Artifact parse/render | EDN in process (`artifact.clj:12-20`) | fresh syntax container per parse/render (`python_source.clj:7-14`) | Python pays a container per verify |
| `artifact/subtree`, `artifact/patch`, stale checks | `artifact.clj:116-125,180` | same, plus `ast.unparse` round trip (`python_worker.py:93-101`) | equal |
| `artifact_call`, validate | `executable.clj:6-57` | same, per-language call strings | equal |
| Preload, applicability, compose, program artifacts | supported | refused (`executable.clj:111`, `artifact.clj:33-37,133-136`) | Clojure only |
| Acquisition | hard-codes the Clojure backend (`acquisition.clj:880,894`) | none | Clojure only |
| Language benchmark driver | 2 families, scripted provider, both languages (`language_benchmark.clj:10-16,93-138`) | same | fixture only |

**Three gaps that block a matched live experiment.** The live path
(`external_task.clj`, `benchmark/paired.py`) is Clojure end to end: native
tool text, context binding, `done` source, assisted helpers and the proof
check. The model would see different interfaces per language: Clojure has
paging, previews and hints; Python has none, drops prints, and has a fixed
64 KiB bound with the opposite overflow behavior. Assurance and cost differ:
the Python proof skips boundary and supervisor checks, and every Python
artifact verify starts a container.

## Part 2. Ranked root causes of past underperformance against Prime

Ranked by measured effect on the comparisons that mattered. "Live" means a
later live run showed the failure gone; "offline" means tests or replay only.

1. **Final-answer delivery.** 64% of the Opus gap (−0.095 of −0.148;
   `OPUS_CAPABILITY_GAP_ANALYSIS.md`). Text-only replies in 9/21 Sonnet and
   4/21 Opus arms, almost all containing the answer line. F1 (transport retry)
   never fired live; F2 (terminal text) was rejected live after it cost a task
   (`CONTRACT_ABLATION_RESULTS.md`). **Unfixed.** Harness, not SCI.
2. **64 KiB output and paged delivery.** Raw overflow killed workers (ten32,
   control-2) and lost 4/10 correct A1 answers at the `done` bound. Fixed by
   `79a3bd9` (bounded surface) and `274e225` (paged delivery); **live** in A1c
   (10/10 completed, 0.845 vs 0.862). Harness design around SCI, not the
   language.
3. **Model-facing EDN commands.** Every arm of V3, V6, V7 failed on markup or
   escaping. Fixed by `a965bd9`; **live**, zero rejections since. Harness.
4. **Process and worker startup.** Cold workers 5.9–15 s, ledger 1.6–3.8 s
   per step, restarts 6–11 s each; 345 s between calls over 8 A1 arms against
   Prime's 51 s (`HARNESS_LATENCY.md`). Fixed by `1a570af`, `87d5fda`,
   `0c4c2d5` (1.15 s cold, 0.18 s ledger offline); **live only through A1c**,
   one run. Still open: two `docker info` calls per start, whole-ledger
   serialization per write, 2–10 s cleanup. Harness and JVM substrate.
5. **Sandbox-rule mismatch and `parse-long`.** Sonnet ten32: every arm failed
   on `Long/parseLong`, multi-form calls and overflow. Fixed by `5bc996d` and
   `79a3bd9`; **live** in A1 (no arm-stopping sandbox errors). A regression in
   the `artifact_call` worker was fixed in `f1c09a5`, offline only. SCI
   surface, now fixed; `Long`, `Math`, `Character` remain unavailable.
6. **Cleanup and infrastructure.** A1 cases 8–10 quarantined by load; killpg
   EPERM; deadline cut-off; Docker VM restart. All fixed and **live**
   (`274e225`, `1b99ef7`, `40a24bd`, Docker gate in V7) except the isolation
   preflight `docker info` timeout, which fails closed and is unfixed.
7. **Counting and reasoning.** Mean absolute count error 4.4 vs Prime's 2.9
   over 15 answered cases; bias correlated with Prime's (r = 0.865). The
   tally intervention is designed, not run. Model, not substrate.
8. **String display and double-escaped regex.** Fixed by `87d5fda`, `4cf04c0`;
   accuracy effect untested. SCI surface.
9. **Answer typing cost.** 4,506 output tokens typing pairs; `done source`
   cut to 1,549 (`1a570af`), **live**. Harness.
10. **`subs` range error.** 4/59 redundant A1 calls and 4/5 interface-arm
    tasks in reuse run 3. Hint added in `f95ac9c`, offline only. SCI surface.

**Never established as causes:** SCI language expressiveness or an incorrect
model program. The Opus gap analysis found no task lost to SCI capability, an
incorrect program or a misread. No comparison has yet isolated the substrate;
every Aljure arm so far carried the harness differences above.

## Part 3. What Phase 2 must build before a matched Q-SUBSTRATE run

In order of necessity, smallest first:

1. A `python_eval` native tool (or a language-neutral `repl_eval` whose
   description and prelude come from the configured backend), selected by
   `execution-language`, with Python text for the task message.
2. Python context binding (`external_context`, `context_lines`) and a
   `done` source path, so answers can be computed, not typed, in both arms.
3. Captured print output returned as part of the Python value, and a bounded
   preview with paging equivalent to `full-result`; the same overflow
   semantics in both arms (recoverable error, worker kept).
4. A Python isolation proof with the same gate checks as SCI gate v2.
5. Only if Experiment C is in scope: a Python tool bridge with the same
   `operate!` authorization path.

Items 1–3 are required for Experiment A. Item 4 is required before any
isolation-equivalence claim. The language benchmark's two fixture families
must grow to the brief's ten task kinds with independent scoring.
