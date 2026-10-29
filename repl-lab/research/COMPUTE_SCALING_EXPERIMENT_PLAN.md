# Compute scaling: more compute against better allocation (preregistered, development)

**Status:**
- Preregistered design; no plan is frozen.
- It needs phases A–C and V-A to V-B (`ELASTIC_IMPLEMENTATION_PLAN.md`), and
  phase D for arm B only.
- Development suites only. The sealed held-out suite `c74547bd…` is not used.
- The done-time verification experiment (`CONTROLLER_VERIFICATION_DESIGN.md`
  §7) runs first. Its V2 result defines the verification part of arm D here.

## 1. Question

At equal inference cost, does **evidence-driven allocation** of extra model
calls improve answers more than **uniform additional inference**? Does either
beat the original harness, and where does each sit against pinned Prime?

## 2. Arms

All Aljure arms use Opus 5.5 with the same pinned settings, F1 as the base
contract and the same suite. Same model in the primary comparison.

| Arm | Configuration | Extra compute |
| --- | --- | --- |
| **A** original Aljure | L0 configuration (F1 only) | none |
| **B** elastic, model-directed | A + `elastic_tools` (phase D): `agent_spawn` / `agent_collect` / `agent_status` / `agent_cancel` tool schemas. No added prompt prose beyond the tool descriptions | whatever the model chooses, within quotas |
| **C** uniform additional inference | A + `k` blind independent solves per task; the answer is the median for integers and the majority for labels, with ties going to the first solve | `k − 1` extra solves on **every** task |
| **D** evidence-driven adaptive | A + V2 verification + P1 allocation (`EVIDENCE_DRIVEN_COMPUTE_SPEC.md` §4): a blind replicate only where the allocator fires, a third on disagreement, the median | extra solves only on triggered tasks |
| **D-rand** allocation control | A + V2 + the **same number** of extra solves as D, on tasks drawn at random (seeded) | matched to D's realized count |
| **E** pinned Prime reference | Prime `c4c238ca…`, the recorded images, unchanged | — |

**Budget levels.** A budget is the mean realized cost per task relative to A
(`c_A ≈ $0.23` on the count suite):
- **1×:** A, B (capped by quotas at +0×), and D at 1×. D at 1× is V2 only,
  because V2 adds about 0 calls.
- **1.5×:** C1.5 (one replicate on a random half of the tasks), and D and
  D-rand with a mean cap of 1.5 `c_A`.
- **matched-Prime (about 2.3×, $0.53 / $0.23):** C2 (one replicate on every
  task, plus a third on disagreement, capped), and D and D-rand capped at
  2.3 `c_A`.

  C3 (two replicates on every task) is also reported, to extend the curve.

## 3. Separating "more compute" from "better allocation"

1. **D against D-rand at the same realized extra-solve count.** They differ
   only in *which* tasks get the extra solves. This is the allocation test.
2. **The frontier.** Plot accuracy against realized cost for A, C1.5, C2, C3
   and for D at each cap. D must lie above the piecewise-linear C frontier at
   its own cost, with a 95% cluster-bootstrap interval over windows.
3. **Triggered against untriggered tasks.** Report D's gain separately on the
   tasks where it fired. A gain only on tasks where D-rand also spent shows
   compute, not allocation.
4. **Shared-bias check.** Report the signed error by arm. If C and D shrink
   only |error| variance and keep the sign, the result is "variance
   reduction", as predicted (`CONTROLLER_VERIFICATION_DESIGN.md` F4).

## 4. Endpoints

**Primary:**
- **Count MAE**, reported both ways: parsed only, and unparsed answers counted
  by their leading number;
- **paired per-task difference against A**, with a 95% cluster bootstrap
  over windows.

**Secondary:**
- official score; completion; signed error;
- item-level accuracy where independent per-item gold exists (MultiNLI,
  `evidence/multinli-count/dev-gold-labels.json`), offline only, for arms whose
  per-item decisions are extractable;
- cost; calls; input and output tokens; p50 and p95 latency;
- variance across contexts and across repeats.

**Activation (first-class):**
- B: share of arms using any elastic tool, children per arm, child
  utilization (child cost / arm cost) and overhead (orchestration turns);
- D: per trigger, eligible / fired / acted; verification activation;
  unnecessary actions (fired, answer unchanged); failed actions;
  `elastic-denied` counts.

**Integrity:**
- auditor violations (0);
- blinding violations (0);
- unknown outcomes.

## 5. A cheaper runner design: pooled independent solves, shared Prime reference

Today every configuration plan re-runs unchanged Prime. That is 70% of cost
and 57% of wall time (`RUNNER_TIMING_AUDIT.md`).

**Design:**

