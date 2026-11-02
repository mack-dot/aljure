# Executable learning recovery — 2026-11-02

The priority is acquisition, validated promotion, retention after restart, and
model-chosen reuse. The service-simulation comparison and new benchmark adapters
are deferred until that mechanism works. No new inference is authorized here.
Prior runs, scores, plans, and rejected artifacts remain unchanged.

## Audit of the zero-proposal thesis pilot

`scripts/audit_acquisition.py` re-read all 162 recorded development task runs.
It matched all 100 offered proposal turns to their raw response and usage receipt.
Evidence: `evidence/learning-recovery-20261102/acquisition-audit-v2.json`.

| Observation | Recorded result |
| --- | --- |
| Stateless A | 54 tasks; no proposal turn by design |
| Exact cache C | 50 offered turns, 50 skips; 4 tasks had no recorded answer |
| Validated E | 50 offered turns, 50 skips; 4 tasks had no recorded answer |
| Submitted candidates | 0; validation therefore received no candidate |
| Proposal output tokens | 99 replies used 27 tokens; one used 78 |
| Visible thinking blocks | One; hidden reasoning-token totals are unavailable |
| Proposal inference cost | $1.195964 API-rate-equivalent, included in the original cost |
| Unknown provider outcomes | 0 |

Two details in the older diagnosis need qualification. The instruction **did**
mention reuse in later tasks. It did not say that those tasks shared the same
record format and labels. Also, the claim that every reply had no thinking was
too strong: one raw response contains a visible thinking block. That response
describes its task answer as weak and declines to retain a proposal. One such
response cannot explain the other 99. These corrections do not change any score.

The existing report remains the official result: **uninformative for the learning
thesis**. No acquired library existed. A corrected audit is not a positive result.

The new read-only report reproduces all nine complete trajectories. These pooled
numbers include every attempted task; success means official score exactly 1.
Costs are API-rate-equivalent. Latency excludes the separate promotion process.

| Arm | Success | Model cost | Cost/success | p50 / p95 seconds | Tool success |
| --- | --- | --- | --- | --- | --- |
| A | 23/54 (42.6%) | $1.2813 | $0.0557 | 21.2 / 44.0 | 89.7% |
| C | 24/54 (44.4%) | $1.8915 | $0.0788 | 23.0 / 50.8 | 91.0% |
| E | 22/54 (40.7%) | $1.8610 | $0.0846 | 25.1 / 47.5 | 90.5% |

There were no missing tool-result records. Tool errors and undelivered answers
remain in the evidence. No candidate validation ran; C/E nevertheless spent
103/149 seconds in promotion-stage processes that handled the recorded declines.
The small accuracy differences do not establish a learning effect or superiority.

## Interface, incentives, and behavior

- The root instruction tells the model to finish with `done`. The later tool
  result says the answer is final, then offers an optional turn with no penalty.
  An empty `skip_proposal` was a valid terminal action. This may favor stopping.
- There was no explicit shared-task context or objective to reduce future work.
  The structured mode already addresses that framing. It is still untested live.
- E asks for a self-contained `(fn [text] label-or-nil)` plus a predicate. Much of
  the recorded task code consists of inline boolean or regex tests. Packaging
  them requires extra work and an applicability decision.
- An additional proposal call rereads history without provider cache use. It is
  charged even when the model declines. No evidence shows that this cost caused
  the observed behavior.
- The older development capture analysis found eligible code in 118/162 tasks
  and at least one candidate passing the candidate rule in 51/162. That is an
  offline upper bound with selected labels, not autonomous acquisition.

No model intent is assumed. The next live check tests the existing structured
interface. It does not force a proposal, seed a library, or auto-capture code.

## Validation audit and bounded repairs

Proposal shape checks run before promotion. E uses a separate isolated worker
for its candidate and a fixed controller-only development panel. Approval checks
precision, coverage, executable behavior, library regression, and code identity.
A version becomes active only after its receipt and parent chain verify. A stage
failure stops the trajectory. Rejections retain their artifacts and reasons.
The zero-proposal result occurred before this validation path.

Two small interface repairs are included:

1. Structured/capture replies must use the offered proposal tool. A structured
   decline must have a nonblank reason of at most 300 characters. The old optional
   control keeps its prior semantics. Malformed replies are recorded, not retried.
2. Exact caching can use the same structured framing (`CS`) as executable reuse
   (`ES`). This removes an avoidable framing difference in the later control.

The development run uses only ES. Capture remains experimental and disabled.
Label-abstention adaptation is also disabled in this new plan. No new agent,
retrieval service, memory database, or execution architecture is introduced.

The real-worker fixture now checks a structured proposal, promotion, reuse in a
new task process on a record absent from acquisition and validation, and refusal
of an exact-cache lookup on that record. Its responses are scripted. It cannot
establish autonomous model reuse. `benchmark.learning_report` requires live
gateway evidence, complete accounting, a committed pre-restart artifact, and
actual post-restart calls to that artifact before it accepts a live lifecycle.
The runner also checks the 6 GiB disk floor before each task and stops on a
crashed promotion process. The report requires cleanup and Docker-session
evidence even for the last task. Missing evidence blocks a lifecycle claim.

## Pilot 1b environment recovery

The original checkout remains `/Users/mackianni/aljure-unblock-v4`. Its source is
`98fc07c11177f499efd052c2ce1f784f9ccb5d9d`. A separate detached checkout under
`var/learning-recovery-20261102/pilot1b-source` uses exactly that source.

The worker was rebuilt from the original pinned base
`clojure@sha256:e3faac65b894d75b36670204a6d6b69bee5efc81e4d2dda5f1eded996614836e`.
Its new identity is
`sha256:842a0864d19e81264e531c059bfa013c929457a4321e146f4b9df84d137d7787`.
An external Docker image archive and SHA-256 seal preserve this identity.

Isolation, SCI contract, artifact path, acquisition, native Prime isolation,
subscription relay, and S/D/P/R reuse fixtures passed. All four regenerated plans
passed preflight. The recovery compared 2,437 historical files before and after:
all were unchanged. SQLite WAL/SHM sidecars are excluded from that file count.
The original missing image is not claimed to have been recovered.

The new plans require new approval because their image identity changed. A full
restart under those plans is the preferred research option; it avoids pooling
old and rebuilt images. Old S1/D1/P1 remain descriptive evidence, including the
two disk-pressure failures. No Pilot 1b inference was resumed in this recovery.

## Next gate

See `LEARNING_DEVELOPMENT_PROTOCOL.md` for the bounded development model check and
`LEARNING_HELDOUT_PROTOCOL.md` for the subsequent controlled design. Execution
approval applies only to an exact frozen plan hash. A passing fixture never
substitutes for the development model gate, and no development score is held-out
evidence. The freeze package records current tests, proofs, plan hash, and limits.
