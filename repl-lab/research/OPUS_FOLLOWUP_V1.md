# Opus subscription follow-up v1

This is a separate, unapproved follow-up to the frozen Sonnet subscription pair. It starts from `a72b8c0` in `/Users/mackianni/aljure-opus-followup`, branch `codex/opus-followup`. The approved Sonnet checkout, plan, model, scoring, and caps remain unchanged. No credential was read and no model request was sent during this work.

## Contract and native support

The fixed model ID is `claude-opus-5-5`. The documented context limit is 1M tokens and maximum output is 128K. Ordinary input/output rates are $4/$20 per million tokens; 5-minute/1-hour cache writes cost $5/$8, and cache reads cost $0.20. These are accounting reference rates for subscription usage, not subscription invoices. [Official overview, reviewed 2026-10-27](https://platform.claude.com/docs/en/models/opus-5-5/overview).

The proposal keeps adaptive/summarized thinking, medium effort, and a 32,768-token maximum output. It omits sampling parameters. Opus rejects disabled/manual thinking, forced tools, and assistant prefill. Signed thinking must remain intact in native tool loops. [Official migration guide](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide).

Pinned Prime `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` already recognizes `opus-5-5` as always-on adaptive in `crates/pa-ai/src/providers/anthropic/mod.rs:240`; `supports_adaptive_thinking` recognizes the Opus 5 family. `params.rs` therefore emits adaptive/summarized thinking and medium effort. Its OAuth user-agent remains the pinned `claude-cli/2.1.281`. No Prime source or native tool is changed.

The external task, provider transport, and durable gateway already take an explicit model ID. The two Sonnet-specific checks on this route were the paired-plan allowlist and relay fixture defaults. The new checkout adds the exact Opus contract, a fixture configuration argument, and a model/settings/rates/budget fingerprint in the relay proof. A Sonnet fixture cannot attest Opus readiness. The gateway rejects Opus forced-tool and assistant-prefill requests before transport. Historical Sonnet smoke/learning configurations remain untouched.

## Fixed economic budget

The new proposal uses the same official Pairs8K case, harness prompts, capabilities, task limits, output allowance, and call/token ceilings. It changes only the requested model and documented prices. Each arm retains a $12 equivalent cap; the pair retains $24. This is an additional, unapproved $24 allocation. Combined with the approved Sonnet pair, the potential campaign ceiling is $48 equivalent.

The gateway reserves the full context bound at the highest input/cache rate, plus requested maximum output. For a maximum-output request:

| Model | Reserved token ceiling | Reserved dollar equivalent | Concurrent full reservations within $12 |
| --- | ---: | ---: | ---: |
| Sonnet 5.5 | 1,032,768 | $4.32768 | 2 |
| Opus 5.5 | 1,032,768 | $8.65536 | 1 |

Actual provider usage releases unused reservation after reconciliation. A second concurrent Opus request can be rejected while the first is pending. This is a documented consequence of the fixed economic budget. The comparison does not promise equal affordable tokens or effective concurrency across models. No cap, reservation rule, or task timeout was relaxed.

The Opus case is selected before observing Sonnet outcomes. Do not choose an easier case, tune prompts, or adjust caps after inspecting either result. This small follow-up cannot establish general model or harness superiority.

## Offline evidence

Focused controls passed: 10 Python tests and 8 Clojure gateway tests with 74 assertions. They verify exact model/rate validation, wrong-model fixture rejection, proof mismatch rejection, retained Sonnet support, Opus forbidden request rejection, and the one-reservation limit under $12. Existing credential/HTTP controls also pass. All responses are scripted; no inference occurred.

The native Opus relay passed all ten checks on its first versioned attempt, at commit `395ca34`. The executed source hash is `7da393ba45e55b8614bcf13ae9b6ee783bb4a6ef33d00bbf2138d269e5988067`; the runtime digest is `16d07ea0085e8510a741ca5ae925e14c1b49b67bda0bf764200c3a9bc83b5929`. It used the same strict SCI/native image proofs and unchanged $12 arm allowance. All eleven requests used the exact Opus ID, adaptive/summarized thinking, and medium effort. There was no forced-tool or prefill request. SCI context execution, native Python tools and children, signed-thinking replay, manual compaction/refinement, OAuth headers, accounting, and cleanup passed.

Aljure recorded five complete fixture receipts (500 synthetic input tokens, 100 output tokens, $0.004 equivalent). Native Prime recorded six (600 input, 120 output, $0.0048 equivalent). These numbers are scripted ledger controls, not actual provider usage, benchmark costs, or evidence of model performance. The current short relay script reports 100 synthetic input tokens per response and invokes manual `/compact` and `/refine`; it does not simulate context-pressure triggering or provider latency.

The [report, raw archive, exact source snapshot, strict proof copies, and hashes](evidence/opus-followup-v1/) preserve the control. Full native request frames are in `prime/stdout.jsonl`; gateway requests, responses, and receipts are in each arm's `gateway/`; SCI execution events are in `aljure/agent/events.jsonl`. Actual provider compatibility remains unverified. The original Sonnet source and approved plan were not modified.

## Commands

From this follow-up checkout's `repl-lab/`:

```sh
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-relay-fixture --provider claude-oauth-subscription --config config/external-opus-subscription-proposal-v1.json --out var/benchmarks/opus-subscription-relay-v1
python3 -m benchmark paired-plan --suite var/official/pairs-one --config config/external-opus-subscription-proposal-v1.json --out var/opus-pairs-one-plan.json
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/opus-pairs-one-plan.json
```

Only after separate approval of the exact new plan and private credential configuration:

```sh
python3 -m benchmark paired-run --suite var/official/pairs-one --plan var/opus-pairs-one-plan.json --out var/benchmarks/opus-pairs-one-live-v1 --authorize-subscription-plan APPROVED_OPUS_PLAN_SHA256
```

Actual OAuth model access, quota, latency, and provider compatibility remain unverified. The fixture cannot establish these. Unknown outcomes retain their reservations; there is no model or API-credit fallback.
