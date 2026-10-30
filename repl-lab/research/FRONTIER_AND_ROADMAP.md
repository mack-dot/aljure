# Recovering the frontier, proving executable learning, then scaling

**Status (2026-10-30):** analysis and preregistration. Nothing live has run for this document.
Scorecard: `RESEARCH_SCORECARD.md`. Diagnosis data: `PILOT1_RESULTS.md`, `THESIS_PILOT_RESULTS.md`,
`UNBLOCK_ACQUISITION.md`. Frozen plans for approval: `UNBLOCK_ACQUISITION.md` §12b.

Two advantages are to be established separately:
1. A minimal Aljure harness that approaches or beats pinned Prime on the quality–cost–latency frontier.
2. An evolving Aljure that moves that frontier further through validated executable knowledge.

Neither is established yet. The scorecard shows what is.

## 1. What the evidence supports today (Phase 1 summary)

- **Replicated:** Aljure costs 42–51% of Prime at matched model on the 21-task synth suite (4 Opus
  plans, 1 Sonnet plan, all the same direction) and 42–64% on the label-count suite (3 plans), with
  lower p50 latency in 7 of 8 of those runs. This is a cost/latency advantage.
- **Not shown:** accuracy parity. Aljure scored below Prime in every Opus paired run (−0.02 to −0.15)
  and −0.031 under Sonnet (CI includes 0). No paired plan was ever run twice.
- **Run variance is larger than most claimed effects.** The same stateless plan (Pilot 1 S) scored
  0.404 then 0.226 on compatible tasks; Prime's identical label-count runs went 0.474 → 0.388 → 0.279.
  Any frontier claim therefore needs repeated plans, not one run.
- **Layers:** (a) stateless: cost/latency replicated, accuracy not; (b) acquisition: never
  model-initiated on a benchmark task (0 of 100 optional turns); (c) artifact execution in SCI:
  proven, hash-attributed, live (262,713 recorded calls in Pilot 1 D); (d) semantic integration:
  minority of tasks, no measurable benefit; (e) cumulative learning: none, every paired run used the
  empty library.

## 2. Why reuse has not improved end-to-end performance (Phase 2, ranked)

From the 162 Pilot 1 task runs and the 162 A/C/E runs. Each item: the evidence, then a
remediation hypothesis that a frozen pilot can test.

1. **The asked label is outside the artifact (largest).** 8 of 14 Pilot 1 count tasks ask for
   "description" or "entity", which the seed never decides. On those, no arm improved (log-error
   0.29–0.30 in S, D and P). On the 6 the seed decides, log-error fell 33–46% (exploratory).
   *Hypothesis:* restricting to addressable tasks shows value. *Test:* Pilot 1b's suite.
2. **Residual bookkeeping.** The library leaves 49–68% of records undecided per window, and the
   model mishandles them both ways: D treated unresolved as negative (335 for a gold 398, with 1,781
   unresolved); P over-counted the residual with its own heuristics (1,238 and 1,202 for 965). The
   library's own count error is 7.6; the residual error is 139–156. *Hypothesis:* a deterministic
   three-state ledger (positive / negative / unresolved) removes the collapse and the double count.
   *Test:* Pilot 1b arm R.
3. **Delivery failures.** 59 of 162 A/C/E tasks and 65 of 162 Pilot 1 tasks first answered in text;
   8 and 17 never delivered. In Pilot 1, D had the most text rejections (27 vs S 20), so artifact use
   may raise the failure rate (not significant at n=2 runs). Scored offline, half the undelivered
   text answers were correct. *Hypothesis:* a narrow completion fix (accept the model's own final
   "Answer: …" line as the done summary only when the correction turn also fails, never rewriting
   it) recovers those tasks on every arm equally. *Test:* preregistered as an ablation, not applied
   to Pilot 1b, so 1b stays comparable to Pilot 1.
4. **Supplying evidence costs more than it saves.** P cost 1.52× S (longer prompts, more calls:
   323 vs 226), which is why criterion (a) failed despite +0.061. *Hypothesis:* the ledger note (R)
   shortens the model's work on the residual; cost per task falls below P's. *Test:* Pilot 1b.
5. **Acquisition friction.** 0 proposals in 100 optional turns; 81% of tasks contain capturable
   detectors; 31% of tasks hold one that would pass validation. *Hypothesis:* structured turns and
   controller-assisted capture yield promotions where the optional turn yielded none. *Test:* the
   acquisition ablation (§4 below).
6. **Attribution blind spot (measurement, not performance).** The preregistered `eligible-reuse`
   heuristic recorded 0 while the model called the library in 28 of 42 tasks. The original measure
   is kept and reported; source-attributed invocation and value-in-answer are added alongside
   (`benchmark/paired.py source_attributed_reuse`), reproduced exactly on Pilot 1's records.

