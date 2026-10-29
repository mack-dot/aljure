# Finalization and transport recovery: validation

Two Opus Aljure arms in plan `d6e9b40d…` delivered no answer. Prime answered
both tasks correctly. Each failure now has its own plan-level switch, off by
default, so the original contract and every earlier plan are unchanged.

Commit `41b53fa`. Switches: `aljure_contract.truncated_turn_retries` (0–2) and
`aljure_contract.terminal_text_answer` (true or false).

## F1: provider-truncated tool turn

**What happened (task 7, imdb):**
- The provider returned HTTP 200 with `stop_reason: tool_use`, but the content
  was only two thinking blocks. The second read: "This part of the response was
  interrupted before it finished."
- The gateway recorded a complete receipt (`msg_011CgVxpsbTFSQw4iiqc66eL`,
  381 output tokens, $0.031).
- Aljure classed the turn as `incomplete-turn`, which cannot be corrected, so
  the task failed.

**How common it is:** 1 of 557 provider responses across A1, A1c, both synth
runs and both Opus smokes. Prime received none.

**Classification:**

| Response | Outcome known? | Side effects? | Policy |
| --- | --- | --- | --- |
| `stop_reason: tool_use`, only text, thinking or redacted-thinking blocks, no tool call | yes: HTTP 200, complete receipt | none: no command exists | **confirmed truncation**: retry if enabled |
| `max_tokens`, `refusal`, `end_turn` carrying a tool call, two tool calls, unknown block types | yes | none | unchanged: rejected; no retry |
| Timeout, cancellation, transport error, missing receipt | **no** | unknown | unchanged: the gateway's `ProviderOutcomeUnknown` path; never retried |

**Recovery rules:**
- Resend the same message list. The truncated turn never enters history, so
  the append-only, thinking-signature and tool-pair rules still hold.
- Both calls are charged under the arm's normal caps.
- A durable task counter (`:transport-retries-issued`) bounds the retries. It
  is separate from the one format correction (`:command-corrections-issued`).
- Every retry writes a `provider-turn-retried` event with the response hash,
  attempt number, and `executed: false`.
- When the retry allowance is spent, the task fails with "Provider turn
  truncated; transport retry budget exhausted".

## F2: terminal text answer

**What happened (task 6, formality):** Opus answered in text twice. Both
replies ended with the correct line `Label: formal`, but neither called
`done`. The first reply used up the task's one correction, and the second
failed the task.

**How common text-only replies are:**
- Sonnet: 9 of 21 arms; Opus: 4 of 21 arms (5 replies).
- 13 of 14 such replies contained a line in the task's requested answer form.
- After the correction the model usually called `done`. In three cases the
  number changed: 60 → 56, 26 → 24 and 45 → 46.

**Policy:**
- Only in the root session, the correction for a text-only reply asks for
  `done`, or for exactly one line: `FINAL ANSWER: <answer>`.
- Only the reply to that instruction is checked. It is accepted as the answer
  only if all of the following hold:
  - it ended with `end_turn`;
  - it has no tool call;
  - it has at least one text block;
  - its whole text, trimmed, is one line that starts with the marker;
  - the answer is non-empty and at most 4,096 characters;
  - the answer contains no second marker.
- Accepting writes a `terminal-text-accepted` event with the answer and the
  response hash.

**What it rejects:**
- intermediate commentary and partial generations;
- a marker inside thinking;
- a marker beside a tool call;
- `max_tokens` or `tool_use` stops;
- a marker before the instruction was given;
- a marker in a child session;
- a marker after the correction was spent on another error.

**Deliberately not used:** parsing the benchmark's own answer form (for
example a line starting with `Label:`). That would rescue the recorded replies
offline, but it is benchmark-specific.

**Offline consequence:** the exact recorded Opus replies carry no marker, so
they **still fail** under F2. Whether Opus follows the new instruction can only
be shown live, by ablation F2.

## Tests

**Unit and session tests** (`test/repl_lab/command_envelope_test.clj`; the
namespace has 33 tests and 313 assertions):
- They use the exact Opus provider responses from the hashed fixture
  `test/fixtures/opus-finalization-responses.json`.
- A truncated turn is retried once, with the same messages, both calls charged,
  and no command rejected. It fails when off, and fails when a second
  truncation exceeds one retry.
- The retry and correction allowances are independent.
- A compliant `FINAL ANSWER` is accepted only after the instruction, and is
  refused when the switch is off. The exact Opus formality trajectory fails
  under both settings.
- 12 adversarial replies are refused (see above).

**Runner tests** (`test_python/test_aljure_sci.py`):
- An absent contract changes neither the request body nor the capabilities.
- Each switch is declared separately.
- Invalid values are refused.

**Integration** (`paired-contract-fixture`; real gateway, receipts and SCI
worker; scripted responses; zero model calls): all **8 of 8 checks passed** at
the attested commit `41b53fa`.

| Check | Result |
| --- | --- |
| Contract arm answer | `6`, from the `FINAL ANSWER` line |
| One retry, not executed | yes |
| Retried request identical to the first | yes |
| SCI ran after the retry | value 6 |
| One text correction, then the accepted answer | yes |
| Instruction text sent | yes |
| Every call charged | 4 requests = 4 receipts |
| Original contract on the identical script | fails after 1 request on `incomplete-turn` |

**Full suites:** Python 153 passed; Clojure 125 tests, 2,066 assertions, 0
failures. The SCI contract proof was regenerated for the changed
`model_protocol.clj` (status TESTED).

## Remaining risks

- **F1 rarely fires.** It occurred once in 557 responses, so a 21-task ablation
  mostly checks for regressions; it cannot measure benefit.
- **F2 changes the correction message for text-only replies.** Wording could
  change model behaviour in cases that used to recover through `done`. The F2
  plan measures this: it records how often a correction ends in `done` and how
  often in `FINAL ANSWER`.
- **F2 accepts what the model explicitly marks as final.** A wrong answer
  marked final is scored as wrong, not as a delivery failure. The event log
  identifies those cases.
