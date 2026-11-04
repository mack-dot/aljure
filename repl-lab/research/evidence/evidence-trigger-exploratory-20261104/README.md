# Exploratory replay of the first detector draft (frozen 2026-11-04)

EXPLORATORY. Produced while designing the evidence detector, on recorded arms of pilot 1
(`h2h-20261104`), Phase B (`h2h-phase-b-20261104`) and the verification ablation
(`verification-dev-20261104`): 322 completed arms over 66 contexts. These contexts are the
detector-development set; trigger v1 (`research/EVIDENCE_TRIGGER_V1.md`) is evaluated elsewhere.

`first-draft-replay.json`: one row per arm with the first draft's task class, state and facts
(the draft triggered on every label task without an item-level record) and the recorded score.

First draft, label-judgement tasks, triggers on right / wrong answers:

| Run and arm | Label tasks | Triggered | of which wrong | of which right | Wrong in total |
| --- | --- | --- | --- | --- | --- |
| ablation A0 | 21 | 21 | 8 | 13 | 8 |
| ablation A1 | 21 | 18 | 3 | 15 | 4 |
| ablation P0 | 20 | 19 | 4 | 15 | 4 |
| Phase B Aljure | 28 | 28 | 13 | 15 | 13 |
| Phase B Prime | 27 | 25 | 9 | 16 | 10 |
| pilot 1 Aljure | 24 | 24 | 8 | 16 | 8 |
| pilot 1 Prime | 25 | 24 | 7 | 17 | 7 |

Two further looks on the 44 baseline Aljure label-comparison arms (same data):

- Count margin, 11 arms with a clean two-way count: margin < 0.30 fired on 4, catching 2 of 3
  wrong and 2 of 8 right. Median margin 0.43 for right answers, 0.25 for wrong.
- Share of the context displayed, 33 arms with no count: under 10% fired on 11, catching 4 of
  8 wrong and 7 of 25 right.

Reading: recall is easy and precision is not; correct answers are usually reached without an
item-level record. Nothing here is a result about the v1 rule.
