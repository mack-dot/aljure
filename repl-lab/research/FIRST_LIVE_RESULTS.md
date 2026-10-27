# First live self-improvement experiment

**Completed with failures. LIVE MODEL RUN + HELD-OUT EXPERIMENT.**

Sonnet independently generated a Clojure scheduling policy and workflow. The
controller accepted them under the unchanged development rule. After a fresh
process reset, direct execution of the retained policy completed all eight unseen
cold-boot tasks. The original policy also completed all eight. Mean makespan fell
from **204.125 to 59.5 virtual ticks (70.85%)**, with improvement on every pair.
The retained policy matched the existing estimate baseline on all eight cases.

This supports **policy-level executable skill transfer (Outcome C)** within one
scheduling experiment. It does not establish a novel algorithm, reliable gains
across panels, or harness-level improvement (Outcome D). All failures remain in
the denominators. No sealed task was retried. See the
[read-only failure analysis](FIRST_LIVE_POSTMORTEM.md).

## Frozen identity and conditions

| Item | Recorded value |
|---|---|
| Acquisition | `model-1793062055972` |
| Held-out | `evaluation-1793062969450` |
| Cold boot | `evaluation-1793064236328` |
| Source commit; clean at launch | `7126edb7e29c0d9431acb52f395057bb274b68c5` |
| Aggregate source hash; 82 files | `4f5262ff38b053e2512046d2e0a5f1c19f530787abab6b23b9d1cd48a9ad36d5` |
| Model-facing prompt SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| Split digest | `69be513f06870cb6c72d95eb475682e18b0c406d30b645b43e8b2a3ce7589e99` |
| SCI image | `sha256:508f6f195f8837324f2c52ec87b193eb7fc79334de8948ff300b8585df03b37a` |
| Requested and returned model | `claude-sonnet-5-5`, every completed receipt |
| Provider | `claude-code-subscription`; Claude Max, `claude.ai`, first-party transport |
| Executed CLI | `2.1.310`; SHA-256 `ffb64331bc0ee1b69efb7c2c428bd3ab516bc31b75bf60886b356c97c1c25ffd` |
| Host runtime | macOS/aarch64, Java 21.0.2, Clojure 1.11.3, Python 3.10.11 |

All 82 source hashes matched at final audit. Simulator, scoring, promotion,
prompt, image and task limits stayed fixed. The operator approved the phase caps
with “yes rip it” and reaffirmed them during execution.
[Authorization](evidence/first-live-20261027/authorization.json).

| Phase | Tasks | Shared root/child limits per task | Deadline | Cap |
|---|---|---|---|---:|
| Acquisition | 3 per arm; 6 development cases | 12 calls / 64,000 tokens | 300 s | $14 |
| Held-out | 8 paired tasks | 6 calls / 64,000 tokens / $0.625 | 120 s | $10 |
| Cold boot | 8 separate paired tasks | 6 calls / 64,000 tokens / $0.625 | 120 s | $10 |

Task allowances were equal and nontransferable. Only the evolving acquisition
arm retained approved artifacts. Both arms could construct task-local code.
Output was limited to 2,048 tokens per call. Cache, native CLI tools, MCP, hooks,
background agents and CLI session persistence were disabled. Sampling/thinking
used the pinned transport configuration; cross-provider parity is untested. The
CLI reported a 1M context window; Aljure's stricter context limits remained.

SCI enforced 256 MiB, one CPU, 32 PIDs, 8 MiB scratch, no network, a read-only
filesystem, a 10-second response limit and a 120-second session limit. Promotion
required paired score improvement of at least 1, without completion or per-case
makespan regression. It evaluated scheduling, not inference efficiency.

## Preflight and acquisition

The [preflight](FIRST_LIVE_PREFLIGHT.json) and
[preserved pre-run report](evidence/first-live-20261027/PRE_RUN_REPORT.md) retain
the earlier successful rehearsal and failed attempts. Preflight made no model
calls. Shared-budget tests passed (5 tests/44 assertions), as did 10 fake-transport
tests. Six initial-policy development cases finished in 54.440 seconds. Artifact,
database and source checks passed. The first isolation positive control failed;
an identical diagnostic and then the unchanged complete nine-case suite passed.
The initial failure's underlying cause was not retained.

The model created **four artifacts: two policies and two workflows**. The
controller made **two promotion decisions: one rejected pair and one accepted
pair**. [Exact source, forms, provenance and decisions](evidence/first-live-20261027/acquisition-audit.json)
and [artifact envelopes](evidence/first-live-20261027/candidates/) are preserved.

