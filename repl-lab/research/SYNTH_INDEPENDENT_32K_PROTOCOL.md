# OOLONG-synth independent contexts, 32K (dev): protocol

**Status: frozen plan awaiting operator approval. No model call has been made
for this protocol.**

## Question and target

Does the current Aljure keep accuracy comparable to native Prime, while costing
less or running faster, across several independent contexts? A1c answered this
on one context only (`independent_contexts: 1`). The target is comparable
accuracy with lower cost or latency, not a higher score.

## Suites (prepared before any result)

Both suites come from the pinned OOLONG-synth test split (revision
`81d2f8d9…`), 32K context, with shards pinned by size and sha256 in
`benchmark/upstream.lock.json` (sha256 equal to the Hugging Face LFS object
IDs). The importer reads only identifying fields, public text, questions and
controller-only answers, never the label-augmented column.

| Suite | Windows (one per dataset) | Tasks | suite_sha256 |
| --- | --- | --- | --- |
| Dev, run under this plan | negation 40016, formality 60016, imdb 20016, app_reviews 90016, yahoo 50016, multinli 70016, agnews 30016 | 21 | `b157ee63…` |
| Held-out, **sealed** | the same datasets, windows …17 | 21 | `c74547bd…` |

- **Selection:** `seeded-sample-per-window`. Three questions per window, drawn
  with `random.Random("0:<dataset>:<window>")` from all pinned rows of that
  window, kept in upstream order. The profiles in the lock file fix the
  windows and the sample size; `validate_provenance` rejects any other
  selection.
- **Independence:** different datasets share no instance text. The held-out
  window of each dataset shares 1–7 distinct instances with its dev window,
  except formality (72 of 602).
- **Prior exposure:** window 40016 had one stopped V1 call (2026-10-27) that
  saw a different question (task `415040016`) and ran no tool. The other
  windows were never run. A1 and A1c used an OOLONG-Pairs context, which is
  not in either suite.
- **Held-out rule:** the held-out suite's hash is recorded in this plan's
  configuration (`sealed_heldout`). It is not run, scored or inspected until
  a mechanism is frozen in its own plan, and its answers are never used for
  tuning.

## Arms

| Arm | Configuration |
| --- | --- |
| Aljure | The A1c harness unchanged: assisted, bounded 64 KiB SCI surface; SCI image `58550c92…`. No context card, residual review or label artifacts. |
| Prime | Native Prime unchanged: commit `c4c238ca…`, image `f3e30aaa…`. |

Both arms use the same model and settings (`claude-sonnet-5-5`, adaptive
summarized thinking, effort medium, 32,768 max output tokens), the same 120 s
task deadline and the same caps per arm. Arm order alternates per task, and
the task order is fixed in the plan. One fresh session per arm; no memory or
artifacts carry over.

## Endpoints and analysis (`STATISTICAL_EVALUATION_PROTOCOL.md`)

- **Score:** the official OOLONG-synth scorer, deadline-aware. A timeout,
  error, missing answer or exhausted budget scores 0.
- **Primary (Q-HARNESS):** mean paired score difference, Aljure − Prime, each
  context weighted equally, with a 95% cluster bootstrap over the 7 contexts
  (10,000 resamples, seed 0). δ = 0.05. With 7 contexts, "equivalent" (90%
  interval within ±0.05) is unlikely to be reachable, and an inconclusive
  result is reported as inconclusive.
- **Secondary, descriptive:**
  - total and per-task wall time (p50, p95);
  - model calls;
  - input, cache and output tokens;
  - API-rate-equivalent cost;
  - **score per model call**, and the marginal score of calls after the first
    data inspection;
  - cost per score point;
  - expression and tool errors per call;
  - per-context and per-task differences; wins, ties and losses.
- **Target met** only if both hold:
  - the primary result is not *inferior*, and the point estimate is at least
    −0.05;
  - Aljure's total cost or total wall time is lower than Prime's.

  This is a development result. It is not a held-out claim.

## Spend and caps

| | Value |
| --- | --- |
| Arms | 42 (21 tasks × 2 harnesses) |
| Hard cap per arm | $12 API-rate equivalent, 12 calls, 12M tokens, 120 s |
| Ceiling | $504, the sum of the disjoint arm allowances (the runner requires it) |
| Expected | about $4–5. A1c averaged $0.083 per Aljure arm and $0.095 per Prime arm; these contexts are 71K–116K characters, against 77K for A1c. |

## Gates before the run (no model calls)

SCI isolation proof and SCI contract proof on image `58550c92…`; Prime
isolation proof; scripted relay fixture; plan freeze; preflight with no
blockers.

## Not tested here

The context card, residual review with conflict detection, and label artifacts
are not implemented yet. That work paused when this benchmark took priority.
They will be tested as a 2×2 (card × review) against this plan's Aljure arm as
the no-change control, and confirmed on the sealed held-out suite.
