# Evidence-coverage ablation on fresh development contexts (evidence-coverage-dev-v1)

Frozen before any model call; the plan hash binds this file. **Not authorized by
this file**: the run needs the owner's approval of the exact plan hash through
`var/host-policy-20261103/run_guarded.py coverage --approve <hash>`. Follows the
owner's decisions of 2026-11-04 after `ALJURE_SELECTIVE_VERIFICATION_PLAN.md`:
evidence coverage is the next direction; the existing audit contract is the Aljure
baseline; evidence trigger v1 failed its pre-registered evaluation, that result is
final, and nothing here implements or re-tunes it.

## 1. Hypothesis

Aljure answers label-judgement questions after displaying less of the relevant data
than Prime. On the verification ablation's recorded arms (exploratory; that data is
already used) baseline Aljure displayed 53% of the relevant records and Prime 65%;
Aljure's wrong arms had displayed 38%, its right arms 61%. The falsifiable claim: an
instruction to read every relevant item in full before a content judgement raises
Aljure's score on label-judgement questions above the existing audit contract, at a
cost that stays at or below half of unmodified Prime's. It is falsified if the
coverage arm does not beat the audit arm, or if it does so only at a cost above that
bound. A second question: is any gain specific to Aljure, or does the same
instruction lift Prime equally?

## 2. Arms (six per task; same model, settings, caps and deadline)

| Arm | Harness | Contract | Role |
| --- | --- | --- | --- |
| A0 | Aljure | `terminal_text_answer: text-answer-v2` | reference: the Phase B harness |
| AU | Aljure | A0 + `structured_labels` + `uncertainty_audit` | **baseline**: the existing audit contract, identical to arm A1 of the verification ablation |
| AC | Aljure | A0 + `evidence_coverage` | the coverage instruction, no audit |
| AUC | Aljure | AU + `evidence_coverage` | both |
| P0 | Prime | unchanged | competitive baseline |
| PC | Prime | `prime_contract.coverage_prompt` | mechanism control: the same instruction as a prompt |

`evidence_coverage` appends `resources/evidence-coverage.txt` to Aljure's
instructions. It is text only: no helper is loaded and no controller step exists.
Prime receives `resources/prime-evidence-coverage.txt`, the same sentences with
"in SCI" replaced by "with code" and without the clause that refers to Aljure's own
"read only what you need" instruction (a test holds the two texts to exactly these
differences). The audit contract is unchanged: its text and its two SCI helpers are
loaded as in the earlier run, where the helpers were not called. No arm uses
`targeted_review`.

Identical for every arm: Sonnet 5.5, adaptive summarized thinking, effort medium,
32,768 max tokens, 16 calls, 240 s, the same public context and question, and the
budget of section 5.

## 3. Inputs (development; held-out data untouched)

One suite, `var/official/coverage-dev`, 17 tasks over 14 contexts, built by
`prepare_coverage_dev` from the pinned profile `oolong-synth:dev-coverage:mixed`.
Selection uses the pinned seed and upstream metadata only (`task_group`, `task`,
`answer_type`); no answer and no question text is consulted.

**Fresh contexts.** Nearly every 8K to 32K window of the shards pinned before today
had been used, so eight more public shards of the pinned dataset revision were
pinned and their metadata columns scanned. Twelve windows that no suite in any
worktree holds (checked by context hash against 159 earlier contexts) are the
development windows: 4K agnews, multinli, spam, yahoo, negation; 8K agnews,
metaphors, spam; 16K agnews, spam; 32K metaphors, spam. Twenty-three further unused
windows are pinned as `reserve` and were not read past their metadata columns: one
of each remaining pair at 4K to 32K and every unused 64K and 128K window. They are
the supply for a later held-out test. Phase B's held-out suites are not touched.

**Strata.**

