# Opus finalization repair (failure A: text-only answer)

**Task:** `oolong-synth-test-32768-615060038` (formality; least common label in a
date range; gold `formal`). Plan `d6e9b40d…`, arm `11-aljure`. Prime answered it
correctly. Aljure delivered no answer, scoring 0.

**Mechanism:** F2, `aljure_contract.terminal_text_answer`, commit `41b53fa`. The
full rule set and tests are in `FINALIZATION_RECOVERY_VALIDATION.md`. This
document covers the brief's requirements, provenance, and what remains unproven.

## The failure, reproduced offline

| Step | Recorded evidence (`11-aljure/agent/events.jsonl`) |
| --- | --- |
| Response 4 | `end_turn`, thinking + text, no tool call. The text explains the method, calls the counts "estimates, not exact", and ends `Label: formal`. Rejected as `no-tool-call`; the one correction is granted (`correction-requested: true`). |
| Response 5 | Same shape; the text ends `Label: formal` again. Rejected; no correction is left, so the session fails: "Command response rejected; no correction permitted". |

**The captured provider responses** are stored, hashed, in
`test/fixtures/opus-finalization-responses.json`. In
`test/repl_lab/command_envelope_test.clj`,
`a-final-answer-line-is-accepted-only-after-the-terminal-instruction` replays them:
- **Original contract:** the task fails exactly as it did live.
- **F2 on:** the task still fails, because neither recorded reply carries the
  `FINAL ANSWER:` marker.
- **F2 on, with a compliant scripted second reply:** the answer is accepted.

## Can Aljure safely recognise an unambiguous terminal answer?

**Only when the harness asked for an explicit terminal form and the reply uses it exactly.**

| Option | Safe? | General? | Rescues the recorded replies? | Decision |
| --- | --- | --- | --- | --- |
| F2: after a text-only reply, offer `done` or one line `FINAL ANSWER: <answer>` | Yes: one narrow path, a strict single line, root only | Yes | No (no marker) | **built**, off by default |
| Accept the task's own answer form (a line starting `Label:`) | Partly: the task text decides | No: benchmark-specific parsing | Yes | rejected by the brief and by us |
| Accept the last line of any text-only reply | No: commentary, estimates and drafts look the same | Yes | Yes | rejected |
| Force a `done` call on the next turn (`tool_choice`) | Yes | Yes | n/a | not available: forced tool choice is rejected with thinking on (`external_task.clj`, the `tool_choice` comment) |
| One prompt sentence mapping a requested answer form to `done` | Yes | Yes | Prevention, not recovery | designed (intervention 3) |

## The brief's requirements

| Requirement | How it is met | Test |
| --- | --- | --- |
| Strict validation of executable commands | Unchanged: exactly one tool call, schema-checked | `tool-calls-map-onto-the-same-command-schemas`; auditor `text-never-executed`, `command-provenance` |
| Never treat intermediate text as the answer | Accepted only in reply to the terminal instruction, and only one exact line | 12 refused replies in `terminal-answers-are-refused-outside-their-one-narrow-path` |
| Never execute code in a text reply | The accepted line becomes `done` with that string as the summary; nothing is evaluated | auditor `f2-terminal` ("only effect is done with that answer") |
| Reject ambiguous partial messages | Must end with `end_turn`; no `max_tokens` or `tool_use` stop; no extra lines; no second marker | the same refusal test |
| Explicit terminal versus commentary | The marker is requested by the harness and must be the whole text | the same refusal test |
| Full provenance of the accepted answer | Event `terminal-text-accepted`, with the answer, the provider id and the response hash | auditor `f2-terminal` re-checks the raw body |
| Record `done` versus terminal text | **New:** `agent/result.json` has `finalization: "done"` or `"terminal-text"` | `the-answer-records-how-it-was-delivered` (`test/repl_lab/verification_test.clj`) |
| No benchmark-specific parsing | The marker is harness-defined; the task's answer form is never parsed | by construction |

## Before and after

| Evidence | Original | F2 |
| --- | --- | --- |
| Recorded Opus formality replies | fail | **fail** (no marker) |
| Scripted compliant reply | fail | accepted |
| Integration fixture (real gateway and SCI) | fails on truncation first | 8/8 checks passed |
| Contract audit of the fixture arm | conformant | conformant; fails if audited as F2-off |
| Live | 1 of 13 corrected text-only arms failed (Sonnet and Opus) | **unmeasured**; plan F2 `b1844732…` |

## What remains uncertain

- **Whether Opus follows the new instruction is unknown.** No recorded reply
  shows it. The F2 plan measures it as "recovered through `done`" against
  "recovered through `FINAL ANSWER`" (`CONTRACT_FIX_ACCEPTANCE_CRITERIA.md`, part C).
- **Text-only replies are not specific to Opus.** Sonnet had more of them: 9
  arms against 4. Prevention (intervention 3) may matter more than recovery.
- **F2 recovers delivery, not correctness.** A wrong answer marked final scores as wrong.
