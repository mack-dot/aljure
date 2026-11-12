# Controller verification, first stage: answer-format validation A/B

**Status:** preregistered before any run. No inference has used the switch.

**Question:** does deterministic validation at `done` remove Aljure's
official-parse failures, without harming accuracy, cost or latency? The
validation is triggered by the controller, so the model cannot skip it.

**Scope (operator decisions of 2026-10-29):**
- This is the smallest safe stage of `CONTROLLER_VERIFICATION_DESIGN.md`: the
  format check only.
- **Deferred,** pending evidence and approval:
  - evidence extraction and invariant notices;
  - blinded review children;
  - any new system-prompt text.
- **Evidence extraction is measured offline instead.** The recorded `repl_eval`
  code is replayed in a fresh isolated worker, with no inference.

## Mechanism

`aljure_contract.answer_format = {max_lines: 1, max_chars: 256}`:
- **The contract:** general, declared in the plan, gold-free. It checks a root
  `done` summary only: lines are counted after trimming, characters on the raw summary.
- **On a violation:** one fixed notice, and the `done` is not run. A second
  violation is accepted as written and recorded.
- **The answer is never extracted, trimmed or rewritten.**
- **Aljure-only:** Prime is unchanged and cited from recorded runs. This is disclosed.

**Implementation:** `runtime.clj` (`answer-format-notice!`), `paired.py`
(validation and capability), and the auditor rule in `scripts/contract_audit.py`.

**Tests:**
- `verification_test/the-answer-format-notice-fires-once-and-never-rewrites`;
- `test_answer_format_is_declared_and_validated`;
- `test_format_notice_only_on_a_real_violation_with_its_switch_once`.

## Baseline (recorded, official scorer)

| Runs | Aljure low-confidence parses (scored 0) | Prime |
| --- | --- | --- |
| Count suite L0–L2 (`dc164044`) | **3 of 33 (9.1%)**: prose after `Answer: N` | 0 of 32 |
| 21-task suite: `d6e9b40d`, control, F1, F2 (`b157ee63`) | 0 of 80 | 0 of 83 |

The official scorer takes the text after the last colon
(`benchmark/vendor/oolong_synth.py:16`).

## Design

**Arms:** Aljure only, Opus 5.5, subscription only, with the limits of plan
`d6e9b40d`: 1,000 calls, 900 s and $100 per arm. Base contract F1. **The arms
differ only in `answer_format`.**

| Plan | Suite | Contract | Runs | Order |
| --- | --- | --- | --- | --- |
| counts-v1 | `dc164044` (11 tasks) | F1 + answer_format | 3 | 1st, 3rd, 5th |
| counts-v0 | `dc164044` | F1 | 3 | 2nd, 4th, 6th |
| synth21-v1 | `b157ee63` (21 tasks) | F1 + answer_format | 1 | 7th |
| synth21-v0 | `b157ee63` | F1 | 1 | 8th |

Each run of a plan goes to a new output directory. The same hash is run
repeatedly, which the runner permits (a fresh output directory is required).

**Prime reference:** recorded, unchanged, cited by hash (`prime_reference`) and
re-verified before every run.
- Count suite: the Prime arms of L0, L1 and L2.
- 21-task suite: the Prime arms of control, F1 and F2.
- **Disclosure:** non-contemporaneous. Drift between dates cannot be estimated
  inside this experiment, and power is reduced.

**Not used:** the sealed held-out suite.

## Endpoints

**Primary:** official-parse failure rate of Aljure answers (low-confidence parse)
in V1 against V0, on the count suite (33 V1 arms, 33 V0 arms).

**Activation (first-class):**
- format notices fired;
- share of notices followed by a conforming answer;
- violations accepted as written.

**Secondary:**
- declared-count mean absolute and signed error;
- official score;
- completion;
- calls, tokens and cost;
- p50 and p95 latency;
- Aljure cost against the cited Prime reference's mean cost per run.

**Integrity:** contract-auditor violations, unknown outcomes and isolation stops.

## Decision rule (fixed before the runs)

**Adopt `answer_format`** (retain, off by default in code, on in future
candidate plans) only if all of these hold:
1. **Contract intact:** 0 auditor violations and no unknown provider outcomes.
2. **Effective:** V1's official-parse failure rate is 0, counting every notice
   that fired.
3. **Activated or vacuous:** at least one notice fired. If none fired in V1
   while V0 shows failures, report "not activated" and do not adopt.
4. **No harm to accuracy:**
   - V1's pooled count error (absolute) is no worse than V0's by more than 2.0;
   - V1's 21-task mean official score is no worse than V0's by more than 0.05.
5. **No harm to cost:** V1's Aljure cost is at most 1.05× V0's on each suite,
   and at most 0.6× the cited Prime mean.

**Not concluded either way:** one-arm-per-task effects on semantic accuracy.
This stage targets delivery, not reasoning.

## Stop rules

As in `REVIEW_ABLATION_PROTOCOL.md`. Any of these stops the plan before the next
arm, and the chain stops before the next plan:
- an isolation-preflight refusal (one bounded `docker info` retry, then fail closed);
- an unknown provider outcome;
- a Docker restart;
- an unconfirmed cleanup;
- a changed Prime reference.

## Cost (API-rate equivalent; Aljure only)

| Block | Arms | Measured $/arm | Expected |
| --- | --- | --- | --- |
| Count suite, 6 runs | 66 | $0.22–0.25 (L0–L2) | $15–17 |
| 21-task suite, 2 runs | 42 | $0.08 (control/F1) | about $3.5 |
| Prime | 0 | cited | $0 |
| **Total** | 108 | | **about $18–21** |

**Hard caps:**
- $100 per arm;
- per plan run, the sum of its arm caps: $1,100 for a count run, $2,100 for a
  21-task run;
- across the 8 runs, $10,800 nominal. These are caps, not estimates.

**Time:** about 95 minutes sequential (about 65 s per count arm, 30 s per 21-task arm).

## Frozen plans (2026-10-29)

**Source:** clean commit `8a93ecf` on branch `claude/verification-v1`.
Execution checkout: `/Users/mackianni/aljure-verify-v1`.

| Plan | plan_sha256 | Arms | Cited Prime reference (plan, Prime arms) |
| --- | --- | --- | --- |
| counts-v0 | `e925596391d4a7633aaa4917a1e0e17438db59505cd95a7f997c61c13fca9fab` | 11 Aljure | L0 `def381f5` (11), L1 `240ce694` (11), L2 `51687387` (11) |
| counts-v1 | `1612cb6751ed600e8b2ec2a45b2438e0f6459b8ab5c909504ee7e8e4af3a0f85` | 11 Aljure | the same |
| synth21-v0 | `5fdab5e292688eb88c913c99edb7d9910d934a8bc082c9109d0184884c68661f` | 21 Aljure | control `87d8c949` (21), F1 `52f51590` (21), F2 `b1844732` (21) |
| synth21-v1 | `9d16cc1a59b899b962551b8c7f5478467b273d23449f1af986e21fc066fc5e93` | 21 Aljure | the same |

**Gates, regenerated at `8a93ecf` with zero model calls:**
- SCI isolation TESTED: 9/9 negative cases, 9/9 startup, both boundary checks,
  and the supervisor hash matching the code;
- Prime isolation 10/10;
- SCI contract 76/76;
- subscription relay fixture 15/15, OAuth protocol verified;
- preflight ready for all four plans, with no blockers.

**Provider:**
- `claude-oauth-subscription`, with subscription fallback `false`;
- no API key in the environment;
- runs use `--authorize-subscription-plan`.

**Evidence:** `evidence/verify-v1/`.
