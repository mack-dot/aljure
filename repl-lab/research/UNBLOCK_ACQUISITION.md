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

**A1c (Opus) arm 08:** capture finds its `lab` classifier, the rule Step 0 measured, and nothing
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

**Source:** A1c arm 08's recorded `lab` (Opus, model-authored, step 5, source sha256 `a47302f3…`),
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

## 9. Pilot 2 protocol: can Aljure acquire that library during ordinary work?

- **Arms** (`config/acquisition-pilot-sonnet.json`, trajectory mode):
  - **A:** stateless.
  - **E:** optional turn, the A/C/E control, now under rule v2.
  - **ES:** structured turn.
  - **EX:** capture turn.
- **Same for every arm:** suite `7b23fbbb`, the panel, seeds 101, 202 and 303, F2 at 8, 11, 14 and
  17, cold restart after task 9.
- **Rule:** v2 with label abstention, for E, ES and EX.
- **Endpoints, per acquisition arm:**
  - **Reliability (primary):** trajectories (of 3) with at least one committed promotion.
  - **Yield:** proposals or captures per offered turn; approved promotions per offered turn.
  - **Quality:** the new-record endpoint (`trajectory-new-records`), pooled F1 coverage and
    precision.
  - **Acquisition cost:** proposal-turn cost per trajectory and per promotion.
  - **Reuse:** `eligible-reuse` activation on F1 tasks after the first promotion.
  - **Negative transfer:** F2 refusals; F2 mean score against A (at or above A − 0.05).
  - **Descriptive at this scale:** score and cost against A, break-even (thesis criteria 1 and 4).
- **Success (an arm acquires reliably):** all three hold:
  1. at least 2 of 3 trajectories commit a promotion;
  2. pooled new-record precision ≥ 19/20 with coverage ≥ 1/10;
  3. no negative transfer.
- **Falsified at this scale:** no arm succeeds. That means none of the three mechanisms makes
  Aljure acquire validated code during ordinary work.
- **Uninformative:** no arm offers 30 or more turns (with ES and EX, decline reasons explain why).
- **Budget:** 12 trajectories × 18 = 216 task runs; $40 cap, $1 margin, hard ceiling $45.
  Expected $8–12.

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

## 12. Frozen plans

Filled in at freeze; see the operator report.
