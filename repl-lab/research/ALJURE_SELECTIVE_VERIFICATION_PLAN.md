# Aljure selective verification: plan, offline evidence and decision (2026-11-04)

Written against the owner's goal "Selective Verification and Compute Efficiency"
and the two follow-up instructions of the same evening (fix the concurrency
reservation first; find the mechanism behind Aljure's cost and Prime's accuracy;
do not optimize the detector on recorded outcomes; evaluate any trigger on
disjoint contexts; prefer a simple falsifiable trigger). **No paid inference was
run. Nothing is frozen for execution.** The offline evidence falsified the simple
trigger before any controller change was justified, so sections 5 and 8 describe
what was deliberately not built and what is proposed instead.

**Decision: NO-GO for evidence trigger v1 as a selective-verification mechanism.
ITERATE on the research question with the experiment in section 8.**

## 1. Prior experimental evidence and limitations

- Phase B, held-out, 49 contexts (`HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md`): Aljure −
  Prime +0.040 [−0.044, +0.138], inconclusive; Aljure at 32% of Prime's cost.
- Verification ablation, development, 10 contexts
  (`ALJURE_VERIFICATION_MECHANISM_RESULTS.md`, commits `cd95720`, `bac800e`),
  re-verified here: the archive's 3,225 files match their hashes; 571 receipts
  equal 571 calls; an independent rescore of all 144 archived answers reproduces
  every score. A1 − A0 = +0.150 [0.000, +0.300]; P1 − P0 = +0.150; difference-in-
  differences 0.000; A3 − A1 = −0.091; A2 − A0 = +0.072. The A3 gate fired zero
  times and `audit-labels` was never called; no improvement is attributed to a
  primitive that was not invoked.
- Limitations carried forward: one run per plan; 10 development contexts; the
  +0.150 is an instruction effect present in both harnesses; two Prime arms were
  killed by the per-arm cap when they spawned subagents.

## 2. Root-cause findings and hypotheses

**Why Aljure is cheaper (exact, from provider receipts; Phase B, 58 and 56
completed arms).**

| Per arm | Aljure | Prime | Gap |
| --- | --- | --- | --- |
| Total | $0.0157 | $0.0501 | $0.0344 |
| Cache writes | $0.0081 (51%) | $0.0380 (76%) | $0.0299 |
| Cache reads | $0.0009 (6%) | $0.0043 (9%) | $0.0034 |
| Output | $0.0067 (43%) | $0.0079 (16%) | $0.0011 |
| Uncached input | $0.0000 | $0.0000 | — |
| Calls | 3.34 | 4.14 | |
| Per call | $0.0047 | $0.0121 | |

Per call, Prime reads about 9,700–11,800 cached tokens and writes about 3,800;
Aljure reads about 2,500 and writes about 1,000. The static prefix (harness
prompt and tool schemas) is about 12,100 tokens for Prime and 2,600 for Aljure.
Both harnesses see the provider cache miss on roughly a third of calls, and each
miss rewrites the whole prefix at the cache-write rate. So the gap is prefix size
times calls: $0.030 of the $0.034 is cache writes of that prefix, $0.003 its
reads, $0.001 output. Output cost is nearly equal. Two consequences:

- The advantage is structural (a small prompt), not "less computation": Aljure
  makes 0.8 fewer calls and emits 15% fewer output tokens.
- It is sensitive to caching. With no misses the per-arm costs would be about
  $0.010 and $0.017 and the advantage about 1.7× instead of 3.2×.

In the ablation the audit contract raised Aljure's cost from $0.0175 to $0.0327
(output $0.0082 → $0.0147, cache writes $0.0083 → $0.0160): verification is paid
in output tokens and in the conversation it adds.

**Why Prime is more accurate (ledger features, baseline arms, both runs).** On
the 8 items Prime won by more than 0.2: Prime ran 3.5 evaluations against 2.5,
received a median 7,600 characters of tool output against 4,800, kept a literal
label record in 4 of 8 against 0 of 8, and relied on keyword-pattern counts in
2 of 8 against 4 of 8. On the 50 items both got right, both read little (2,600
and 3,600 characters). Prime's edge is one more step and more of the data read
on the hard items.

