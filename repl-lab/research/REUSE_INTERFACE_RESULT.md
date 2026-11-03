# Reuse interface A/B result: NO-GO

Run 3 of the frozen plan `40db9df9422121aa53779bb27461076858530f18078fe1510803b0dd85f45ce4`
executed on 2026-11-03 from 12:32:54 to 12:36:13 local time against source
commit `08bb759c44e8ab7bd6e3cfd9e6ff48b2560ccf21`. The protocol is
`REUSE_INTERFACE_PROTOCOL.md`. The frozen criteria are unchanged. The
automatic development gate reports **NO-GO**. Attribution review below
confirms that result. Raw traces remain in `var/reuse-interface-20261103/run-3`.
The committed copy is `evidence/reuse-interface-ab-20261103/`; it omits
signed assistant reasoning blocks, sqlite stores and raw transport bodies.

## 1. Official gate

NO-GO. All ten attempts completed with exact accounting and cleanup evidence.
All five repaired-arm answers were correct. Zero of the three repaired-arm
eligible tasks recorded a source-attributed invocation. The GO rule requires
at least one. Neither negative control executed the retained classifier.

## 2. Inspections and invocations

The repaired arm made zero `artifact_inspect` calls and zero `artifact_call`
calls across all five tasks. It never referred to `route-hold-rules` in any
`repl_eval` source. The interface was present: every repaired-arm first request
listed seven tools and the inventory with hash
`8a58405a8c92d07f141b74efe0f8f532b0b2aae617c3a2ca96006752bd32d959`,
call syntax, and `invocation-allowed true` on eligible tasks.

The baseline arm recorded one invocation, on task 1 (reuse-dev-1), through the
preloaded path at call-sequence 7. The executed code hash was
`4a2419a7e967b76d4510d79c28a8c6578990cf8f902ef539c08900b236f46236`. The source
was `(count context-lines) (take 5 context-lines) (route-hold-rules (first context-lines))`.
The result shown to the model was `nil`. The model then wrote inline regex
counting and answered from that. Under the frozen primary endpoint this counts
as a baseline invocation. The attribution review classifies it as a probe on a
non-record line whose return value was not used in the answer. It is reported,
not reinterpreted.

## 3. Paired outcomes

Cost is API-rate-equivalent subscription usage from gateway usage records.
Latency is wall seconds per task including worker start and cleanup.

| Case | Kind | Arm | Correct | Answer | Cost USD | Requests | Seconds | Inspect | Invoke | Tool errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reuse-dev-1 | eligible | baseline | yes | 7 | 0.01181 | 4 | 28.7 | 0 | 1 (probe, nil) | 0 |
| reuse-dev-1 | eligible | repaired | yes | 7 | 0.01571 | 4 | 20.6 | 0 | 0 | 1 |
| reuse-dev-2 | eligible | baseline | yes | 24 | 0.00732 | 3 | 16.1 | 0 | 0 | 0 |
| reuse-dev-2 | eligible | repaired | yes | 24 | 0.01141 | 4 | 21.4 | 0 | 0 | 1 |
| reuse-dev-3 | eligible | baseline | yes | 14 | 0.00675 | 3 | 17.0 | 0 | 0 | 0 |
| reuse-dev-3 | eligible | repaired | yes | 14 | 0.01076 | 4 | 21.8 | 0 | 0 | 1 |
| reuse-dev-4 | parity | baseline | yes | 10 | 0.00720 | 3 | 20.8 | 0 | 0 | 0 |
| reuse-dev-4 | parity | repaired | yes | 10 | 0.00912 | 3 | 17.4 | 0 | 0 | 1 |
| reuse-dev-5 | changed-rules | baseline | yes | 4 | 0.00725 | 3 | 15.8 | 0 | 0 | 0 |
| reuse-dev-5 | changed-rules | repaired | yes | 4 | 0.01172 | 3 | 16.2 | 0 | 0 | 0 |

| Arm | Correct | Known cost USD | Requests | Seconds | Eligible tasks invoked |
| --- | --- | --- | --- | --- | --- |
| baseline | 5/5 | 0.0403342 | 16 | 98.4 | 1 (probe) |
| repaired | 5/5 | 0.0587305 | 18 | 97.4 | 0 |

Total known cost was $0.0990647 of the $6.00 cap. Reserved unknown cost was
$0. Total provider requests were 34 of 120 allowed. No request failed. The
subscription invoice amount is unknown.

## 4. Voluntary reuse

No. The repaired arm never inspected or invoked the artifact. The baseline arm
probed it once and did not use the result. Every one of the ten answers came
from fresh inline Clojure written by the model.

## 5. Negative controls and transfer

Parity (reuse-dev-4): the controller refused preload in both arms with reason
`inapplicable`. Both answers were 10, correct. No invocation was attempted.
Changed-rules (reuse-dev-5): the controller admitted the artifact in both arms,
as the predicate design allows. Neither arm invoked it. Both answers were 4,
the v2 answer; the v1 answer would have been 30. No negative transfer occurred.
No unauthorized call was attempted anywhere in the run.

## 6. New limitations and confounders

- The model never touched the new tools, so this run cannot separate
  discoverability from selection. It shows only that the combined interface did
  not change behavior on these tasks.
- Four of five repaired-arm tasks began with `(subs ... 0 3000)` over fifteen
  context lines and failed with a range error, then retried without `subs`.
  No baseline task did this. The repaired prompt is longer and changed the
  model's first action. This added one request to each of those tasks and is
  the main source of the repaired arm's higher cost. It is unrelated to the
  artifact tools, but it is an interface side effect.
- The tasks restate the routing rules in context, and the inventory summary
  restates them again. Inline reimplementation took one expression. There was
  no accuracy or cost advantage to reuse, so the experiment cannot show whether
  the model would reuse when reuse matters.
- The primary endpoint counts any return from the retained code hash. The
  baseline probe shows that a nil-returning probe counts. The criterion is
  unchanged here; a future protocol should require decision use.
- Five cases, one model (claude-sonnet-5-5), one trial per cell. No statistical
  claim is possible.
- Two earlier launches of the same plan stopped before any inference: run-1 on
  Docker Desktop Resource Saver idling the engine, run-2 on an unset credential
  source. Their evidence is in `evidence/reuse-interface-ab-20261103/launch-attempts`.

## 7. Next experiment

Highest value: a necessity condition. Keep the same library, interface, and
control structure, but withhold the rule text from the task context so the
only verified route to a correct answer is the retained artifact, by
inspection or invocation. If the model still writes fresh code and gets the
answer wrong, selection is the defect. If it reaches for the artifact only
when necessary, the interface works and the current tasks were too easy to
show it. This needs a new preregistered protocol and approval; it is not
authorized by this record.
