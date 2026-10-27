# Skill discovery v4: completed offline controls

**FIXTURE. All 20 slots executed; 25/25 workers started and confirmed cleanup.**
There were no startup, code-loading, transport or cleanup failures in v4.
Two intentional blind-reuse controls failed algorithmically on GPU workloads.
No new model calls or model-authored selector were involved.

The study now supports a narrow conclusion: the existing learned policy is useful
within its CPU/memory contract, and adapting the computation is necessary on these
GPU cases. A simple fixed applicability checker matches the scripted selector.
This is **not** evidence of learned metareasoning, autonomous reuse, inference
savings, unseen selector transfer, language superiority, or a Prime advantage.

## Four requirements before a live selector study

| Requirement | Evidence and boundary |
|---|---|
| GPU tasks distinguish reuse from adaptation | Blind reuse failed both GPU cases with rejected capacity checks; every adaptation control completed both |
| Retained and temporary routes share healthy isolation | Same loader/caller, image, readiness check, limits and cleanup path; all 25 workers confirmed cleanup |
| Scripted selector labeled fixture | Manifest, source provenance, per-case selector status and report say FIXTURE/developer stand-in |
| Model-authored candidates independently accepted/rejected | Gate implemented and fixture-tested: exact provider/staging receipt match, fixed development panel, replayed scores, ledger costs, no hidden-outcome input; **no real selector accepted yet** |

The live selector campaign still needs route/acquisition integration and separate
authorization. Its gate does not itself promote an active library. A real learned
strategy must beat the applicability guard on unseen cases, with acquisition costs
included, and transfer beyond this resource example. External Prime benchmarking
does not depend on completing that selector campaign.

## Results

All arms received identical public worlds and tool capabilities. Limits remained
6 shared parent/child calls, 64k tokens, $0.625 equivalent and 120 seconds per task.
The actual provider was `fixture-script-v1`; `claude-sonnet-5-5` is the unchanged
future live pin and the retained policy's historical source model.

| Condition | Verified completions | Makespans by case 0/1/2/3 | Retained function calls | Scripted provider turns |
|---|---:|---|---:|---:|
| Opaque hash, scripted synthesis | 4/4 | 31 / 26 / 42 / 27 | 0 | 12 |
| Descriptive discovery | 4/4 | 24 / 23 / 42 / 27 | 55 | 20 |
| Always reuse | 2/4 | 24 / 23 / failure / failure | 8,387 | 0 |
| Scripted selector stand-in | 4/4 | 24 / 23 / 42 / 27 | 55 | 13 |
| Fixed applicability checker | 4/4 | 24 / 23 / 42 / 27 | 55 | 6 |

Cases 0/1 use CPU/memory; 2/3 additionally require GPUs. In case 2 the retained
code dispatched `j000` (needs one GPU) to `w1` (no GPU). The independent simulator
rejected it with `capacity`. Repeated invalid dispatches prevented progress;
the two GPU controls ended at the unchanged event budget, with 4,999 and 6,666
rejected actions respectively. These are algorithmic failures after healthy startup,
not timeout-derived evidence of an improvement. Generic resource-fit source handled
the same cases through SCI at 42 and 27 ticks.

The fixed checker recognizes unsupported resource keys against the reviewed
contract; it does not test the literal word GPU. This current fixture domain
always supplies numeric CPU/memory fields. Broader contract inference remains
untested. The stand-in's compute/delegate routes add plumbing work but improve
neither correctness nor makespan here. Its branch choices are developer-authored.

Mean makespan over all four successes is 31.5 ticks for scripted synthesis and
29.0 for descriptive discovery, the stand-in and the fixed checker. Always-reuse's
23.5 mean covers **only its two successful cases** and is not a comparable overall
score. All failures remain in the denominator.

Actual discovery evidence: 10 initial inventories delivered to scripted sessions,
four list requests, four detail requests, and zero source-inspection requests.
There were **8,918 successful SCI policy invocations** (including valid function
returns that led to rejected dispatches), four selector calls, and one compute
REPL worker. Across all controllers, 50 root and one child scripted turns reconcile.
The descriptive script deliberately exercises list/detail APIs; its turn count
is a coverage choice, not an estimate of live metadata overhead.

