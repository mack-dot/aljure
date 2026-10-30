# Unblocking cumulative executable learning

**Status:** offline work done; Pilot 1 and Pilot 2 preregistered here and frozen (section 12),
awaiting operator approval. No model call, no sealed held-out access and no change to the A/C/E
pilot were made for this work. Evidence: `evidence/unblock/`, `evidence/reuse-pilot-seed*/`.

**Thesis (unchanged):** can an agent autonomously accumulate, validate, structurally transform and
reuse executable knowledge, to improve future-task quality and inference efficiency?

**Order of proof:**
1. Retained executable knowledge is useful (Pilot 1).
2. Aljure can acquire it during ordinary work (Pilot 2).
3. Only then: structural learning (section 10), and Prime's continual learning.

The A/C/E pilot's final result is reported separately in `THESIS_PILOT_RESULTS.md`: uninformative,
0 proposals in 100 offered turns.

## 1. Diagnosis of the failed proposal mechanism

**Observed facts** (A/C/E traces, 162 tasks):
- The proposal turn's text says the answer is "final… nothing in this turn can change it", then
  "Optional, one turn, no penalty". Nothing says later tasks exist or resemble this one
  (`acquisition.clj`, `instruction`).
- `skip_proposal` takes no input. A decline costs one empty tool call and needs no reason.
- All 100 offered turns ended in an immediate `skip_proposal`: about 27 output tokens, 0 thinking
  tokens, no text.
- During the tasks themselves, the model wrote reusable-looking code in 131 of 162 tasks (81%;
  section 2).
- The E tool asks for `(fn [text] label-or-nil)`. The model's own code is a single-label
  true/false regex test, used inline. Proposing it means rewriting it in another shape.

**Hypotheses** (not tested here; they motivate mechanisms B and C, and Pilot 2 tests them):
- **Framing:** an optional, unrewarded turn after a final answer is taken as an exit.
- **No future context:** with no mention of later related tasks, reuse value is not apparent.
- **Interface mismatch:** the required function shape differs from the code the model actually
  wrote.

We make no claim about the model's motivations.

## 2. Inventory of reusable code already generated

These counts come from reading recorded `repl_eval` sources; nothing was run.

| Measure (162 A/C/E tasks) | Count |
| --- | --- |
| Tasks with single-label regex tests | 131 (81%) |
| Tasks with a multi-label classifier | 0 |
| Tasks with hardcoded index sets or record-text lists | 0 |
| Tasks with an eligible capture candidate (`repl-lab.capture`) | 118 (73%) |
| Eligible candidate × question-label pairs | 397 |
| Pairs passing the promotion rule's candidate part (≥ 19/20 precision, ≥ 1/10 coverage) | 67 |
| Tasks with at least one passing candidate (upper bound: best named label) | 51 (31%) |
| Single-label (numeric) tasks with a passing candidate | 18 of 81 |

- **Why the other pairs fail:**
  - precision below 19/20: 153 pairs;
  - precision and coverage both below: 25 pairs;
  - coverage only: 15 pairs;
  - decides nothing: 137 pairs (mostly the wrong label of a two-label question).
- **Which pass:** the model's location and numeric-value regexes, at 96–100% precision. Location
  detectors sit just above the 1/10 coverage line.
- **Feasibility method** (`scripts/capture_feasibility.clj`):
  - Every eligible candidate runs in one fresh isolated worker on the development panel.
  - Each is tried with the label or labels its own question names; the real capture turn asks
    the model.
  - The applicability predicate is a developer stand-in: the header lists that label.

**A1c (Sonnet 5.5) arm 08:** capture finds its `lab` classifier, the rule Step 0 measured, and nothing
else eligible. Its hardcoded index sets (`ent`, `numx`) are correctly excluded.

## 3. Text-only delivery (does it hide correct answers?)

- 59 of 162 tasks first answered in plain text (A 20, C 24, E 15).
- 34 later called `done` with the same answer, and 17 changed it (for example 60 became 58).
- 8 never delivered, all in C or E. Scored offline (never changing a recorded score), the model's
  first text answer would have scored 1.0 in 4 of the 8.

