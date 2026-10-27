# Prime head-to-head v1: frozen protocol and current blocker

**LIVE MODEL RUN — stopped after one response. No completed head-to-head.**

The Claude subscription login was renewed through the normal CLI login command.
The final credential, isolation and accounting checks passed. The approved frozen
Sonnet protocol ran once. Aljure received a real HTTP 200 response from
`claude-sonnet-5-5`, but the local gateway rejected its usage receipt. The stop
rule then prevented Prime from starting. Neither arm produced a benchmark answer.
The original API protocol remains unused. Opus and the ten-case study remain
unapproved and unrun.

## Observed outcome and failure

| Measure | Aljure | Native Prime |
| --- | --- | --- |
| Actual provider responses | 1 | 0; not dispatched |
| Provider-reported input / output tokens | 2,416 / 20 | 0 |
| API-rate-equivalent from the saved receipt | $0.005032 | $0 |
| Agent tool executions / final answers | 0 / 0 | 0 / 0 |
| Attempt wall time | 7.921 seconds | Not attempted |

The model returned `{:op :context/metadata :handle "context"}`. This is a request
to inspect context, not evidence that inspection executed. Receipt rejection
stopped the controller before it could run the command. No child session, SCI
computation, skill creation, or policy/harness improvement occurred in this attempt.

