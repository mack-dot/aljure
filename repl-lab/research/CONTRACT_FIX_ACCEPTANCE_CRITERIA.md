# Contract fixes F1 and F2: acceptance criteria

**Status: written before any of the three plans ran.** This document fixes how
their results will be judged. It does not change the plans, their hashes, or
any historical score.

**Question:** did F1 and F2 fix Opus's two delivery failures without
compromising Aljure's execution contract?

| Plan | Aljure contract | plan_sha256 |
| --- | --- | --- |
| Control | original | `87d8c949a5dafe983c8965fd0d352ebafe8977210d27663a65c64013ff369eb7` |
| F1 | `truncated_turn_retries: 1` | `52f51590c44e60df2af1cb7e7284792a2d35b0a6f16f868cb11fbca062bb0773` |
| F2 | `terminal_text_answer: true` | `b1844732305d2b9236a89af7ddd7078667fad530b04777ccb326b12547ed6e5d` |

All three run Opus 5.5 with open limits on the 21 dev tasks, at clean commit
`41b53fa`, with native Prime unchanged (`ADAPTIVE_COMPUTE_ABLATION_PLAN.md`).

## The auditor

`scripts/contract_audit.py` reads the recorded traces only and makes no model calls:
- It classifies every provider response from the raw body the gateway recorded:
  tool call, text-only, truncated, multiple commands, incomplete turn, or bad blocks.
- It then checks Aljure's recorded handling of that response against the
  contract and the plan's switches.

It checks these rules in every Aljure arm:

| Check | Rule |
| --- | --- |
| `text-never-executed` | Only a response with exactly one tool call is executed. |
| `command-provenance` | The executed command is that tool call's input. |
| `handling` | Each response shape gets only its allowed handling. |
| `rejection` | Every rejection is marked unexecuted and names the reason that fits the shape. |
| `one-correction` | At most one format correction per task. |
| `correction-text` | The correction sent is the terminal instruction only under F2, in the root, after a text-only reply. Otherwise it is the original instruction. |
| `f1-retry` | Only a confirmed truncation is retried. The retry resends the identical request, stays within the allowance, and happens only when F1 is on. With F1 on, a truncation is never rejected. |
| `f2-terminal` | Accepted only with F2 on, in the root, in reply to the terminal instruction actually sent. The reply must pass an independent re-check of the strict `FINAL ANSWER:` rule, and its only effect is `done` with that answer. |
| `append-only` | Each request in a session extends that session's previous request. |
| `verbatim-history` | Every assistant turn in history is a provider response, byte for byte, thinking signatures included. |
| `answer-provenance` | The answer file holds the root's `done` result and nothing else. A failed root leaves no answer. |
| `accounting` | Agent results, gateway responses and complete receipts agree in number and cost. |
| `unknown-outcome` | A request with no recorded outcome is never resent. |

**How the auditor was validated (zero model calls):**
- **Unit tests** (`test_python/test_contract_audit.py`, 9 tests): each check is
  shown to fire on a trace with that one violation planted, and to pass the
  conformant shapes.
- **Fixture:** the scripted fixture arm with both fixes on is conformant
  (1 retry, 1 correction, 1 accepted `FINAL ANSWER`). Audited under the wrong
  switches, the same arm fails `f1-retry`, `f2-terminal` and `correction-text`.
- **Baseline:** every recorded native-tool run, 69 Aljure arms and 415 provider
  responses, has zero violations (`evidence/contract-audit/baseline.json`).
  - The responses: 400 tool calls, 14 text-only replies, 1 truncated turn.
  - Six earlier arms are unauditable. Under the old 12-call and 120 s limits
    they ended by deadline or error before the runtime exported its event log.

## Criteria

### A. Contract integrity (all must hold)

1. All 63 Aljure arms across the three plans are auditable and conformant. An
   unauditable arm fails this criterion until it is explained.
2. **Switch isolation:**
   - control: zero retries and zero accepted terminal answers;
   - F1: zero accepted terminal answers;
   - F2: zero retries.
3. The SCI isolation, SCI contract and Prime isolation gates and the image
   digests are the ones the plans pinned.

Any violation means the contract was compromised, whatever the scores.

### B. F1: truncated turns

- **Offline, already met:** the recorded truncated response shape is retried
  once with the identical request, and the arm completes. On the identical
  script, the original contract fails (`FINALIZATION_RECOVERY_VALIDATION.md`).
- **Live trigger is unlikely.** The observed rate is 1 truncation in 557
  responses. A plan sends about 96 Aljure responses, so the chance of at least
  one truncation in the F1 plan is about 16%.
- **Fixed live:** at least one truncation in the F1 plan, and every truncation
  retried and the arm answering.
- **Not triggered:** no truncation in the F1 plan. F1 then rests on the offline
  evidence, and the live plan is a regression check only.
- **Not fixed:** any F1 arm ends on a truncated turn, or any `f1-retry` violation.

### C. F2: text-only final answers

- **Trigger:** a text-only reply in the root that receives the terminal
  instruction.
- **Recovered:** the next reply is a `done` call or an accepted `FINAL ANSWER`.
- **Unrecovered:** the arm ends with "no correction permitted".
- **Baseline under the original contract:** 13 arms received a correction after
  a text-only reply; 12 recovered through `done`, and 1 (Opus formality) failed.
- **Fixed live:** at least 3 triggers in the F2 plan, every one recovered, and
  no F2 arm failing on a text-only reply.
- **Not shown:** fewer than 3 triggers, so the plan saw too few cases. The
  Opus run had text-only replies in 4 of 21 arms, so this outcome has about a
  25% chance. A repeat would then need a new frozen plan and its own approval.
- **Not fixed:** any trigger unrecovered.
- **Also reported:** the trigger count n, recoveries through `done` against
  `FINAL ANSWER`, and the rule-of-three upper bound on the unrecovered rate
  (about 3/n).
- **A wrong answer marked `FINAL ANSWER` is scored as wrong.** It counts as a
  reasoning error, not a delivery failure, and is reported separately.

### D. Regressions (reported; one run cannot estimate effect sizes)

- Per-task scores, completion, calls, cost and wall time for F1 and F2 against
  the control.
- Any task the control answered that a fix arm failed to answer, with its cause.
- Each plan's paired result against Prime, under
  `STATISTICAL_EVALUATION_PROTOCOL.md`.
- Prime's three runs give Prime's run-to-run spread. Score differences inside
  that spread are not attributed to the fixes.

## Verdict

**"Fixed without compromising the contract"** requires all of A, plus C
"fixed live", plus B either "fixed live" or "not triggered" with no F1 failure.
Every other outcome is reported as the criterion that failed or was not shown.