**Actual model calls/input tokens/output tokens/new inference cost: 0 / 0 / 0 / $0.**
Scripted turns are not model inference. Historical acquisition is shown separately:
$0.166624 known plus $0.394712 unresolved reservation for the whole earlier
acquisition, both arms. Dividing by four verified solutions gives $0.041656 known
plus $0.098678 reserved per solution; the two-success control doubles those figures.
This is disclosed bookkeeping, not measured marginal skill cost or an economic win.
Local-compute dollars and subscription invoices remain unknown.

## Readiness repair and preserved failures

V2 stopped at 1/16 before policy loading. Its legacy proof was invalidated because
negative workers could time out before readiness and still count as passes.
The repaired gate requires a positive response in **each** negative-test worker,
specific operation/resource failure evidence, matching image and supervisor hash.
Legacy/stale proofs are rejected by both Clojure and the subscription transport.

The startup profile adds `-XX:TieredStopAtLevel=1` and inherits the identical worker
filesystem. In a predeclared three-pair readiness check, both profiles answered:
old end-to-end session times 7.95–10.30 s, new 4.84–6.95 s. These include Docker
creation and cleanup. First versus subsequent-response evidence points to initial
runtime readiness as a major delay; internal JVM phases were not separately timed.
No deadline or sandbox limit moved. This small sample is not a reliability estimate.

V3 reached 12/20, then stopped when removal confirmation timed out after a completed
GPU adaptation. Its raw row says complete, but stderr/audit record the cleanup
failure; treat it as algorithmically complete with unconfirmed cleanup. Independent
inspection found the container absent. V4 adds bounded absence verification after
removal errors, distinct cleanup exit handling, and cleanup-aware completion counts.
Unknown/present containers still quarantine. The strict isolation suite passed again.
V4 is a regression on the same public fixtures, not a retest of any sealed live set.
No prior run was overwritten or resumed.

The shared host is not dedicated. A later external-adapter fixture encountered
Docker API timeouts under host load; its evidence is separate. V4's 25 successful
workers do not promise that future external runs cannot fail.

## Source, validation and evidence

- Source: `bf6c6a8881c8a20983393e7f593b1245f46a6e9e`, clean at freeze.
- Source hash: `20e5f2797fcb42a93597d47af6b3681ecabda649acffc142573929e531cce889`.
- Worker: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
- **75 Clojure tests / 1,554 assertions and 59 Python tests passed.**
- All 20 v4 SQLite stores passed integrity checks. All 12 v3 and 20 v4 recorded
  episodes replayed. All 92 v4 source hashes, 1,369 prior evidence files and 87 v3
  raw files matched. Raw archives were individually hash-verified.

[V4 manifest](evidence/skill-discovery-v4/v4-manifest.json),
[full results](evidence/skill-discovery-v4/v4-report.json),
[integrity/accounting](evidence/skill-discovery-v4/verification.json),
[strict isolation summary](evidence/skill-discovery-v4/strict-isolation-summary.json),
[strict proof](evidence/skill-discovery-v4/strict-isolation-proof.json),
[replays](evidence/skill-discovery-v4/replay.log),
[v3 preserved results](evidence/skill-discovery-v4/v3-report.json).

Exact traces include
`var/diagnostics/skill-discovery-v4-controls/episodes/deterministic-reuse-2.jsonl`
(invalid GPU dispatch), `episodes/model-authored-selection-2.jsonl` (adaptation),
and `sessions/model-authored-selection-3.jsonl` (scripted child delegation).
Per-worker supervisor evidence is under that run's `workers/` directory.
[V4 archive](evidence/skill-discovery-v4/v4-archive.json),
[v3 archive](evidence/skill-discovery-v4/v3-archive.json),
[readiness/cleanup archive](evidence/skill-discovery-v4/readiness-archive.json).

Executed once, from `repl-lab/`:

```sh
source var/worker.env
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/skill-discovery-v4-controls/workers" \
  make skill-discovery-v4-fixtures OUT=var/diagnostics/skill-discovery-v4-controls
```

Do not rerun that output directory. The [protocol](SKILL_DISCOVERY_V4.md) defines
the engineering intervention and preserves earlier versions.

For the learning track, the next experiment should test whether a model can acquire
a selector that beats the fixed applicability checker on new task families—not
merely encode the GPU rule. For the independent competition track, the next result
is one official same-model Aljure/Prime case through the common accounted transport,
then a preregistered ten-case pilot, after new inference authorization.