1. **Shared Prime reference.** No new Prime arms. The reference is the pinned
   Prime arms already recorded on the count suite `dc164044…`: L0, L1 and L2,
   32 arms finished when this was written, plus L3 when it finishes. They are cited by plan hash
   and results SHA-256.
   - This needs a runner change: an **Aljure-only plan** with a
     `reference_plans` field. Preflight checks that the cited plans have
     the same suite, the Prime pin and image digests, and complete accounting.
   - This needs its own approval.
2. **A pool of independent A solves.** For each count task, run `P = 6`
   independent arms of configuration A, as fresh sessions.
   - C, D-rand and the replication part of D only decide **whether to use**
     extra independent solves of the same task. So they can be evaluated
     exactly from the pool, offline: the expected accuracy over all ordered
     choices of root and replicates.
   - Their costs are the sums of the costs of the chosen solves.
   - Latency is modelled two ways:
     - concurrent, for C: the slowest chosen solve;
     - triggered at `done`, for D: root plus replicate.

     Both are reported as modelled.
   - Each replicate in the pool is a fresh arm. A live replicate would be an
     elastic child, with the same task text and model but inside the root's
     arm. The difference is disclosed, and step 4 below validates it.
3. **Live runs only where the trajectory changes:**
   - B (the model sees new tools);
   - V2 verification notices, taken from the verification experiment;
   - a **live D validation**: one repeat of D with real elastic replicate
     children, to check the pooled estimate. The pre-registered tolerance is
     that the live D MAE lies inside the pooled 90% interval.
4. **Order:** run the configurations interleaved in a balanced rotating order
   (a Latin square over tasks), so time-of-day drift does not separate arms.
   Run arms sequentially, as now, so latency stays clean and the stop rules
   still act between arms.

## 6. Projected inference budget

API-rate equivalent. Measured Opus costs per count arm: Aljure
$0.22–0.24 mean (range $0.12–0.40); Prime $0.53 mean (range $0.2–0.9).

| Block | Arms | $/arm | Projected |
| --- | --- | --- | --- |
| Pool: A × 11 tasks × 6 | 66 | 0.12–0.40 (mean 0.23) | $15 (range $8–26) |
| B live: 11 × 3 | 33 | 0.15–0.45 | $9 (range $5–15) |
| D live validation: 11 × 1, with replicate children | 11 | 0.3–0.9 | $5 (range $3–10) |
| Prime | 0, reference reused | — | $0 (or about $17 for one new Prime block if reuse is not approved) |
| **Total** | 110 | | **about $29 (range $16–51); hard cap $75** |

The offline evaluation of C1.5, C2, C3, D-rand and D at three caps costs $0.

**For comparison,** the naive design re-runs Prime per configuration and runs
every configuration live (A, B, C1.5, C2, C3, D ×3 caps, D-rand ×3 caps;
3 repeats). It needs about 330 Aljure arms at a mean multiplier of about 1.7
(about $130) plus 10 Prime blocks (about $175): **about $300**.

**Time:** about 110 arms at 65–90 s each, so about **2–2.8 hours**
sequential.

## 7. Decision rules (fixed in advance)

1. **Allocation is shown** only if all four hold:
   - at the matched-Prime cap, D's MAE is lower than D-rand's on ≥ 7 of 11
     tasks;
   - D's pooled MAE paired difference against D-rand has a 95% interval
     below 0;
   - every D trigger fires on ≥ 90% of its eligible tasks;
   - D's cost is ≤ 0.6 of the Prime reference's.
2. **"More compute, not better allocation"** applies if D and D-rand are not
   distinguishable but both beat A.
3. **"No effect of extra inference"** applies if C2 does not beat A on ≥ 7 of
   11 tasks.
4. **B is "not activated"** if fewer than 50% of B arms use any elastic tool.
   Then no B accuracy claim is made.
5. **Development evidence only.** One frozen candidate may go to a new dev
   dataset, and then, with separate approval, to the sealed held-out suite
   once.

## 8. Contamination and integrity

- **Suites:**
  - the count suite `dc164044…` was built from row groups that hold no
    held-out window (`REVIEW_ABLATION_PROTOCOL.md`);
  - the 21-task dev suite `b157ee63…` is for the side-effect check only.
- **Gold:** dev gold is read only by offline analysis scripts, never by the
  harness, the allocator, verifiers or reviewers (`ELASTIC_SECURITY_INVARIANTS.md`
  I20).
- **Stop rules:** as now. Any isolation refusal, unknown provider outcome,
  Docker restart or unconfirmed cleanup stops the plan.
- **Pool integrity:** every pool arm's capability hash, runtime snapshot and
  image digests are identical. A pool arm that fails for infrastructure
  reasons is re-run, never imputed.
