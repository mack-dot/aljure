# Uncertainty-aware semantic review: development evaluation protocol

**Status:**
- Preregistered before any review run.
- No inference has used a review switch.
- This version replaces the two-configuration design in
  `REVIEW_ABLATION_PROTOCOL_SUPERSEDED.md` (plans `5743ef29…` and `a02824eb…`).
  Those plans will not be run.

**Question:** which part of the review mechanism, if any, reduces Aljure's
judged-count error, and at what cost? The parts are:
1. recording labels;
2. auditing uncertainty;
3. targeted review.

The aim is to keep Aljure's cost advantage over Prime.

## Background

**Count errors so far.** Across four Opus runs of the 21-task dev suite, on its
four judged-count tasks:
- Aljure's mean absolute count error was 4.4;
- Prime's was 2.9 (15 answered cases each; `CONTRACT_ABLATION_RESULTS.md`).

**Why the review targets this.** On MultiNLI, Aljure named its uncertain pairs
and then dropped them (`MULTINLI_COUNT_FAILURE_ANALYSIS.md`).

## Configurations

Finalization is the same in all four configurations: the base contract is F1,
`truncated_turn_retries: 1`, with the original text-only correction. Each review
level adds to the one before it.

| Config | `aljure_contract` additions | What the model is told | Question answered |
| --- | --- | --- | --- |
| **L0, baseline** | none | — | reference |
| **L1, structured labels** | `structured_labels` | Record one label per item in SCI and compute the answer from them. `show-items` pages whole items | Is externalizing judgements enough? |
| **L2, + uncertainty audit** | `+ uncertainty_audit` | Label unsure items `:unknown`; `audit-labels` reports missing, conflicting and unknown items, and each count's range | Does identifying unresolved work help? |
| **L3, + targeted review** | `+ targeted_review` | Before `done`, reread and decide every open item, then audit again. At most once, a `done` with an open audit is answered with that audit | Does more targeted reasoning improve accuracy enough to justify its cost? |

**Prompt sizes:** 58, 64 and 13 words, in `resources/structured-labels.txt`,
`uncertainty-audit.txt` and `targeted-review.txt`. Each level's text is appended
only with its switch, and L0 is byte-identical to the original.

**Not used:** gold labels, benchmark-specific classification rules, subagents,
skill caching, the sealed held-out suite, and any controller judgement of label
correctness.

## Task selection

**Suite:** `dc16404457b369c56579c32e0744ea75b94eef220a0aeaee0c0591826891474a`,
built by `prepare-official --label-counts`.

**Pinned profile:** `oolong-synth:dev-label-counts:32768`.