The provider included `usage.speed: "standard"`. The frozen gateway's strict
allowlist omitted `speed`, so `usage-cost` raised `Missing, invalid or unpriced
usage`. The raw HTTP 200 response and token counters survived in the event log.
This is a local accounting compatibility failure, not a model reasoning failure.
The documented field distinguishes standard and separately priced fast mode.
[Provider speed semantics](https://platform.claude.com/docs/en/build-with-claude/fast-mode#checking-which-speed-was-used).

The original ledger conservatively holds one unknown reservation of **$4.32768**
and 1,032,768 tokens. It remains unchanged. Offline replay of the saved response
with only the new `speed` field removed reproduced the rejection boundary and
computed 2,436 total tokens / $0.005032 equivalent. The fixed parser accepts
standard speed and still rejects fast, unknown and malformed speeds. A separate
analysis copy reconciles that one receipt while retaining `gateway-stopped`.
This is postmortem accounting, not a resumed or improved experiment result.
Actual subscription invoices remain unknown.

The raw scorer assigns zero to each incomplete slot and mechanically reports a
tie across one planned pair. **That is not a measured tie.** There are zero
completed pairs, and Prime was never attempted. The original report is preserved
without relabeling its fields. Neither harness has demonstrated an advantage.

Exact evidence: [immutable file hashes and archive](evidence/prime-head-to-head-v1-live-attempt1/manifest.json),
[raw run](evidence/prime-head-to-head-v1-live-attempt1/raw-run.tar.gz),
[provider response](evidence/prime-head-to-head-v1-live-attempt1/provider-response.json),
[original report](evidence/prime-head-to-head-v1-live-attempt1/report.json),
and [original normalized results](evidence/prime-head-to-head-v1-live-attempt1/results.jsonl).
Inside the archive, `00-aljure/gateway/events.jsonl` sequence 4 is the HTTP response;
sequence 5 marks it unknown. `00-aljure/agent/events.jsonl` shows the root failure.
`01-prime/gateway/usage.jsonl` is empty. Both SQLite stores passed integrity checks.
No experiment worker remained after cleanup.

A separate pre-dispatch Keychain problem also occurred: the reader parsed a valid
credential, then prematurely killed Apple's utility during normal teardown and
received `EPERM`. No provider request occurred at that stage. The run used the
already supported private-file credential option, outside the repository and
workers, with mode 0600 and no copied refresh token. That temporary file was
removed after the run. The new reader waits for normal exit within the same
deadline. Credentials and authorization URLs were never printed or archived.

The operator requested these engineering fixes. The sealed run, model, scoring,
thresholds, budgets and frozen source were not changed or rerun. The recommended
next experiment is one new versioned Sonnet pair after the repaired transport
passes offline replay. It must preserve this failure and receive its own concrete
execution authorization; Opus and the ten-case study should remain on hold.

## Executed subscription protocol

The same official Pairs case, model, scoring rules, worker images, arm order and
failure rules below apply. The transport uses Claude subscription OAuth, with no
API-key fallback. The caps are **$12 per arm / $24 total API-rate-equivalent**,
not subscription invoices. Root, child, refinement and compaction calls share
the existing accounted boundary. Credentials stay on the trusted host.
The [approval receipt](evidence/subscription-gateway-v1/subscription-pairs-one-authorization.json)
and [initial expired-token preflight](evidence/subscription-gateway-v1/approved-preflight-status.json)
record the authorization and earlier blocker. The later request to also try Opus is a separate follow-up;
it does not change this Sonnet protocol.

- Source: `a72b8c0200302cc8dfd4e904d4f8c23370ab2fcb`.
- Full source SHA-256: `30ef1d62e2ed8d2a69c2125df6c75f30dd15858affde16615bc969fadf069754`.
- Runtime SHA-256: `fd2e5d73c4152602516ad03ee35c93e4c65d1378c3ecf7ee4b0d4e843dce7692`.
- Plan SHA-256: `92a6f0cf5de31273e69bc140d5124219442663bfc1e581234bc7a0bd9ff804a4`.
- [Frozen plan](evidence/subscription-gateway-v1/subscription-pairs-one-plan.json)
  and [preflight](evidence/subscription-gateway-v1/subscription-pairs-one-preflight.json): ready, no blockers, zero model calls.

The new native OAuth relay passed all ten checks: native root/child/tool calls,
manual compaction/refinement, signed thinking, SCI context, shared budget,
OAuth protocol and cleanup. Six native and five Aljure requests used scripted
responses. The focused transport suite passed 16 tests. These are **FIXTURE**
results. Actual provider acceptance, quota and benchmark scores remain unverified.
An unexpired credential is also required at dispatch; a prior metadata check is
not a permanent authentication guarantee. [Transport details and raw evidence](SUBSCRIPTION_GATEWAY_V1.md).

The dedicated checkout remains frozen. These were the execution commands. The
existing output directory must not be reused, and this run is not authorized for retry:

```sh
cd /Users/mackianni/aljure-subscription-gateway/repl-lab
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/subscription-pairs-one-plan.json
python3 -m benchmark paired-run --suite var/official/pairs-one --plan var/subscription-pairs-one-plan.json --out var/benchmarks/subscription-pairs-one-live-v1 --authorize-subscription-plan 92a6f0cf5de31273e69bc140d5124219442663bfc1e581234bc7a0bd9ff804a4
```

The trusted process selects the existing private Keychain source before execution.
No credential is supplied in these commands. This proposal excludes ten-case and
selector inference. Both still need separate approval.

## Separate requested Opus follow-up

The operator also requested Opus. The new protocol uses `claude-opus-5-5` with the
same official case, prompts, scoring, output allowance and time limits. Its source
is frozen separately at `d10f779396cbe3ee1d46d19ecc1cd5d6ba421188`.
Plan SHA-256: `6017c3c139ba5f35498bc61cd3d8a441cec8817613e1ab6c650bacaa1b48f52c`.
The [plan](evidence/opus-followup-v1/opus-pairs-one-plan.json) and
[preflight](evidence/opus-followup-v1/opus-pairs-one-preflight.json) are preserved.

Its ten-check native relay and preflight passed offline. This is an **additional,
unapproved $24 equivalent** allocation, $12 per arm. Together the two model
campaigns would have a $48 ceiling. Higher Opus rates permit only one full
concurrent reservation under $12, compared with two for Sonnet. That economic
constraint must remain visible. The case was selected before either live result.
See [contract, limits and exact commands](OPUS_FOLLOWUP_V1.md).

## Preserved API first pair

| Item | Frozen value |
| --- | --- |
| Aljure source | `ac34a0f03b22623f211710875dee01dd36643156`, clean checkout |
| Full source SHA-256 | `24a4fa5badfb13944ea8ea78966bf2a788eb8b33e4f0a0763c408112eba50b0f` |
| Execution/config SHA-256 | `255dfb5c55e94a9c53321ffabab4fdec33bb37b9d77f63fed71943a00483f671` |
| Native Prime | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, unmodified |
| Official task | `oolong-pairs-validation-8192-1` |
| Suite SHA-256 | `e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded` |
| Pairs scorer SHA-256 | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Model/provider | `claude-sonnet-5-5`, Anthropic Messages API |
| Thinking | Adaptive, summarized display, medium effort; sampling parameters omitted |
| Output ceiling | 32,768 tokens per request, including thinking |
| Per-arm caps | 12 calls, 12,000,000 accounted/reserved tokens, $12, 120 seconds |
| Pair ceiling | **$24 API usage at configured rates; approved, credential-blocked** |
| Pair order | Aljure, then Prime; no selective retries |
| Plan SHA-256 | `39c383fb51f77f1c7806a0c8816409a45eb94ca124ce52e83bd162d40d5af5dc` |

The first matching upstream row was selected before model execution. It has not
been consumed by an Aljure/Prime model run in the preserved project evidence.
This is a public benchmark; prior model-training exposure is not established.
Pairs questions/gold are pinned to `mit-oasys/oolong-pairs` revision
`d1e1522b86ac0c169bbc890b0471408aaa29e8fa` (declared MIT license). The unlabelled
`trec_coarse` validation context is pinned to OOLONG synth revision
`81d2f8d9349f6ff329d695f9be494051e9f05cb9`. The Apache-2.0 Pairs parser/F1 scorer
is pinned to `research-environments` revision
`ba10ef5a303943a08e1ccf92f9c0d63b1159b369`. See
[source verification and scoring semantics](OOLONG_SOURCES.md).

Both agents receive the same original question and unlabelled context. The shared
answer-format instruction adapts the upstream output path without changing F1.
Prime reads `/work/context.txt`; Aljure receives `external-context` in isolated SCI
and a line-query broker. Gold and scorer metadata stay outside both workers.
The scorer sees the answer and gold, not the harness identity.

The frozen plan contains source/prompt-template hashes and a capability matrix.
Actual native prompt bodies, hashes and returned model IDs will be recorded at
dispatch; they do not exist yet for this live campaign. State starts fresh in
both arms. The approved initial Aljure library for this external task is empty.
Prime keeps its native Python tools, skills, subagents and refinement mechanisms.

## Accounting and failure rules

The documented 1M context bound is reserved at the highest permitted input/cache
rate, plus the requested output ceiling. A full 32,768-output request reserves
**$4.32768**. This is a conservative bound, not predicted task cost. The common
dollar cap can limit concurrent admissions below the configured eight-request
ceiling. Actual billed-token receipts reconcile reservations; unknown outcomes
retain their full reservation. No allowance transfers between arms.

All root, child and native housekeeping requests cross this boundary. Cumulative
SSE counters are merged, not summed. Provider invoices are not measured. Native
per-agent ancestry/purpose attribution remains unverified even when every request
is accounted for. No subscription-to-API or model fallback occurs.

The host transport does not retry. A retry initiated by native Prime must enter
the gateway as another charged request. A provider-unknown outcome, cleanup failure
or runner exception stops later dispatch. Unattempted cases and runtime failures
remain in the denominator. No failed arm is rerun or replaced. Timeouts, program
errors and ordinary incorrect answers remain recorded outcomes; the independent
scorer never turns a failed empty output into a successful empty answer.

SCI image: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Native image: `sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
Both strict gates passed. Every negative probe requires same-worker readiness;
the native allocation probe also requires actual OOM evidence. Unconfirmed removal
sets quarantine. No isolation or scoring threshold was relaxed.

## What the offline evidence establishes

Merged regression: **75 Clojure tests / 1,554 assertions; 83 Python tests**, all
passed. The corrected relay v6 exercised actual SCI and native processes using
scripted responses: five Aljure requests and six Prime requests, including native
child, manual compaction and manual refinement calls. Signed thinking blocks
survived the native tool loop. All nine relay checks passed and cleanup completed.
This is **FIXTURE**, not real-provider validation or an official task score.

Earlier startup, cleanup, non-OOM-control and relay failures remain preserved.
The pinned Prime parser reads initial input usage from the wrong nesting level
for the preserved valid stream. The external ledger records it correctly. Manual
housekeeping passed; automatic triggering remains unverified. The short offline
control used explicit `/compact` and `/refine` plus a smaller retained-history
setting to exercise those paths. Production task runs retain native defaults.
[Exact traces and source references](EXTERNAL_COMPARISON_V1.md).

Other differences remain material: Prime has native filesystem/package/process
tools and asynchronous subagents; Aljure uses its EDN capability broker and
synchronous children. SCI has a ten-second expression limit. Prime has a whole-task
watchdog. Prime's Rust host shares its 256MiB container with Python; Aljure's trusted
controller runs outside the worker with a 512MiB heap cap. Whole-system compute
envelopes are not equal. Local compute cost is unpriced. This first diagnostic
matches inference caps; it cannot establish equal total economic cost, a language
effect, continual-learning superiority or statistical superiority.

## Predeclared ten-case follow-up

After the first Pairs result, the proposed follow-up is the fixed first ten official
OOLONG-synth `negation` test rows in the 32K profile. IDs run from `415040016` through
`415040025`. Suite hash:
`cf8cb56d4bcaa1558f168740ea517d72652395edbd47c67ba44159ceb1256bb1`.
Plan hash: `5653483eb5835ba7e1b2ab59d941c1e4c3ef82e0844fcaf4a8897190d4837890`.

The same per-arm settings/caps give a **$240 ceiling for twenty disjoint task
allowances**, requiring separate approval. This is not an estimate of likely spend.
Arm order alternates by case. Selection does not change based on the first score.
Any necessary engineering revision requires a new declared protocol before its
execution. These ten questions share one context and cannot be treated as ten
independent benchmark observations. Report every outcome descriptively.

## Exact next commands

The existing separate checkout stays frozen while Track B develops elsewhere:

```sh
cd /Users/mackianni/aljure-benchmark-integration/repl-lab
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-preflight --suite var/official-import-validation/oolong-pairs-8192-1 --plan var/prime-head-to-head-v1/one-plan.json
```

That command makes no model call and returned `ready: true`. The exact API plan
is approved. It still requires private `ANTHROPIC_API_KEY` configuration and a
decision to proceed with that transport; subscription work must not overwrite it:

```sh
python3 -m benchmark paired-run --suite var/official-import-validation/oolong-pairs-8192-1 --plan var/prime-head-to-head-v1/one-plan.json --out var/prime-head-to-head-v1/live --authorize-api-plan 39c383fb51f77f1c7806a0c8816409a45eb94ca124ce52e83bd162d40d5af5dc
python3 -m benchmark compare --suite var/official-import-validation/oolong-pairs-8192-1 --results var/prime-head-to-head-v1/live/results.jsonl --out var/prime-head-to-head-v1/independent-rescore.json
```

Never put a credential in command arguments or artifacts. The approval hash is
an operator attestation, not permission for an assistant to infer approval.
The earlier $35 Claude subscription experiment does not authorize this campaign.

[Frozen plans, preflight, source identities and merged test logs](evidence/prime-head-to-head-v1/).
Raw control traces and checksums are in
[the corrected-contract archive](evidence/external-comparison-contract-v2/summary.json).
