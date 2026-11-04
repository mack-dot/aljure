# Head-to-head v8, pilot 1: results

**LIVE MODEL RUN, development evidence, run once.** Plan
`bdb21429a930c371229aa40c6f9352ea8b2637dadfc2f6d1a093cea60e4e7502`
(protocol `HEAD_TO_HEAD_V8_PROTOCOL.md`, source commit `ac5b99f` clean, SCI image
`40f00364…`, Prime `c4c238ca…` / `f3e30aaa…`), approved by the owner and
launched through host policy v1 on 2026-11-04 from 13:05:04 to 13:37:58 local
time, Sonnet 5.5 through the Claude subscription. All 68 arms ran; accounting is
complete; no infrastructure failure, no timeout, no orphan container. Raw
traces: `var/h2h-20261104/run-1`; committed copy:
`evidence/head-to-head-v8-20261104/` (no transport bodies or sqlite stores).
`report-as-run.json` is the report the runner wrote; `report.json` was
regenerated after two report fixes (Pareto dominance judged within a suite
only; no interval below five contexts). Per-arm rows are identical in both.

## 1. Headline

| | Aljure | Prime |
| --- | --- | --- |
| Arms | 34 | 34 |
| Deadline-aware mean score (all suites, descriptive) | 0.767 | 0.833 |
| Completed with an answer | 33 | 34 |
| Timeouts / infrastructure failures | 0 / 0 | 0 / 0 |
| Cost, API-rate-equivalent | **$0.964** | $2.082 |
| Model calls | 133 | 167 |
| Agent latency p50 / p95 | **22.8 s / 36.6 s** | 25.9 s / 50.6 s |
| Tool calls / tool errors | 120 / 4 | 133 / 4 |
| Output tokens | 41,363 | 45,512 |
| Cache-read tokens | 393,597 | 1,908,039 |

Total $3.05 against the $5.52 estimate (range $3.9–9.9); both arms came in
below their priors at every length. Aljure cost 46% of Prime and was faster at
p50 and p95, with the same tool-error count. Prime scored higher on every suite;
only the 32K suite reaches a decision under the pre-registered rule, and that
decision is **equivalent**. Prime used `python_repl` only: no spawn, refine or
compaction in any arm.

## 2. Per suite (primary endpoint: context-weighted paired difference, Aljure − Prime)

| Suite | Tasks (contexts) | Aljure | Prime | Difference | 95% / 90% interval | Decision | W/T/L | Cost per task A / P | p50 A / P |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synth8, unexposed | 12 (6) | 0.861 | 0.911 | −0.058 | [−0.324, 0.208] / [−0.303, 0.188] | inconclusive | 2 / 8 / 2 | $0.025 / $0.052 | 19.7 / 23.9 s |
| synth32, development | 7 (7) | 0.879 | 0.888 | −0.010 | [−0.029, 0.0] / [−0.029, 0.0] | **equivalent** | 0 / 6 / 1 | $0.032 / $0.066 | 28.4 / 23.3 s |
| synth128, unexposed | 6 (3) | 0.513 | 0.638 | −0.083 | none (3 contexts) | no interval | 0 / 5 / 1 | $0.018 / $0.060 | 20.0 / 31.0 s |
| pairs32, development | 3 (1) | 0.720 | 0.846 | −0.156 | none (1 context) | no interval | 0 / 0 / 3 | $0.054 / $0.084 | 23.1 / 41.0 s |

Repeats (6 tasks, fresh sessions): mean absolute score change between trials was
0 for both arms on synth8 and synth32; 0.5 for Aljure and 0 for Prime on
synth128 (one Aljure task flipped from wrong to right); 0.10 for Aljure and 0.06
for Prime on pairs32. The synth32 "equivalent" decision rests on 7 contexts with
6 exact ties; the interval is narrow because the only difference is one task,
and it should be read as "no difference observed", not as proof of parity.

McNemar on success at 0.9: synth8 2 against 2 discordant pairs, synth128 0
against 1, pairs32 0 against 2, synth32 0 against 0; no p below 0.5.

## 3. Pareto (within each suite; mean score, cost per task, agent p50)

No point is dominated within any suite: on all four suites Aljure is cheaper,
and on three it is faster, while Prime scores higher. The trade-off is
score against cost and latency, and this pilot cannot rank the two harnesses
without a weighting. Single-run points; the per-run spread is unmeasured.

## 4. Failure attribution (every non-perfect arm, from the traces)

**Aljure, one error (synth8, task 213020056, gold 6).** The model computed the
answer and replied in text, "Answer: 6 … classified each by hand", without a tool
call. The contract rejected it, spent its single correction, got text again and
ended the session. A correct answer was lost to the no-text-answer rule. This is
the delivery failure mode recorded in `OPUS_FINALIZATION_REPAIR.md` and
`CONTRACT_ABLATION_RESULTS.md` (`terminal_text_answer` is off); it cost 0.083
of the synth8 mean, more than the whole observed synth8 gap.

**Aljure, four tool errors, all recovered within the task:** `.indexOf` on a
vector refused by the SCI deny list (synth128 task 417040041, trial 0, which
then answered wrong; trial 1 answered right), two `String.substring` on nil
(a short-string `subs` after the first read; synth8 and synth32), one unmatched
delimiter. None ended a task.

