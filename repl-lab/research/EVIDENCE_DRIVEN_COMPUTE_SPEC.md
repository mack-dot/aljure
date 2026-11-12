# Evidence-driven compute: what the controller authorizes, and why

**Status:** specification. The done-time verification pipeline (format,
typed-evidence extraction, invariants, blind review, stop rule) is specified in
`CONTROLLER_VERIFICATION_DESIGN.md` and is not repeated here. This document
gives the general rule for authorizing extra reasoning actions, the signal
taxonomy, the first deterministic policy, and its estimates.

## 1. Rule

The model may **propose** an action. The controller may also **dispatch** one
itself. In both cases the controller authorizes it only when **all** of these
hold:

1. A signal the controller can observe makes it eligible. Self-reported
   confidence is never a signal.
2. The marginal cost fits the remaining budget and keeps the root floor.
3. Latency allows it: the remaining wall time is at least 2 × the plan's p95
   call latency for each extra sequential call.
4. The policy's expected benefit per dollar for this situation is at least
   the plan's threshold λ. Benefit and cost come from the table in §4, which
   is fixed per plan.
5. The action's per-task counter is not spent. Every action has a bound.

The L2 evidence (0 of 11 arms used the described helpers) means that
model-proposed actions cannot carry the policy. Controller-dispatched actions
carry it, and model proposals are measured separately.

## 2. Signals

| Signal | Observable by the controller without model cooperation? | Source | Used as |
| --- | --- | --- | --- |
| Answer violates the declared answer contract | **yes** | the `done` summary | trigger |
| Answer not linked to recorded per-item state | **yes** | extraction probe at `done` | trigger |
| Ids out of scope, duplicates, missing map coverage (failed invariants) | **yes**, once evidence is extracted | probe and verifier | trigger |
| Disagreement between independent judgements | **yes**, after the controller dispatches a blind reviewer or a replicate | reviewer or replicate result | trigger for reconciliation |
| Records never shown whole to the model (incomplete coverage) | **yes** | recorded tool results | report only (a poor trigger: `ADAPTIVE_COMPUTE_POLICY.md`) |
| Unresolved requirement (no `done`; delivery failed) | **yes** | ledger | existing F1 and correction paths |
| Missing evidence (no computation behind a stated number) | **yes**: the answer value never appears in a tool result | ledger | report; trigger only through "not linked" |
| Model-recorded `:unknown` or conflicts | only if the model records them; 0 of 11 L2 arms did | worker | trigger when present |
| Model text saying "estimate" or "judgement call" | text only | reply | **never** used (self-report) |

## 3. Actions

| Action | Proposed by | Dispatched as | Bound per task |
| --- | --- | --- | --- |
| Continue (one more turn) | model | ordinary turn | the plan's step and call caps |
| More effort | model or controller | per-child `:profile`, only if the plan and gateway authorize it | none authorized now (`ELASTIC_EXECUTION_DESIGN.md` §4) |
| Spawn an independent branch | model (`agent_spawn`, phase C) | elastic child | `max-children`, quotas |
| Reinspect uncertain records | controller (targeted notice) or model | a root turn | 1 notice |
| Deterministic verification | controller | the probe and verifier: SCI or controller code, no model call | per `done` |
| Reconcile a disagreement | controller | a targeted notice to the root, or a third blind replicate taking the median for numeric answers | 1 |
| Stop | controller | accept, with unresolved items recorded | always reachable |

**Independence rules:**
- A reviewer or replicate never sees the first answer, labels, history or
  worker.
- A replicate gets the task verbatim with a fresh worker.
- A reviewer gets the sampled records shuffled and renamed
  (`CONTROLLER_VERIFICATION_DESIGN.md` §3 V3).

**Deterministic recomputation:**
- When the answer comes from `done/eval`, the controller already computes it
  in SCI (`runtime.clj:83-128`).
- The verification pipeline adds a recomputation of the linked quantity from
  the extracted evidence (count of the set, or the label histogram) and
  compares it with the summary.

**Format** is validated separately from semantics (V0). No single completion
gate covers every task type: the verifier decides which stages apply.

## 4. First policy P1 (deterministic), with estimates from development evidence

**Unit costs** (Opus, measured):
- Aljure count arm $0.22–0.24 (L0/L1 means; range $0.11–0.40). Prime $0.53
  (range $0.2–0.9).
- One cached root turn: about $0.02–0.04 and 5–15 s.
- One reviewer call with 24 records inline (uncached): about $0.03–0.06 and
  10–20 s.
- One blind replicate: about one arm.