| Artifact | Hash prefix | Result |
|---|---|---|
| Original serial policy | `aa12262b1989` | Initial control |
| Original workflow | `966c8048c0c8` | Four selected job rows; automatic analyst delegation |
| First generated policy | `567d990ffcd0` | SCI rejected `letfn`: `clojure.core/alter-var-root is not allowed!` |
| First generated workflow | `6388a689ce33` | Rejected; 6/6 candidate cases failed |
| Retained policy | `834a4e02cd94` | Estimated downstream-path ranking; capacity-aware packing onto faster workers |
| Retained workflow | `4160eb5684c2` | Up to 12 full permitted job rows; automatic delegation removed |

The model submitted a complete workflow replacement, not a structural patch.
No handwritten winning fixture was supplied or substituted. It queried external
context and used real child sessions. It did not directly request `repl/eval` or
development evaluation during acquisition; workflow submission triggered the
existing independent SCI evaluator. Tool availability is not proof of tool use.

Accepted development makespans were **37, 35, 40, 36, 59, 47**. Paired original
results were **145, 145, 154, failure, failure, failure**. The recorded promotion
gain of 37,630 is inflated by three worker failures. **That aggregate is not an
algorithmic improvement estimate.** The three healthy pairs show lower makespan,
but do not replace the six-case denominator.

Only the first learning task in each arm completed: frozen 184 ticks, evolving
50 ticks. Thus each arm completed **1/3 acquisition tasks**. Docker cleanup then
became unconfirmed and activated quarantine. Four later tasks stayed checkpointed.
The 48 development execution records include failures. Six uncertain provider
reservations remain. The existing recovery command confirmed cleanup; the actual
unchanged nine-case isolation suite passed again before held-out evaluation.
No acquisition task was resumed.

## Sealed outcomes and cold transfer

All failed tasks remain scored. A penalized score is not a completed makespan.
Fixed baselines execute trusted host functions; the two direct policy controls
execute through Docker/SCI. This execution difference limits baseline comparisons.

| Condition | Held-out complete | Mean penalized score | Cold complete | Mean penalized score |
|---|---:|---:|---:|---:|
| Frozen agent | 0/8 | 21,360 | 0/8 | 27,960 |
| Evolving agent | 5/8 | 13,465.125 | 3/8 | 23,295.5 |
| Retained policy, direct SCI | 1/8 | 19,804.875 | 8/8 | 59.5 |
| Original policy, direct SCI removal control | 6/8 | 3,276.5 | 8/8 | 204.125 |
| Fixed FIFO, host | 8/8 | 100.375 | 8/8 | 65.875 |
| Fixed estimate, host | 8/8 | 85.625 | 8/8 | 59.5 |

Held-out frozen failures: seven shared-call-budget failures and one malformed EDN
response. The evolving agent chose temporary policies for all eight tasks: five
completed, one exhausted the event budget after 4,991 capacity rejections, and
two failed worker loading. Its five successes do not establish retained-policy
reuse. Seven direct retained-policy cases and two original-policy cases failed
with `Worker terminated without result`. These failures do not show algorithmic
superiority or inferiority. The postmortem identifies missing diagnostics.

Cold boot started new JVMs (outer PID 97199, evaluator 97235) after the held-out
JVM 58031 exited. It used fresh stores and conversations. The approved export
contained two executable artifacts and interface metadata, totaling 1,476 bytes.
Literal/source inspection found no task-answer tables, hidden seeds, transcripts
or narrative memory. Fresh envelopes remap the policy hash to
`eb336176819f34a4a955fd21b8f735bbdad1dd1a66ea9d15b3dab5d1248d760e`;
the executable forms remain the same.

The retained policy made **565 recorded invocations** on the eight cold tasks.
Paired retained/original makespans were **34/126, 32/133, 32/141, 35/144,
53/161, 42/151, 137/408, 111/369**. The direct control makes no model calls and
allows no task-local replacement. This is the positive transfer evidence.
One retained library is one learning run, not eight independent replications.
The report's descriptive intervals do not establish cross-run significance.

Cold agent failures stay separate. Frozen tasks 0–3 exhausted the call allowance.
Evolving task 1 failed worker loading. Tasks 4–7 in both arms failed transport
preflight after the installed Claude CLI changed to 2.1.311. A read-only doctor
confirmed the pin mismatch with valid login. Twelve reservations remain uncertain.
No request was retried and no pin, model or scoring rule was changed.

## What learned, and what did not

- **Executable code:** yes, recorded Sonnet responses created the candidates.
- **Useful abstraction:** a reusable standard scheduling heuristic helped on the
  cold direct panel against the weak serial control. It matched the estimate baseline.
- **Independent acceptance:** yes, but infrastructure failures inflated the development gain.
- **Workflow change:** yes. Context selection expanded and automatic delegation disappeared.
- **Unseen execution:** yes, in the direct controls. Agent successes used temporary policies.

