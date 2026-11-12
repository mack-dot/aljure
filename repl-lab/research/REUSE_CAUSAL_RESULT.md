# Causal reuse study result: reuse-only-when-necessary

Run 1 of the frozen plan `1d5a4db2f5f730eed81664700a4efad64f58daba326a6aa47d2a055b2b0e4546`
(protocol `REUSE_CAUSAL_PROTOCOL.md`, version `reuse-causal-development-v1`, suite
`7101a245…`, retained library `f273cf89…`) executed live on 2026-11-04 from 10:07:16 to
10:11:46 local time against source commit `ce64874`. The owner invoked the exact plan
hash through the host launcher (`run_guarded.py causal --approve <hash>`); two earlier
invocations were refused by the host gate (another project's container, swap above 90%,
credential under one hour) and dispatched no inference. The frozen criteria, scorer,
gold and library are unchanged. The automatic development gate reports
**COMPLETE-PENDING-ATTRIBUTION-REVIEW** with outcome pattern
**`reuse-only-when-necessary`**. The trace review in section 3 confirms that pattern.
Raw traces remain in `var/reuse-causal-20261103/run-1`; the committed copy is
`evidence/reuse-causal-20261104/` (it omits raw transport bodies and sqlite stores).
Every number below is a live model result unless marked otherwise.

## 1. Official gate

All twenty attempts completed with exact accounting, cleanup evidence, and no
failure. Eighteen answers were correct; the two wrong answers are both C0 withheld
cases, which is the designed guess floor. No negative control executed the retained
classifier, and none was wrong in a library arm.

| Endpoint | Value |
| --- | --- |
| B eligible tasks at level 8 (used) and correct | 0 of 3 |
| A eligible correct / B eligible correct | 3 of 3 / 3 of 3 |
| C withheld correct / C0 withheld correct | 2 of 2 / 0 of 2 |
| C withheld levels reached | admitted, used |
| C withheld correct through execution (level 8) | 1 |
| C withheld correct without execution | 1 |
| C sufficient correct / C0 sufficient correct | 1 of 1 / 1 of 1 |
| Negative-control executions, all arms | 0 |
| Negative-control failures, library arms | 0 |

Frozen mapping: no B task reached level 8, and one C withheld task reached level 8 and
was correct, so the pattern is `reuse-only-when-necessary`. Discovery works; selection
is governed by need. With one trial per cell this is a diagnosis, not a statistical
claim.

## 2. Arms

| Arm | Configuration | Tasks | Correct | Known cost $ | Requests | Wall s | First-request tokens, mean | Tool schema bytes | Levels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | stateless, full rules | 5 | 5 | 0.0525 | 15 | 58.9 | 3338 | 3090 | no-library 5 |
| B | library, full rules | 5 | 5 | 0.0526 | 16 | 72.3 | 4188 | 4576 | admitted 4, exposed 1 |
| C | library, withheld rule | 5 | 5 | 0.0515 | 17 | 69.5 | 4201 | 4576 | admitted 3, exposed 1, used 1 |
| C0 | stateless, withheld rule | 5 | 3 | 0.0619 | 18 | 68.6 | 3776 | 3090 | no-library 5 |

Total: $0.2185 known model cost, $0 unknown reservations, 66 of 240 allowed requests,
272 s wall, all under the $6 ceiling. Every task took 3 to 5 requests. Costs include
every request and cache charge.

Parity of information (A against B): same correctness, same cost to four decimals, one
more request in B, 13 s more total wall time in B, and about 850 more first-request
tokens in B. The library adds prompt and tool-schema bytes and, when the task text
states the rule, buys nothing.

## 3. Trace review

Every tool call of all twenty tasks is listed in `evidence/reuse-causal-20261104/run-1/trace-review.json`.
Findings that bear on the attribution:

**B eligible (tasks 1, 2, 3; attempts 02, 03, 06).** The applicability predicate
preloaded `route-hold-rules` in all three. The model read the task text, then wrote a
fresh regex-and-count expression that restates the three rules, and answered. Zero
`artifact_inspect`, zero `artifact_call`, zero evaluations naming the export. This
repeats the interface A/B of 2026-11-03 (`REUSE_INTERFACE_RESULT.md`): across both
studies the model has chosen the retained artifact in 0 of 6 eligible tasks when the
rule is in the text.

**C withheld, task 7 (attempt 13-C), level 8.** The task text omitted the
retry-versus-hold rule. The model's third evaluation was
`(count (filter #(= "hold" (route-hold-rules %)) (filter #(re-find #"^Date" %) context-lines)))`.
The worker's invocation log records 52 counted calls of code hash `4a2419a7…`
(`route-hold-rules`) over the 52 record lines, 52 non-nil returns with values hold,
expedite and retry, and the evaluation at call-sequence 17 returned 27, the delivered
and correct answer. The count is computed over the task's own records, not a literal,
so there is no counter manipulation. This is genuine executable reuse of a retained
skill under necessity, with real task-data use.

**C withheld, task 6 (attempt 12-C), level 3, correct.** The same withheld text. The
model did not execute or inspect the artifact. It wrote fresh code with the predicate
`attempts >= 3`, which is not in the task text. The only place that threshold appears
in the model's input is the inventory entry's model-authored summary:
"blocked=yes→hold; age_minutes>=60→expedite; attempts>=3→retry; else hold". The
paired stateless attempt (11-C0) saw no inventory, guessed a different threshold and
answered 4 against gold 6. So this correct answer depended on the library through its
description, not its execution. The frozen levels credit this only as "admitted"
(textual similarity never rises above level 5), which is the protocol's intended
conservatism; the result is recorded here as description-mediated reuse.

