# Cumulative executable knowledge: GO/NO-GO (2026-10-29)

**Branch:** `claude/thesis-v1`. The merge is at `b8a1ca3`, and this report is committed on top of it.

**Scope:**
- Offline only, with no model calls.
- The frozen answer-format experiment ran independently and was not modified.
- Its concurrent gate windows are recorded in `evidence/thesis-gates/gates-window.txt`
  and `evidence/step0/window.txt`.

| Item | Status | Evidence |
| --- | --- | --- |
| Thesis review and historical audit integrated | Done | `RESEARCH_THESIS_REVIEW.md`, `HISTORICAL_PERFORMANCE_AUDIT.md` |
| **Step 0:** generated rules on unseen data | **GO** | `STEP0_RULE_TRANSFER.md`. Override control 8/8, applicability 8/8. Best retained rule set: 48–60% of never-seen items at 98.2–99.7% precision. Entity is never decided |
| Stable executable identity | Done | `artifact/code-hash` (canonical forms only). Unchanged across envelopes and cold-boot restore |
| Promotion-accounting defects | Fixed | First-live gain 14,590 inflated, 332 healthy. A zero-gain candidate is no longer approved. Failed episodes name no executed artifact |
| Discovery (hash-pinned library over the existing registry) | Done | `libraries/<sha256>.edn`; only approved entries; fails closed on mismatch |
| Applicability checks with recorded refusals | Done, **proven in the real worker** | `artifact-path-proof.json`: preload when applicable, refuse when inapplicable |
| Safe structural composition | Done | `artifact/compose` and `patch` on code data; validated in a fresh worker before promotion |
| Task-path preload (`aljure_contract.artifacts`, off by default) | Done, proven | Invocation counted by code hash in the real worker. Off-path byte-identity is verified |
| Activation metric (eligible reuse, refusals, direct answers) | Done | `artifact-reuse-summary` (`ARTIFACT_TASK_PATH_V1.md` §6) |
| Offline suites | Pass | Clojure 166 tests, 2,717 assertions, 0 failures. Python 182 passed |
| Isolation gates | Pass | SCI isolation 9/9 (supervisor hash current), artifacts SCI proof 6/6 |
| A/C/E pilot frozen | **NO-GO** | Blocked; see below |

## The single remaining blocker

**There is no acquisition step between tasks.**
- The benchmark path runs with learning off.
- The model has no way to propose a function it wrote, with its applicability
  predicate, for validation.
- The runner pins one library version for a whole plan, so a newly promoted
  artifact can never reach the next task.

The building blocks all exist and are proven:
- `executable/validate!`;
- `promotion-evidence`;
- `skills/add-entry!`;
- the hash-pinned library;
- the preload switch.

The missing link is two small pieces:
1. **A model-facing `propose` step** after a task. The model submits a function and
   a predicate from its own session. The controller validates it on a
   controller-only development panel, with no inference, and promotes or rejects it.
2. **A trajectory mode in the paired runner** that passes each new library pin to
   the next task in sequence order, with the preregistered cold restart after task 10.

Arm C, the exact cache, is a small variant of the same trajectory mode: an
item-text-hash memo.

## What is ready for the pilot once the blocker is built

- **Compatible tasks (F1):** 8 unexposed `trec_coarse` validation windows (shards
  3 and 6). Step 0 has already measured them offline, and no model has seen them.
- **Incompatible tasks (F2), the negative-transfer test:** 4 `spam` validation
  windows. Same record format, different taxonomy: a retained `trec_coarse`
  classifier must be refused by applicability, and any refusal is recorded.
- **Arms and criteria:** as in `RESEARCH_THESIS_REVIEW.md` §5.
  - A stateless, C exact cache, E validated artifacts with structural improvement.
  - 20 tasks per trajectory (16 F1, 4 F2), 3 seeded orderings, Sonnet.
  - About $10–15 likely, cap $40.
  - Falsification thresholds as written there, with activation split into
    eligible reuse, correct refusal and direct answer.
- **Exact plan hashes cannot exist yet.** They are frozen only after the trajectory
  mode and the propose step are built, tested, and proven in the real worker.

## Addendum (2026-10-29): the blocker is built, offline only

- The propose step and the trajectory mode exist behind off-by-default switches. See
  `THESIS_PILOT_PROTOCOL.md` (preregistration draft, not frozen).
- Offline proofs pass with scripted fixtures. The real-worker proofs (Docker) are still to
  be run; the protocol, §10, names the exact commands.
- The pilot stays **NO-GO** until those proofs pass and the operator approves an exact plan hash.

## Addendum 2 (2026-10-29): layout change and real-worker proofs

The text above is kept as written. These operator decisions change it
(`THESIS_PILOT_PROTOCOL.md`, "Operator decisions"):
- **F1 has 7 windows, not 8.** The (524288,12) window is dropped, because it held almost the
  whole `trec_coarse` pool. F2 is 2 `spam` windows (4 tasks).
- **18 tasks per trajectory** (14 F1, 4 F2). F2 is at positions 8, 11, 14 and 17, and the
  cold restart is after task 9.
- **A new-record endpoint** decides falsification criterion 2. It scores each arm-E pin in
  force on records that neither the panel nor any earlier task held, offline, in a fresh
  isolated worker.
- **Budget as built:** $5 per task; a $40 cap with a $1 check margin, so the hard ceiling is
  $45. Arm E promotes classifiers only.

The real-worker proofs now pass with zero model calls (protocol §10). The pilot stays
**NO-GO** until the operator approves an exact plan hash.