Held-out frozen inference used 44 calls/$0.410536; evolving used 36 calls/$0.392848.
The evolving arm cost 4.31% less, but used slightly more tokens: **160,660 versus
160,524**. It removed eight automatic analyst sessions (23 child calls) and
selected richer initial context. No workflow-only ablation held the policy and
task-local synthesis fixed. Promotion did not test inference cost.
**Harness improvement remains unproven.** Cold transport failures prevent a clean
cold inference-efficiency comparison. No Clojure-over-Python or Prime claim follows.

## Accounting and verification

All **139 completed receipts** reconcile with controller ledger entries. They have
distinct CLI session IDs, the same returned model, one turn, no cache tokens and
no native CLI subagents. All Aljure child requests share their parent's task
budget. No extra compaction/refinement provider calls were observed.

| Phase | Completed calls | Input tokens | Output tokens | Known equivalent | Uncertain reserved | Cap |
|---|---:|---:|---:|---:|---:|---:|
| Acquisition | 16 | 61,477 | 4,367 | $0.166624 | $0.394712 / 6 calls | $14 |
| Held-out | 80 | 301,057 | 20,127 | $0.803384 | $0 | $10 |
| Cold boot | 43 | 155,839 | 9,841 | $0.410088 | $0.789614 / 12 calls | $10 |
| New total | 139 | 518,373 | 34,335 | **$1.380096** | **$1.184326** | $34 |

Known plus reserved new usage is **$2.564422**. Earlier smoke retains its full $1
allocation ($0.03 known plus $0.119028 uncertain within it). Counting that full
allocation gives **$3.564422 against the $35 ceiling**. No allowance was reused.
Rates are $2/M input and $10/M output. This used the Claude subscription, not direct
API credits. Actual subscription invoices and local-compute dollar costs are unknown.

All 1,208 archived file hashes and 38 read-only SQLite integrity checks passed.
No experiment JVM, worker container or quarantine marker remained at completion.
A shared-host limitation remains: a read-only replay briefly ran concurrently
with early cold tasks, was observed using about one CPU, and was stopped after
about 50 seconds to avoid load. `replay-deferred.json` preserves this event. No
wall-time performance claim is made. Final verification replayed **all 150 recorded episodes** (54 acquisition, 48
held-out, 48 cold) to the expected final hashes. Restored policy forms and export
hashes verified. This replay made no inference or generated-policy calls.

## Evidence and exact commands

Committed evidence includes [candidate decisions](evidence/first-live-20261027/acquisition-audit.json),
[acquisition accounting](evidence/first-live-20261027/acquisition-usage-audit.json),
[held-out audit](evidence/first-live-20261027/heldout-audit.json),
[cold audit](evidence/first-live-20261027/coldboot-audit.json), and
[approved library](evidence/first-live-20261027/approved-library/).
These include exact case IDs, source hashes, root/child accounting, receipt hashes,
selected policies and invocation counts. [Replay verification](evidence/first-live-20261027/replay-verified.log)
passed all 150 records. A private [raw archive](../var/archives/first-live-20261027T004645Z.tar.gz)
preserves 1,208 files; its hash is recorded in [archive metadata](evidence/first-live-20261027/archive.json).
Full raw evidence also remains in its original paths:

- [Acquisition](../var/runs/model-1793062055972/): all candidate code/forms, SQLite
  ledgers, development episodes, export and consumed split seals.
- [Held-out](../var/evaluations/evaluation-1793062969450/): 48 episodes and full model/action traces.
- [Cold boot](../var/evaluations/evaluation-1793064236328/): 48 episodes and fresh-session evidence.
- [Operator records](../var/experiments/first-live-20261027T004645Z/): logs, recovery,
  process boundaries, read-only audit scripts and verification output.

Exact executed commands, from `repl-lab/`:

```sh
source var/worker.env
export INFERENCE_PROVIDER=claude-subscription INPUT_USD_PER_M=2 OUTPUT_USD_PER_M=10
make evolve LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=14
make evaluate LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=var/runs/model-1793062055972/export PROFILE=heldout
make cold-boot LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=var/runs/model-1793062055972/export
```

These are historical commands, **not authorization to rerun**. Both sealed splits
are consumed. The installed CLI no longer matches the experiment pin. Receipt
analysis uses the saved `audit_phase.py`; recorded-action verification uses
`replay-records.clj`. Earlier fixtures and failures remain preserved.

Exactly one next experiment is proposed: **policy-runtime-diagnostic-v1**, specified
in the [postmortem](FIRST_LIVE_POSTMORTEM.md). It is not started. Additional model
learning, Prime and language comparisons remain outside this experiment.