**C0 withheld (attempts 11, 14).** Both wrong (4 against 6, 32 against 27). The
necessity manipulation worked: the withheld rule was not recoverable from the text.

**Sufficient (attempts 15-C0, 16-C).** Both correct from the restated rules; the C
attempt preloaded the artifact and did not use it, as intended for a case decidable
without it.

**Parity controls (07-B, 17-C, 08-A, 18-C0).** The predicate refused the artifact
(`inapplicable`); all four answers correct with fresh code. **Routing v2 controls
(10-B, 20-C, 09-A, 19-C0).** The predicate preloaded the old classifier on the changed
rules, and the model wrote the new rule in fresh code without executing it; all four
correct. The predicate's text-literal matching is the known limitation recorded in the
protocol; it did not cause a wrong answer here.

## 4. Answer to the three possibilities

The study was framed to separate three explanations (owner's framing, 2026-11-03):

1. **The agent cannot recognize when the skill applies.** Not supported. In every
   library-arm task whose text carried the rule fragment, the artifact was admitted
   and listed in the first request with its call syntax, and in both withheld tasks
   the model found and used it (once by execution, once by description) when it
   needed the rule. Recognition did not fail in this sample.
2. **The agent recognizes it but prefers to reimplement.** Supported for the
   full-information case. With the rule in the text, B reimplemented 3 of 3 times
   here and 3 of 3 times in the interface A/B. The retained skill offered no saving
   the model valued: the reimplementation was one short expression, one request,
   and cost the same as A.
3. **The agent selects and executes the retained skill, improving cost, latency or
   quality.** Observed once, under necessity. Attempt 13-C executed the skill and was
   correct where its stateless pair (14-C0) was wrong; within that single pair it cost
   $0.0122 against $0.0169, four requests each, 16.0 s against 15.2 s. The quality gain
   is real for that pair; the cost and latency figures are one trial and carry no
   inference.

Engineering implication, following the owner's rule: the failure is not retrieval or
applicability signalling, so improving those would address nothing observed. The lever
is the economics of reuse. The model reuses when reuse is the only route to the answer
and reimplements when reimplementation is one cheap expression. Whether it reuses when
reimplementation is expensive but possible is the untested case.

## 5. Host and isolation record

Launched through host policy v1 (`evidence/reuse-causal-20261104/host-policy/`). Gate
record `gate-1793804832.json`: admitted with one warning (one-minute load above the CPU
count). The refused attempt an hour earlier (`gate-1793804743.json`) measured 95% swap
after the probe woke the Docker VM; the owner quit the browser, swap fell to 83.7%, and
the next gate passed. During the run (44 samples at 5 s): swap 78.2% to 83.7% of a
6 GB swap file, free host memory 84 MB to 1250 MB, one-minute load 4.7 to 12.4, Docker
Desktop session unchanged, no other project's container at any sample. Docker events:
20 worker containers, each create, start, die with exit 0, destroy; no OOM kill. Worker
audits: 20 containers, startup 685 / 762 / 1233 ms (min / median / max), no supervisor
error, 20 cleanups confirmed; gateway cleanup `ok` on all 20 tasks; no orphan after the
run. Per-task Docker state checks passed before and after every task.

## 6. Limitations

- One trial per cell. Nothing here is a rate; the three-favorable-pair McNemar
  threshold in the protocol was not reached and not needed for the diagnosis.
- The inventory summary carries the rule text. The description path (12-C) is a
  property of model-authored summaries and could not be separated from execution in
  this design; an arm with summaries withheld would be needed to separate them.
- The applicability predicate matches text literals, so it admitted the artifact on
  withheld and Routing v2 texts. No wrong answer followed, but admission is not a
  measure of recognition by the model.
- Single model (pinned Sonnet 5.5 subscription transport), development cases only,
  no held-out inputs. Supports no claim of capability over a comparably informed
  baseline, as the protocol states.
- The host ran at 78% to 84% swap with free memory as low as 84 MB. No worker or
  Docker failure occurred, but the latency figures were measured on a saturated host.

## 7. Smallest next experiment (proposed, not frozen)

**Reuse economics, paired A against B.** Keep the retained library, predicate and
interface fixed. Generate cases whose rule is stated in full but is long enough that a
correct fresh implementation needs at least three evaluations or a multi-clause
expression (for example six ordered clauses over four fields), while the retained
skill answers in one call. Endpoints: B eligible level-8 rate, requests, cost and wall
time against A; same negative controls; same levels and trace review. Add one arm with
inventory summaries replaced by names and hashes only, to separate execution reuse
from description reuse. Twenty to thirty attempts at the observed $0.01 per task is
about $0.30. If B still reimplements when reimplementation is expensive, the interface
economics are not the lever either and the retained-skill mechanism should be judged
on necessity cases alone. If B switches to the skill, reuse is an economics question
and the harness should make the skill the cheap path.

## 8. Files

- `var/reuse-causal-20261103/run-1/results.json` sha256 `db0dbace…`; `report.json` `2be765a1…`; `authorization.json` `a89a234c…`; `trace-review.json` `7f1e2983…`.
- `evidence/reuse-causal-20261104/MANIFEST.json` lists every archived file with its hash.
- Host policy files as archived: `host_gate.py` `29841b6a…`, `run_guarded.py` `0f66b8f9…`, `host_monitor.py` `102e1265…`.