**Rule:** every whole-window label-count question ("In the above data, how many
data points should be classified as label 'X'?") of the dev windows.
- Selection uses the question text alone; answers play no part.
- Questions are read only from parquet row groups that hold no row of a held-out window.
- That rule is checked on metadata columns before any text is decoded. Mixed row
  groups are never read past their metadata.

| Window | Items in context | Questions (labels) |
| --- | --- | --- |
| negation 40016 | 683 | True, False |
| formality 60016 | 602 | formal, informal |
| imdb 20016 | 81 | negative, positive |
| app_reviews 90016 | 627 | negative, positive |
| multinli 70016 | 438 | entailment, neutral, contradiction |

**Notes on the selection:**
- **11 tasks; 10 are new questions** on contexts already used in development.
  Only MultiNLI contradiction was in the earlier dev suite.
- **The AG News and Yahoo dev windows are absent**, because their label-count
  questions sit only in row groups shared with held-out windows.
- **Questions in one window are not independent.** The two binary counts of a
  window are complementary, and all three MultiNLI counts share one labelling.

## Endpoints

**Primary: count accuracy per configuration over the 11 tasks:**
- mean absolute count error (MAE);
- mean absolute relative error (|error| / gold);
- signed error.

Unanswered tasks are reported separately, never imputed.

**Secondary:**
- score;
- completion;
- Aljure/Prime cost;
- model calls;
- p50 and p95 latency.

**Prime reference:** Prime runs in every plan, unchanged, giving four Prime runs
on the same 11 tasks. Its MAE across those runs is the comparison bar. Its spread
is a lower bound on run-to-run noise, not a measure of Aljure's.

**Mechanism invocation, per Aljure arm, from traces:**
- **L1:** whether a per-item label map was built in SCI. This is a heuristic on
  the executed code, and the rule is reported.
- **L2/L3:** `audit-labels` calls, unknowns at the first audit, and open items
  when `done` was accepted.
- **L3:** open items reduced by review, and gate firings.

A change on a task is attributed to a level only if that level's mechanism was
invoked on that task.

## Decision rules (fixed before the runs)

**Comparisons, paired by task (11 tasks, 5 window clusters):**
- L1 against L0: externalization;
- L2 against L1: the audit;
- L3 against L2: review.

**Rules:**
- **Invocation is required.** A level whose mechanism is invoked on fewer than 6
  of 11 tasks is reported as "not used by the model", not as "no effect".
- **Targeted review earns its place** only if all of these hold:
  - L3's absolute error is below L2's on at least 7 of 11 tasks;
  - L3's MAE is below L2's overall;
  - L3's Aljure/Prime cost on this suite stays at or below 0.6.
- **An "impressive" result:** L3's MAE below Prime's MAE on the same suite, at a
  cost ratio of 0.6 or less, with the improvement absent in L2.
- **Not established:** one run per configuration over 5 clusters cannot establish
  an effect size. A configuration that passes goes next to a new-dataset test and
  then the sealed held-out suite, each with its own approval.

## Integrity checks before execution

- **Contract audit:** every Aljure arm is audited by `scripts/contract_audit.py`.
  The gate is legal only under `targeted_review`.
- **Isolation stop rule:** a failed worker isolation preflight stops a plan
  (`IsolationPreflightFailed`), as do an unknown provider outcome and a Docker restart.
- **Accounting:** every call is reserved and receipted. Per-arm caps are $100,
  1,000 calls and 900 s, as in the earlier Opus plans.
- **Gates regenerated in the execution checkout:**
  - SCI isolation;
  - Prime isolation;
  - SCI contract, including the helper probes;
  - the subscription relay fixture;
  - the review fixture, through the real gateway and SCI with a no-review control;
  - preflight for each plan.

## Frozen plans (2026-10-29): SUPERSEDED, never executed

The operator approved the design but required a single bounded `docker info` readiness retry before execution
(commit `40270ba`). These four hashes are kept for the record and will not be run. Their evidence is in
`evidence/review-levels-opus-superseded-docker-retry/` and `var/review-levels-opus-superseded-docker-retry/`.

**Source:** clean commit `f59c0fb`, execution checkout `/Users/mackianni/aljure-review-v1`.
That checkout moved from `60fa124`, where the superseded plans were frozen and
never run. Their files are kept in `var/review-ablation-opus-superseded`.

**Suite:** `dc164044…`, 11 tasks, 22 arms per plan.

| Config | plan_sha256 |
| --- | --- |
| L0, baseline | `279bb4f116b1e452fc2c123b71b7cd8f4fe2ed38cecfa47731aee7b9d683cd39` |
| L1, structured labels | `dd794ddc110ebb0fa72b4f20a2d8e8ccef89b92c1f30a7cb00df2d7ee4ffe0c4` |
| L2, + uncertainty audit | `fd5c352c3614413e72aea33b123bf0b7b1f1e6b5fee69840d0294ef1aa7f4b4c` |
| L3, + targeted review | `2723ae802f87004bc6b9ac0e0af4419fd5b49fe2ef5092dc4b07d7b262dcdaa2` |

**Run order:** L0, L1, L2, L3, once each. The base contract is F1 throughout.

**Gates:**
- SCI isolation 9/9, Prime isolation 10/10 and SCI contract 76/76. These were
  generated in this checkout; their inputs are unchanged since.
- Subscription relay fixture 15/15, rerun at `f59c0fb`.
- Review fixture 9/9 at `f59c0fb`.
  - The first attempt failed before its control arm started: `docker info` timed
    out at the 5 s isolation preflight, the same stall as F2's MultiNLI arm.
  - Its report is kept as `review-fixture-docker-timeout-report.json`.
- Preflight ready for all four plans, with no blockers.

**Spend:**
- **Expected:**
  - Aljure about $0.25–0.40 per count arm, rising with the level; Prime about
    $0.3–0.6 per count arm.
  - About $7–10 per plan, about **$30–40** in total at API-rate equivalent.
- **Time:** about 35–55 min per plan.
- **Hard caps:** $100 per arm and $2,200 per plan; $8,800 nominal in total.

**Known operational risk:**
- `docker info` normally answers in about 0.15 s. It stalled past 5 s twice in
  roughly 200 worker starts today.
- Under the stop rule, such a stall stops a plan, failing closed with no model call.
- At that rate, about 1 plan in 10 could stop early and would need a rerun.

**Evidence:** `evidence/review-levels-opus-superseded-docker-retry/`.

## Frozen plans for execution (2026-10-29)

**Source:** clean commit `40270ba`, which adds the bounded `docker info`
readiness retry. Execution checkout: `/Users/mackianni/aljure-review-v1`.

| Config | plan_sha256 |
| --- | --- |
| L0, baseline | `def381f5c51141b9111bfffc7a78c7f6e5f3e8a54f2554be38323c583accccfb` |
| L1, structured labels | `240ce69422ec865b0465a00fc0cc6fa3da9a474971c037a9387ff5a64dcb4b5a` |
| L2, + uncertainty audit | `51687387bed1deea88c0c3ba2a7f44c76c03390ef9727bc3bc72febcadb02dc6` |
| L3, + targeted review | `20f256246300dd2a7f7549fa3b0d31fc4c9a4857e4567c2753e9e579d76f956a` |

**Isolation between plans:** they differ only in `aljure_contract`, the capability
declaration derived from it, and labels (`ablation`, `campaign_version`,
`authorization_scope`). These are identical in all four:
- source and runtime snapshots;
- the suite `dc164044…`;
- the Prime pin and images;
- limits, rates and the arm sequence.

**Gates, all regenerated at `40270ba` with zero model calls:**
- SCI isolation TESTED: 9/9 negative cases, 9/9 startup, both boundary checks,
  and the supervisor hash matching the retry code;
- Prime isolation 10/10;
- SCI contract 76/76, including 7 verification probes;
- subscription relay fixture 15/15, OAuth protocol verified;
- review fixture 9/9;
- preflight ready for all four plans, with no blockers.

None of the 11 worker preflights during regeneration needed the retry.

**Run order:** L0, L1, L2, L3, once each. Any isolation-preflight refusal, unknown
provider outcome or Docker restart stops the plan before the next arm.
