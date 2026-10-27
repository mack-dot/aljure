# Sonnet 5.5 API contract review

Reviewed on 2026-10-27. Evidence: public provider documentation and read-only
inspection of pinned Prime source. Model requests: **0**. This review neither
authorizes API billing nor changes any prior experiment or its accounting.

## Verified public contract

The requested Claude API model ID is `claude-sonnet-5-5`. Its documented context
limit is 1,000,000 tokens and output limit is 128,000 tokens. The base rates are
$2 per million input tokens and $10 per million output tokens. Cache rates per
million tokens are $2.50 for five-minute writes, $4 for one-hour writes, and
$0.10 for reads. These are published rates, not measured invoices or confirmation
of access for a particular account.

Sources: [model specification](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
and [current pricing table](https://platform.claude.com/docs/en/about-claude/pricing).

Anthropic identifies dateless IDs from generation 4.6 onward as fixed model
snapshots. Serving infrastructure can still change. Preserve the returned model
ID and request date for each call.
[Model IDs and versioning](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions).

## Problems found in the draft external proposal

The proposal at integration commit `35cd465` used `thinking.type=disabled`, a
200,000-token context bound, and a $0.20 cache-read rate. The official migration
guide says Sonnet 5.5 rejects `disabled`. It accepts `adaptive` or
`between_tools`. It also rejects sampling parameters and forced `any`/`tool`
tool choice. `between_tools` accepts no extra thinking fields and requires effort
no higher than `high`. A scripted transport accepting the old request does not
establish live API compatibility.
[Migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide).

The gateway reserves the whole documented context bound at the highest supported
input/cache rate, plus requested output. At 1M input and 32,768 output tokens,
one reservation is $4.32768. The draft $2-per-arm allowance cannot admit it.
That number is a conservative reservation, not expected task cost. Concurrent
requests require separate reservations. Any replacement caps need new operator
approval. Do not weaken the reservation to make an unapproved plan run.

## Pinned native implementation

Prime remains pinned to `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`.
Its `crates/pa-ai/src/providers/anthropic/params.rs` emits `disabled` for the
current `--thinking off` route. Its supported adaptive route can emit
`thinking={type:adaptive,display:summarized}` with an explicit effort.
Use a documented native configuration and match it in Aljure. Do not rewrite
requests secretly or modify upstream Prime. Confirm actual emitted bodies for
root and child requests before calling the configuration ready.

Native tool loops must return complete thinking blocks and signatures. Aljure's
current text/EDN route does not use API tool blocks; omission of previous thinking
blocks is allowed for that route. This is a harness difference to disclose.
Thinking tokens count toward output limits and billing even when their text is
omitted. A synthetic signature replay can test transport preservation but cannot
test provider signature validation.
[Thinking protocol](https://platform.claude.com/docs/en/build-with-claude/thinking).

## Remaining live boundary

The frozen API comparison remains unchanged and has dispatched no inference.
The operator approved that exact API plan, then asked to use the subscription.
Native Prime supports Claude subscription OAuth in its pinned Anthropic provider;
an API key is not inherently required. A separate host-only subscription gateway
is now being tested. It must preserve the native OAuth identity, tool names,
thinking blocks and headers. The real credential must stay outside both workers.

Anthropic's current guidance permits third-party, Agent SDK and `claude -p`
usage against subscription limits. API keys from a linked Console organization
use a separate API-credit allowance. Do not conflate these routes or silently
fall back between them. [Subscription guidance](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).

The local Max login and a valid OAuth credential were confirmed without a model
request. This establishes credential availability at that time, not provider
acceptance of benchmark requests. Tokens expire; dispatch must recheck validity.
The historical CLI adapter pins 2.1.310, while the installed CLI is 2.1.311. That
old pin remains unchanged. Direct native OAuth is a separate versioned transport.
Keep the subscription protocol and plan distinct from the approved API plan.
The first approved subscription attempt then returned a real Sonnet 5.5 response.
Its usage object contained `speed: "standard"`, which the initial gateway omitted
from its allowlist. The new parser accepts standard speed and still rejects fast
or unknown speed pricing. The raw response and the stopped run are preserved in
[the first-pair report](PRIME_HEAD_TO_HEAD_V1_RESULTS.md). Basic account/model access
is confirmed for that request; native provider tool loops and task performance
remain unverified. [Usage speed semantics](https://platform.claude.com/docs/en/build-with-claude/fast-mode#checking-which-speed-was-used).