| Stratum | Tasks | Definition | Use |
| --- | --- | --- | --- |
| label-judgement | 12, one per fresh window | the answer needs a label for each relevant item; six cells (whole or filtered scope × COMPARISON, NUMERIC, LABEL), each twice | the primary and every score contrast |
| structural | 3, one at 4K, 8K, 16K/32K, from the same windows | answered from dates or user ids; no label is judged | negative control |
| audit-correct | 2 (8K multinli, 32K agnews) | tasks of the verification ablation whose audit arm scored 1.0 on every trial; a seeded choice among such tasks, one per length; contexts and questions already exposed | negative control |

| Stratum | Dataset | Length | Window | Cell | Answer type | Task |
| --- | --- | --- | --- | --- | --- | --- |
| label-judgement | agnews | 4096 | 30006 | whole / COMPARISON | COMPARISON | `oolong-synth-dev-4096-312030035` |
| label-judgement | metaphors | 8192 | 80010 | filtered / NUMERIC | NUMERIC | `oolong-synth-dev-8192-813080056` |
| label-judgement | spam | 32768 | 10017 | whole / NUMERIC | NUMERIC | `oolong-synth-dev-32768-115010045` |
| label-judgement | agnews | 8192 | 30009 | filtered / COMPARISON | COMPARISON | `oolong-synth-dev-8192-313030033` |
| label-judgement | spam | 8192 | 10010 | whole / LABEL | LABEL | `oolong-synth-dev-8192-113010034` |
| label-judgement | metaphors | 32768 | 80000 | filtered / LABEL | LABEL | `oolong-synth-dev-32768-815080217` |
| label-judgement | yahoo | 4096 | 50006 | whole / COMPARISON | COMPARISON | `oolong-synth-dev-4096-512050047` |
| label-judgement | agnews | 16384 | 30012 | filtered / NUMERIC | NUMERIC | `oolong-synth-dev-16384-314030028` |
| label-judgement | multinli | 4096 | 70006 | whole / NUMERIC | NUMERIC | `oolong-synth-dev-4096-712070037` |
| label-judgement | spam | 16384 | 10013 | filtered / COMPARISON | COMPARISON | `oolong-synth-dev-16384-114010056` |
| label-judgement | negation | 4096 | 40006 | whole / LABEL | LABEL | `oolong-synth-dev-4096-412040006` |
| label-judgement | spam | 4096 | 10006 | filtered / LABEL | LABEL | `oolong-synth-dev-4096-112010038` |
| structural | negation | 4096 | 40006 | - | USER | `oolong-synth-dev-4096-412040035` |
| structural | metaphors | 8192 | 80010 | - | NUMERIC | `oolong-synth-dev-8192-813080050` |
| structural | spam | 16384 | 10013 | - | USER | `oolong-synth-dev-16384-114010042` |
| audit-correct | multinli | 8192 | 70010 | - | COMPARISON | `oolong-synth-dev-8192-713070057` |
| audit-correct | agnews | 32768 | 30016 | - | COMPARISON | `oolong-synth-dev-32768-315030019` |

Three label-judgement tasks, a seeded choice, run twice in fresh sessions: 20 items
× 6 arms = **120 arms**.

## 4. Order

One seeded task order; within each item the six arms run back to back in a seeded
order rotated so every arm is first equally often. Every planned arm gets a row.
Only infrastructure failures stop the run; `--resume` continues from the first arm
not attempted; completed arms are never rerun. No failed arm is repaired or
excluded.

## 5. Budget and reservation policy

The gateway reserves $4.32768 for every provider call (the full context bound at
the highest input rate plus the output bound) and releases it only on the receipt.
That amount is unchanged.

