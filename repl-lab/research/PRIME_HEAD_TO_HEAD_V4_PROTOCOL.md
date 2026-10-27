# Prime head-to-head V4: frozen command-interface recovery candidate

**FROZEN / BLOCKED / NOT AUTHORIZED / NOT RUN.** No new inference occurred.
The parser repair passed offline tests, but current SCI isolation failed. The
new actual-container relay must not run until that gate passes. This protocol
records a candidate, not a request to approve inference against failed proof.

## Exact freeze

| Item | Value |
| --- | --- |
| Plan SHA-256 | `f29512b53f036d13ca743a842eb6d3c26b59684a34cc35bdaebe6348c0bf8d99` |
| Execution commit | `3ff80b797c853e3f5c119d7518e08ec79d9c70d4` |
| Source SHA-256 | `582b21d2713c5d23bf265f2412b301807f61db1e059e123a175faf5cf6425e40` |
| Runtime SHA-256 | `991c846a1e313d6530f7c7ac6864e5e75b62dbca1668d03cf5911b12a5f6dc4a` |
| Configuration SHA-256 | `0478c8988112dfea6f9720b0ea74a0d125b023f9360ecccec495fd3f95d27f58` |
| Capability SHA-256 | `1c9f81c4da7e964eebc9efb48f464ce9df796c13d8696440fe57f0838f87d95a` |
| Base prompt SHA-256, unchanged | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| New response-envelope prompt SHA-256 | `7ee98b9ee1cafa4edff61985d201d031cd3bad4f8a51c1bd92da3a609a3e45db` |
| Official scorer SHA-256, unchanged | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Suite SHA-256, unchanged | `e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded` |
| Native Prime, unchanged | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` |
| Case | `oolong-pairs-validation-8192-1` |
| Model / transport | `claude-sonnet-5-5` / Claude subscription OAuth |
| Thinking | Adaptive/summarized, medium effort |
| Order | Aljure first, native Prime second |
| Deadline | 120 seconds per harness, unchanged |
| Proposed new caps | $12 per harness / $24 total API-rate-equivalent |
| Other limits | 12 calls, 12M accounted/reserved tokens per arm; 32,768 output tokens per call |

SCI image: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Native image: `sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
[Plan](evidence/prime-head-to-head-v4/plan.json),
[manifest](evidence/prime-head-to-head-v4/experiment-manifest.json),
[proposal](evidence/prime-head-to-head-v4/proposal.json),
[scope audit](evidence/prime-head-to-head-v4/scope-check.json).
The clean execution checkout is `/Users/mackianni/aljure-sonnet-pair-v4`.

## Deliberate interface change

Aljure alone uses `single-edn-map-v1`: one complete EDN map in one text block,
without extraction, markup removal or inferred command selection. A complete
provider turn is required. Duplicate/conflicting commands, invalid schemas,
unsafe readers, mixed content and incomplete turns fail safely.

Limited formatting errors can request one new complete response. One durable
allowance covers root, descendants and resumed sessions. It never resets on
success. Every correction uses the normal gateway and existing shared call,
token, money and time limits. The malformed response never executes and is not
replayed as an assistant command. Provider failures and unknown usage never
trigger this mechanism. [Exact contract and tests](COMMAND_ENVELOPE_V1.md).

The base reasoning prompt and all existing tools stay in place. The appended
contract is the only model-facing instruction addition. Native Prime's host,
Python tools, skills, subagents, refinement and prompts are unchanged. SCI,
supervisor, scoring, official inputs and gateway accounting are unchanged.
No workflow, scheduler, promotion threshold or hidden split was modified.

## Preflight and evidence classification

- **OFFLINE / FIXTURE:** 96 Clojure tests / 1,804 assertions and 106 Python tests
  pass. Tests cover the exact V3 response, adversarial envelopes, no rejected
  execution, accounted correction, root/child/resume sharing and denial under
  exhausted call/token/cost/time budgets. Unknown charges retain reservations.
- **Actual native isolation:** all ten fresh checks pass on the pinned image.
- **Actual SCI isolation: FAILED.** First attempt timed out before readiness.
  In the instrumented second attempt, allocation timed out without required OOM
  evidence; a later Docker preflight timed out before readiness. The gate stopped.
  Three intermediate healthy positive controls did not override those failures.
- **Revised native/SCI relay: NOT RUN.** It is blocked by missing SCI proof. Its
  two new mandatory checks require an accounted correction and no execution of
  the rejected fragment, in addition to the existing native root/child/tools,
  signed thinking, compaction/refinement, shared accounting and cleanup checks.
- **Credential metadata:** configured Claude OAuth, checked without inference or
  refresh. This is not a fresh provider-acceptance claim. No API fallback exists.
- **Combined preflight: NOT READY.** SCI proof and revised relay proof are absent.

[Final preflight](evidence/prime-head-to-head-v4/preflight.json),
[credential status](evidence/prime-head-to-head-v4/credential-status.json),
[isolation failures](evidence/command-envelope-v1/isolation-blocker.json),
[native proof](evidence/command-envelope-v1/native-isolation-proof.json),
[test results](evidence/command-envelope-v1/validation.json).
Worker limits and images were not changed to obtain a pass. Startup/host latency
remains unexplained; current isolation must be repaired or re-established before
requesting authorization. Any executable change requires a new frozen source and
plan, plus matching proofs. Do not reuse stale V3 proofs.

## Outcome and failure rules

Primary feasibility: both arms return an independently scored official answer.
Diagnostic competitive target: Aljure F1 at least **0.967741935483871**, with
total per-task inference cost **below $0.0663848 equivalent**, including every
correction and descendant. Those are exact V3 Prime reference values, not rounded
thresholds or tighter spending caps. Also compare against the concurrent V4 Prime
arm. Do not call an early failure efficient because it costs less.

After a separate approval, execute one pair only. No selective retries, extra
cases, model substitutions or answer repair. Known model/command failures remain
failed slots; unknown provider charges or cleanup failures retain the existing
stop rule. Correction is only the preregistered in-task mechanism, not an arm
rerun. Keep all receipts, rejected commands, correction decisions, code execution,
timing, answers and independent scores. Do not score nonexistent answers as a tie.

V1, V2 and V3 remain byte-preserved. Their charges/reservations remain separate.
No prior transcript, answer, learned artifact or V3 inspection enters the new
model conversation. This is nevertheless a previously inspected public recovery
case, not a new held-out observation. It cannot establish general superiority,
a Clojure language effect or learned harness improvement.

## Permitted next command and later authorization

Read-only preflight is permitted now:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v4/repl-lab
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/sonnet-pair-v4/plan.json
```

It currently returns NOT READY. Do not invoke `paired-run` now. After current
isolation and matching relay proof pass, recheck private credentials and present
this exact plan (or its replacement if source changes) for separate approval of
$12 per harness / $24 total through the subscription. Earlier approvals do not
apply. No Opus, selector or ten-case inference is included.

[Results](PRIME_HEAD_TO_HEAD_V4_RESULTS.md) remain **NOT RUN**.
