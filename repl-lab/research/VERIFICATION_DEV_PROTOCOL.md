# Verification ablation on development data (verification-dev-v1)

Frozen before any model call; the plan hash binds this file. **Not authorized by
this file**: the run needs the owner's approval of the exact plan hash through
`var/host-policy-20261103/run_guarded.py verify --approve <hash>`. Follows the owner's
2026-11-04 order of work after Phase B (`HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md`): the
reservation-aware cap is fixed (step 1); this is steps 2 and 3 plus the cross-harness
comparison; a held-out run (step 4) only if the GO rule below is met.

## 1. Hypothesis

Aljure's held-out losses to Prime came from accepting a cheaper judgement without a
verification step (rounds 16 and 50: a re-tuned keyword count trusted without reading;
a one-shot read with no tally). The falsifiable claim: making the harness record one
label per item and audit coverage before answering raises Aljure's score on
comparison and count questions by at least 0.10 while keeping its cost at or below
half of Prime's. A second question: is that gain specific to Aljure, or available to
any harness given the same instruction?

## 2. Arms (six per task, same model, settings, caps and deadline)

| Arm | Harness | Contract | What it isolates |
| --- | --- | --- | --- |
| A0 | Aljure | `terminal_text_answer: text-answer-v2` | the Phase B harness (baseline) |
| A1 | Aljure | A0 + `structured_labels` + `uncertainty_audit` | the verification contract: prompt text plus the SCI helpers `show-items` and `audit-labels` |
| A2 | Aljure | no text answers, no verification | the text channel (A2 − A0) |
| A3 | Aljure | A1 + `targeted_review` | the controller's one-time evidence gate (A3 − A1) |
| P0 | Prime | unchanged | baseline |
| P1 | Prime | `prime_contract.verification_prompt` | the same contract as a prompt (`resources/prime-verification.txt`), with Prime's kernel in the role of SCI |

Identical for every arm: Sonnet 5.5, adaptive summarized thinking, effort medium,
32,768 max tokens, 16 calls, 240 s, **$4.93 per arm** (one $4.33 reservation plus a
$0.60 allowance; the Phase B defect fixed), the same public context and question.
Prime's contract is the harness-neutral wording of Aljure's three texts; Aljure's
helpers are SCI functions, Prime's equivalent is its Python kernel. That asymmetry is
the comparison's point and is disclosed.

## 3. Inputs (development)

Two new suites from the pinned OOLONG-synth development windows, selecting by
upstream `answer_type` only (COMPARISON and NUMERIC: the kinds lost in Phase B),
excluding every question id any prepared development suite has used (pinned list):

| Suite | Windows | Tasks |
| --- | --- | --- |
| `verify8-dev` `93f2b21a…` | 8K …010: negation, formality, imdb, app_reviews, yahoo, multinli | 12 (7 comparison, 5 count) |
| `verify32-dev` `1c9da9b4…` | 32K …016: yahoo, multinli, agnews, negation | 8 (5 comparison, 3 count) |

20 tasks over 10 contexts (the contexts were seen in pilot 1 and the October runs;
these questions were not), a seeded 20% (4 tasks) repeated: 24 items × 6 arms =
**144 arms**. The round-16 pattern (yahoo topic frequency, including "Entertainment
& Music" against "Health" at 8K) and the round-50 pattern (multinli subset
comparisons) are both present. Held-out suites are untouched.

## 4. Order and budget

Seeded task order; within each item the six arms run back to back in a seeded order
rotated so that every arm is first equally often. Every planned arm gets a row;
only infrastructure failures stop the run; `--resume` continues. Known spend is
refused past **$12** (the next arm is refused when spend plus $4.93 would exceed it).
Expected about $6.5 at Phase B per-arm costs; verification arms may cost more.

## 5. Pre-registered analysis

- **Primary:** A1 − A0, context-weighted mean paired deadline-aware score
  difference over the 10 contexts, repeats averaged within task, 10,000-resample
  cluster bootstrap, δ 0.05, decision rule as the campaign's.
- **Secondary contrasts, same statistic:** A2 − A0 (text channel), A3 − A1 (gate),
  P1 − P0 (contract in Prime), A0 − P0 and A1 − P1 (harness gap before and after),
  and the harness-specific part (A1 − A0) − (P1 − P0) with its own bootstrap.
- **Per arm:** score, completion, cost per task and per success, latency p50/p95,
  model calls, tool calls and errors, answer provenance (done / file / terminal
  text), use of `show-items`, `audit-labels`, the evidence gate, and Prime's dict
  tallies, from the traces.
- **GO rule for a later held-out run:** A1 − A0 ≥ +0.10 (point estimate) and
  A1's cost per task ≤ 50% of P1's. Otherwise NO-GO, and the next step is a
  different mechanism, not a held-out run.
- Text-channel interpretation: A2 − A0 measures the channel's effect on the same
  tasks; a 0.50 against 0.79 descriptive gap in Phase B does not establish
  causation and is not used here.

## 6. Commands

```
python3 -m benchmark.verification_ablation plan --out var/verification-dev-20261104/plan.json
python3 -m benchmark.verification_ablation preflight --plan var/verification-dev-20261104/plan.json
python3 var/host-policy-20261103/run_guarded.py verify --approve <plan_sha256>          # owner only; paid
python3 -m benchmark.verification_ablation report --out var/verification-dev-20261104/run-1
```

Freeze from a clean commit; any commit outside `var/` voids the plan. Results go to
`VERIFICATION_DEV_RESULTS.md`; evidence archived in a separate later commit.
