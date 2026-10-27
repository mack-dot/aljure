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

## Preserved earlier offline evidence

The serial control `var/external-relay-control-v4` PASSED its scripted contract at source commit
`35cd465`. Aljure's root and child each executed SCI over the supplied external
context. Native Prime's root and child executed Python through its native tools.
Both produced the independently checked answer. The common ledger contains all
nine scripted provider requests: five Aljure requests and four Prime requests.
All reservations reconciled. Both SCI workers and the native container were removed.
Actual native isolation had passed all nine same-worker readiness controls before
the common relay runs. Review then found that its allocation check accepted exit
137 without checking `OOMKilled`. That proof is insufficient for OOM attribution
and is superseded by the strengthened gate described below. This is **FIXTURE**
evidence, with zero live model calls.

The official imports and scoring tests are separate evidence. No agent has yet
attempted a live official OOLONG or OOLONG-Pairs task through this runner.
The full regression run passed 75 Clojure tests / 1,554 assertions and 79 Python
tests. One subsequently added attestation test also passed. It checks that reports,
evidence, test files and plan output cannot invalidate execution attestation, while
runtime, configuration, prompt, scorer and dependency changes do invalidate it.

The preserved v4 runtime attestation is
`08b46ee13f36b01cd871d604139bbe8b4eb93514bd3cdf433c706205a83dd946`.
Full source provenance remains separate. The v3 and v4 full source hashes are
preserved in their original reports. A live plan freezes the full current tree;
relay preflight compares the narrower execution/configuration attestation. Adding
this report and its raw evidence therefore does not bypass or invalidate the
validated runtime proof.

Raw controls, failed attempts, strict isolation proofs, official import manifests,
file hashes and test counts are packaged under
[evidence/external-comparison-v1](evidence/external-comparison-v1/summary.json).
`raw-controls.tar.gz` preserves the complete local traces. Inspect archived native
state as data; do not load serialized Python state into a host interpreter.

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
Local computation is recorded as elapsed time and enforced resource limits. It is
not assigned a dollar price. The proposed dollar caps bound model inference; they
do not establish a fixed total economic-cost comparison or measured provider bill.

Remaining live prerequisites are: a passing current combined relay control; explicit approval for the new
API transport and frozen caps; private API credential configuration; and the first
actual provider response. Model availability is not tested by an offline fixture.

## Sonnet 5.5 contract correction

Read-only verification found that the earlier scripted contract was unsuitable for
the real API. Sonnet 5.5 has a 1M context window, a 128K output maximum, and a $0.10
per-million cache-read rate. Its input/output rates remain $2/$10; cache writes are
$2.50 for five minutes or $4 for one hour. The new proposal uses those documented
values. They describe provider capabilities, not observed account responses.
[Official model documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)

The API rejects disabled thinking and sampling parameters. The new experiment
configuration uses adaptive thinking, summarized display and medium effort. Native
Prime receives `--thinking medium` and its supported custom `thinkingLevelMap`
sets the experiment's minimum to medium. This matters because compaction and
refinement use the native minimum, rather than the root's requested level. No
outgoing native request is rewritten. The gateway rejects a request that differs.
[Official migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)

Native tool loops must return signed thinking blocks unchanged. A new scripted
control supplies a signature and checks that native subsequent requests retain it.
Aljure uses text/EDN messages, with no API tool-use/result blocks, and may omit prior
thinking under the documented rules. Both raw responses remain in gateway traces.
This interface difference is recorded; it is not a language-only comparison.

The whole-context reservation at the highest cache rate is $4.32768 for a request
with the experiment's 32,768-token output ceiling. The old $2-per-arm proposal
cannot admit even one request. The replacement proposal is **$12 per arm / $24 per
pair, unapproved**. It is a conservative inference ceiling, not expected cost or
reuse of the previous subscription allowance. A ten-case disjoint-allocation plan
would require a separate larger approval; no such plan is authorized.

The strengthened native gate records `docker.State` in each container before
cleanup. Exit 137 passes allocation restriction only with `OOMKilled=true`.
An intentional non-OOM SIGKILL control must be rejected as allocation evidence.
Earlier native gate proofs and earlier v3/v4 relay controls remain preserved.

