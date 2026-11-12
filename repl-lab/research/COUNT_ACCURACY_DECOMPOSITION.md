# Count error on the dev label-count suite: decomposition

Sources: `REVIEW_ABLATION_RESULTS.md` (L0–L2) and the earlier four-run dev
evidence (`CONTRACT_ABLATION_RESULTS.md`).

## By component

| Component | Evidence | Size |
| --- | --- | --- |
| **Shared semantic bias** (same model, same boundary disagreement with gold) | Per-task mean signed error, Aljure against Prime: **r = 0.866**. Same direction on every biased window: formality leans formal, app_reviews leans positive, MultiNLI leans neutral | Most of both harnesses' error |
| **Aljure-only excess** | formality "formal": Aljure +40/+10/+15 against Prime 0/+2/+9. app_reviews somewhat larger. negation: one Aljure outlier (+11) and one Prime outlier (+30) | A few items per task |
| **Run-to-run noise** | Prime's identical configuration: mean absolute error 6.0, 8.5, 11.3. Single tasks swing by up to 31 | As large as any level-to-level difference measured |
| **Coverage or arithmetic** | All arms read every item; counts are computed in SCI from the model's own per-item sets | Not a material source |
| **Answer format** | 3/33 Aljure answers had prose after `Answer: N`; the official parse (last colon) failed, scoring 0. Prime 0/31 | 3 tasks' scores; counts unaffected |

## By window (Aljure, mean signed error over L0–L2)

- **imdb** (81 items): 0. Easy for both.
- **negation** (683): about +1, with one outlier. The labels are close to rule-like.
- **formality** (602):
  - formal +21.7;
  - informal −17.3;
  - the largest Aljure-only excess.
- **multinli** (438):
  - entailment −12;
  - neutral +13;
  - contradiction −6;
  - a shared lean toward "neutral".
- **app_reviews** (627):
  - negative −20.7;
  - positive +13;
  - a shared lean toward "positive".

## What can be fixed, and how

| Error | Reachable by | Expected |
| --- | --- | --- |
| Format parse failures | A deterministic answer-format check at `done` (no model judgement) | Recovers all 3; certain |
| Aljure-only excess (formality) | Possibly an independent blinded re-judgement of a sample; unproven | Small |
| Shared bias | Not by same-model review: a reviewer with the same model likely shares it. Needs calibration against independent evidence, a separate question | Unknown |
| Noise | More runs per configuration; nothing in the harness | Measurement only |
