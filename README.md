# Aljure

Aljure studies whether a fixed model can improve its computational environment by
creating, validating and reusing executable software. The implementation is in
[`repl-lab/`](repl-lab/README.md).

Two research tracks remain distinct:

1. Compare Aljure with pinned native Prime Agent on independently scored RLM tasks.
2. Test whether validated executable learning improves later tasks after restart.

The first live experiment produced a retained Clojure scheduling policy. Direct
cold-boot execution improved against the original policy and matched a fixed
baseline. Worker failures and weak autonomous reuse limit the result. Harness-level
improvement and a live performance advantage over Prime remain unproven.

- [First live results and failures](repl-lab/research/FIRST_LIVE_RESULTS.md)
- [Completed offline skill-discovery control](repl-lab/research/SKILL_DISCOVERY_V4_RESULTS.md)
- [Native Prime comparison integration](repl-lab/research/EXTERNAL_COMPARISON_V1.md)
- [Frozen first paired protocol and live blocker](repl-lab/research/PRIME_HEAD_TO_HEAD_V1_RESULTS.md)
- [Current acceptance status](repl-lab/ACCEPTANCE.md)
- [Full progress and test history](repl-lab/PROGRESS.md)

Fixture results are labeled separately from model experiments. New inference
requires explicit approval, fixed caps and current isolation evidence. Historical
Claude subscription runs do not authorize new API billing.
