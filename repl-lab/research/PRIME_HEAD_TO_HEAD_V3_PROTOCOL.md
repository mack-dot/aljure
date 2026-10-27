# Prime head-to-head v3: frozen engineering recovery protocol

**FROZEN / PREFLIGHT PASSED / NOT AUTHORIZED / NOT RUN.** No model call was made
while preparing v3. The operator must approve this exact plan and new allocation.
V1 and v2 remain sealed. This public-case reuse tests engineering recovery; it is
not a new independent held-out observation.

## Frozen comparison

| Item | V3 value |
| --- | --- |
| Official case | `oolong-pairs-validation-8192-1` |
| Order | Aljure first, native Prime second |
| Model | `claude-sonnet-5-5`, exact returned ID required |
| Transport | Claude subscription OAuth, `native-claude-oauth-v1` |
| Provider endpoint | `https://api.anthropic.com/v1/messages` |
| Thinking | Adaptive, summarized display, medium effort |
| Output ceiling | 32,768 tokens per request, including thinking |
| Per-arm ceiling | **$12 API-rate-equivalent**, 12 calls, 12M accounted/reserved tokens |
| New pair allocation | **$24 API-rate-equivalent**, no allowance transfer |
| Task deadline | **120 seconds per harness**, unchanged |
| Scorer | Pinned official OOLONG-Pairs F1; outside both agents |
| Retries | No runner retries or selective reruns; native retry requests must enter the gateway as new accounted calls |
| Native Prime | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, unmodified |
| Execution source | `7c06c68d0aa400ea4fe1ed364cccf80585af9281`, clean dedicated checkout |
| Plan SHA-256 | `b81b71d58858258c2d7869b20ad8fbef30bd62596e4001b5d6a816921bcb40c8` |
| Full source SHA-256 | `ce1aec169cd491abda4dd16bf94d8cfadd68afdeee5764b0de84f0a4b37acb25` |
| Runtime SHA-256 | `c930cf81a0ebe519d475634602e5a342f47381d5ba211d1c7edde0c9b0b40d4f` |
| Configuration file SHA-256 | `3b93be01c316b33d99e68cb1a8f2e534c810536095bcb2b0cecded89d1ccb7ab` |
| Canonical configuration SHA-256 | `fcd44ad041ca48a13ebe703a236d32fe97b77d6453afdcc0ef2395d84dd74377` |
| Provider contract SHA-256 | `3e628f737600cf174fbceceec3420e723da6a9e11d83f743628347f01efd42e1` |
| Scorer SHA-256 | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Base prompt template SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| Suite SHA-256 | `e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded` |

