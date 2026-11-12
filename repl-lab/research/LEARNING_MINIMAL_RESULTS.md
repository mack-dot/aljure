# Minimal autonomous executable-learning result — 2026-11-02

**NO-GO under the frozen development rule.** All six tasks were correct, but the
model never invoked the retained skill on the three unseen routing tasks.
Acquisition, validation, promotion, and cold-restart retention worked in this
live run. Autonomous executable reuse did not.

The user explicitly approved this six-task run and its $6 aggregate
API-rate-equivalent cap before any inference. The two runner phases completed
under the same frozen source and plan. No task was rerun, no threshold changed,
and no held-out task was accessed. Original historical results are unchanged.

## Frozen identity

| Item | Exact value |
| --- | --- |
| Safety commit | `4f7ee0014f1d80eee33978b063086a8e4279c514` |
| Execution commit | `3eeed084d6cb1c19e3c9d1dda6c9047b3030db59` |
| Plan SHA-256 | `036adfd5b0d2e7029c7cba3490ed2fea184466cfc5fb58bb8021ab9e0feafb9b` |
| Suite SHA-256 | `1b387a7078376a9eadb8d9f4748569bf4bcf2157ba48a0d8680f6c9082c36a0a` |
| Panel SHA-256 | `1ada5d23ba9ed609f9e3987afa1a9cee453c50bf3b2358cf17ff8a0fcc26b1a1` |
| Runtime SHA-256 | `b2976e328fb60e9266908ed7d6b0d8a701a6f8691e69a75193db6be77d2bfc14` |
| Config SHA-256 | `db44ced74beb03400acd183ee9b2c4915eb0e9bfde3c919b5efc61f28618886a` |
| Protocol SHA-256 | `da28b6de00de3ad90d05fa420f4f0df04051ff2fe78c3e3729ee13ad3812c8b0` |

Full source, image and archive hashes are in
[freeze.json](evidence/learning-minimal-freeze-20261102/freeze.json).
The worker image is archived outside Git. Preflight returned `ready: true`,
zero blockers and zero model calls. Credential expiry metadata was checked
without printing the credential. The source checkout remains detached and clean.

## Preregistered criteria and observed evidence

| Criterion | Result |
| --- | --- |
| All six tasks attempted; complete accounting and safety evidence | Pass |
| Model-authored proposal validated and promoted before restart | Pass: task 1 |
| Same committed library pin retained on all tasks after restart | Pass |
| Prior skill invoked and a valid routing label returned on each of tasks 3–5, with correct final answers | **Fail: zero invocations on all three** |
| Incompatible task correct, artifact refused, no prior-skill call | Pass: task 6 |

The model made two proposals. Task 1 proposed `route-hold-rules`. It classified
all 36 admitted validation records correctly, with no candidate error. Despite
its name, the candidate decided all routing labels. Promotion committed code
hash `4a2419a7e967b76d4510d79c28a8c6578990cf8f902ef539c08900b236f46236` into library
pin `f273cf89770402469f31d549a51c7c25a5d955940706b202565fdd3adc5b2c88`.

Task 2 proposed `route-full-rules`. It also classified 36/36 validation records
correctly, but added no correct panel record. The controller rejected it with
`insufficient-panel-gain` and kept the prior pin. This rejection is retained.

After task 2, the first runner exited. A new process resumed the same library.
Tasks 3–5 each recorded that the artifact was available, but none recorded an
artifact invocation. Their task tools reconstructed the count logic instead.
Task 4 first tried `(source route-hold-rules)`. SCI rejected `source` as an
unresolved symbol. That is one observed interface problem; it does not establish
the cause of non-use on the other tasks. Task 6 refused the artifact as
inapplicable and solved the parity task separately.

## Measurements

| Metric | Recorded value |
| --- | --- |
| Exact task success | 6/6 (100%) |
| Model requests | 21, including 2 acquisition requests |
| Known model cost, including acquisition | $0.0812073 API-rate-equivalent |
| Cost per successful task | $0.01353455 |
| Acquisition cost | $0.025166 |
| Unknown reservations | $0; accounting complete |
| Candidate validation time | 8.7832 seconds |
| Full promotion-stage time | 15.9754 seconds, including validation and process overhead |
| Task latency p50 / p95 | 16.5016 / 22.5014 seconds; excludes the separate promotion stage |
| Tool results | 19; 17 successful, 2 errors, 0 missing |
| Tool success rate | 89.47% |
| Proposals / promotions | 2 / 1 |
| Successful post-restart reuse tasks | 0/3 compatible tasks |
| Correct reuse tasks per acquisition dollar | 0 |

| Task | Role | Answer | Correct | Requests | Cost USD equivalent | Seconds |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Acquire: hold count | 31 | Yes | 4 | 0.0278466 | 22.501 |
| 2 | Acquire: expedite count | 20 | Yes | 4 | 0.0180485 | 22.229 |
| 3 | New records: retry count | 17 | Yes | 3 | 0.0101508 | 13.336 |
| 4 | New records: hold count | 51 | Yes | 4 | 0.0101815 | 16.502 |
| 5 | New records: expedite count | 18 | Yes | 3 | 0.0067047 | 15.602 |
| 6 | Incompatible parity count | 12 | Yes | 3 | 0.0082752 | 21.297 |

Both tool errors remain counted. Task 4's source-inspection error is described
above. Task 6 requested a substring past the end of its context. Both tasks
recovered within their original task budgets. There were no unresolved provider,
isolation, cleanup or promotion-stage failures.

The approved limits were $5 per task and $6 aggregate, 12 calls and 300 seconds
per task. The full next-task cap was reserved before dispatch. These caps are
not the subscription invoice; actual subscription billing and local compute
dollar cost remain unknown. The earlier $0.50 task / $3 aggregate draft failed
offline reservation admission before any model call. It is preserved in the
verification archive and was not used for live execution.

## Verification, preservation and limits

The safety commit makes promotion crashes stop before another task. Tests cover
crashes before and after a write, at the restart boundary and on the final task.
They verify that prior pins, orphan files and failure records survive, and that
an interrupted run cannot resume as a normal cold restart. The final development
source passed 44 Python tests and all seven offline verification stages. The
unchanged Clojure source previously passed 204 tests and 3,104 assertions.

The preparation check confirmed disjoint record texts and feature tuples across
all tasks and validation windows, including after identifiers are removed.
“Unseen” is relative to this live development trajectory. The generator and
rules were known during implementation. This is a single synthetic development
run with no control arm. It cannot establish held-out generalization, a learning
advantage, or statistical superiority.

[The result archive](evidence/learning-minimal-results-20261102/index.json)
contains the raw responses and receipts, task events, proposals, promotion
decisions, answers, safety records and reports. All 200 original run files have
recorded hashes; SQLite files remain in the original checkout. Archive copies
do not replace the original files. The prior 2,437 Pilot 1b files and 533 audited
thesis files still matched their saved hashes before this run.

The remaining mechanism problem is use of an available skill after restart.
The source-inspection failure and the artifact's name/interface are development
evidence for a future revision. No repair was applied to this run, and no further
paid experiment or held-out evaluation was started after this NO-GO.
