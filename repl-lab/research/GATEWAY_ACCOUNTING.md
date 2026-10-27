# Shared gateway accounting

Current follow-up: [Sonnet v2](PRIME_HEAD_TO_HEAD_V2_RESULTS.md) reconciled two
real receipts, then retained a third unknown reservation and stopped. The
[transport failure repair](TRANSPORT_FAILURE_REPAIR_V1.md) adds safe diagnostics,
partial response evidence and a deadline tied to the remaining task allowance.
Its HTTP and native/SCI controls pass offline. The earlier study below is retained.

Evidence: **FIXTURE**. No new model inference was used in this phase.

`gateway.clj` reuses the existing controller and SQLite CAS ledger. All trusted
routes share one cap. Each request reserves calls, tokens and dollars before its
transport runs. An uncertain result keeps the reservation and stops retries,
including after reopen. Completed usage remains recorded when the model differs
or a reservation is exceeded. Duplicate provider receipts cannot release funds.
Gateway session IDs identify requests; native agent ancestry remains unverified.

The current scope permits text, client tools and pinned sampling/thinking settings.
Server tools, media, priority tiers, regional pricing, provider fallback and
server-side compaction need separate contracts. Native host-side refinement and
compaction can use ordinary Messages requests, but those paths have not yet been
connected and tested through the gateway.

Reservations cover the full declared model context bound at the highest configured
input/cache rate, plus output. The actual enforced context bound and applicable
rates need verification before live use. Token-count estimates are not assumed to
be hard bounds. Cache reads, five-minute writes and one-hour writes have explicit
rates. Missing cache durations or unknown charge fields stop reconciliation.
Dollar values are configured-rate estimates, not provider invoices.

The [official streaming contract](https://platform.claude.com/docs/en/build-with-claude/streaming)
places initial usage in `message.usage`. Final `message_delta` counters are
cumulative. The gateway merges these counters instead of adding them.

## Findings in pinned Prime

Source: `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`. No upstream changes were made.

- `crates/pa-cli/src/print_rlm.rs:627` describes the daemonless host as omitting
  child usage attribution. `rlm_usage_store: None` selects a default store in
  `runtime_wiring.rs:166`; it does not disable it. The earlier checkpoint's
  explanation of this missing attribution was incorrect and has been corrected.
- `crates/pa-ai/src/providers/anthropic/stream.rs:298` reads initial token counters
  directly from `message`, rather than nested `message.usage`. A later delta can
  recover a counter only if that counter appears there.
- `var/benchmarks/prime-http-20261026` reproduced that accounting issue through
  the normal HTTP provider path. Four scripted responses across root and child
  supplied 4,000 input and 80 output tokens. Native transcripts recorded 0 input
  and 80 output tokens. Computation, message delivery and the independent answer
  check passed. The report separately sets `native_counters_match: false`.

These are fixture transport findings, not live measurements or a competitive win.
The local HTTP server runs inside the disposable, network-disabled container.
Its files are diagnostics, not a trusted live billing source.

The external gateway replay at `var/benchmarks/gateway-native-replay-20261026`
accounted for all four raw scripted responses: 4,080 total tokens and $0.0088 at
fixture rates. No reservations remained. Replay does not establish a connected
gateway. Actual incurred model inference cost in this phase was zero.

## Commands and missing boundary

```sh
source var/prime-worker.env
make prime-http-fixture OUT=var/benchmarks/new-http RUN=var/benchmarks/language-pilot-20261026-json
make gateway-fixtures OUT=var/benchmarks/new-gateway
make gateway-native-replay OUT=var/benchmarks/new-accounting RUN=var/benchmarks/new-http
```

Use fresh directories. The native command requires its actual isolation proof.
These commands do not accept provider credentials.

Still required: bounded transport from isolated Prime to the trusted external
ledger, prevention of direct provider access, credentials outside generated-code
processes, phase/arm/task caps within the global envelope, cancellation, and actual
descendant/refinement/compaction/retry tests. Live execution remains disabled.
