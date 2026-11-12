# Answer-format verification A/B: results

**LIVE MODEL RUNS, development evidence.**
- **Approval:** the operator approved four frozen plans (`ANSWER_FORMAT_VERIFICATION_PROTOCOL.md`).
- **Source:** commit `8a93ecf`, checkout `aljure-verify-v1`.
- **Configuration:** Opus 5.5, subscription only, Aljure only, with the Prime reference cited by hash.
- **Order:** as preregistered, all 8 runs, exit 0, with no infrastructure stop.
- **Evidence:** `evidence/verify-v1/comparison.json`, from `scripts/verify_v1_compare.py`.

## Decision: NOT ADOPTED (not activated)

| Rule | Result |
| --- | --- |
| 1. Contract intact | **Pass:** 0 auditor violations in 108 Aljure arms |
| 2. V1 official-parse failures = 0 | Pass, but vacuous (see rule 3) |
| 3. At least one notice fired | **Fail:** 0 notices in 54 V1 arms. No V1 answer broke the format |
| 4a. Count MAE no worse than V0 + 2.0 | Pass: V1 8.4 against V0 10.2 |
| 4b. 21-task score no worse than V0 − 0.05 | Fail: 0.80 against 0.86 |
| 5a. Cost ≤ 1.05 × V0 | Fail on the 21-task suite: $2.20 against $1.62 |
| 5b. Cost ≤ 0.6 × cited Prime | Count suite 0.51 (pass); 21-task suite 0.62 (fail) |

**Why every V1–V0 difference is noise:**
- The format notice never fired, so no V1 arm behaved differently because of it.
- V0 had 2 official-parse failures in 33 count answers (6%, both in run 1). V1 had none, by chance.
- The 21-task score and cost differences have known causes unrelated to the switch:
  - a text-only delivery failure (below);
  - V1's longer calls on a few tasks (128 calls against 93).

## Totals (Aljure, pooled)

| | counts V0 (3 runs) | counts V1 (3 runs) | synth21 V0 | synth21 V1 | Cited Prime (mean per run) |
| --- | --- | --- | --- | --- | --- |
| Completed | 33/33 | 32/33 | 21/21 | 20/21 | — |
| Official-parse failures | 2 | 0 | 0 | 0 | 0 |
| Count MAE / signed error | 10.2 / −2.2 | 8.4 / −3.7 | — | — | 8.5 (counts) |
| Mean official score | 0.419 | 0.396 | 0.865 | 0.802 | 0.381 / 0.890 |
| Cost | $8.14 | $8.13 | $1.62 | $2.20 | $5.35 per counts run, $3.56 per 21-task run |
| p50 / p95 latency | 65 / 207 s | 64 / 192 s | 22 / 39 s | 22 / 125 s | — |

## The two failed V1 arms (neither caused by the switch)

1. **counts-v1 r2, arm 01: a harness bug.**
   - The model's `frequencies` result had a `nil` key.
   - Event export threw *after* the root session completed with `Answer: 421`
     (gold 422), and the outer handler discarded the delivered answer.
   - The bug is present in every Aljure version. It is fixed on `claude/thesis-v1`
     (`bd083b9`, with a regression test); the frozen code here is unchanged.
2. **synth21-v1 r1, arm 02: a text-only delivery failure under the base contract.**
   - The model answered in text twice, and the single original correction did not
     recover it.
   - This is the failure F2 targeted. F2 was rejected; F2b (accept a final marker
     line) remains untested.

## Disclosures

**Concurrent offline Docker work** ran while this experiment was live:
- the dev isolation test and Step 0 (19:08–19:13 UTC);
- the thesis gates and full suites (19:25–19:30 UTC).

**Affected runs:** the end of counts-v0 r1, counts-v1 r2, and the start of
counts-v0 r2. Their p95 latencies (207–442 s) may be inflated and are not
compared. This does not affect the decision, which does not rest on latency.

The Prime comparison is non-contemporaneous, as disclosed in the protocol.

## What this shows

- **The mechanism is safe:** 0 violations, never misfired.
- **It is not needed at the observed rate in this experiment:** 0 verbose answers in
  54 V1 arms, against 2 in 33 V0 count arms.
- **Keep it in the code, off by default,** as a guard. It was not shown to help.
- **Two real delivery risks remain:**
  - the event-export bug, now fixed;
  - text-only final answers, still open.

  Both are reliability work, not semantic gains.
