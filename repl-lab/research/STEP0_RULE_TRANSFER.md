# Step 0: do Aljure's own generated rules transfer to unseen data?

**Status:** offline and complete, with zero model calls. This is the first step of
the decisive thesis test in `RESEARCH_THESIS_REVIEW.md`.

**Sources:**
- Script: `scripts/step0_rule_transfer.py`.
- Evidence: `evidence/step0/` (report, spec, run window).
- The refused first attempt is kept in `attempt1-*`.

**Question:** the rules and parsers that A1c's Aljure arms wrote for one
`trec_coarse` window (Sonnet, run `sci-ablation-speed-64k`, commit `41b53fa`) were
never seen again. Can they decide unseen items accurately?

## Method

**Replay.** Each of the 8 instrumented A1c arms' own recorded code is replayed in
the isolated SCI worker. Only the final `done` expression is replaced, by that arm's
diagnostic from `scripts/residual_reasoning_analysis.py`, so the arm returns one
label per item.

**Context swap.** The replay runs against another window's public text, using a new
optional `context` field in the replay spec (`src/repl_lab/replay.clj`).
- **Default path unchanged:** without the field, the replay uses the arm's own
  recorded input.
- **Control:** the same override on A1c's own window must reproduce the recorded labels.

**Windows.** Three unexposed validation-split `trec_coarse` windows from pinned
shard 6: 32K window 1, and 64K windows 3 and 4.
- No prepared suite has used them; the script asserts this.
- The sealed held-out suite is test-split and holds no `trec_coarse` window.

**Scoring.**
- Item gold comes from the label-augmented column, offline only.
- Windows share an instance pool, so results are reported on all items and on items
  whose text never appeared in A1c's window ("new only").
- **Counted as undecided:** `unk`, meaning no rule fired, and the `ent*` default
  that arms 03 and 08 use when nothing matched.

## Results

- **Override control:** 8 of 8 arms reproduce their recorded labels byte for byte.
- **Applicability:** 8 of 8 arms ran on all 3 windows, with no applicability failures.

| New-only items | 32K w1 (563) | 64K w3 (1,107) | 64K w4 (1,248) |
| --- | --- | --- | --- |
| Arm 08: coverage / precision | 0.49 / 0.982 | 0.60 / 0.997 | 0.48 / 0.985 |
| Arm 03 | 0.60 / 0.878 | 0.69 / 0.911 | 0.58 / 0.881 |
| Arm 00 | 0.28 / 0.891 | 0.29 / 0.934 | 0.21 / 0.932 |
| Arm 12 (weakest) | 0.40 / 0.744 | 0.36 / 0.821 | 0.39 / 0.789 |
| Majority vote of 8 | 0.68 / 0.819 | 0.78 / 0.880 | 0.68 / 0.828 |
| Items where arms conflict | 69 | 137 | 101 |

## Per class (new only)

- **Location, human, numeric:** high precision. Arm 08 has at most 4 false
  positives per class per window.
- **Description:** precise in arm 08 (0–2 false positives). The vote over-predicts
  it (56–129 false positives) because weaker arms label broadly.
- **Entity:** never decided by any rule, so 0% recall. Only the `ent*` default
  covers it, and that default is correct 17–50% of the time. Entity is the
  residue that needs judgement.
- **Abbreviation:** every abbreviation item in these windows also appears in A1c's
  window, so there are no new-only abbreviation items.

## Verdict against the preregistered falsification

The memo's rule: *if retained rules cannot decide a useful share of unseen items at
high precision, the accuracy route is falsified for this family.*

- A single retained, model-generated rule set (arm 08) decides **48–60% of
  never-seen items at 98.2–99.7% precision** on three windows.
- **The accuracy route is not falsified.** Retained executable rules carry real,
  transferable knowledge.
- **The limits are just as clear:**
  - entity is never decided;
  - an unweighted vote of all arms is worse than the best single arm;
  - so **selection and validation of which artifact to keep** matters as much as
    retention.

## Disclosure

- **Concurrent with the live experiment:** the dev checkout's isolation test and
  Step 0 ran from 19:08 to 19:13 UTC, concurrently with the approved answer-format
  experiment.
- **Arms affected:** the last arms of `counts-v0 r1` (ended 19:12:28) and the first
  arm of `counts-v1 r2`. Their latency is flagged in that analysis.
- **First attempt refused:** the dev checkout's isolation proof predated the
  `docker info` retry change, so the replay refused to start any worker and no code
  ran. It ran after `make isolation-test` passed (TESTED 9/9).
