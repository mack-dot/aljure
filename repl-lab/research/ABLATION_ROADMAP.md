# Ablation roadmap (Phase C)

Controlled one-variable experiments on **development** tasks only. Each row is
its own frozen plan and its own evaluation. A configuration chosen here is
frozen again and evaluated on held-out tasks (`BENCHMARK_CAMPAIGN_PROTOCOL.md`).
Use the analysis rules in `STATISTICAL_EVALUATION_PROTOCOL.md`; development
results inform choices and support no claim.

Prerequisites for every row:
- fresh proofs at the execution commit;
- the relay fixture;
- the audit (`python3 -m benchmark audit`) with no violations;
- the stability gates.

| Priority | Variable (one at a time) | Arms | Tasks | Primary measure | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | SCI surface | raw (control) vs assisted vs assisted + bounded, all at 64 KiB | 32K Pairs development suite (1 context; diagnostic) | Aljure completion and score; expression errors per call; worker restarts | control done (`50911e6b…`); `bounded-64k` frozen, not run; needs re-freeze after `178bfc3` |
| 2 | Output bound | assisted raw 64 KiB vs assisted raw 1 MiB | same | as above, plus tokens per call and ledger size | 1 MiB proven (isolation, boundary, contract); not run |
| 3 | Worker prewarming | lazy start vs start during the first model call | development OOLONG-synth (multiple contexts) | latency p50/p95; timeout rate | not implemented |
| 4 | Execution substrate (Q-SUBSTRATE) | SCI vs Python under the same native-tool controller | development set with ≥ 10 contexts | deadline-aware score; first-try execution success; calls per solution | Python path needs: image rebuild, gate v2 proof, language-specific tool text, `external_task` language switch, `paired.py` arms (see audit) |
| 5 | Tool-output representation | plain-text strings vs EDN-escaped | 8K Pairs development | score; tokens | done implicitly (`87d5fda`); isolate only if needed |
| 6 | Controller compute boundary | Aljure controller on host vs inside a matched 256 MiB / 1 CPU container | development set | latency; score | not implemented; needed for Q-HARNESS parity (matrix row 4) |
| 7 | Persistent computation | session worker kept vs fresh worker per call | development set | calls per solution; score | runtime flag needed |
| 8 | Verification (Q-LEARNING) | B vs C (unverified vs validated retention) | `EXECUTABLE_LEARNING_EXPERIMENT.md` | held-out completion | arm B missing |
| 9 | Reuse | C vs A | same | held-out completion, cost | defects 1–2 in that document first |
| 10 | Orchestration | synchronous children vs parallel children | multi-part development tasks | latency; score | parallel children not implemented |

## Interactions

Test the SCI surface (1) and output bound (2) as a 2×2 only if (1) shows the
assisted surface matters. Test prewarming (3) × substrate (4) only if Python
and SCI differ by more than their startup gap. Otherwise, keep one variable
per plan.

## Stop rules

- Stop an ablation line when two consecutive development runs show a change
  smaller than run-to-run variance (measured from repeats).
- Never tune on held-out tasks. Any held-out exposure marks the suite as
  development from then on, in `BENCHMARK_VALIDITY_AUDIT.md`.
