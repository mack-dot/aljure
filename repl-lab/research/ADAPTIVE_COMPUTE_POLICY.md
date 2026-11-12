# Adaptive compute policy

**Goal:** spend extra model calls only where a deterministic signal says the
current answer is unsupported. The aim is not to make Aljure think longer.

**Evidence:**
- `evidence/opus-capability-gap/interaction-metrics.json`: 84 arm-tasks, with
  algorithm class, answer basis, coverage, verification, remaining budget and finalization.
- `evidence/multinli-count/analysis.json`.

Both are read-only and made no model calls.

## The policy loop, mapped to mechanisms

| Step | Mechanism | Deterministic? |
| --- | --- | --- |
| 1. Build a candidate | The model's SCI program and judgements, as now | — |
| 2. Run checks | `audit-labels`: coverage, conflicts, unknowns, count ranges. `show-items`: items shown whole | yes |
| 3. Find unresolved or suspicious items | `:missing`, `:unresolved`, `:conflicts`, `:never-shown-count` | yes |
| 4. Estimate the value of more reasoning | Whether the open items can still change the answer. For an exact count, any open item can. For a comparison, only overlapping `:count-range`s can | the ranges are deterministic; whether the task needs an exact count is the model's call |
| 5. Spend targeted review | Reread only the open items (`uncertainty_review`); the evidence gate shows the open audit once (`evidence_gate`) | the trigger is; the review is model judgement |
| 6. Recompute and revalidate | `audit-labels` again | yes |
| 7. Stop | No open items, or the model confirms after the one gate, or the budget is spent | yes |

## Four policies

| Policy | `aljure_contract` | What spends extra compute |
| --- | --- | --- |
| A. Current Aljure | none | the model alone; `done` is always accepted |
| B. Verification only | `verification_helpers` | nothing extra is forced; the model may audit |
| C. + targeted review | `verification_helpers`, `uncertainty_review` | the model rereads its own open items before `done` |
| D. + adaptive continuation | `verification_helpers`, `evidence_gate` | at most one gated turn, only when the model's last audit is open |

None of them adds subagents, and none forces a call on a task whose audit is
complete, or that never audits.

## What the recorded runs say (Opus Aljure, 21 tasks)

| Tasks | What the trace shows | Score | B would report | C/D would spend |
| --- | --- | --- | --- | --- |
| 16, 19, 20, 21 (exact counts over judged labels) | All items shown; answer stated, with no per-item record; on 16, about 20 uncertain items named, 11 dropped as not-C | 0.08, 0.75, 0.18, 0.18 | no ledger, so nothing to audit; with a ledger, open items and a count range | **a review of the open items (likely useful)**: 1 call each |
| 2, 3 (label in a date range) | 52% of in-range items read; answer stated | 1, 1 | missing items, if the full range is audited | a gate would fire although the answer was right; +1 call each |
| 4, 18 (top user) | 13–20% read, a top-user shortcut | 1, 1 | the same | the same: +1 call each, no gain |
| 6, 7 (delivery failures) | correct answer reached; delivery failed | 0, 0 | — | nothing; F1 and F2 cover these |
| other 11 | full or structural coverage | 1 | nothing open | nothing |

**Reading this table:**
- **The useful trigger is "an exact count with open items".** All four count
  tasks scored below 0.8, so it would have flagged no task that was already right.
- **Partial coverage alone is a poor trigger.** On tasks 2, 3, 4 and 18 the
  margins were wide enough that sampling was enough. Gating them would cost about
  4 calls ($0.08–0.12, +20–40 s) per run, for nothing.
- **The model cannot reach a deterministic signal it never records.** Under Opus,
  Aljure computed 0 of 20 judgement answers in code; Prime computed 6 of 20.
  Policies B to D act only if the model keeps a ledger. Whether it does is the
  first thing ablation 3 measures.
- **More calls did not buy accuracy across harnesses.** On the 18 tasks all four
  arms completed:
  - Prime used 30% more calls and gained less from Opus than Aljure did:
    +0.084 against +0.113.
  - No arm in either run hit a limit. Every arm except Aljure's two delivery
    failures ended by the model's own choice. The largest were Aljure at 8 calls
    and 48 s, and Prime at 26 calls and 91 s.

## How much extra inference is likely useful

- **Count tasks:** one targeted review of the open items, about 10–20 items. Cost
  +1 call, a few hundred output tokens, about +$0.02–0.04 and +5–15 s each, on 4
  of 21 tasks.
- **Comparison and label tasks with a clear margin:** none.
- **Expected total:**
  - **policy C:** +4–8% calls per run;
  - **policy D:** up to +4 more calls when partial coverage is audited as missing
    (see "Not yet built" below).

## Not yet built

- **A margin-aware gate:**
  - The current gate fires on any open audit. A refinement would add to the
    audit whether the order of the labels is already fixed, meaning no two count
    ranges overlap.
  - The gate notice would then say that only exact counts can still change. That
    lets the model stop at once on comparison tasks.
  - It is deterministic and general, but it is left until ablation 5 shows the
    gate fires on comparison tasks at all.
- **Any controller-side judgement** of whether a task needs an exact count. That
  would be task-text parsing, and it is excluded.
