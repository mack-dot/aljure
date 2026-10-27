# Native subscription gateway v1

Status: IMPLEMENTED / UNVERIFIED against a real provider. This work has sent no new model requests. The API plan and its execution checkout remain unchanged. Subscription use requires approval of a separate frozen plan.

## Why direct subscription use is feasible

Anthropic's current help page says SDK, `claude -p`, and third-party application use still draws Claude subscription limits when signed in with a Claude plan. Max API credits are a separate route that requires a linked Console API key. This gateway uses the subscription route. It does not consume those API credits through an automatic fallback. [Official account guidance, reviewed 2026-10-27](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).

Pinned Prime `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` already implements Claude Pro/Max OAuth:

- `crates/pa-core/src/auth/provider_oauth.rs` exposes the Anthropic subscription provider.
- `crates/pa-ai/src/oauth/anthropic.rs` defines the native login and refresh flow. This integration does not invoke either flow.
- `crates/pa-ai/src/providers/anthropic/mod.rs` selects OAuth when the credential contains `sk-ant-oat`. It sends Bearer authorization, OAuth beta headers, `x-app: cli`, and its pinned `claude-cli/2.1.281` user agent.
- `params.rs` inserts the native Claude Code identity before the harness prompt. `convert.rs` preserves tool structure and performs native tool-name conversion. `stream.rs` preserves signed thinking for later native tool turns.

These are native Prime behaviors. No Prime source or capability was removed or replaced. The installed Claude CLI is not used to run inference in this transport. Its local version therefore does not replace the version built into the pinned Prime protocol.

## Narrow implementation

`benchmark/subscription_protocol.py` records the public native protocol. The native disposable container receives only a clearly fake OAuth-shaped sentinel. The sentinel activates Prime's existing OAuth serializer. It cannot authenticate. The relay checks the sentinel locally, removes authorization from its event stream, and exposes only six allowlisted public headers.

The host checks those headers and the native identity block before admission. It forwards native bodies unchanged. Aljure gets the same identity prefix before admission. Its existing text/EDN history and non-streaming JSON response remain intact. Prime retains native SSE, Python tools, skills, asynchronous children, signed thinking, refinement, and compaction. Native cache markers remain intact; Aljure does not add an explicit cache marker to the identity prefix. These differences appear in the frozen capability metadata.

`ClaudeSubscriptionTransport` uses the existing bounded host HTTP subprocess. It reads the current OAuth credential only after durable budget admission. It sends Bearer authorization to the fixed Anthropic Messages endpoint. Redirects are refused. It never falls back to `ANTHROPIC_API_KEY`. Unknown outcomes keep their full reservations. Root, child, refinement, and compaction requests use the same global task ledger.

Credential sources must be selected explicitly. Supported sources are a private Prime/Claude JSON file, or one macOS Keychain service/account pair. Keychain reads have a five-second deadline and a one-MiB output bound. The loader checks token type and expiry. It ignores refresh tokens and never updates the store. Expired credentials require operator renewal. The HTTP process re-reads the selected source for each dispatched request so normal credential rotation does not require storing a token in a plan.

No token, refresh token, private account identifier, or credential path enters a plan, worker, prompt, trace, or report. `credential_status()` is an explicit read-only operator check. Normal benchmark preflight does not read credentials or contact a provider.

## Accounting and claim limits

The new proposal uses Sonnet 5.5 with adaptive/summarized thinking and medium effort. Sampling parameters remain absent. Rates remain $2/M ordinary input, $10/M output, $0.10/M cache reads, and $2.50/M or $4/M cache writes. The proposed $12 per arm and $24 total are API-rate-equivalent ceilings, not subscription invoices or expected costs. The prior API approval does not authorize this new plan.

Aggregate accounting covers all admitted native requests. Native parent/child/refinement attribution remains unverified where Prime omits identity. No timing-based attribution is invented. The known native input-usage parsing defect remains unchanged. Manual `/compact` and `/refine` controls test their request paths; they do not establish correct automatic triggering or autonomous improvement.

Offline fixtures cannot establish actual account/model compatibility, remaining plan quota, or provider acceptance of the pinned native protocol. The first authorized subscription request will test those boundaries. A failed request remains evidence and retains its reservation when usage is unknown. No API fallback or silent model change is permitted.

## Validation and commands

Seven new fake/local-HTTP tests passed. The focused combined transport suite passed 16 tests in 12.580 seconds. Tests cover separate authorization, explicit file/Keychain selection, expiry and scope checks, no API fallback, credential redaction, native body/header preservation, JSON/SSE EOF handling, redirect refusal, concurrent global reservations, and unknown-outcome retention. This is FIXTURE evidence, with zero external model calls.

The native subscription relay control is pending. Its versioned result will be added here after the other worker study releases Docker. The original API relay and all sealed experiments remain unchanged.

Run from the frozen subscription checkout, `repl-lab/`:

```sh
python3 -m unittest test_python.test_external_transport test_python.test_subscription_gateway -v
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-relay-fixture --provider claude-oauth-subscription --out var/benchmarks/subscription-relay-v1
python3 -m benchmark paired-plan --suite var/official/pairs-one --config config/external-subscription-proposal-v1.json --out var/subscription-pairs-one-plan.json
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/subscription-pairs-one-plan.json
```

Only after approval of the exact new plan hash and private credential configuration:

```sh
python3 -m benchmark paired-run --suite var/official/pairs-one --plan var/subscription-pairs-one-plan.json --out var/benchmarks/subscription-pairs-one-live-v1 --authorize-subscription-plan APPROVED_PLAN_SHA256
```

The execution command accepts only the authorization flag for its frozen transport. An API hash cannot authorize a subscription plan, and a subscription hash cannot authorize API billing.
