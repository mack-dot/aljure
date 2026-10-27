# Sonnet v2: live attempt and transport failure

**LIVE MODEL RUN — incomplete. No completed Aljure/Prime comparison.**

The operator approved plan `a5b717479e78fd0e0174ae86a00b7189e82267a618b45622a69da33db10a3b1a`
with a new $12 per-harness / $24 total API-rate-equivalent allocation through
Claude subscription. Credential, strict isolation-proof, image and runtime checks
passed with no inference. The frozen runner executed once on 2026-10-27 at
12:30:57 UTC. No source, scoring, model, threshold or case changed. There was no
runner retry, API fallback, Opus call, selector call or additional benchmark case.

| Measure | Aljure | Native Prime |
| --- | --- | --- |
| Status | Provider outcome unknown on request 3 | Not dispatched by the frozen stop rule |
| Completed benchmark answer / actual F1 | None / unavailable | None / unavailable |
| Recorded failure-slot score | 0 | 0 |
| Gateway-admitted requests | 3 | 0 |
| Completed provider receipts | 2 | 0 |
| Known input / output tokens | 4,864 / 53 | 0 / 0 |
| Known cache-write / cache-read tokens | 0 / 0 | 0 / 0 |
| Known API-rate-equivalent cost | $0.010258 | $0 |
| Unresolved reservation | $4.32768; 1,032,768 tokens | $0 |
| Attempt wall time | 63.093 seconds | Not attempted |

The known charge plus the unresolved reservation is **$4.337938**, below Aljure's
$12 cap. The unknown reservation is an upper bound, not measured consumption.
The third request has no complete receipt; its actual tokens, model response and
charge are unknown. Actual subscription invoices are not measured. The earlier
v1 receipt remains separate at $0.005032 equivalent.

The scorer retains both failed/unattempted slots as zero. Its mechanical
`wins_ties_losses: [0,1,0]` and `paired_cases: 1` refer to the planned slots. They
are **not a measured tie or one completed pair**. There are zero completed pairs.
Prime's recorded 0.704 ms is skip-bookkeeping time, not Prime runtime. The overall
launcher took 68.352 seconds, including preflight and reporting.

## What executed

Both complete responses returned the exact requested `claude-sonnet-5-5` model.
The repaired standard-speed receipt parser accepted both and reconciled their
reservations. The model used `context/metadata`, then `context/query` with offset
0 and limit 5. Both controller tools completed. The external context contained
195 lines; the query returned five lines, including one question record.

The third request included these results. No complete response reached the
ledger. There was no `repl/eval`, SCI worker creation, child session, retained-skill
invocation, candidate proposal or final answer. This attempt establishes two
successful live context-broker operations, not recursive computation, learning,
benchmark correctness or native Prime provider compatibility.

## Read-only failure analysis

The gateway records request 3 as `provider-outcome-unknown`, with no corresponding
`gateway-response`. The agent received a generic gateway rejection. Unlike v1,
there is no saved HTTP 200 receipt to reconcile after the fact.

The frozen host transport collapsed all HTTP, connection, timeout, credential and
worker errors into one generic outcome. It also imposed a 45-second total response
cutoff inside the 120-second task budget. A cutoff is consistent with the observed
elapsed time, but the evidence does **not establish** whether this request timed
out, received an HTTP error or failed for another transport reason. Event records
lack per-request timestamps. Do not attribute the failure to the model or claim
that a particular provider error has been diagnosed.

The outer process reports exit -9 after it received the explicit agent completion
frame with `native_exit_code: 2`. The bounded supervisor deliberately kills its
client on completion. This is not evidence of OOM or an SCI startup failure.
No experiment worker or HTTP/gateway process remained after cleanup.

The next engineering correction is bounded, credential-safe transport diagnostics,
partial-response preservation, and a request deadline bounded by the remaining
existing task allowance. It must be validated offline and versioned separately.
It cannot change or resume this sealed attempt.

## Evidence and provenance

- Aljure source: `bf9a8fbcb5eb31f7b7ffafe13d58c05dd83b1ca1`, still clean.
- Full source SHA-256: `449d37253cf35ee589ef8e8e7c98137bcf3681e22bfbc0beb56e5e02301de369`.
- Runtime SHA-256: `d4a2e98d1f74100ecce5a2cc716c2f229bf17aa0bb225239216f7d79b3c58e3d`.
- Prime pin: `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, unmodified and not dispatched.
- Official case: `oolong-pairs-validation-8192-1`; same public repair-follow-up case as v1.
- Scorer SHA-256: `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce`.
- Both original SQLite stores passed integrity checks. All 21 original run files
  retained identical hashes after analysis. Scoring was independently recomputed
  from the preserved files without any model call.

The [evidence manifest](evidence/prime-head-to-head-v2-live-attempt1/manifest.json)
indexes the [raw archive](evidence/prime-head-to-head-v2-live-attempt1/raw-run.tar.gz),
whose SHA-256 is `fb7d0ec89d9374432a65eca70b7f9010cad8b4bbb2a5463b4668d2022e075209`.
[Approval](evidence/prime-head-to-head-v2-live-attempt1/authorization.json),
[preflight](evidence/prime-head-to-head-v2-live-attempt1/authorized-final-preflight.json),
[original report](evidence/prime-head-to-head-v2-live-attempt1/report.json),
[normalized results](evidence/prime-head-to-head-v2-live-attempt1/results.jsonl), and
[independent accounting check](evidence/prime-head-to-head-v2-live-attempt1/independent-check.json)
remain separate from this interpretation.

Exact archive references:

- `00-aljure/gateway/events.jsonl`, sequences 4 and 10: complete HTTP 200 receipts.
  Provider IDs: `msg_011CgSkC6JEksPGRL4bdrcks` and `msg_011CgSkCWHtF9Rzg4aWwNqVF`.
- Gateway sequences 14–16: third request, reservation and unknown outcome.
  Request ID: `2fb08c9f-b80d-412e-b7c4-208295e58e88`.
- `00-aljure/agent/events.jsonl`, sequences 4–5 and 9–10: successful context tools.
  Sequences 11–14: final reservation, request, unknown outcome and failed root.
- `00-aljure/gateway/usage.jsonl` and `report.json`: two complete receipts and one
  unresolved reservation. No estimate substitutes for that missing receipt.
- `01-prime/trace.json`: stopped slot; `gateway/usage.jsonl` is empty.

The [frozen protocol](PRIME_HEAD_TO_HEAD_V2_PROTOCOL.md) contains the exact command.
The existing output directory must not be reused. Reproduction of scoring is
read-only; repeating inference needs a new versioned, separately approved attempt.
One public case cannot establish general superiority. The documented differences
in prompts, context access, tools, orchestration and whole-system resources remain.
