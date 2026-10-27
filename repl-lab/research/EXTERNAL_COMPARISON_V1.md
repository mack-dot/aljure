# External comparison v1

Status: IMPLEMENTED / UNVERIFIED for live inference. No new API or subscription
inference is authorized. This work does not reuse the earlier $35 subscription
experiment authorization. No live comparison or learning result is claimed.

The runner uses the existing Aljure controller, isolated SCI worker, pinned native
Prime adapter, independent OOLONG scorers, and durable accounting ledger.
Prime source remains unmodified at
`c4c238ca025e382d96fb5f37e6328ca77fb82ef3`. Native Python tools, executable skills,
subagents, messaging, refinement and host-side compaction remain available.
There is no faux-provider flag in the external native adapter.

## Official inputs and independent scoring

`benchmark/official.py` downloads only pinned public artifacts and verifies their
byte counts and SHA-256 hashes. The first one or ten matching upstream rows are
selected before any agent result exists. The public task directory contains the
question and original context, never answers, label-augmented context or scoring
metadata. Gold remains in the controller directory.

The runner supports OOLONG-synth negation at 32K/128K and official OOLONG-Pairs
trec_coarse at 8K/32K. Pairs uses the pinned official pair parser and F1 function.
These selected profiles are pilot subsets, not the complete published benchmark.
See [OOLONG_SOURCES.md](OOLONG_SOURCES.md) for source pins, licenses and import
evidence. Ten cases in each selected profile share one context. They are not ten
independent benchmark observations.

Both agents receive identical original text outside the model window. Prime reads
`/work/context.txt`; the SCI worker receives the `external-context` binding through
bounded initialization chunks. Aljure also retains its context query broker.
The independent scorer ignores harness identity. Failures stay in the denominator.

## Common transport and accounting

The new host transport forwards Anthropic Messages bodies, client tools and bounded
SSE responses through the existing accounting gateway. The gateway reserves the
full declared context bound plus requested output before dispatch. Root, child,
refinement and compaction requests share one atomic per-task ledger. Four scripted
concurrent request intents and over-budget rejection pass the same bridge. Unknown
outcomes retain reservations and stop further dispatch. No automatic retry occurs
in the host transport. A native retry is a new independently charged request.

Task allowances are disjoint. Their sum cannot exceed the frozen experiment cap;
unused task allocations cannot migrate to a different task. The sequence alternates
which harness starts each case. Both receive the same model, sampling/thinking
configuration, token/call allowances, cost rates, dollar cap and 120-second deadline.
All source, task, prompt-bearing request, container, capability and library evidence
is preserved. Actual requested and returned model IDs are checked.

Aggregate accounting and caller attribution are distinct. Every request crossing
the sole provider route is reserved and reconciled. The normalized ledger states
`agent ancestry unverified`. It does not infer parentage or refinement/compaction
purpose from timing or request text. Native session transcripts are retained for
inspection, but this implementation does not claim exact cross-linked native
ancestry for every provider receipt. Refinement/compaction request coverage is a
scripted gateway control, not evidence that native automatic refinement ran.

The Claude subscription adapter is a text/EDN CLI route. Native Prime needs an
Anthropic Messages stream with tool-call semantics. Subscription compatibility for
that route remains unverified. The CLI refuses a subscription plan; it never changes
subscription requests to API billing. The new API transport reads credentials only
on the trusted host, after explicit authorization and a durable reservation. No
provider credential enters either generated-code worker or any trace.

## Actual isolation and failed control

