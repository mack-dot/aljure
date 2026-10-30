# Pilot 1 (seeded validated library): results

**Plans:**
- S `7f089a8f…`
- D `b89df89b…`
- P `46d89446…`

All three were approved and run unchanged on 2026-10-29: commit `6b7feb9`, execution checkout
`/Users/mackianni/aljure-unblock-v1`, Sonnet 5.5, Claude subscription only, no API fallback. Each
plan ran twice (S1, D1, P1, S2, D2, P2), giving 162 task runs. Protocol:
`UNBLOCK_ACQUISITION.md` §8. Evidence: `evidence/pilot1-results/`.

**Integrity:**
- Every precondition was verified before dispatch (`dispatch-check.json`): commit, hashes, 27 task
  ids, model route, scorer, caps, library bytes, no API key, preflight.
- All 6 runs completed 27 of 27 rows, with no stop signal and no unknown provider outcome.
- Spend: $3.71 API-rate-equivalent.
- Failures are preserved: 17 task runs recorded no answer (S 7, D 6, P 4 in total, mostly
  text-only delivery).

## Preregistered result

**The library is NOT useful when supplied** by the preregistered rule: none of (a), (b) or (c)
holds for P against S on compatible (F1) tasks.

| Criterion | P against S | Holds? |
| --- | --- | --- |
| (a) score ≥ S + 0.05, at cost ≤ 1.2 × S | +0.061 (95% CI −0.020, +0.162), but cost 1.52 × S | no (on cost) |
| (b) count log-error ≤ 0.75 × S, at score ≥ S − 0.03 | 0.252 against 0.281 (−10%) | no |
| (c) cost ≤ 0.8 × S, at score ≥ S − 0.03 | cost 1.52 × S | no |

- **No negative transfer:** holds. The library was refused on 12 of 12 spam runs in D and P,
  preloaded on none, and spam scores held (S 0.525, D 0.664, P 0.510).
- **D used reliably:** no, by the preregistered heuristic. D's `eligible-reuse` activation is 0%,
  but see the next section.
- **D against S** (F1 score difference): +0.009 (CI −0.104, +0.159). Count log-error difference:
  +0.05 (CI −0.11, +0.18).

## Reuse, measured directly

The preregistered `eligible-reuse` heuristic counts reuse only when an artifact ran inside the
delivered `done` source, or when one of its scalar results equals the trimmed answer text. The
model computes in SCI and then types "Answer: N", so the heuristic recorded **0 everywhere**. This
is a measurement limitation.

Verified reuse, attributed by what each evaluation's own source references (post-hoc,
descriptive; `pilot1-detail.json`):

| F1, 42 task runs per arm | D (model-directed) | P (controller-supplied) |
| --- | --- | --- |
| Library preloaded | 42 / 42 | 42 / 42 |
| Model named and called the seeded function | **28 / 42** (8 delivered the value it returned) | 0 / 42 |
| Model read `library-labels` | — | **38 / 42** (6 delivered a value derived from it) |
| Records the library decided (P, per task) | — | 32–51%, at 98.8% precision overall (offline) |

The two kinds of reuse are distinct. In D the model chose to call the function, often over every
record (thousands of verified calls per task). In P it read the controller's labels and never
called the function.

## Accuracy, cost, latency and residual error

| F1 (2 runs × 21 tasks) | S | D | P |
| --- | --- | --- | --- |
| Mean official score | 0.315 | 0.324 | 0.377 |
| Count tasks: median absolute error | 61 | 32.5 | 39 |
| Count tasks: mean log-error | 0.281 | 0.244 | 0.252 |
| Library's own count error on its decided records | 7.6 | 7.6 | 7.6 |
| Error on records the library left undecided (residual) | 138.9 | 155.6 | 148.2 |
| Comparison and label tasks: mean score | 0.357 | 0.429 | 0.500 |
| Cost per run, F1 | $0.385 | $0.442 (1.15×) | $0.584 (1.52×) |
| Calls (all 54 task runs) | 226 | 252 | 323 |
| Latency p50 / p95 | 21 s / 37 s | 24 s / 36 s | 29 s / 50 s |

For S, which has no library, the residual row is simply its full count error.

**Where the error comes from** (post-hoc, descriptive):
- The library's own counts are accurate. The error comes from the residual, the 49–68% of records
  it leaves undecided.