So text-only delivery does obscure some correct answers. The remedy was tested before and
rejected (F2, terminal text answer). It stays out of scope here and is reported as a cost on
every arm equally.

## 4. Seeded validated library (Pilot 1's library)

**Source:** A1c arm 08's recorded `lab` (Sonnet 5.5, model-authored, step 5, source sha256 `a47302f3…`),
the best rule in Step 0. It is kept verbatim inside a controller adapter: keywords become label
names, and its `:ent` default becomes nil. The applicability predicate is developer-written: the
header must declare the six trec_coarse labels. Provenance is recorded per part (function
`:controller-generated` around the model's forms; predicate `:human-edit`).

**Rule v1 rejected it** (`evidence/reuse-pilot-seed/`):
- Panel result: 638 decided, 587 correct, **92.0% < 95%**.
- **Diagnosis:** the description branch is 70% precise (88 of 125 on A1c's own window). It labels
  "What is NASA ?"-type abbreviation questions as descriptions. The other labels are 98–99%.
- These records recur across the instance pool. On records new to the panel, the full rule is
  97.8–100% precise, which is what Step 0 measured. On all records it is 88–95%.

**Operator decisions (2026-10-29):**
1. **Per-label abstention.** A new candidate that fails precision only through some output labels
   is wrapped to abstain on each label whose own panel precision is below 19/20 (adapter
   `label-abstention-v1`; forms verbatim; parent hash recorded). It then runs again in a fresh
   worker.
2. **Rule v2:**
   - Library precision must stay at or above 19/20 (v1 required it never to fall). Under v1 a
     99.2%-precise second entry after a 99.25% first one is rejected, so a library can hardly
     grow.
   - Coverage must not fall, as before.
   - Candidate thresholds, no-correct-record-lost and the structural checks are unchanged.

**Disclosed circularity:** abstention selects labels on the same panel that then validates the
candidate. The independent checks are the fresh-window gold below and the live pilot.

**Attribution correction (2026-10-30):** the A1c run's plan records `claude-sonnet-5-5`, not Opus. The
pinned seed library `3eb127bf…` and its receipt carry the wrong author string ("Opus") in the entry
description and the seed record. The pinned bytes are frozen evidence that Pilot 1 ran on, so they are
left as they are; `scripts/seed_library.py` is corrected for any future seed. Consequence worth noting:
Pilot 1's arm D reused code written by the same model family that ran the task.

**Rule v2 approved it** (`evidence/reuse-pilot-seed-v2/`):
- Pin `3eb127bfdfb3203cc917bf6677329e9795649d3f752a1393171f69cd4580d4a7`.
- Abstained label: description only.
- Panel: 492 of 975 decided (50.5%), 487 correct (99.0%). No model calls.

**Offline reuse results** (`scripts/reuse_offline.py`, `evidence/unblock/reuse-offline.json`; fresh
isolated worker; zero model calls):

| Check | Result |
| --- | --- |
| Faithfulness: reproduces arm 08's recorded Step 0 labels on A1c's window (abstained label excluded) | **exact**: 396 of 396 decisions, none extra |
| Pilot 1's 7 fresh trec windows, all 19,279 records | 46.5% decided, **98.8% precise** |
| The same windows, the 12,578 records that neither A1c's window nor the panel held | 38.6% decided, **98.2% precise** |
| Per window, all records | 32–51% decided, 92.3–100% precise (lowest: the 39-record (2048,4) window, 12/13) |
| Pilot 1's 3 spam windows | refused by the predicate: 0 admitted, 0 decided |

**Fallback:** the library leaves 49–68% of records per window undecided. The model must handle them
(protocol below: the fallback endpoint).

## 5. Acquisition designs compared

| Mechanism | What the model does | Controller work | Size of change | Offline evidence |
| --- | --- | --- | --- | --- |
| A Optional (control) | Optional turn; empty decline | None | None | 0 / 100 proposals |
| B Structured | Told later tasks share the format and many labels; reviews its own code; proposes, or declines with a one-sentence reason | None | Instruction text and one schema field | Untested live |
| C Controller-assisted capture | Chooses one listed candidate; names the label of a true/false test; writes the predicate; or declines with a reason | Reads the session code (never runs it); lists eligible text tests, verbatim with inlined session definitions; adapters recorded | `capture.clj` (about 220 lines) and the turn variant | 73% of tasks have candidates; 31% have one that would pass (upper bound) |

**Guards in C:**
- Session data (`external-context`, `context-lines`, anything that reads them), literal index or
  record sets, unresolved names and non-text helpers are excluded.
- The controller nominates. It never invents functionality, and nothing is promoted without
  validation.
- No turn is offered when nothing is eligible.

## 6. Smallest code changes made

- **`acquisition.clj`:**
  - modes `optional`, `structured` and `capture`, with tools and instructions;
  - decline reasons;
  - capture input assembled from the chosen candidate;
  - rule v2 (`decide` floor; `label-precision`, `abstained-labels`, `abstention-source`);
  - `seed-proposal!` and CLI;
  - `score-version` and CLI;
  - provenance per part.
- **`capture.clj`** (new): the candidate extractor and adapters.
- **`external_task.clj`:**
  - the `supply "applied"` positive control (`library-labels`, the `:artifact-supplied` event);
  - mode and candidates passed into the proposal turn.
- **Bug fixed:** a `#(...)` in model code read as `p1__N#`, which the artifact store refuses, and
  `fn*`. Any such E proposal would have crashed promotion. It never fired, because nothing was
  proposed. The head check still rejects a bare `#(...)` proposal.
- **`benchmark/paired.py`:**
  - `artifacts.supply`;
  - `aljure_only` (Aljure-only plans with no Prime counterpart);
  - acquisition modes;
  - arms ES and EX;
  - rule v2 validation;
  - the reuse-fixture preflight gate;
  - the `reuse-pilot-v1` method.
- **`benchmark/official.py`:** a named-profile importer, and two numeric questions per window
  without changing the thesis suite's hash (`7b23fbbb`, rebuilt and compared).
- **`benchmark/relay_fixture.py`:**
  - `reuse-fixture` (Pilot 1, real gateway and worker);
  - arms ES and EX added to `trajectory-acquisition-fixture`.
- **Lock file:** validation shards 0, 1, 2 and 7 pinned, each matching the Hub's LFS sha256. The
  `reuse-pilot` profile was added.
- **Scripts:** `seed_library.py`, `reuse_offline.py`, `capture_feasibility.clj`,
  `reuse_pilot_compare.py`.

## 7. Data

- `trec_coarse` exists only in the validation split (Parquet footer statistics,
  `evidence/unblock/shard-footers.json`). Shards 3 and 6 were exhausted.
- **Pilot 1 windows** (no suite, Step 0 or the A/C/E pilot used them):
  - trec (2048,3), (2048,4), (4096,8) from shard 2;
  - trec (131072,6), (131072,8), (262144,9), (262144,10) from shard 7;
  - spam (8192,10009), (16384,10012), (32768,10016) from shard 1.
- **Record overlap:** the large windows share 25–40% of their records with A1c's window.
  Endpoints report new-record splits where relevant.
- **Pilot 2** reuses the A/C/E suite (`7b23fbbb`) byte for byte. No unused trec windows remain for
  a second fresh suite. Disclosure: the mechanism designs were informed by traces of these same
  tasks.

## 8. Pilot 1 protocol: does a validated executable library improve quality or cost?

- **Arms** (`config/reuse-pilot-{S,D,P}.json`; Sonnet 5.5, subscription only, Aljure only):
  - **S:** stateless.
  - **D:** the seeded library is preloaded where its predicate admits the task and named in the
    task note; the model decides whether to use it.
  - **P (positive control):** as D, and the controller also binds `library-labels` (one label or
    nil per record).
- **Suite:** `reuse-pilot`, 27 tasks.
  - F1: 21 trec tasks (14 count, 7 comparison/label).
  - F2: 6 spam tasks.
  - Questions are a seeded choice by type and id.
- **Runs:** each plan runs twice, interleaved S, D, P, S, D, P, each to a fresh output directory.
- **Endpoints** (`scripts/reuse_pilot_compare.py`):
  - **Value when used (primary):** P against S on F1.
    - Official mean score.
    - Mean |log((count+1)/(gold+1))| on count tasks; a missing count takes the worst error seen
      for that task.
    - Cost.
  - **Use when available (primary):** D's activation, the share of F1 tasks where the library ran
    and its output entered the answer (`eligible-reuse`).
  - **Negative transfer:** D and P preload nothing on F2; F2 mean score at or above S − 0.05.
  - **Fallback:** undecided records per F1 task (P's `:artifact-supplied` counts); cost and calls
    against S.
  - **Also reported:** calls, p50/p95 latency, incomplete tasks, refusals.
- **Uncertainty:** paired per-task differences (mean of two runs); 95% bootstrap intervals
  resampling the 7 F1 windows (10,000 resamples, seed 0); per-window values reported.
- **Decision rule (fixed now):** the library is **useful when supplied** if P meets at least one
  of these on F1:
  - (a) mean score ≥ S + 0.05, at cost ≤ 1.2 × S;
  - (b) count log-error ≤ 0.75 × S's, at score ≥ S − 0.03;
  - (c) cost ≤ 0.8 × S, at score ≥ S − 0.03.

  **D is used reliably** if its activation is at least 50% of F1 tasks and it gains at least half
  of P's score gain.
- **Falsification:**
  - If P meets none of (a)–(c), this retained, validated, model-generated knowledge gives no
    measurable value on these tasks even when supplied. The reuse premise fails for this family
    at this scale.
  - If P is useful but D is not used reliably, the bottleneck is use or discovery, not value.
- **Stop rules:** as in earlier pilots (isolation refusal, unknown provider outcome, Docker
  restart, unconfirmed cleanup). The run chain also stops before a run if recorded spend exceeds
  $25.
- **Budget** (API-rate-equivalent): $5 per task and $135 per run (hard caps). 162 task runs.
  Expected $5–8 in total.

## 8b. Pilot 1b protocol: the value of reuse where the artifact applies

Preregistered 2026-10-30, before any run. Operator brief: `FRONTIER_AND_ROADMAP.md` §3.

- **Suite:** `reuse-pilot-1b` (profile `oolong-synth:reuse-pilot-1b:validation`): on the 7 Pilot 1
  trec windows, every NUMERIC_ONE_CLASS question whose asked label is one of abbreviation, human
  being, location, numeric value. 28 tasks, fixed by the label list, never by answer. No spam tasks:
  the incompatible-taxonomy control is Pilot 1's 12/12 refusals. Panel: the thesis panel, byte for byte.
- **Disclosure:** these windows were shown to the model in Pilot 1 (6 of the 28 questions were asked
  there). No seed was built or tuned on them. Arms see the same exposure.
- **Arms** (`config/reuse-pilot-1b-{S,D,P,R}.json`): S stateless; D library preloaded, model decides;
  P as D plus controller-applied `library-labels`; **R** as P plus `library-ledger`, the record
  indexes the library marked positive, negative and unresolved for the asked label, with a note
  giving the three counts and asking the model to judge only the unresolved records. Unresolved is
  a third state and is never counted as negative (`external_task.clj ledger-source`).
- **Runs:** two per plan, interleaved S, D, P, R, S, D, P, R. Stop rules as Pilot 1; the chain stops
  before a run if recorded spend exceeds $25.
- **Task classes:** addressable (the library resolves ≥ 50% of the window's records, by P's
  supplied counts) and residual-dependent (< 50%), reported separately.
- **Endpoints** (`scripts/reuse_pilot_compare.py --1b`): official score; count log-error, paired
  per task (mean of two runs) with a 95% bootstrap CI clustered by window; cost per run with all
  controller overhead; calls; p50/p95 latency; delivery failures (text rejections, undelivered);
  preloads and refusals; source-attributed reuse (model-directed calls, value in answer, reads of
  supplied labels) alongside the original `eligible-reuse` heuristic.
- **Failure policy (one, preregistered; `PILOT1_CORRECTED_ANALYSIS.md`):** a count is delivered
  only if the official parser reads an integer; an undelivered count takes the fixed penalty
  `log(gold + 1)` in every mean, paired difference and decision. Delivery counts are reported beside
  every error. Non-delivery cannot improve an arm's number.
- **Arm R is reported in four separate parts:** (1) ledger availability: tasks where
  `library-ledger` was bound, with its three counts; (2) actual use: tasks whose root code read
  `library-ledger` (source-attributed); (3) residual handling: the model's declared count minus the
  ledger's positive count, against the true number of unresolved records that carry the label;
  (4) final-answer accuracy: official score and count log-error. The library's labels are
  empirically validated on the panel (98.8–99.0% precision there and on fresh windows); they are
  not guaranteed correct, and the ledger's "positive" count carries that error.
- **Decision rule (fixed):**
  - **Useful when supplied:** P or R has log-error ≤ 0.75 × S, the paired CI upper bound < 0, and
    cost ≤ 1.5 × S.
  - **Bookkeeping helps:** R's log-error ≤ 0.8 × P's.
  - **Used reliably:** D calls the library in ≥ 50% of tasks (source-attributed).
  - **Falsified at this scale:** neither P nor R is useful on tasks the artifact can address.
- **Budget:** $5 per task, $140 per run (hard caps). 224 task runs. Expected $5–8.

## 9. Pilot 2 protocol: can Aljure acquire that library during ordinary work?

- **Arms** (`config/acquisition-pilot-sonnet.json`, trajectory mode):
  - **A:** stateless.
  - **E:** optional turn, the A/C/E control, now under rule v2.
  - **ES:** structured turn.
  - **EX:** capture turn.
  - **EXS:** capture with controller-selected applicability (mechanism D): the model names the labels
    the function decides; the controller writes the contract (the header must name those labels,
    adapter `label-header-v1`, provenance `:controller-generated`) and validates as usual.
- **Same for every arm:** suite `7b23fbbb`, the panel, seeds 101, 202 and 303, F2 at 8, 11, 14 and
  17, cold restart after task 9.
- **Rule:** v2 with label abstention, for E, ES and EX.
- **Endpoints, per acquisition arm:**
  - **Reliability (primary):** trajectories (of 3) with at least one committed promotion.
  - **Yield:** proposals or captures per offered turn; approved promotions per offered turn.
  - **Quality:** the new-record endpoint (`trajectory-new-records`), pooled F1 coverage and
    precision.
  - **Acquisition cost:** proposal-turn cost per trajectory and per promotion.
  - **Reuse:** `eligible-reuse` activation (original heuristic, kept) and source-attributed
    model-directed invocation with value-in-answer, on F1 tasks after the first promotion.
  - **Count error by decidability:** F1 count log-error split by whether the version in force
    decides the asked label (from the new-record step's whole-window scoring).
  - **Negative transfer:** F2 refusals; F2 mean score against A (at or above A − 0.05).
  - **Descriptive at this scale:** score and cost against A, break-even (thesis criteria 1 and 4).
- **Success (an arm acquires reliably):** all three hold:
  1. at least 2 of 3 trajectories commit a promotion;
  2. pooled new-record precision ≥ 19/20 with coverage ≥ 1/10;
  3. no negative transfer.
- **Falsified at this scale:** no arm succeeds. That means none of the three mechanisms makes
  Aljure acquire validated code during ordinary work.
- **Uninformative:** no arm offers 30 or more turns (with ES and EX, decline reasons explain why).
- **Budget:** 15 trajectories × 18 = 270 task runs; $40 cap, $1 margin, hard ceiling $45.
  Expected $10–14. If the cap stops the chain, the trajectories that completed are reported and
  the rest are listed as not run.

## 10. Structural learning (design only, after Pilots 1 and 2 succeed)

- **Sequence:** about 8 tasks where exact caching cannot work.
  - Tasks 1–3: trec counts over new windows, so a classifier is acquired.
  - Tasks 4–6: the same records with a changed requirement, for example a label merge
    (location ∪ entity → "place or thing"), or a coarser taxonomy.
  - Tasks 7–8: a composition, for example a count restricted to users or dates parsed by a
    second acquired function.
- **The agent must** patch or compose the earlier artifact (`artifact/patch`,
  `artifact/compose`; `:replaces`; dependencies by hash).
- **Record:**
  - the original hash;
  - the exact patch path or composition;
  - independent validation;
  - the decision;
  - the new hash;
  - use on the new requirement.
- **Compare against:** fresh generation (A) and exact caching (C), all acquisition and validation
  costs included.
- **Build only after** Pilot 2 shows reliable acquisition. Most of the machinery already exists
  (`artifact/patch`, `compose`, `replaces`).

## 11. Tests and gates

- **Unit tests:**
  - Clojure: 185+ tests, including `capture_test` (6 tests: extraction, exclusions, adapters,
    modes, rule v2) and `acquisition_test` (13 tests).
  - Python: 204 tests, including `test_unblock` (5 tests) and `test_thesis_trajectory` (16 tests).
- **Real worker (regenerated in the execution checkout, section 12):**
  - SCI isolation; Prime isolation;
  - SCI contract; artifact path; acquisition;
  - subscription relay fixture;
  - acquisition fixture, now with arms ES and EX;
  - reuse fixture: D preloads and invokes the seed; P binds `library-labels` (6 records,
    4 decided; the description record stays nil, as the approved seed abstains on it); spam
    refuses and binds nothing.
- **First-run fixes found by the real-worker fixtures** (before any live run): the worker's
  reader takes no regex literal in controller code, so `supply-source` builds its pattern from a
  string.

## 12. Frozen plans (2026-10-29) — awaiting operator approval

**Not approved. Not run.** Source: commit `6b7feb9` (clean). Execution checkout:
`/Users/mackianni/aljure-unblock-v1`. Provider: `claude-oauth-subscription`, no API fallback, no API
key in the environment. Model: Sonnet 5.5. Evidence: `evidence/unblock-freeze/`.

| Pilot | Plan | `plan_sha256` | Tasks per run |
| --- | --- | --- | --- |
| 1 | S (stateless) | `7f089a8f7b04d1163797227de7ffaafc0ff28de10aa942a65a3fce9b7580580b` | 27 |
| 1 | D (seeded library) | `b89df89bf4f14fc04f5a0610fc52fbc4284a9501fa25df31052b322d76c93495` | 27 |
| 1 | P (positive control) | `46d89446f73e87726d5d244c0178e8c8331d6b70d83f7b38d3886fbab82e750f` | 27 |
| 2 | A, E, ES, EX trajectories | `d16f383e18bb1f4486424ce84ffdc2b57d98c247cece11181592f5a3f84e42af` | 12 × 18 = 216 |

- **Pilot 1 suite:** `806c5b2b7b9b56c693d93de8c272afc5a77dd23e5f0e6b05b44fb6459d3a877c`. It was
  built twice, identically (once in the dev scratchpad, once in the execution checkout).
  - Panel `6c4d6420…`, the panel the seed was validated on.
  - Seed library pin `3eb127bf…`.
  - Two runs per plan, interleaved S, D, P, S, D, P; the chain stops before a run if recorded spend
    exceeds $25.
- **Pilot 2 suite:** `7b23fbbb…`, copied byte for byte from the A/C/E execution checkout and
  verified. Panel `7ae02b6d…`, rule v2 `56ab7426…`; seeds 101, 202 and 303. Each trajectory runs
  twice (tasks 1–9, then 10–18 in a new process); then `trajectory-new-records` and
  `trajectory-report`.
- **Gates, regenerated in the execution checkout with zero model calls:**
  - SCI isolation 9/9 negative cases and 9/9 startup; Prime isolation 10/10;
  - SCI contract 76/76; artifact path 6/6; acquisition 7/7;
  - subscription relay fixture 15/15; acquisition fixture 13/13; reuse fixture 7/7;
  - preflight ready for all four plans, with no blockers.
- **Expected usage (API-rate-equivalent):**
  - Pilot 1: about $4–8, 162 task runs, about 1.5 hours. Hard caps: $5 per task and $135 per run.
  - Pilot 2: about $7–12, 216 task runs, about 2 hours. Cap $40 with a $1 margin; hard ceiling $45.

## 12b. Frozen plans (2026-10-30) — Pilot 1b and the five-arm acquisition pilot

**Not approved. Not run.** Source: commit `748905c` (clean). Execution checkout:
`/Users/mackianni/aljure-unblock-v2`. Subscription only, no API key, Sonnet 5.5. Evidence:
`evidence/unblock2-freeze/`. The 2026-10-29 plans in §12 (`7f089a8f`, `b89df89b`, `46d89446`,
`d16f383e`) are superseded: the first three were run as Pilot 1; `d16f383e` was never run.

| Pilot | Plan | `plan_sha256` | Tasks |
| --- | --- | --- | --- |
| 1b | S (stateless) | `d9ca5ed0c4b50bb8c269ac21557f79d5200dbf59efa83fff93115a8a32750ed4` | 28 per run |
| 1b | D (model-directed) | `15e5ac15998551f4134ffa4963ab3c26a2a9a50daab9e511f0a66ad3bebcc50b` | 28 |
| 1b | P (controller-supplied labels) | `2c9294a53926d6aaecb333edac2318b16633c43b2faee4048279113c3e7eb614` | 28 |
| 1b | R (P + three-state ledger) | `4bf8c137527eedafed95fc59cf6f5c7ca1ca41234d82f4cb16871a5b22ae4d1f` | 28 |
| 2 | A, E, ES, EX, EXS trajectories | `595897f8617c16d8fedda9acd5d468dc5aca9983e9ec20f343d1fb7f140c0bbd` | 15 × 18 = 270 |

- **1b suite** `7dd5e1d446caee687c66038d9f00dee744b8609a9a319d43d7897722a96ff733` (built twice,
  identically); panel `443ac876…`, item-identical to the seed's validation panel `6c4d6420…` (the byte
  hash differs only by the spam window's descriptive overlap count; checked at item level). Seed pin
  `3eb127bf…`, unchanged. Two runs per plan, S, D, P, R, S, D, P, R.
- **Pilot 2 suite** `7b23fbbb…`, panel `7ae02b6d…`, rule v2 `56ab7426…`, seeds 101, 202, 303.
- **Gates at `748905c`, zero model calls:** SCI isolation 9/9 + 9/9 startup; Prime isolation 10/10;
  SCI contract 76/76; artifact path 6/6; acquisition 7/7; subscription relay 15/15; acquisition
  fixture 14/14 (arms E, C, ES, EX, EXS); reuse fixture 9/9 (arms S, D, P, R); preflight ready for
  all five plans.
- **Expected usage:** Pilot 1b about $5–8 (224 task runs, ~2 h; caps $5/task, $140/run). Pilot 2
  about $10–14 (270 task runs, ~2.5 h; cap $40, ceiling $45).

## 12c. Frozen plans (2026-10-30, revised) — awaiting operator approval

**Not approved. Not run.** Source: commit `2768379` (clean). Execution checkout:
`/Users/mackianni/aljure-unblock-v3`. Subscription only, no API key, Sonnet 5.5. Evidence:
`evidence/unblock3-freeze/`. The §12b plans at `748905c` are superseded, never run: the analysis
script's failure policy was corrected (`PILOT1_CORRECTED_ANALYSIS.md`), promotion stage faults now
stop a trajectory, and capture's scope resolution was fixed. The seed, the task selection, the
S/D/P/R mechanisms and the route are unchanged; the suites hash as before (`7dd5e1d4…`, `7b23fbbb…`).

| Pilot | Plan | `plan_sha256` | Tasks |
| --- | --- | --- | --- |
| 1b | S | `f9d9da701169bb838045bcb6791cc0c6311e4edb61e86f199723a6291c21e0f5` | 28 per run |
| 1b | D | `17d92639282ba27cc81663c18ace77184302d9e66f9a5531ab31b39c42fdde2f` | 28 |
| 1b | P | `11f014b408ce77c4f68a27e602b965d14adf7464faa560adaa3f277298a130c9` | 28 |
| 1b | R | `8ffd205913608b0e5b491d9b5aedeee0730fd707fe3166d387e356e24105e537` | 28 |
| 2 (not authorized) | A, E, ES, EX, EXS | `65e03df6eab4134159e774b9b757fdec30e2065a39921367b97dd776ad56fec4` | 270 |

Gates at `2768379`, zero model calls: SCI isolation 9/9 + 9/9; Prime 10/10; SCI contract 76/76;
artifact path 6/6; acquisition 7/7; subscription relay 15/15; acquisition fixture 14/14; reuse
fixture 9/9; preflight ready for all five plans.
