# Transport failure repair v1

**IMPLEMENTED / OFFLINE TESTED. No new inference.** The operator requested these
repairs after the sealed Sonnet v2 attempt. Its unknown request cannot be
retroactively diagnosed or assigned zero cost. The original source and all run
files remain unchanged; [v2 results](PRIME_HEAD_TO_HEAD_V2_RESULTS.md) record the
failure without treating the two uncompleted slots as a measured tie.

## Changes

- Remove the implicit 45-second per-response cutoff. Each request remains bounded
  by the common gateway's remaining task allowance, including HTTP helper startup.
  The 120-second task limit, cancellation, output bounds and spending reservations
  still apply. No retry, model change, provider fallback or token-cap change.
- Record safe request stages: host, credential read, connection and response.
  Distinguish deadline, cancellation, DNS, TLS, connection, truncated body,
  decoding, size-limit and generic failures. Never record raw exception text,
  request headers, credential values or private credential paths.
- Link host transport IDs to durable gateway reservation IDs. Fsync a timestamped
  transport journal before dispatch and after completion or failure. The journal
  supplements the existing ledger; it does not grant reconciliation authority.
- Preserve successful and partial HTTP 200 body bytes as they arrive, including
  native SSE tool-use and signed thinking blocks. A truncated Content-Length body
  is a failure. Incomplete receipts remain unknown with their full reservation.
- Preserve HTTP error status, validated request ID, allowlisted error type and
  original body hash. Omit arbitrary error messages because they can echo secrets.
  HTTP errors do not trigger retries or release an unverified charge.

Raw response bodies remain limited to 4 MiB. The helper's encoded JSON-line frame
bound is 32 MiB to accommodate JSON escaping plus incremental frames. This does
not increase the model output allowance or worker output limits. Credentials stay
in the trusted host helper. Workers receive the same native or SCI interface.

The provider documents HTTP errors, request IDs and errors within an HTTP 200 SSE
stream. Its guidance recommends streaming for long requests. These repairs retain
the frozen harnesses' current stream choices; no silent stream conversion was
added. [HTTP errors](https://platform.claude.com/docs/en/api/errors),
[streaming semantics](https://platform.claude.com/docs/en/build-with-claude/streaming).

## Validation

The focused transport, bridge, subscription and model-contract suite passed
**29 tests**. A local HTTP server and the real host helper process exercise full
signed SSE delivery and interrupted bodies through the durable gateway. A 429
fixture verifies status/type/request-ID preservation, secret-message exclusion,
no retry and retained accounting. Fake-clock testing accepts a response after
61 seconds within a 90-second task remainder and rejects one past that remainder.
Real process tests cover cancellation, timeout and helper cleanup.

Clojure gateway tests passed **10 tests / 105 assertions**. They retain cumulative
stream accounting, standard-speed pricing, reservation and unknown-outcome rules.
Two focused partial-response/deadline checks also passed after adding streamed
byte counts and hashes to host timeout records.

One intermediate offline test failed because urllib wraps HTTPError's response
stream differently from a normal HTTPResponse. The reader now uses the underlying
stream consistently. The failed log and passing rerun are both retained in
[evidence](evidence/transport-failure-repair-v1/transport-repair-tests.log).
The [passing suite](evidence/transport-failure-repair-v1/transport-repair-final-tests.log)
and [gateway tests](evidence/transport-failure-repair-v1/transport-repair-gateway-tests.log)
are fixtures, not evidence of another successful live call.

The final actual-container relay at source
`435d57dda9067f3c71cfbb5ab65e944090b85ffc` passed all ten checks: native root,
child, tools, manual compaction/refinement, signed thinking, OAuth serialization,
SCI context execution, shared accounting and cleanup. Five Aljure and six native
requests used scripted replies. Model calls: **0**. Three SQLite stores passed
integrity checks. Runtime SHA-256:
`efaa0ad72b0f7daf1f08f3780778efe7b8cbeb916433e6f37d3c89b6ffa26ec1`.
The [relay report](evidence/transport-failure-repair-v1/native-relay-report.json)
and [46-file raw archive manifest](evidence/transport-failure-repair-v1/native-relay-manifest.json)
preserve this evidence. This relay tests controller/native integration; the local
HTTP tests above exercise the real transport helper. Neither contacts a provider.

Exact offline checks:

```sh
python3 -m unittest test_python.test_external_transport test_python.test_gateway_bridge test_python.test_subscription_gateway test_python.test_opus_followup -v
python3 scripts/clj.py -e "(require '[clojure.test :as t] '[repl-lab.gateway-test]) (let [r (t/run-tests 'repl-lab.gateway-test)] (shutdown-agents) (System/exit (if (zero? (+ (:fail r) (:error r))) 0 1)))"
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-relay-fixture --provider claude-oauth-subscription --config config/external-subscription-proposal-v1.json --out var/benchmarks/transport-failure-repair-v1
```

The recorded relay output directory already exists. Any independent offline
reproduction must use a new directory and retain the earlier result.

## Remaining limits

V2 did not record enough transport detail to distinguish a timeout from an HTTP,
network or credential failure. These changes repair that observability defect and
remove the shorter deadline, but they do not establish the missing historical
cause or prove that a live retry will complete. The unknown $4.32768 reservation
remains unresolved. No provider invoice is inferred from the API-equivalent rate.

A new live attempt must freeze the changed runtime and receive its own
authorization. Its matching offline relay proof now passes. The two sealed attempts cannot be
rerun selectively. Opus, selector inference and the ten-case study remain unapproved.