| # | Situation (observable) | P1 action | Marginal cost | Expected benefit (dev evidence) | Benefit per $ | P1 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Answer breaks the answer contract | format notice (1) | $0.02–0.04, only when triggered | Fires in about 10% of Aljure count arms (3 of 33). A rescue is worth up to 1.0 on an exact task (F2 task 1); ≈ 0 when the count is far off anyway (all 3 L-trace cases) | high | **on** |
| 2 | Aggregate answer, evidence not linked | evidence request (1) | $0.02–0.04; about 1/3 of aggregate tasks (11 of 33) | Enables 3 and 4; accuracy effect unknown (L1 per-item state did not move MAE beyond noise) | unknown | **on** (enabler) |
| 3 | Invariant fails on the extracted evidence | targeted notice (1) | $0.02–0.04 | None observed so far: every arm read all records whole | low | **on** (cheap) |
| 4 | Aggregate, linked, `n ≥ 50` | blind review of `k = 24` sampled records, then a targeted notice when they disagree | $0.03–0.10 | **Probably small.** Per-task bias is shared with Prime (r = 0.865), so a same-model reviewer probably shares it. At most it fixes the sampled items it disagrees on, about 1–3 per task, and it gives a measured bias estimate | about 0.1–0.3 score/$ at best (assumed) | **measured in the V3 experiment**; default off |
| 5 | Aggregate, linked; replication | 1 blind replicate; on disagreement above tolerance, a 3rd and the median | +1–2 arms ($0.22–0.48) | Variance only: removes outliers such as Prime's +30 swing; does not touch shared bias | < 0.1 score/$ (assumed) | **only in the uniform-compute arms** (C), as a comparison |
| 6 | Non-aggregate answer | format only | 0 | — | — | on |
| 7 | Random audit: probability 0.2 (seeded), at most 1 per task, on tasks where 4 did not fire | blind review | as in 4 | Measures the miss rate of the skip rule ("confidently wrong") | estimation | on whenever 4 is on |

**How the benefit numbers were reached:**
- Row 1: rate from `evidence/controller-verification/l-traces.json`. Value
  from the scorer: `0.75^|e|` for numbers; an unparsed answer scores 0.
- Row 4: if the root's net bias is `b` items over `n` records, a perfect
  reviewer of `k/2` items per stratum finds about `k·|b|/n` disagreements. For
  MultiNLI (`b ≈ −9`, `n = 438`, `k = 24`) that is about 0.5, so a review round
  changes the count by about 1 at best. Review cannot close a shared bias.
  This is a prediction to falsify, and the V3 experiment's offline
  reviewer-precision endpoint tests it.
- Row 5: Aljure's repeated count errors keep their sign across runs (for
  example AG News 025: +6, +5, +4, +2; app_reviews negative: −24, −18, −20).
  The median of independent runs therefore keeps the bias.

**Consequence:**
- The cheapest reliable gains are deterministic: rows 1–3.
- Extra model calls (rows 4 and 5) are justified only by a measured effect.
- The experiment plans test both rows against matched-budget controls, so a
  gain from more compute cannot be read as better allocation.

## 5. Bounded random audit

- On tasks where the policy chose **not** to act, a seeded random 20% (at most
  1 per task, and at most 3 per run) get the same review anyway.
- The audits measure the rate of confidently wrong answers that the skip rule
  passes:
  - reviewer disagreement on skipped tasks;
  - offline, the error against gold.
- Audit results are recorded with `:audit true` and analysed separately.
  An audit sends no targeted notice, so the trajectory of an audited task
  stays the same as without the audit. This lets the audit estimate the miss
  rate without changing the outcome.

## 6. Coding tasks

For coding tasks the verifier is the task's declared tests, contracts or
invariants, executed in the isolated worker. The rules:
1. Completion is reported as test results.
2. A failing test is a V2 invariant failure: one targeted notice.
3. Review means a blind reviewer child reading the diff and the task, not
   the author's reasoning.
4. No model judgement replaces a test.

This is outside the current experiments.

## 7. Endpoints that every policy experiment reports

- **Activation, per action:** eligible, fired, acted.
- **Refused actions:** `elastic-denied` and spent counters.
- **Unnecessary actions:** fired, but the answer did not change.
- **Failed actions:** an invalid reviewer reply, an unknown outcome.
- **Per-policy cost and latency:** calls, tokens, cost, p50 and p95.
- **Accuracy:** official score, count error, and item-level accuracy where
  gold labels exist offline (MultiNLI).
- **Variance across contexts:** a cluster bootstrap over windows.
