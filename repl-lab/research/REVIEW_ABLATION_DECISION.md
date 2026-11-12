# Review ablation: decision

Evidence: `REVIEW_ABLATION_RESULTS.md`, `REVIEW_ACTIVATION_ANALYSIS.md`,
`COUNT_ACCURACY_DECOMPOSITION.md`, `STRUCTURED_STATE_EVALUATION.md` and
`UNCERTAINTY_REVIEW_ECONOMICS.md`. The preregistered criteria were applied as
written.

## Per mechanism

| Mechanism | Activation | Effect | Decision |
| --- | --- | --- | --- |
| **L1: structured-labels prompt and `show-items`** | 6/11, against 4/11 natively; `show-items` 0/11 | −2.6 error, interval [−11.7, +3.8], within run-to-run noise; +9% cost | **INVESTIGATE.** Drop the prompt text; keep the insight that evidence already sits in SCI |
| **L2: optional uncertainty audit (`:unknown`, `audit-labels`)** | **0/11** | Not attributable | **REJECT** as a model-optional interface: "not used by the model" |
| **L3: review instruction and gate on an open audit** | 1 arm run, no audit; the plan stopped by the isolation gate | Not evaluated | **NO-GO in this form.** It depends on audits the model does not run. Do not re-run as frozen |
| **Done-triggered answer-format validation** (generic) | — | Would recover 3/33 lost official scores | **GO to build and test** (deterministic, about $0) |
| **Controller-owned verification** (evidence read at `done`, invariants, blinded sampled review) | — | Unmeasured | **GO to a frozen experiment** (`CONTROLLER_VERIFICATION_DESIGN.md`) |

The L3 preregistered rule (beats L2 on at least 7 of 11 tasks, lower error, cost
ratio at most 0.6) could not be applied: L3 did not run.

## The ten questions

1. **Does structured state improve accuracy independently of review?** Not
   shown. The model already keeps per-item state natively.
2. **Does identifying unknowns and conflicts change model behaviour?** It was
   never identified. The model did not use the interface (0/11).
3. **Does targeted review improve classification accuracy?** Not measured. L3
   stopped and was structurally inert.
4. **Does L3 reduce signed bias and absolute error?** Not measured.
5. **Official scores?** Aljure's mean scores were 0.36, 0.27 and 0.42, driven by
   the format failures and noise, not by the mechanisms.
6. **Extra calls for review?** About +1 targeted turn, or +2–3 for a blinded
   child, where it fires. That is an estimate.
7. **Extra cost and latency?** L1 +9% cost, L2 +12%. Review would add about
   $0.02–0.10 and 5–30 s per triggered task. That is an estimate.
8. **Does any improvement generalize across the five contexts?**
   - imdb and negation are at or near 0 for both harnesses.
   - Movement sits in formality, MultiNLI and app_reviews, and matches Prime's
     own swings.
   - No consistent improvement is established.
9. **Cost advantage kept?** Yes: Aljure ran at 0.42–0.47 of a complete Prime run.
10. **What advances?** Not L1–L3 as frozen. Next:
    - (a) the deterministic answer-format check at `done`;
    - (b) a frozen experiment on controller-owned verification: optional audit,
      against done-triggered verification, against adaptive blinded review, at
      matched budgets, with activation as a first-class endpoint.

## Limits

- One run per configuration, over 5 window clusters.
- Prime's own run-to-run error swing (5.3) is as large as any level difference.
- L3 was not evaluated.
- Dev data only: no generalization is claimed.
