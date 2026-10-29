# Why Opus helped Prime more than Aljure

**Diagnostic evidence from observed dev tasks.** It does not change any
historical score. Companion documents:
- `SONNET_OPUS_PAIRED_DECOMPOSITION.md` (per-task numbers);
- `PRIME_MULTINLI_TRAJECTORY_ANALYSIS.md`;
- `MODEL_HARNESS_PROMPT_AUDIT.md`;
- `FINALIZATION_RECOVERY_VALIDATION.md`;
- `ADAPTIVE_COMPUTE_ABLATION_PLAN.md`.

## Evidence pinned

| Run | Plan | Commit | Model | Suite | Limits | Report sha256 |
| --- | --- | --- | --- | --- | --- | --- |
| Sonnet | `0b6a0451…` | `dfd82fb` | `claude-sonnet-5-5` | `b157ee63…` (21 tasks, 7 contexts) | 12 calls, 120 s | `3f944e23…` |
| Opus | `d6e9b40d…` | `f96f0fb` | `claude-opus-5-5` | `b157ee63…` | 1,000 calls, 900 s | `f2cba0c7…` |

Images: SCI `58550c92…`, Prime `f3e30aaa…`. Prime commit `c4c238ca…`. In both
runs, the provider receipts name the pinned model on every call.

The reported figures (0.768, 0.800, 0.771, 0.919; $0.81, $1.59, $1.73,
$3.81; 501, 564, 567 and 741 s; 95, 94, 96 and 125 calls; 21, 20, 19 and 21
answered) match the saved scorer reports and gateway receipts.

## Every weak task, classified (score < 0.9)

Classes: 1 model reasoning, 2 incorrect program, 3 SCI capability mismatch,
4 missing semantic review, 5 premature stopping, 6 final-answer protocol,
7 provider transport, 8 insufficient computation or algorithm, 9 task
misread.

| Arm | Task | Score | Class | Evidence |
| --- | --- | --- | --- | --- |
| Aljure Sonnet | 4 formality, user | 0.00 | 4 | Regex "informal" heuristic, then an immediate answer; 12% of items shown (`SYNTH_INDEPENDENT_32K_RESULTS.md`) |
| Aljure Sonnet | 16 multinli, count | 0.00 | 1 | 97% of pairs shown; count far off |
| Aljure Sonnet | 19–21 agnews, counts | 0.02 / 0.01 / 0.10 | 1 | 99% shown; counts off by 8–16; the replies themselves call the counts estimates |
| Prime Sonnet | 16 multinli | 0.01 | 1 | All shown; count far off |
| Prime Sonnet | 17 multinli, user count | 0.00 | 6 | Worked out an answer, then "I did not write /work/answer.txt" |
| Prime Sonnet | 19–21 agnews | 0.24 / 0.42 / 0.13 | 1 | All shown |
| Aljure Opus | 6 formality, label | 0.00 | 6 | Two text-only replies, both ending with the correct `Label: formal` |
| Aljure Opus | 7 imdb, comparison | 0.00 | 7 | `stop_reason: tool_use` with only thinking blocks ("interrupted before it finished") |
| Aljure Opus | 16 multinli | 0.08 | 8 (1) | Read all 438 pairs in 5 pages and counted once at the end (120 against 129); no running tally |
| Aljure Opus | 19 agnews | 0.75 | 1 | Off by 1 (better than Prime) |
| Aljure Opus | 20 / 21 agnews | 0.18 / 0.18 | 1 | Off by about 6. On task 21 only 2% was shown, a rules path, but Prime scored the same after reading everything |
| Prime Opus | 19–21 agnews | 0.56 / 0.56 / 0.18 | 1 | All shown |

**No task failed from an SCI capability mismatch, an incorrect program or a
misread task.** Aljure's tool errors (5 under Sonnet, 2 under Opus) were all
recovered.

## Answers

1. **How much did Opus improve Aljure's reasoning on completed tasks?** By
   **+0.108** on the 19 tasks Aljure Opus answered (0.744 → 0.852). Prime gained
   +0.132 on the same tasks.