- **8 of the 14 count tasks ask for "description" or "entity",** which the seed never decides.
  There the library cannot help, and no arm improved (log-error 0.29–0.30 in all three).
- **On the 6 count tasks whose label the library decides,** log-error falls from 0.267 (S) to 0.144
  (D, −46%) and 0.180 (P, −33%). Median absolute error falls 29 → 12 → 22. The official score
  barely moves (0.228, 0.235, 0.292), because it decays steeply with absolute error on large counts.
- **Residual handling differs by arm:**
  - **D** often took the library's count and treated undecided records as "not this label" (for
    example 335 against a gold of 398, after 1,781 undecided records).
  - **P** often over-counted the undecided records with its own heuristics (1,238 and 1,202
    against 965).

These subgroup results are exploratory: 6 tasks, 2 runs, not preregistered.

## Post-run fix (disclosed)

`scripts/reuse_pilot_compare.py` (frozen at `6b7feb9`) read each task's events through a one-pass
generator, so its preloaded, refused and supplied fields came out empty. It was fixed after the
run (commit after `6b7feb9`) and rerun. The preregistered decision and the paired intervals are
identical in both versions. Both outputs are kept (`pilot1-compare-frozen.json`,
`pilot1-compare-fixed.json`).

## What Pilot 1 establishes

1. **A validated, model-generated library transfers and is safe.** It is 98.8% precise on fresh
   windows, it is refused on every incompatible task, and it caused no negative transfer.
2. **Sonnet uses retained executable knowledge without being forced:** it called the library in
   67% of compatible tasks.
3. **Under the preregistered criteria, that knowledge does not yet improve the task outcome or its
   cost.** The limit is not the library's accuracy. It is (i) the labels it cannot decide, and
   (ii) how the model handles the undecided residual. Supplying the labels raised cost by half.
4. **Where the library covers the asked label, count error fell by a third to a half.** This is
   exploratory and needs a preregistered test.

## Pilot 2: assessment before execution (it remains frozen and unrun)

Pilot 2 (`d16f383e…`) still asks a valid question: can Aljure acquire validated code during
ordinary work? Its primary endpoints (promotions per trajectory, the new-record precision of what
is promoted, acquisition cost) do not depend on Pilot 1's result. Pilot 1 nevertheless exposed
concerns that should be fixed **before** it runs. Fixing them changes the source, and so needs a
re-freeze and a new plan hash.

1. **The reuse endpoint is broken in Pilot 2 as well.** Its activation measure is the same
   `eligible-reuse` heuristic, which recorded 0 although the model called the library in 28 of 42
   tasks. **Fix:** source-attributed reuse (the function named in the evaluated code) and
   value-in-answer, preregistered and computed by the report.
2. **Value endpoints repeat Pilot 1's dilution.** Several of Pilot 2's count questions ask for
   labels a captured single-label detector cannot decide. **Fix:** preregister count log-error
   split by whether a promoted function decides the asked label. Keep the official score, but do
   not rely on it alone, because it saturates on large counts.
3. **The order of evidence.** Your stated priority is to prove usefulness first. Pilot 1 did not
   meet its preregistered usefulness criteria. Running Pilot 2 now would test acquisition of
   knowledge whose value is unproven. A small Pilot 1b would test value where the knowledge
   applies: compatible count tasks whose asked label the library decides, with a preregistered
   log-error endpoint. That is about $2–3.
4. **Residual handling dominates the error.** Neither D nor P handled undecided records well. The
   same will hold for acquired detectors. This is a property of the task, not of acquisition.
   Report it as a limit; do not change prompts to fix it without a separate test.
5. **Minor points:**
   - Rule v2's 1/10 coverage minimum blocks rare-label detectors (15 precise candidate-label pairs
     in the offline check).
   - Text-only delivery affects every arm (S 20, D 27, P 18 rejected text replies in Pilot 1).
   - Pilot 2 reuses the A/C/E suite, whose traces informed the mechanism designs.
   - The same one-pass generator bug class was checked in `trajectory_report`, which reads its
     files as lists. It is not affected.

**Recommendation:** do not run Pilot 2 as frozen. First fix items 1–2 (analysis only; mechanisms
unchanged), re-freeze, and decide whether to run Pilot 1b before Pilot 2.
