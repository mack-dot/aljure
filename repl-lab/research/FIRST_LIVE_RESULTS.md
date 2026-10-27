# First live self-improvement experiment

**Status: NOT RUN — explicit experiment and cap approval is still required.**

This document records preflight evidence. It does not report a learning result.
No new inference was requested. Outcomes A–D cannot be assigned before a real
acquisition attempt. The prior capability smoke and developer fixtures remain
separate evidence.

## Baseline and identifiers

Preflight ID: `first-live-20261027T003144Z` (UTC).
The checkout was clean when the baseline was recorded.

| Item | Recorded value |
|---|---|
| Source commit | `3a5d517a858aef384caa3fb2f43e09be9cce9462` |
| Aggregate source hash, 82 files | `c51373f19902389af1e7557aaffe0f203dbdab1cc1b310b6bf36faf7a217cafd` |
| Model-facing EDN prompt SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| SCI worker image | `sha256:508f6f195f8837324f2c52ec87b193eb7fc79334de8948ff300b8585df03b37a` |
| Claude Code version | `2.1.310 (Claude Code)` |
| CLI binary SHA-256 | `ffb64331bc0ee1b69efb7c2c428bd3ab516bc31b75bf60886b356c97c1c25ffd` |
| Requested model | `claude-sonnet-5-5` |
| Provider | `claude-code-subscription`, existing Claude Max / first-party login |
| Returned model for this experiment | Not observed; no request made |
| New live experiment/run IDs | Not created |

[FIRST_LIVE_PREFLIGHT.json](FIRST_LIVE_PREFLIGHT.json) records every source-file
hash, base configuration, planned phase configurations, runtime versions, public
transport metadata and preflight measurements. All 82 source files still matched
after the checks. Simulator, promotion thresholds and scoring code were unchanged.
No new held-out or cold-boot split was generated or consumed. The acquisition
command creates and hashes its existing split design after authorization.

## Fixed proposed configuration

The output limit is 2,048 tokens per request. Prompt caching and native CLI tools
are disabled. Sampling and thinking use the pinned CLI's defaults; no explicit
equivalent sampling configuration has been validated against another harness.
All experimental root and child calls pass through Aljure's shared task ledger.

| Phase | Planned cases | Calls / tokens per task, including children | Task deadline | Phase allowance |
|---|---|---|---|---|
| Acquisition | 3 learning tasks per arm; 6 paired development cases | 12 / 64,000 | 300 seconds | $14 new |
| Held-out | 8 paired tasks | 6 / 64,000 | 120 seconds | $10 |
| Cold boot | 8 separate paired tasks and compatible removal ablation | 6 / 64,000 | 120 seconds | $10 |

Each phase allocates equal, nontransferable task allowances to frozen and evolving
conditions. Frozen tasks can construct and test temporary code. Only the evolving
condition retains independently accepted artifacts across tasks. A fresh task
cannot spend another task's unused or uncertain allowance.

The earlier smoke retains its full $1 allocation. The total proposed ceiling is
$1 + $14 + $10 + $10 = **$35 API-rate equivalent**, using $2/M input and $10/M output.
These are accounting limits, not subscription invoices. Actual billed cost and
local-compute prices remain unknown.

SCI retains 256 MiB memory, one CPU, 32 PIDs, 8 MiB scratch, 10 seconds per
expression and 120 seconds per worker session. The fixed promotion rule requires
paired score improvement of at least 1, with no completion or per-case makespan
regression. The model cannot edit that rule. The rule measures scheduler behavior,
not the independent value of context selection or delegation.

## Preflight evidence

Evidence category: **FIXTURE**, except the read-only authentication/environment
checks. No new provider response or model-generated candidate is represented here.

| Check | Result |
|---|---|
| Initial and final doctor | Ready; recorded worker image and limits match |
| Worker/process cleanup | No workers before or after; no worker supervisors after |
| Claude login | Ready, pinned CLI hash; zero model calls |
| Parent/child subscription budget accounting | 5 tests, 44 assertions, zero failures/errors |
| Subscription transport, receipts and isolation checks using fake CLI | 10 tests passed |
| Actual SCI negative suite | Positive control and all 9 negative tests passed on retry |
| Current six-case development panel | 6/6 complete in 54.440 seconds; deadline 300 seconds |
| Development reservations and calls | Zero model calls; zero outstanding reservations |
| Preserved artifact integrity | 20 registry envelopes and 2 exported artifacts validated |
| Preserved database/source integrity | 10 SQLite databases passed; 82 archived source hashes matched |