**Hypotheses.** H1: Aljure under-reads on judgement tasks; its instructions say
"read only what you need", Prime's do not. H2: the audit instruction works by
inducing exhaustive labelling, in any harness. H3 (falsified below): a
deterministic check of the execution ledger can tell which answers need that
labelling.

## 3. Detector specification (`benchmark/evidence.py`, `evidence-v1`)

Inputs: the task question and the controller's ordered ledger of root-session
evaluations (source, status, returned value). No model call; no gold, score or
answer text as input.

- **Task class** from the question text: `label-comparison`, `label-count`,
  `pairs`, `structural-count`, else `unknown`.
- **Facts:** literal item-level records typed into the worker (index
  collections, label strings over a small alphabet, id-to-label maps), numbered
  items displayed, count results, direction flips between successive counts,
  the margin of the last two-way count, whether the last step failed.
- **States:** `supported`, `incomplete`, `approximation`, `contradictory`,
  `missing`, `undeterminable` (unrecognised class or unreadable ledger; never
  triggers).
- **Trigger v1** (pre-registered in `EVIDENCE_TRIGGER_V1.md`, commit `70a63e0`):
  O1 contradiction, O2 narrow margin (< 0.30), O3 missing aggregation, O4
  incomplete coverage; trigger if any holds.

The detector establishes structural sufficiency only; it says so in its own
documentation and never claims an answer is correct.

## 4. Verification-trigger state machine (as designed; not wired)

```
root proposes an answer (done, done/eval, or accepted terminal text)
  -> controller assesses the ledger (pure function, recorded as an event)
     undeterminable / supported / wide-margin approximation -> accept
     incomplete | contradictory | narrow-margin | missing:
         first time in this task -> answer is not submitted; one corrective
                                    request naming the condition; counter = 1
         already requested once   -> accept, record the state after correction
  any detector error -> accept (fail-safe), record the error class
```

One request per task, charged to the task's ordinary budgets; the corrective
work runs in the isolated worker; the controller records the condition, the
request and the state at the next finalization.

## 5. Controller and worker changes: built and not built

Built (offline, tested): the detector reference and replay tool
(`benchmark/evidence.py`), ledger readers for both harnesses, the corrective
request texts, the reservation policy (section 7).

**Not built, on purpose:** the Clojure controller hook, the contract flag, the
prompt-only audit and helpers-only contract variants, and the native Prime
continuation (`prime-agent --continue` exists and would carry a corrective
message into the same session). The trigger failed its pre-registered offline
test (section 6), so wiring it into two harnesses would have added machinery the
evidence does not support. The existing SCI helpers stay as they are; the
ablation showed them unused.

## 6. Offline correctness, security and discrimination tests

**Unit tests** (`test_python/test_evidence.py`, 10 tests): each observable fires
on its condition; a wide margin, a complete record and a computed structural
count do not; an unrecognised task and an unreadable ledger are undeterminable
and never trigger. Fabricated or malformed evidence does not satisfy the
detector: a result string claiming an audit, a map literal declaring sufficiency,
a record inside a step that failed, a computed collection (`(set (range 400))`),
prose, `None` or non-dict steps. A child session's steps are ignored. The
function signature and source contain no score or gold input.

