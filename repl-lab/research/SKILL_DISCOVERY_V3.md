# Skill discovery v3: offline continuation

**FIXTURE only. No additional inference authorized.** The failed v2 1/16 run is
preserved unchanged. V3 is a new engineering control, with new seeds and a new
explicit worker profile. It does not replace v2 or any sealed live score.

The four primary conditions remain opaque hash, descriptive discovery, deterministic
reuse, and a **developer-authored selector stand-in**. A fifth, stronger control is
now required: a fixed applicability checker. It inspects resource keys against the
reviewed CPU/memory contract. It reuses the policy inside that contract and calls
the same synthesis path outside it. It is not learned, and it does not special-case
the word GPU. A license-resource unit counterexample checks that distinction.
Its synthesis responses are scripted in this offline run, just like all other arms.

V3 uses seeds 840200–840203 with the same four workload profiles as v2: two ordinary
CPU/memory cases, then two GPU-constrained cases. Four cases × five conditions =
20 slots, with rotating arm order, fresh sessions/stores/workers, no retries and
the same stop-on-infrastructure rule. The retained function, generic temporary
fixture, model pin, tool surface, scorer, 6-call/64k-token/$0.625-equivalent/120-second
task limits, and worker resource/response limits stay fixed across conditions.
Only fixture calls occur; no Sonnet usage or cost-efficiency claim is possible.

The startup profile inherits the exact old worker filesystem. It adds only
`-XX:TieredStopAtLevel=1`; its image is
`sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
The isolated worker still has 256 MiB, one CPU, 32 PIDs, no network, a read-only
filesystem, and a 10-second response allowance. All arms use this same image.
The stricter gate requires readiness **in each negative-test worker**, checks the
specific rejection/resource outcome, pins supervisor source, and rejects stale
proofs. No response deadline was moved or extended.

Pre-run engineering measurements are recorded under
`var/analysis/worker-readiness-v2`: three old-profile and three startup-profile
fresh-container probes, alternating order, no retries; identical rootfs verified.
All six answered. End-to-end sessions took 7.95–10.30 s with the old profile and
4.84–6.95 s with the new profile. These include container creation/cleanup and
are not pure JVM timings. The old positive control's first response arrived at
10,072.485 ms, versus 10,072.831 ms for the second response. That is consistent
with initial runtime readiness dominating latency; it does not localize JVM
initialization internally or prove a general startup reliability rate.
The response deadline intentionally includes startup. Transport delivered both
responses. The new profile passed the strict positive plus all nine same-worker
negative checks. Its negative-worker readiness times were 4.38–7.68 s.

The separate `selector-gate` validates candidate source/provenance against durable
provider/staging receipts, a fixed development panel, isolated execution, exact
route schema and approved hashes. It verifies scores by simulator replay and reads
costs from parent/child ledgers, rejecting unresolved reservations. Its controller
entry point has no hidden-outcome argument and gives selector code only permitted
observations and reviewed skill interfaces. A model cannot invoke the acceptance
function through its broker. Development acceptance requires no paired regression,
lower acquisition-inclusive cost than model-directed selection, and a strict
cost/score benefit over the applicability guard. Startup failures cannot earn credit.

That gate is **implemented with fixture tests**, including accept/reject, corrupt
scores, missing authorship, hidden-data exclusion, and infrastructure failure.
Fixture receipts cannot promote an active library. A real model-authored selector
and fresh-process unseen transfer are still **NOT RUN**. Full selector live
acquisition/campaign accounting and route orchestration remain to be connected;
the gate's caller must supply the complete acquisition ledger and trusted route
executor. This gate is not a claim that a live selector study is ready.

Success criteria for this offline study: both ordinary and GPU workloads execute
through the same healthy SCI path; GPU cases expose the retained policy's contract
limit under unchanged independent scoring; synthesis fixes those cases; the fixed
applicability guard demonstrates the strength of a simple alternative. None of
these outcomes establishes learned metareasoning. Generalizing an acquired decision
strategy beyond the GPU/resource example remains a separate future experiment.

```sh
source var/worker.env
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/skill-discovery-v3-controls/workers" \
  make skill-discovery-v3-fixtures OUT=var/diagnostics/skill-discovery-v3-controls
```

Run once after strict isolation validation. Preserve failures and unattempted slots.
The external native-Prime/OOLONG comparison is a separate track and does not depend
on selector completion. It still requires compatible same-model transport,
complete accounting, native Prime isolation, and new inference authorization.