Task-level examples are in `evidence/pilot1-results/pilot1-detail.json` (per task, per arm:
declared count, gold, library count, residual error, invocation, attribution).

## 3. Pilot 1b: the value of reuse where it applies (Phase 3)

`UNBLOCK_ACQUISITION.md` §8b has the preregistered protocol. In brief:
- **Suite** `reuse-pilot-1b` (`7dd5e1d4…`): the 28 count questions on Pilot 1's 7 fresh trec windows
  whose asked label the seed decides (7 each of abbreviation, human being, location, numeric value).
  The windows were exposed to the model in Pilot 1; this is disclosed and is why no new seed is
  built from them.
- **Arms:** S (stateless), D (model-directed), P (controller-supplied labels), **R** (P plus a
  three-state ledger for the asked label; unresolved never becomes negative). Two runs each.
- **Task classes, evaluated separately:** addressable (the library resolves ≥ 50% of the window),
  residual-dependent (< 50%); plus Pilot 1's spam refusals as the incompatible-taxonomy control
  (already shown 12/12, not re-run).
- **Endpoints:** official score; count log-error (paired, window-clustered bootstrap); cost per run
  including controller overhead; latency; delivery failures; refusals; source-attributed reuse.
- **Decision (fixed):** the library is useful when supplied if P or R reaches log-error ≤ 0.75 × S
  with the paired CI below 0 at cost ≤ 1.5 × S. Bookkeeping helps if R's log-error ≤ 0.8 × P's.
  D is used reliably if it calls the library in ≥ 50% of tasks. Falsified: neither P nor R meets
  the bar on the tasks the artifact can address.

## 4. Autonomous acquisition ablation (Phase 4)

`UNBLOCK_ACQUISITION.md` §9. The A/C/E study is the negative control (arm E is retained unchanged).
Arms: A (stateless), E (optional turn), ES (structured turn, decline with reason), EX
(controller-assisted capture), EXS (capture with controller-selected, validated applicability).
Guards against hardcoded answer sets, session data and non-transferable rules are in
`capture.clj`; every candidate is validated on the panel before promotion. Endpoints: candidate
yield, promotion precision/coverage on new records, acquisition cost, source-attributed invocation
afterwards, F2 refusals, count error split by whether the promoted function decides the asked label.
The model is never required to write code: a reasoned decline is a valid outcome.

## 5. Pareto-frontier framework (Phase 5 groundwork)

A frontier point is (official score, cost per task, p50 latency) for one harness on one suite at one
model, from **repeated runs of one frozen plan** (≥ 2). Rules:
- Compare only within a suite hash and model. Never pool suites.
- Report the per-run spread beside every mean; an advantage counts only if the intervals from
  repeated plans separate, or a paired window-clustered CI excludes 0.
- Three harness rows per suite: Prime (native memory, skills and refinement available), stateless
  Aljure, evolving Aljure (library in force at each task position). The evolving row charges
  acquisition, validation and retrieval.
- Learning curves: score and cost by task position, per ordering; a causal library ablation
  (the same order with the library withheld) is the test that improvement depends on retained
  knowledge.
- Matched total budgets: the per-task caps are the same for all rows; spend is reported, not
  equalized after the fact.
Existing paired runs already give the Prime and stateless rows for suites `b157ee63` and `dc164044`,
but each is a single run; the first frontier step is therefore to repeat the best stateless plan
and the matching Prime plan twice each (about $25 Opus, $8 Sonnet) before any evolving row exists.

## 6. Staged roadmap: scale only what shows evidence (Phase 6)

| Stage | Gate to pass before the next | Cost |
| --- | --- | --- |
| 1b: value where the artifact applies | P or R useful by §3's rule; no negative transfer | ~$5 |
| Acquisition ablation | ≥ 1 arm acquires reliably (2 of 3 trajectories promote; new-record precision ≥ 19/20) | ~$10–14 |
| Delivery fix ablation | recovers undelivered answers on all arms without changing any delivered answer | ~$3 |
| Frontier baseline | repeated stateless and Prime plans; spread known | ~$30 |
| Curriculum (Phase 5) | evolving Aljure beats its own stateless row on cost per verified solution with activation ≥ 80%, and the library-withheld ablation loses the gain | ~$40–60 |
| Compute scaling | only after the curriculum: targeted vs uniform extra compute at matched cost | later |

No async-agent or test-time-compute framework is built before the curriculum gate. A mechanism
is scaled only with actual activation, a credible quality or cost gain, no material
negative-transfer regression, acceptable latency and reproduction across independent contexts.