The first isolation-suite attempt failed its positive control. Its generic error
did not preserve the underlying worker diagnostic. An identical direct positive
control then returned both expected values in 9.943 seconds. The unchanged full
suite subsequently passed. No image, limits, code or gate was altered. The cause
of the initial failure is **unconfirmed**; startup timing remains a reliability
limitation, not a hidden pass.

Two older subscription quota failures retain $0.059514 each in uncertain
reservations. The successful earlier smoke recorded $0.03 equivalent usage.
Known usage plus uncertainty totals $0.149028, within the reserved $1 allowance.
The reservations were not erased or reused. There are no new unresolved provider
requests. The interrupted older fixture rehearsal remains preserved and is not
resumed as part of this experiment.

These checks establish readiness for a bounded attempt. They do not establish
current provider quota availability, successful model synthesis or transfer.

## Experimental results — pending authorization

| Required result | Current evidence |
|---|---|
| Learning tasks/development cases completed by the real model | Not run |
| Model-generated candidate count and exact sources/forms/hashes | Not measured |
| Accepted/rejected model candidates and decision evidence | Not measured |
| Original versus evolved executable library | No model-evolved library |
| Frozen/evolving verified completion and makespan | Not measured |
| Root/child input tokens, output tokens and calls | No new requests; no experiment measurements |
| Acquisition/held-out/cold-boot cost equivalents | Not incurred by this experiment |
| Workflow context/delegation changes | Not observed from a model |
| Accepted artifact invocation on unseen tasks | Not observed from a model |
| Fresh-process and fresh-conversation transfer | Not run with learned artifacts |
| Compatible artifact-removal ablation | Not run with learned artifacts |
| Policy improvement | Not established |
| Harness improvement | Not established |
| Advantage after restart | Not established |

After acquisition, preserve every candidate and decision, including rejection and
failure. Inspect workflow strategy fields separately from policy replacement.
A changed hash is not evidence of better orchestration. Only observed invocation
and independently scored outcomes can support transfer. Do not infer Outcome D
from a scheduling improvement alone.

No next experiment is selected yet. Exactly one recommendation will follow the
actual acquisition, held-out and cold-boot evidence.

## Raw evidence and reproduction

Local preflight evidence is in
[`var/preflight/first-live-20261027T003144Z`](../var/preflight/first-live-20261027T003144Z/).
It contains `baseline.edn/json`, the offline driver, actual development episodes,
artifact/source/database checks, subscription tests, all isolation attempts,
public login metadata, worker checks and prior-smoke accounting.

The successful rehearsal remains at
[`mechanism-rehearsal-blocks-20261026`](../var/benchmarks/mechanism-rehearsal-blocks-20261026/).
The earlier failed attempt remains at
[`mechanism-rehearsal-20261026`](../var/benchmarks/mechanism-rehearsal-20261026/).
Those paths contain developer fixtures, not model learning.

Existing offline commands, from `repl-lab/`:

```sh
source var/worker.env
make doctor
python3 scripts/claude_subscription.py doctor
make isolation-test
python3 -m unittest discover -s test_python -p test_claude_subscription.py
python3 scripts/clj.py -e "(require 'repl-lab.subscription-test) (let [r (clojure.test/run-tests 'repl-lab.subscription-test)] (shutdown-agents) (System/exit (if (zero? (+ (:fail r) (:error r))) 0 1)))"
```

The recorded panel used:

```sh
python3 scripts/clj.py -i var/preflight/first-live-20261027T003144Z/offline-readiness.clj -e nil
```

That local driver records a new controller run and refuses reuse of its existing
run ID. Reproduction requires a fresh output path. Do not overwrite this evidence.

**Only after explicit approval**, use the existing private subscription login:

```sh
source var/worker.env
export INPUT_USD_PER_M=2 OUTPUT_USD_PER_M=10
export INFERENCE_PROVIDER=claude-subscription
make evolve LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=14
```

Inspect acquisition evidence and the actual exported library before final stages.
Keep the source frozen across all three stages. Substitute the printed export
path below; the angle-bracket value is not a literal shell argument.

```sh
make evaluate LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=<printed-export-path> PROFILE=heldout
make cold-boot LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=<printed-export-path>
```

The cold-boot command starts a new JVM. The evaluator restores only approved
executables and interface metadata, creates fresh model conversations, and runs
its existing compatible policy-removal control. Do not tune on either final split.
