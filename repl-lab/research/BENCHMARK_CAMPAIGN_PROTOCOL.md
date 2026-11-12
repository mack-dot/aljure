# Benchmark campaign protocol

The study plan for issue #1 and the 2026-10-28 brief: phases, freeze points,
task groups, budgets, claim boundaries, and the exact next benchmark protocols.

Companion documents:
- `BENCHMARK_VALIDITY_AUDIT.md` (state and defects);
- `PRIME_PARITY_MATRIX.md` (capability differences);
- `SCI_EXECUTION_CONTRACT.md`;
- `STATISTICAL_EVALUATION_PROTOCOL.md` (analysis rules and question labels);
- `BENCHMARK_SUITE_MATRIX.md`;
- `EXECUTABLE_LEARNING_EXPERIMENT.md`;
- `ABLATION_ROADMAP.md`.

**No live run starts without explicit approval of its exact frozen plan hash
and budget.**

## 1. Phases

| Phase | Purpose | Data | Harness changes allowed | Claims |
| --- | --- | --- | --- | --- |
| A — Engineering validation | Fix integration defects; check that contracts, isolation, recovery and accounting work | Development only: OOLONG-Pairs 8K and 32K ten-task suites (already exposed), plus development contexts from new suites | Yes, between plans | None (diagnostic) |
| B — Frozen head-to-head | Q-HARNESS on unexposed task groups | Held-out independent contexts (section 3) | **No**, from freeze until the last case | Q-HARNESS, under the statistical protocol |
| C — Controlled ablations | One mechanism at a time (`ABLATION_ROADMAP.md`); Q-SUBSTRATE; Q-LEARNING | Development tasks; Q-LEARNING has its own held-out split | Yes, between plans | Mechanism effects on development data; held-out only for Q-LEARNING |

## 2. Freeze points

1. **Harness freeze.** Aljure and adapter commit, clean checkout, both images by
   ID, SCI surface and bound, prompts, tool schemas, gateway rules and the
   Prime commit. All are recorded in the plan (`paired-plan`).
2. **Proof freeze.** SCI isolation and SCI contract proofs for the configured
   bound, the native Prime proof, and the relay fixture, all at the frozen
   commit. Preflight refuses otherwise.
3. **Data freeze.** Suite manifest hash, task IDs, context grouping, selection
   rule, and the scorer pinned by commit and hash.
4. **Analysis freeze.** This document and `STATISTICAL_EVALUATION_PROTOCOL.md`,
   at a recorded commit, before the first held-out arm.

## 3. Task groups

| Group | Use | Status |
| --- | --- | --- |
| OOLONG-Pairs 8K, tasks 1–10 (one context) | development / regression | exposed 6 times |
| OOLONG-Pairs 32K, tasks 1–10 (one context) | development / ablation | exposed 3 times (tasks 6–10 twice) |
| **LongBench Pro, English without T4: 484 independent contexts** | 10 development contexts (pilot) and **60 held-out contexts** (20 each at 8k, 16k and 32k), one question each, selected by seeded shuffle and fixed before the first run | **first Phase B held-out**; importer and scorer not built (section 6, step 3) |
| OOLONG-synth (at most 16 windows per length on test; windows share a source pool) | clustered secondary suite; Q-LEARNING task family | partial importer |
| Further suites (LongCoT-Mini, ManyIH Coding, Terminal-Bench 2.0) | later Phase B / Q-SUBSTRATE | see `BENCHMARK_SUITE_MATRIX.md` |

OOLONG cannot supply many independent contexts. Pairs has one context per
length, and synth has two windows per dataset and length (recounted). The
earlier plan of 30 synth contexts at 32K is therefore impossible, and
LongBench Pro replaces it. OOLONG-Pairs contexts are built from synth
`trec_coarse` validation windows, so any synth use must keep to the test split.

## 4. Budgets

Distinguish three numbers on every plan:
- **Expected spend.** API-rate-equivalent, from measured per-arm costs.
- **Hard reservation ceiling.** $12 per arm × arms. This is a bookkeeping bound
  from the conservative per-call reservation, not an expectation.
- **Call ceiling.** 12 per arm.

Billing is the Claude subscription; the actual invoice is unknown.