SCI image: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Native image: `sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
The verified upstream data and scorer identities, licenses and official F1
semantics remain those in [OOLONG sources](OOLONG_SOURCES.md).

[Plan](evidence/prime-head-to-head-v3/plan.json),
[experiment manifest](evidence/prime-head-to-head-v3/experiment-manifest.json),
[configuration](evidence/prime-head-to-head-v3/proposal.json), and
[provider contract](evidence/prime-head-to-head-v3/provider-contract.json) contain
machine-readable pins. The full source map includes every prompt, broker, provider,
scorer, dependency and worker hash. Dynamic model request bodies and returned IDs
will be recorded only if execution is authorized; none is invented here.

## Scope audit

Executable configuration and the capability matrix match v2. Campaign metadata
now identifies v3 and both earlier failures. Base instructions, external-task
adapter, native relay bootstrap, native container supervisor, worker source,
subscription header contract and official scorer are byte-identical to v2.
The Python AST of `run_arm` is unchanged, including prompt construction, execution
limits and artifact collection. [Scope checks](evidence/prime-head-to-head-v3/scope-check.json).

Changes since v2 repair transport timing, bounded response preservation, terminal
usage validation and cleanup accounting. Tool elapsed-time fields were added only
to controller trace records; broker results and model messages are unchanged.
[Runtime instrumentation patch](evidence/prime-head-to-head-v3/runtime-instrumentation.patch).
No scheduler, promotion rule, hidden split, benchmark answer, model instruction,
Prime algorithm or tool capability was changed.

The first preparation used the base proposal and failed a provenance-metadata
equality assertion. Execution settings already matched. The rejected draft is
preserved, and v3 now records the correct campaign history. This was a preparation
check, not inference. The relay used that initial proposal's identical executable
transport contract. The final preflight verifies the contract and runtime match.
[Preparation note](evidence/prime-head-to-head-v3/preparation-note.json).

## Required offline boundary tests

**FIXTURE / OFFLINE:** 34 focused Python tests passed. Gateway/runtime Clojure tests
passed **18 tests / 156 assertions**. Five new regression methods cover ten cases:

| Scenario | Verified behavior |
| --- | --- |
| 61-second response after 20 seconds of startup | Completes at simulated task second 81; body preserved and receipt reconciled |
| 91-second response with only 90 seconds left | Rejected at simulated task second 121; partial/full received bytes preserved; reservation remains unknown |
| Stream stalls after partial data | Explicit deadline failure, bytes and request identity preserved; helper terminated |
| Cancellation after partial data | Explicit cancellation, conservative unknown charge and bounded helper cleanup |
| Terminal usage missing, empty, string-valued or negative | Receipt rejected; full reservation held; subsequent dispatch blocked |
| Valid receipt then HTTP-helper cleanup failure | Receipt reconciled, arm fails, later dispatch blocked; cleanup failure recorded |
| Valid receipt then gateway cleanup failure | Settled usage survives, transport pool joins, cleanup report fails explicitly |

The long-response checks use a deterministic virtual clock, not a timed live
request. Separate tests use real local helper processes and local HTTP, covering
signed native SSE, truncated bodies, HTTP errors, cancellation and cleanup.
The first regression run exposed empty terminal usage falling back to initial
counters and a cleanup exception masking a received response. Its failed log is
preserved alongside the passing run. No incomplete receipt is assigned zero cost.

[Before](evidence/prime-head-to-head-v3/regression-before.log),
[after](evidence/prime-head-to-head-v3/regression-after.log),
[full Python suite](evidence/prime-head-to-head-v3/python-final.log), and
[Clojure tests](evidence/prime-head-to-head-v3/clojure-final.log).
The provider's streaming counters are cumulative, not additive. The terminal
output count must be present and valid. [Official streaming contract](https://platform.claude.com/docs/en/build-with-claude/streaming).

Reproduce the focused long-response/budget tests without inference:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v3/repl-lab
python3 -m unittest test_python.test_v3_transport -v
```

## Complete preflight evidence

Fresh strict SCI tests passed the positive control and all nine negative tests,
with readiness confirmed in the same worker before each negative operation.
Fresh native isolation passed all ten enforcement/reset checks, including actual
OOM evidence, rejection of an unrelated kill, process limits and state reset.
The images and isolation code match the frozen source.
[SCI proof](evidence/prime-head-to-head-v3/isolation-proof.json),
[native proof](evidence/prime-head-to-head-v3/prime-isolation-proof.json).

The actual-container native/SCI relay passed **all ten checks** on the frozen
source. Five Aljure and six Prime scripted requests were fully reconciled.
Aljure used three root and two child calls. Prime used two root, two child, one
manual compaction and one manual refinement call. All crossed the common gateway.
Signed thinking, tools, SCI context, shared reservations and cleanup passed.
The 50-file archive retains all receipts and traces; three SQLite stores passed
integrity checks. This remains **FIXTURE**, not native live-provider verification.
[Relay proof](evidence/prime-head-to-head-v3/relay-proof.json),
[raw archive manifest](evidence/prime-head-to-head-v3/relay-manifest.json).

Final [preflight](evidence/prime-head-to-head-v3/preflight.json) is ready with no
blockers. The separate [private credential check](evidence/prime-head-to-head-v3/credential-status.json)
passed without inference or automatic refresh. No experiment worker, HTTP helper
or agent process remains. Credentials stay in the host Keychain and HTTP helper;
workers receive an explicitly invalid sentinel. No real credential was copied
into a worker, source file or evidence bundle. There is no API-credit, model or
transport fallback. Credential validity and source/isolation checks must pass
again at dispatch; current validity does not guarantee future provider availability.

## Time, accounting and failure interpretation

