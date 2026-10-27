# Fixed-policy diagnostic v1: startup failure isolated

**HELD-OUT EXPERIMENT / no new inference. Status: STOPPED—UNHEALTHY.**

The authorized diagnostic attempted 23 of 48 planned episodes. It stopped at the
predeclared readiness failure rule, without retries or changed limits. Twenty-two
episodes completed, forming 11 healthy original/retained pairs. The next worker
timed out before either policy was loaded. Twenty-five episodes remain unattempted;
the reversed-order second repetition never ran. This is not a completed 48-episode
reliability pass.

Source: `087939ef23c55190ed9c8321e33fdd96d8ae99a8`.
Source hash: `cd9dd508a75a62adb1eae7479eb5a75a7768ebb77dae958ec3d344441b42ee94`.
All 83 source files matched. The [frozen specification](POLICY_RUNTIME_DIAGNOSTIC_V1.md)
and [manifest](evidence/policy-runtime-diagnostic-v1/manifest.json) record exact
worlds, order, image, policies and limits. Model provenance stays Sonnet 5.5;
model requests, tokens and inference cost were **zero**.

## Stage-specific failure

Attempt `retained-11-r0`, seed 830011, failed the fixed `(+ 20 22)` startup check.
It never reached code loading and made zero policy invocations. The failure belongs
to a scheduled retained slot; it was not caused by executing retained policy code.

The [supervisor record](evidence/policy-runtime-diagnostic-v1/startup-failure-worker.json)
shows container verification, attachment at 183.756 ms, request write at 183.832 ms,
and `Worker wall-time limit` at 10,190.618 ms. No response was received. The
container was still running, with `OOMKilled=false`, immediately before cleanup.
Cleanup was confirmed. The attach process's 137 exit followed forced removal and
is not evidence of OOM. Total episode elapsed time was 12.820 seconds, including
controller checks, startup and cleanup.

| Stage | Confirmed failures |
|---|---:|
| Worker startup/readiness | 1 response timeout |
| Code loading | 0 observed |
| Execution/transport after loading | 0 observed |
| Algorithm/contract | 0 terminal failures observed |
| Cleanup | 0; all attempted workers removed |

This confirms a startup-deadline failure mechanism under the current limits.
It does not identify why the JVM/SCI worker was slow, or prove the cause of every
older generic worker failure. Earlier missing stderr cannot be reconstructed.
No limit was extended, image rebuilt, or worker warmed outside its task allowance.
The readiness request before loading is a declared change from the earlier run,
so this diagnostic does not replace any old score.

## Policy results and denominators

| Arm | Planned | Attempted | Complete | Startup failures | Unattempted | Actual policy invocations |
|---|---:|---:|---:|---:|---:|---:|
| Original | 24 | 11 | 11 | 0 | 13 | 2,473 |
| Retained | 24 | 12 | 11 | 1 | 12 | 1,186 |

Every planned slot remains accounted for. Unattempted slots are not algorithmic
failures or successful runs. The raw attempted mean penalized scores are 206.545
for original and 4,086.333 for retained; unequal attempted coverage and the startup
penalty prevent interpreting that difference as algorithm quality.

**Conditional secondary analysis: 11 pairs with healthy execution in both arms.**
All 11 completed in both arms; the retained policy improved makespan on every pair.
Mean makespan was **206.545 original versus 94.182 retained**, a **54.40% reduction**.
These are simulated ticks, not wall-time or model-token savings.

| Seed | Original | Retained |
|---|---:|---:|
| 830000 | 118 | 28 |
| 830001 | 141 | 42 |
| 830002 | 139 | 46 |
| 830003 | 142 | 33 |
| 830004 | 133 | 29 |
| 830005 | 163 | 49 |
| 830006 | 260 | 99 |
| 830007 | 298 | 97 |
| 830008 | 292 | 87 |
| 830009 | 295 | 261 |
| 830010 | 291 | 265 |

The source policy is unchanged and no inference occurred. This supports a policy
advantage over the original serial policy on these new workloads. It does not
show new learning, autonomous skill choice, harness improvement, or reliable
startup. There is one acquired library and no completed reliability repetition.
No fixed host baseline is used in this diagnostic; both policies follow SCI.

## Verification, accounting and preservation

Ten Python supervisor tests passed. The actual positive control and all nine
isolation negative tests passed before the diagnostic. Per-worker audit records
from those gate tests are separate from the 23 policy attempts. All 23 recorded
simulator episodes, including the startup failure transition, replayed to their
expected final hashes without executing policy code or inference again.

Model calls/input/output tokens/inference equivalent: **0 / 0 / 0 / $0**.
Summed episode elapsed time was 96.066 seconds for original and 103.149 seconds
for retained, including its startup failure. Local-compute dollars and total
economic cost remain unknown. These timings are not a causal runtime speed claim.

No worker container or quarantine marker remained. All **1,212 prior experiment
files** retained identical hashes. All raw traces, exceptions, worker state,
worlds, policy envelopes and unattempted slots remain in
[the diagnostic run](../var/diagnostics/policy-runtime-diagnostic-v1-20261027/).
[Compact summary](evidence/policy-runtime-diagnostic-v1/summary.json),
[replay result](evidence/policy-runtime-diagnostic-v1/replay.log),
[raw archive metadata](evidence/policy-runtime-diagnostic-v1/archive.json).

The old skill-selection behavior is analyzed separately in
[SKILL_REUSE_ANALYSIS.md](SKILL_REUSE_ANALYSIS.md). The proposed four-condition
[skill-selection-v1](SKILL_SELECTION_V1.md) is not started or authorized. Its live
phase requires healthy execution first; the present diagnostic does not satisfy
that prerequisite.