Native negative probes now require a readiness message and a host acknowledgment in
the same container before the negative operation begins. An early timeout is an
infrastructure failure. The proof covers the probe code and both supervisor sources.
All nine actual native controls passed once on image
`sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.

The first positive probe exposed a supervisor bug: valid JSON scalar output `42`
was forwarded to a handler that expected an object. This was fixed and tested.
The failed diagnostic is preserved at
`var/prime-readiness-diagnostic-1793073408921289000.json`.

The first common relay invocation stopped in preflight because a completed Clojure
doctor process retained its executor threads. The preflight now shuts those threads
down. It made no model calls.

The next control, `var/external-relay-control-v2`, FAILED. SCI workers hit Docker
create timeouts at the existing five-second supervisor bound. A direct diagnostic
at `var/external-worker-diagnostic/` records that failure and confirmed cleanup.
Prime produced its scripted answer through a native root, child and Python tool,
with four complete gateway receipts. Native cleanup was not confirmed within the
existing bounds, so the control failed and set quarantine. The marker was preserved
under the failed run before the existing recovery command verified absence. No
timeouts or isolation limits were increased. This failure is infrastructure evidence,
not a score, language result or model result.

The final versioned control report is the authority for whether the combined path
passed. Live preflight requires a successful relay proof tied to current source and
both image digests. It refuses failed, missing or stale proofs.

## Limits on the comparison

`benchmark/paired.py::CAPABILITIES` is the machine-readable difference record.
This is a complete-harness pilot, not a causal language comparison. Native Python
has filesystem/process/package tools that SCI lacks. Prime gets an additional
8MiB writable `/work` area. Aljure has a 10-second expression watchdog; Prime has a
whole-task watchdog. Aljure children are synchronous; Prime children are native
asynchronous agents. The API gateway buffers bounded SSE before returning it.

The common maximum output allowance is recorded, but native Prime chooses smaller
per-request maxima in some paths. The runner records those bodies rather than
silently rewriting native requests. Both start with fresh task state. Aljure's
retained library is empty in this initial external configuration; its existing
scheduling development/promotion evaluator is not exposed to OOLONG. Native Prime
keeps its native within-task skills/refinement machinery. This is not continual-
learning parity or a claim that the strongest possible Aljure configuration ran.

Remaining live prerequisites are: a passing current combined relay control; verified
primary-source model context and cache-price bounds; explicit approval for the new
API transport and frozen caps; private API credential configuration; and the first
actual provider response. Model availability is not tested by an offline fixture.
The JSON proposal deliberately marks the model contract unverified.

## Commands

Run from `repl-lab/`. Data preparation and the scripted control make no model calls:

```sh
python3 -m pip install -r benchmark/requirements-official.txt
python3 -m benchmark prepare-official --suite oolong-synth --cache var/official-cache --count 1 --context-len 32768 --out var/oolong-one-v1
python3 -m benchmark prepare-official --suite oolong-pairs --cache var/official-cache --count 10 --context-len 32768 --out var/pairs-ten-v1
source var/worker.env
source var/prime-worker.env
make prime-isolation-test
make benchmark-relay-fixture OUT=var/external-relay-control-new-version
python3 -m benchmark paired-plan --suite var/oolong-one-v1 --config config/external-paired-proposal.json --out var/oolong-one-plan.json
python3 -m benchmark paired-preflight --suite var/oolong-one-v1 --plan var/oolong-one-plan.json
```

Use `--offline` on data preparation to require an already verified local cache.
The ten-case plan needs an explicitly reviewed total allocation of twenty per-arm
allowances. The sample proposal covers one pair only; it grants no spending.
Freeze the plan after source changes and the final passing transport control.

Only after separate operator approval and private API credentials:

```sh
python3 -m benchmark paired-run --suite var/oolong-one-v1 --plan var/oolong-one-plan.json --out var/oolong-one-live-v1 --authorize-api-plan APPROVED_EXACT_PLAN_SHA256
python3 -m benchmark compare --suite var/oolong-one-v1 --results var/oolong-one-live-v1/results.jsonl --out var/oolong-one-rescored.json
```

Never put a credential in those arguments. A missing or mismatched authorization
hash stops execution before a transport is constructed. Passing a hash is a CLI
operator attestation; agents must still obtain actual user authorization.