**Exploratory replay (frozen, not an evaluation).** The first draft ("no
sufficient tally recorded") fired on nearly every label task in the three
recorded runs, right or wrong
(`evidence/evidence-trigger-exploratory-20261104/`). Those 66 contexts became
the development set.

**Pre-registered evaluation on disjoint contexts**
(`evidence/evidence-trigger-v1-disjoint-20261104/`): 134 completed baseline
Aljure arms from the thesis pilot (arm A, three seeds), the reuse pilots (arm S)
and the ten-case Pairs 8K run; 20 contexts, none in the development set.

| Set | Arms | Right | Wrong | Triggered | Precision | Recall | False-trigger rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pooled | 123 | 43 | 80 | 67 (54%) | 0.46 | 0.39 | 0.84 |
| label-comparison | 34 | 23 | 11 | 30 (88%) | 0.37 | 1.00 | 0.83 |
| label-count | 80 | 13 | 67 | 33 (41%) | 0.61 | 0.30 | 1.00 |
| pairs | 9 | 7 | 2 | 4 (44%) | 0.00 | 0.00 | 0.57 |

**FAIL** on all three criteria (precision ≥ 0.50, recall ≥ 0.50, false-trigger
rate ≤ 0.30). Estimated effect had it been used: about 12 of 80 errors avoidable
(31 wrong-and-triggered × the ablation's 0.375 fix rate) at about +$0.020 per
task, more than the always-on audit's measured +$0.0145. It is neither selective
nor cheaper. The rule was not re-tuned on this set.

What this says: correct and incorrect answers look the same in the execution
ledger. Right answers are usually reached without any recorded tally, and a
count's margin does not predict its correctness. The stage-8 tests "missing
tallies trigger" and "complete tallies do not" pass at the unit level; the
mechanism is falsified at the level that matters, discrimination.

Stage 8 items 5–7 (budget, isolated corrective step, controller recording) apply
to the controller hook, which was not built.

## 7. Reservation-policy repair (built and tested)

The gateway reserves the whole declared context bound at the highest input or
cache rate plus maximum output for every call, $4.32768 at Sonnet 5.5 rates, and
releases it only on the receipt. Phase B ($4.40) and the ablation ($4.93)
admitted one call in flight while declaring a concurrency of 8; when native
Prime spawned four subagents their calls were refused and the arms died.

Policy for new plans (`benchmark/headtohead.py` `check_reservation_policy`, used
by both drivers): `usd_per_arm ≥ concurrent_requests × reservation + $0.50`, so
the declared concurrency is what the cap admits; the reservation itself is never
lowered. Run-level rule unchanged: an arm starts only if known spend plus unknown
reservations plus `usd_per_arm` fits under the ceiling.

Invariants and where they are enforced and tested:

| Requirement | Enforced by | Test |
| --- | --- | --- |
| Spend plus active reservations within the cap | `controller/reserve!` | `reservation_policy_test.clj`: a cap of K admits exactly K calls in flight (K = 1, 2, 4); the next is refused |
| Reconciled exactly once | `controller/reconcile!` (status must be pending or unknown) | second reconcile throws |
| Unknown outcomes keep their reservation | `controller/recover!` | an unknown call still occupies one slot; a late receipt reconciles once at real cost |
| Failed calls do not release uncertain charges | same | same |
| Concurrent requests cannot oversubscribe | `reserve!` is one atomic ledger update | exposure checked after every admission |
| Same limits for both harnesses | one config, `gateway_config` | `test_headtohead.py` policy tests |

**Budget consequence.** The $12 ceiling is incompatible with any concurrency
above one for a run of this size. Required ceiling = high spend estimate + one
per-arm cap:

| Declared concurrency | Per-arm cap | Ceiling at a $10 high estimate | at $16 |
| --- | --- | --- | --- |
| 1 | $4.83 | $15.2 | $20.8 |
| 2 | $9.16 | $19.6 | $25.2 |
| 4 (what Prime spawned) | $17.81 | $28.2 | $33.8 |
| 8 (Prime's nominal) | $35.12 | $45.5 | $51.1 |

These are reservation ceilings, not expected spend, which stays at the
experiment's estimate. A cheaper honest alternative would be reserving on a
provider token count per request instead of the context bound; that needs the
count endpoint verified on the subscription transport and is not assumed here.

## 8. Experimental protocol: what is proposed instead of the six arms

The six-arm plan in the goal (A2, A3 and P1 built on the selective trigger) is
not frozen, because its central mechanism failed offline. The question that the
evidence now supports asking is the owner's second priority: does spending part
of Aljure's savings on targeted computation raise its correctness, and what
computation helps? Proposed development ablation, to be frozen only on the
owner's direction:

| Arm | Contract | Tests |
| --- | --- | --- |
| A0 | Aljure base (text-answer-v2) | baseline |
| A1 | A0 + audit contract, prompt-only (new text, no helpers loaded) | H2 without the unused primitives |
| A2 | A0 + evidence-coverage instruction only: on label-judgement questions, display every relevant item in full before deciding; no audit | H1, the cheaper targeted computation |
| A3 | A1 + A2 | whether they add |
| P0 | native Prime | reference |
| P1 | Prime + the audit contract prompt | general against specific |

Class-gated application is the one selectivity the evidence supports: the
contract text is added only when the trusted task text is a label-judgement
question, so structural counts pay nothing. Inputs: fresh development questions
from the pinned windows (new seed, every previously used id excluded), stratified
into label comparison, label count, long-context frequency, pairwise aggregation
(Pairs 32K development tasks not used in pilot 1), deterministic counts and easy
comparisons as negative controls; the ablation's five decisive tasks kept as a
separate regression stratum outside the primary. 24 fresh tasks plus repeats.
Primary: A2 − A0 (paired, context-clustered). Secondaries: A1 − A0, A3 − A1,
A2 − A1 on cost per full-score equivalent, requests, tokens, latency,
completion, negative-control cost, Aljure against Prime, difference-in-
differences. Expected spend about $7; ceiling $28 at concurrency 4 or $15 at
concurrency 1 with the Prime-subagent risk disclosed.

## 9. Cost and latency measurement methodology

Cost from provider receipts only (`gateway/usage.jsonl`), by token category at
the pinned rates, per call and per arm, with first-call and later-call cache
writes separated as in section 2; cost per full-score equivalent = arm cost /
arm score sum. Latency = the harness process's own wall time
(`execution.json`), with time to first request and model time from the gateway
transport log; host-saturated runs are reported as comparative only. Requests,
tokens and tool calls from the ledgers. Added computation per corrected answer =
(treated − control cost on tasks the treated arm fixed) / fixes.

## 10. Statistical decision rules

Unchanged from the campaign: context-weighted paired difference, repeats
averaged within task, 10,000-resample cluster bootstrap over independent source
contexts, δ = 0.05; superior only if the 95% lower bound is above zero and the
estimate ≥ δ. Correlated questions from one context are one cluster. For the
next ablation, GO to a held-out test only if the primary gains ≥ 0.10 with a 95%
lower bound above zero and the treated arm's cost stays ≤ 50% of Prime's.

## 11. Risks of over- and under-verification

- Over-verification is the measured risk: v1 would have fired on 84% of right
  answers. Any always-on instruction costs 1.3× where it cannot help.
- Under-verification: single label counts from a pattern cannot be assessed
  structurally (recall 0.30 on label-count tasks).
- A structural check can be satisfied by a wrong record; it must never be
  reported as correctness.
- Class gating by question text is brittle outside OOLONG-style wording; an
  unrecognised task gets no contract, by design.

## 12. Expected advantages and falsification criteria

- H3 (ledger-based selective trigger): **falsified** by section 6.
- H1 (evidence coverage) is falsified if A2 − A0 < 0.05 or if A2 costs more than
  A1 for no more gain.
- H2 is falsified as Aljure-specific if P1 − P0 again equals A1 − A0.
- The cost position is falsified as structural if the gap closes when the cache
  hit rate rises; section 2 quantifies it (3.2× → about 1.7×).

## 13. Frozen execution readiness

Nothing is frozen. Ready offline: the reservation policy and its tests; the
detector, its tests and both evaluations; the cost decomposition. Tests: Clojure
223 tests / 3,260 assertions pass; Python suites for the drivers, evidence and
policy pass. Needed before a paid run: the owner's choice between the section 8
ablation and stopping at the audit contract; a ceiling above $12 or acceptance
of concurrency 1; then the contract texts, the fresh suite, the driver campaign,
a plan hash and preflight. Historical runs and archives are unchanged.