| Plan | Arms | Expected | Reservation ceiling | Calls ceiling |
| --- | --- | --- | --- | --- |
| A1: `bounded-64k` SCI ablation, 32K development (re-frozen after `178bfc3`) | 20 | ≈ $2 | $240 | 240 |
| A2: LongBench Pro development pilot, 10 contexts × 1 | 20 | ≈ $2–3 | $240 | 240 |
| B1: LongBench Pro held-out, 60 contexts × 1 (+12 repeats) | 144 | ≈ $12–25 | $1,728 | 1,728 |
| Q-LEARNING minimum design | ≈ 192 model tasks + acquisition | ≈ $35–65 | per plan | per plan |

## 5. Claim boundaries

- No claim from one context, from development data, or from a run with more
  than 10% infrastructure failures.
- No comparison of our Sonnet 5.5 scores with Prime's published numbers for
  other models or settings.
- Q-HARNESS compares complete systems. A win or loss is not attributed to SCI,
  memory or orchestration without the matching ablation.
- Capability differences are disclosed (`PRIME_PARITY_MATRIX.md`), not removed.
- Equivalence is claimed only under the TOST rule.

## 6. Exact next protocol

**Step 1 — offline, no approval needed.**
1. Rebuild the Python worker image, or record it as unavailable.
2. Regenerate the SCI isolation proofs (64 KiB and 1 MiB) and the native Prime
   proof at the execution commit.
3. Regenerate the SCI contract proofs.
4. Run the relay fixture to confirm the Prime stream fix
   (`message_update` markers). Its checks must pass, and the native stream
   must stay under 4 MiB.
5. Run `python3 -m benchmark audit`; it must report no violations.

**Step 2 — Plan A1 (needs approval).** Re-freeze `sci-ablation-bounded-64k` at
the new commit on `var/official/pairs32-ten` (the development suite).
- Same model, settings, caps and gates as the control (`50911e6b…`).
- **Purpose:** check that the assisted, bounded SCI surface works with a live
  model.
- **Measures:** Aljure completion, expression errors per call, worker
  restarts, truncation notes and `page` use.
- **Success gate to proceed:** Aljure completes at least 7/10, with no worker
  restart caused by output size.
- **Expected:** ≈ $2.

**Step 3 — offline: LongBench Pro adapter.**
- **Importer:** pin HF `caskcsg/LongBench-Pro` @ `4996884d` and the JSON's
  SHA-256 in `upstream.lock.json`. Downloading public data needs network
  access, not inference.
- **Selection:** English, excluding T4; one question per context. A seeded
  shuffle of context hashes, stratified over 8k, 16k and 32k, fixes the 10
  development contexts and the 60 held-out contexts in the manifest, before any
  run.
- **Scorer:** port the official `modules/evaluation.py` and `utils.py` metrics
  (NDCG, pairwise accuracy, accuracy, F1, SubEM) at a pinned commit, with an
  AST or behavioural equivalence check like the OOLONG one.
- **Pre-registration:** the question variant. `question_thinking` matches
  adaptive thinking; record the choice.
- **Delivery:** the context as `/work/context.txt` for Prime and
  `external-context` for Aljure, as for OOLONG. The answer format follows the
  official prompt.
- **Tests:** selection reproducibility and answer-independence; context
  independence; gold isolation; the scorer self-test (`benchmark audit`).

**Step 4 — Plan A2 (needs approval).** A LongBench Pro development pilot on
the 10 development contexts. It checks the scorer and delivery end to end and
estimates per-arm cost and σ_c. It is not held out.

**Step 5 — Plan B1 (needs approval): first held-out Q-HARNESS evaluation.**
- **Data:** LongBench Pro, English without T4, the 60 held-out contexts (20 per
  length), one question each; plus 12 repeated tasks (20%, fresh sessions; 24
  arms) for run-to-run variance.
- **Arms:** frozen Aljure (surface chosen in A1; default assisted + bounded,
  64 KiB) against native Prime at `c4c238ca`, with the stream fix.
  Q-SUBSTRATE does not depend on B1. ManyIH Coding (427 problems with unit
  tests) is its cheapest suite once the Python path exists.
- **Rules:** the same model and settings, 120 s, 12 calls and $12 per arm;
  alternating order; stability gates.
- **Primary:** context-weighted mean paired deadline-aware score difference,
  with a bootstrap over contexts (one question each). Decision rules as in the
  statistical protocol.
- **Expected:** ≈ $12–25 API-rate-equivalent; reservation ceiling $1,728.