2. **How much of Aljure's deficit comes from completion failures?** The Opus
   gap to Prime is −0.148. Completion failures account for **−0.095 (64%)**,
   the MultiNLI count for −0.044 (30%) and AG News noise for −0.009.
3. **Why did Prime benefit more?** For three reasons:
   - A completion failure it had under Sonnet (task 17) did not recur.
   - It got one exact count (task 16) by counting each page into program
     state.
   - It made modest AG News gains.

   Meanwhile Opus brought Aljure two new delivery failures that cancelled its
   own gains. Recursion did not cause Prime's MultiNLI result: the sub-agents'
   output was never used.
4. **Which Prime affordances were used?** `python_repl` in every arm.
   `rlm.spawn` in one arm, with output unused. Skills, refinement, compaction,
   `bash` and MCP: never.
5. **What could Aljure expose through small, general interfaces?**
   - A completion rule mapping a requested answer form to `done`.
   - The terminal-answer and retry paths (built: F1, F2).
   - A per-batch tally sentence or helper.
   - A clearer `agent_call` description.
6. **Is Aljure stopping too early?** Not relative to Prime:
   - Under Opus, Aljure arms ended by the model's own choice, far inside the
     limits (longest arm 48 s against 900 s).
   - Both harnesses answered count tasks after one pass with no verification.
   - Aljure skipped the per-page tally Prime used once.
   - Under Sonnet, Aljure answered one label task from rules alone (task 4);
     under Opus, its review coverage rose on several tasks.
7. **Would more reasoning, verification or delegation help?**
   - Verification and per-batch tallying: plausible for exact counts, where the
     errors are accumulated judgement.
   - Delegation: not shown to help here.
   - All three are untested.
8. **Which changes keep Aljure's cost and latency advantage?**
   - F1 and F2 cost nothing unless triggered.
   - A completion sentence and a tally sentence cost about 30 tokens and no
     extra calls.
   - Verification passes and delegation add calls; measure them before
     adopting.
9. **What is the smallest experiment that could establish the cause?**
   - **Delivery:** F2 against a control on the observed dev suite with Opus,
     plus, separately, the completion sentence. Both are frozen or designed.
   - **Counting:** the tally intervention against a control on the four
     exact-count tasks, 3 repeats each, with Opus.
10. **What would falsify "Aljure's controller constrains stronger models"?**
    Two conditions together:
    - with F1 and F2 on, Aljure completes every task;
    - its per-task difference from Prime on completed tasks stays within
      run-to-run variance (estimated from the control and the Prime replicates).

    The matched-subset gains already observed (+0.108 against +0.132) are more
    consistent with completion handling than with suppressed reasoning.

## The three highest-value interventions

| Rank | Intervention | Estimated impact (Opus, dev) | Uncertainty | Effort | Evaluation |
| --- | --- | --- | --- | --- | --- |
| 1 | **Reliable completion**: F2, then the completion sentence; F1 as a safety net | Up to +0.095 (both lost tasks had correct answers available) | Medium: depends on Opus following the instruction; F1's event is rare | F1 and F2 done and tested; the sentence is ~30 tokens | Frozen plans: control `87d8c949…`, F1 `52f51590…`, F2 `b1844732…`. The completion sentence follows as its own plan |
| 2 | **Per-batch tally** for judged counts (sentence, or prelude helper) | Up to +0.044 (task 16), possibly agnews | High: one supporting trajectory | Small | 4 count tasks × 3 repeats, control against sentence against helper |
| 3 | **Explicit uncertainty checks** (unknown and conflict review) | Protects rule-heavy label tasks (the Sonnet task 4 kind) | Medium: strong offline A1c evidence (`RESIDUAL_REASONING_ANALYSIS.md`), no live test | Medium: helpers, prompt and tests | Label tasks on dev with Sonnet and Opus; then one frozen candidate on the sealed held-out suite |

None of these copies Prime's architecture. Each is a small, general mechanism
that can be ablated separately.