Gateway recovery now derives its evidence category and bridge protocol from the
persisted manifest. A LIVE ledger cannot turn into FIXTURE evidence during recovery.
Unknown attempts retain their reservations and separate uncertainty count. The
recovery regression test uses metadata only and sends no provider request.

## Current verified control: v6

`var/external-relay-control-v6/report.json` PASSED at `e889509`. Its runtime digest is
`255dfb5c55e94a9c53321ffabab4fdec33bb37b9d77f63fed71943a00483f671`.
All nine combined checks passed. Five scripted Aljure requests and six scripted
native Prime requests were reserved and reconciled. The native requests included
two root calls, two child calls, one manual compaction and one manual refinement.
Both SCI workers computed the context length. Native tool loops returned the
synthetic thinking signature unchanged twice. Both answers were independently
checked. Cleanup succeeded. No actual model response or official benchmark score
was produced.

Every captured request used adaptive/summarized thinking with medium effort and
omitted sampling parameters. Root and child requests used the common 32,768 output
ceiling. Native compaction requested 13,107 output tokens and refinement 32,000;
these were preserved, not overwritten. The native model catalog's minimum mapping
kept all four call types on the pinned thinking configuration.

The fixture appends supported `/compact` and `/refine` commands after the task in
the same native print-mode process. Only this short control sets native
`keepRecentTokens=1`, so compaction has an old prefix to summarize. Production
comparisons append no commands and retain native compaction settings. This proves
manual housekeeping transport, settings and accounting. It does not prove that
automatic compaction or autonomous refinement improves performance.

The previous corrected-contract v5 control remains FAILED. Root/child settings,
signatures, SCI execution, independent answer checks and accounting passed, but
the attempted automatic housekeeping trigger did not run. The pinned reader at
[`stream.rs:298`](https://github.com/PrimeIntellect-ai/prime-agent/blob/c4c238ca025e382d96fb5f37e6328ca77fb82ef3/crates/pa-ai/src/providers/anthropic/stream.rs#L298)
reads initial usage directly from `message`, rather than `message.usage`. In v5,
the gateway recorded 995,000 scripted input tokens for provider response
`fixture-fe571e98440b4ab6babb858cacc5bc54`; the native transcript recorded zero.
Exact references are `v5/prime/gateway/events.jsonl` and
`v5/prime/native/sessions/01a17ba0-13f1-753d-9806-f449826e438c.jsonl` inside the final
evidence archive. A later delta with input usage might compensate on some streams;
actual provider behavior remains unverified. The gateway supplies authoritative
aggregate accounting without changing native behavior. This is a pinned native
limitation, not an Aljure win.

Strict native gate version 3 passed all nine original restrictions/reset controls
plus a separate non-OOM kill-rejection control. Allocation exit 137 had
`OOMKilled=true` in the same container. Host-side KILL had `OOMKilled=false` and was
correctly rejected as allocation-limit evidence. An earlier self-signal control
exited zero because of namespace-init signal behavior; that failed gate report is
preserved as well.

The latest focused regression command passed 18 Python tests. These include live-
category recovery without a provider call, real localhost Content-Length/chunked
EOF checks, and a slow-drip process test that verifies total deadline and cleanup.
Seven Clojure gateway tests / 61 assertions also passed after the recovery change.
The earlier full runs passed 75 Clojure tests / 1,554 assertions and 79 Python tests;
the subsequently added tests are recorded separately in the evidence packet.

The API transport runs in a killable trusted host process. It uses `read1` and a
remaining socket timeout, handles closed-response EOF, enforces an outer total
deadline even for slow headers, and cancels/joins pending transport work. It has
never contacted the Anthropic API during these controls.

One further resource difference must remain explicit: the 256MiB/one-CPU limits
apply to generated-code workers. Prime's Rust host also runs inside its container;
Aljure's trusted controller JVM runs on the host with its existing 512MiB heap cap.
These are not identical whole-system CPU/memory envelopes. Report total elapsed
time and worker limits separately; do not infer equal total compute cost.

Current traces, strengthened proofs, failed v5 evidence and checksums are in
[the corrected-contract evidence packet](evidence/external-comparison-contract-v2/summary.json).

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
