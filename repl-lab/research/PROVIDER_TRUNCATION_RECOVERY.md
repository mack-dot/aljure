# Provider truncation recovery (failure B)

**Task:** `oolong-synth-test-32768-215020018` (imdb: is `negative` more common
than `positive`? gold: less common). Plan `d6e9b40d…`, arm `12-aljure`. Prime
answered it correctly; Aljure delivered no answer and scored 0.

**Mechanism:** F1, `aljure_contract.truncated_turn_retries` (0–2), commit `41b53fa`.
Rules: `FINALIZATION_RECOVERY_VALIDATION.md`.

## The failure boundary, from the trace

| Question | Answer | Source |
| --- | --- | --- |
| Provider termination | HTTP 200, `stop_reason: tool_use`, content `[thinking, thinking]`, no `tool_use` block. The second thinking block reads "This part of the response was interrupted before it finished." | `12-aljure/gateway/events.jsonl`, response 6 (`msg_011CgVxpsbTFSQw4iiqc66eL`) |
| Usage receipt | Complete: 381 output tokens (365 thinking), 4,052 cache-write tokens, 13,639 cache-read tokens, $0.0306 | `gateway/usage.jsonl` |
| Had a tool executed? | No: the turn had no tool call. Aljure recorded `command-rejected`, `reason: incomplete-turn`, `executed: false` | `agent/events.jsonl` |
| Was the outcome known? | Yes: the response was received whole and charged once | gateway receipt, `status: complete` |
| Was retry safe? | Yes: no side effect existed, and the same request has the same meaning | — |
| Deadline left | 871 s of 900 (the request ran from 23.2 s to 28.8 s of the task) | `gateway/transport.jsonl` |
| Budget left | 6 calls ($0.12) of 1,000 calls ($100) | `agent/result.json` |
| What the model was doing | Its thinking had concluded "the positive labels are more common overall", which is the correct answer | response body |

Frequency: once in 557 responses across all recorded runs.
Over the 415 responses the contract auditor can classify, it is once in 415.

## Recovery policy

| Response | Outcome known | Side effects | F1 policy |
| --- | --- | --- | --- |
| `tool_use` stop with only text or thinking blocks (empty content included) | yes | none | resend the identical request, within `truncated_turn_retries` |
| `max_tokens` or missing `stop_reason`; text, or a cut inside a tool call | yes | none, but the turn is incomplete | rejected as `incomplete-turn`; never retried, never executed |
| Malformed body or stream, missing usage, non-200, wrong id | **no** | unknown | the reservation is held and the gateway stops; never retried |
| Timeout, cancellation, transport error | **no** | unknown | the same |
| Duplicate receipt or duplicate frame | charged once | — | the second copy is refused; the gateway stops |
| Deadline or budget too short for the resend | yes | none | `invoke!` refuses before dispatch; the task fails on that limit |

**Separate allowances:**
- Transport recovery uses `:transport-retries-issued`.
- The model's format correction uses `:command-corrections-issued`.
- Neither replenishes the other. Both are task-wide, so children share them.

## Tests (all offline: scripted frames, no network, no inference)

| Failure mode | Test |
| --- | --- |
| Malformed or partial bodies, malformed stream events (undecodable data, event before `message_start`, unknown type, event after stop, no `message_stop`, no terminal usage) | `transport_failure_test/malformed-or-partial-provider-bodies-are-unknown-outcomes-and-never-retried`; existing gateway and v3 transport tests |
| Partial turns (`max_tokens`, missing `stop_reason`, a cut inside a tool call), with F1 at 2 | `partial-turns-are-charged-rejected-and-never-retried-or-executed` |
| Unknown outcomes with F1 on (5 reply shapes, plus a throwing provider) | `unknown-outcomes-are-never-retried-even-with-transport-retries-enabled`; Python `test_an_unknown_receipt_stops_the_pilot_before_the_next_arm` |
| Duplicate delivery | `the-same-receipt-delivered-twice-is-charged-once`; Python `test_bridge_rejects_duplicate_late_and_reused_transport_frames` (the real `gateway-stdio` process) |
| Late response for an abandoned request | `a-late-receipt-for-an-abandoned-request-is-reconciled-once`; the bridge test above |
| Cancellation | `a-cancelled-session-is-charged-once-for-its-in-flight-call-and-cannot-call-again`; Python `test_cancel_before_dispatch_never_opens_a_connection_or_retries`; existing v3 cancellation tests |
| Deadline or budget exhaustion at retry time | `a-retry-without-deadline-or-budget-left-is-never-dispatched` (calls, USD, tokens, deadline) |
| F1 itself | `a-truncated-turn-through-the-external-provider-resends-the-identical-body`; `the-transport-retry-allowance-is-bounded-and-task-wide`; the 3 F1 tests in `command_envelope_test`; fixture 8/8 |

**Suites:**
- Clojure: 139 tests, 2,394 assertions, 0 failures.
- Python: 167 passed.

The new tests are in `test/repl_lab/transport_failure_test.clj` (10) and
`test_python/test_transport_failures.py` (3).

## Found and resolved

**A refused retry is recorded as a retry. This is evidence wording, not a safety issue.**
- **What happens:** `retry-truncated-turn!` writes `provider-turn-retried {:retried true}`
  when it grants the allowance. If the next `invoke!` then refuses on a cap or the
  deadline, nothing is sent, but the event still reads `retried: true`.
- **Effect:** the contract auditor reported a false `f1-retry` violation.
- **Resolution:** the auditor now reads `retried: true` as "allowance granted".
  - The resend is the next gateway request, and it must be identical.
  - If no request follows, the session must have failed on a limit. The auditor
    reports this as `retries_refused_by_limit`.
  - The runtime is unchanged, so the frozen F1 plan's code still matches.
- **Recording:** `transport_failure_test/a-refused-retry-is-not-recorded-as-a-retry`
  keeps the runtime behaviour as a recorded known issue.

## Before and after

| Evidence | Original | F1 |
| --- | --- | --- |
| Recorded imdb truncated response (scripted replay) | task fails after 1 request | retried once, identical body; the task completes |
| Real gateway and SCI fixture | fails on `incomplete-turn` | 8/8 checks passed |
| Live | 1 truncation in 557 responses ended a task | **unmeasured**. A plan has about a 16% chance of seeing one (`CONTRACT_FIX_ACCEPTANCE_CRITERIA.md`, part B) |

## Not testable offline

- Real HTTPS and SSE behaviour of the provider (real cut-offs, 529 bodies). Local fakes stand in.
- The Python process kill at `task_seconds` racing the Clojure ledger deadline.
  If the kill wins, the arm's events are not exported, and the arm is reported as unauditable.
- Prime's transport, which is out of scope.