The per-harness task execution watchdog remains 120 seconds. The gateway's own
120-second allowance starts at its initialization. Each HTTP request uses only
the remainder of that gateway allowance; there is no new 120-second grant per
request and no inner 45-second cutoff. Published attempt wall time also includes
startup, collection and cleanup overhead, which is reported separately rather
than presented as pure provider computation.

`gateway/transport.jsonl` records request/response stages, request duration, task
elapsed time, remaining budget, HTTP status and safe provider request IDs.
`transport-bodies/` preserves received HTTP 200 bytes, including partial SSE.
Duration includes network and host transport overhead; provider internal compute
time is not directly observable. Error messages that can echo credentials are
omitted; status/type/hash remain available. Missing terminal usage retains the
full conservative reservation. A full Sonnet request reserves $4.32768; no
unverified charge is silently released.

Aljure tool traces record elapsed time without changing tool returns. Native
`event-timing.jsonl` records host-observed tool-start/end events; raw events remain
in `stdout.jsonl` and the native session archive. These timings are not identical
CPU-time measurements and nested/delegated intervals can overlap. SCI worker
audits supply startup and execution evidence. Request journals, normalized usage,
ledger reports and cleanup reports must reconcile before a success claim.

An unknown provider outcome, unconfirmed cleanup or runner exception stops later
dispatch. A complete provider receipt followed by cleanup failure is still charged
correctly, but the arm fails. Failed and unattempted slots remain in the report.
Mechanical zero scores for such slots must never be called a measured tie.
If transport fails again, inspect the exact request ID, stage, partial bytes,
receipt validation and cleanup record before proposing another version.

## Preserved earlier attempts and limits on claims

V1's 23 archived files and v2's 21 archived files match their original bytes and
archive hashes. [Independent integrity check](evidence/prime-head-to-head-v3/prior-evidence-integrity.json).
Their known equivalent usage totals $0.015290; v2 still holds $4.32768 unresolved.
The original v1 ledger also remains sealed, with its separate reconciliation
addendum. None of these is a subscription invoice. V3 asks for a new $24 ceiling;
the known-plus-unresolved-plus-new-ceiling total for these external attempts would
be $28.342970. No earlier reservation is released by approving v3.

Neither prior arm produced a scored answer. V3 loads no prior conversation,
trajectory, result or learned benchmark answer. The case remains a public,
previously attempted recovery case. Native Prime retains Python, skills, subagents
and refinement; Aljure retains its Clojure-oriented broker and synchronous children.
Prompt/tool/resource differences remain documented in the capability matrix.
Aljure's controller runs outside its SCI worker, while Prime's host and Python
share the native container limit. Local compute costs remain unpriced.

Complete aggregate gateway accounting does not establish perfect native parent/
child ancestry attribution. Manual compaction/refinement passed offline; automatic
context-pressure behavior remains limited by the pinned native usage parser.
No language-only or harness-learning claim follows from this comparison. One pair
can establish feasibility, not statistical superiority. A multi-case study is a
separate preregistration and budget after valid results; none is authorized here.

## Approval and exact execution command

Approve only plan **`b81b71d58858258c2d7869b20ad8fbef30bd62596e4001b5d6a816921bcb40c8`**, model `claude-sonnet-5-5`, Claude subscription
transport, **$12 per harness / $24 new total API-rate-equivalent**, on the one case
above. This excludes Opus, selector inference and the ten-case campaign.
Earlier approvals covered v1/v2 and do not authorize this run.

After explicit approval, use the frozen checkout and selected private Keychain
source. These selectors are names, not secret values:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v3/repl-lab
source var/worker.env
source var/prime-worker.env
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT='mackianni'
python3 -c 'import json; from benchmark.subscription_protocol import credential_status; print(json.dumps(credential_status()))'
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/sonnet-pair-v3/plan.json
python3 -m benchmark paired-run --suite var/official/pairs-one --plan var/sonnet-pair-v3/plan.json --out var/benchmarks/sonnet-pair-v3-live --authorize-subscription-plan b81b71d58858258c2d7869b20ad8fbef30bd62596e4001b5d6a816921bcb40c8
```

Run the final command only if the credential and isolation preflights pass.
The live output directory does not exist. It must be created once by the runner.
The [results report](PRIME_HEAD_TO_HEAD_V3_RESULTS.md) is explicitly NOT RUN.