- **Per arm: $17.82** = four concurrent reservations plus a $0.50 allowance. Inside
  an arm the controller refuses any call for which spend plus active reservations
  plus the new reservation would pass $17.82, so four calls can be in flight (native
  Prime's observed fan-out of four subagents) and a fifth is refused.
- **Run: $28.20 reservation ceiling.** An arm starts only while known spend plus
  reservations of unknown outcome plus $17.82 is at most $28.20. So known spend
  plus outstanding reservations can never pass $28.20, and the run stops attempting
  arms once known spend passes $10.38.
- **Expected spend $5.31; high estimate $9.56** (1.8 × expected). The ceiling this
  needs is $9.56 + $17.82 = **$27.38**, within the proposed $28.20. If spend passed
  the high estimate the run would end with arms marked not attempted; it cannot
  overspend.

$28.20 is reservation capacity, not a spending target. Residual risk: an arm in
which Prime starts more than four calls at once has the extra calls refused, as in
the earlier run.

## 6. Measures

Per arm: deadline-aware score (official scorer; 0 for an arm that did not
complete), completion status and failure class, model calls, input, cache and
output tokens, cost from provider receipts, agent wall time, tool calls and errors,
answer provenance, and **context coverage** (`benchmark/coverage.py`): of the
records the question concerns (all, or the month or users its filter names), the
share whose text reached the model as tool output, counted as seen (the start of
the record) and full (the whole record), root and child sessions together.
Coverage says what was displayed, not what was understood.

## 7. Pre-registered analysis

All score contrasts use the label-judgement stratum only. Repeats are averaged
within task. The unit is the context: questions from one context are one cluster.

- **Primary endpoint: AC − AU**, the context-weighted mean paired score difference,
  with a 10,000-resample cluster bootstrap over the 12 contexts (95% and 90%
  intervals), δ = 0.05. Decision: superior if the 95% lower bound is above zero and
  the estimate is at least δ; inferior by the mirror rule; equivalent if the 90%
  interval lies within ±δ; otherwise inconclusive.
- **Secondary contrasts**, same method: AUC − AU (coverage added to the audit),
  AC − A0 (coverage alone), AU − A0 (replication of the audit effect on fresh
  contexts), PC − P0 (the instruction in Prime), and AU, AC, AUC each against P0.
- **Mechanism control:** (AC − A0) − (PC − P0), clustered by context. Near zero
  means the instruction is a general prompt effect; clearly positive means Aljure
  gains more from it.
- **Work:** for each coverage contrast, the paired mean difference in cost, model
  calls, input and output tokens, tool calls, latency, coverage and completion.
- **Negative controls** (never in a score contrast): the structural stratum, the
  audit-correct stratum, and the fresh label-judgement tasks the audit arm answers
  with a full score in this run. For each, the work differences of AC, AUC and PC
  against their controls. The third subset is selected on the control arm's outcome,
  so its score difference is biased against the treated arm; only its work measures
  are interpreted.
- **Reliability:** completion, timeouts, errors and tool failures per arm; exact
  sign and McNemar tests; wins, ties and losses per contrast.
- **GO rule for a later held-out test** of arm X in {AC, AUC}: X − AU ≥ 0.10 with a
  95% lower bound above zero, and X's cost per task at most half of P0's on the
  label-judgement stratum. A GO on AUC is a GO on a secondary contrast and is
  reported as such. Otherwise ITERATE or NO-GO on the evidence.

With 12 contexts the design can detect only a large effect (about 0.2 or more). A
null result here is weak evidence of no effect.

## 8. Claims this run can and cannot support

It can support a development-data statement about these arms on these twelve
contexts. It cannot support a held-out or superiority claim, a claim about 64K or
longer contexts, or a claim that coverage causes correctness beyond the paired
contrast. One run per plan; run-to-run variance is estimated only from the three
repeated tasks.

## 9. Changes from the verification ablation

New arms AC, AUC and PC; arms A2, A3 and P1 dropped; fresh contexts instead of
exposed ones; strata with negative controls; the coverage measure; four concurrent
reservations per arm ($17.82 instead of $4.93) and a $28.20 ceiling instead of $12.
Unchanged: model and settings, calls, deadline, scorer, reservation amount,
statistics, images, Prime commit.
