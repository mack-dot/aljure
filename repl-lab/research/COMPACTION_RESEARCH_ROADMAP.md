# Compaction research roadmap

Prioritized milestones, each with its acceptance criteria. Live milestones need
a frozen plan and explicit approval. Related documents:
- `COMPUTATIONAL_COMPACTION_HYPOTHESIS.md`;
- `ARTIFACT_DATAFLOW_AUDIT.md`;
- `ARTIFACT_PROTOCOL_DESIGN.md`;
- `ARTIFACT_SECURITY_CONTRACT.md`;
- `RECURSIVE_COMPACTION_ABLATION.md`.

| # | Milestone | Kind | Acceptance criteria |
| --- | --- | --- | --- |
| 1 | **Paged answer delivery (B) verified** | offline | Unit tests (pages, length and hash check, cap, non-string); the real-worker contract check delivers an answer of 3× the bound exactly, with one worker (no restart); isolation proofs unchanged (supervisor untouched); full suites pass |
| 2 | Fault injection for B (O2) | offline | A worker killed mid-page, a corrupted page, a length mismatch and a value over the cap each fail explicitly, write no answer, and retire the worker |
| 3 | Offline delivery benchmark (O1) | offline | A table of delivery time, pages and success, from 10K to 8M characters (ASCII and multi-byte); A fails above the bound and B delivers exactly |
| 4 | L1 (A1b): B on the 32K development suite | live, about $2 | No delivery failure; delivery-free cases within run-to-run variance of A1; worker restarts from output size equal to 0 |
| 5 | Worker prewarm and restart cost | offline, then live | Cold start removed from the first `repl_eval` (start during the first model call); restarts measured. A restart cost 6–11 s in A1 |
| 6 | Handles (C) prototype | offline | Only if milestone 4 still shows worker loss or a sharing need: store, inspect, page, load and `done artifact:` with the security tests in the contract |
| 7 | Recursion study (L3) | design, then live | Only with a decomposable task family where children are used; pre-registered comparison against single-agent handles |
| 8 | Semantic compaction (Q-LEARNING) | offline fixes, then live | `EXECUTABLE_LEARNING_EXPERIMENT.md` §3 defects fixed; arms A–D with break-even analysis |

**Order:** 1 → 2 → 3 → 4 → 5. Then 6, 7 and 8 only if their entry conditions
are met.

**Status (2026-10-28):**
- 1 done (`274e225`, `a2504ac`).
- 3 done: O1 delivers exactly from 10K to 8M characters, multi-byte included.
- 5 done offline (`0c4c2d5`; `HARNESS_LATENCY.md`).
- 2 is open.
- 4 is not run. The counterfactual replay of A1 already shows the delivery
  effect without a model call (`SCI_EXECUTION_CONTRACT.md` §7). The next live
  run should include 5 and the reader syntax (`4cf04c0`), so it measures the
  current surface.