**Prime, four tool errors, all in pairs32, all recovered:** two
`SyntaxError: Generator expression must be parenthesized`, one `NameError` on
an undefined helper after a kernel cell failed, one `NameError: name 'U'`.

**Shared wrong answers (both arms, same wrong label):** synth128 517050024
(topic frequency, keyword heuristics in both arms), 717070025 (count 591 against
599, both), 717070028 (NLI label neutral against entailment, both). At 128K
three of six tasks beat both harnesses the same way, so the 128K gap of −0.083
is one task (417040041) in which Aljure's first trial was wrong after the deny-list
error and Prime's was right.

**Aljure-specific wrong answers:** synth8 413040037 (count 77 against 87;
Prime 87) and synth32 315030025 (52 against 40; Prime 48, also wrong). Pairs:
Aljure's F1 was lower on all three tasks (0.68, 0.79, 0.73 against 0.91, 0.74,
0.93); its pair lists anchored on a different user set in two tasks (user 12646
instead of 12455; 10352 included), so the loss is in choosing which users meet
the condition, not in pair generation.

**Prime-specific wrong answer:** synth8 513050037 (topic comparison reversed).

## 5. Host and isolation record

Gate `gate-1793815502.json` admitted the run at 87.5% swap with two warnings
(under 512 MB free memory; load above CPU count); the earlier gate
`gate-1793815339.json` refused at 91% swap, and a watcher script launched the
run when swap fell below 88%. During the run (305 samples at 5 s): swap 82.4%
to 97.5% of a swap file that macOS grew from 8 to 14 GB, free memory 40 MB to
4.5 GB, one-minute load 7.9 to 23.3, Docker Desktop session unchanged. Docker
events: 68 containers created and destroyed; 34 SCI workers exited 0; 34 Prime
containers were killed at cleanup (exit 137, the adapter's normal stop); no
OOM kill. SCI worker startup 757 / 883 / 2,441 ms (min / median / max), all 34
cleanups confirmed; gateway cleanup ok on 68 of 68; no orphan after the run.
Credential 6.9 h from expiry at launch. **Latency was measured on a saturated
host**; both arms shared it, but absolute times carry no inference.

## 6. Limitations

- Development pilot, one run per plan. The only cross-context decision
  (synth32, equivalent) has 7 contexts and 6 ties. synth8 is inconclusive with a
  wide interval; synth128 and pairs32 have too few contexts for any interval.
- Mixed exposure: synth32 and pairs32 tasks were used in October development.
- Compute boundary (parity matrix row 4) and the saturated host both favour
  no particular arm in principle but are not controlled.
- The no-text-answer contract cost Aljure one correct answer; the comparison
  is of the harnesses as frozen, including that rule.
- OBLIQ-Bench and LongBench Pro are not yet run (pilot 2).

## 7. Prioritized recommendations for Aljure

1. **Accept a final text answer when it carries the requested form** (the
   `terminal_text_answer` path already built; `OPUS_FINALIZATION_REPAIR.md`).
   The one Aljure failure in 34 arms was a correct answer rejected for arriving
   as text. Expected gain: +0.03 on this pilot's mean; zero cost.
2. **Keep the cost and latency position.** Aljure at 46% of Prime's cost with
   lower p50 and p95 is the best-replicated advantage in the repository (now
   five Sonnet and Opus plans in the same direction). Do not trade it for
   accuracy fixes that add calls.
3. **Pairs: user-set selection, not pair generation.** All three Pairs losses
   came from choosing the user set; the pair list from the chosen set was right.
   A verification step that re-checks each selected user against the condition
   in SCI (one evaluation, no model call) is the cheapest candidate.
4. **SCI surface: `subs` on nil and `.indexOf` on vectors.** Three of four
   Aljure tool errors are surface friction already seen in A1c. Add the
   `safe-subs` helper and allow `.indexOf` on persistent collections in the
   assisted prelude (`SCI_EXECUTION_CONTRACT.md`).
5. **128K is where both harnesses fail the same way**: keyword heuristics for
   topic and NLI labels. Improving that needs the model to read, not the
   harness; test it with Opus before building anything.
6. **Sizing Phase B.** Per-task cost under $0.07 for either arm at every
   length, so the LongBench Pro held-out (60 contexts, 144 arms) is about $8–12
   at Sonnet rates, not $12–25. σ_c from this pilot: synth8 contexts gave
   differences {−0.5, 0, 0, 0, +0.25, −0.1}, so σ_c ≈ 0.25 at 8K; 49 contexts
   detect Δ = 0.10.

## 8. Files

- `var/h2h-20261104/run-1/results.json`, `report-as-run.json`, `report.json`,
  `plan.json`, `preflight.json`, `authorization.json`; hashes in the evidence
  manifest.
- Host policy: `gate-1793815339.json` (refused, swap), `gate-1793815502.json`
  (admitted), `monitor-h2h-20261104-130502.jsonl`,
  `summary-h2h-20261104-130502.json`, `launch_h2h_when_clear.sh` and its log,
  `run_guarded.py`, `host_gate.py`, `host_monitor.py`.
