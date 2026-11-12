# Frozen development protocol: does the cost of reimplementation decide reuse?

Version: `reuse-economics-development-v1`. No live run is authorized by this file.
Approval must name the exact generated plan hash. The causal study of commit
`0efefde` (`REUSE_CAUSAL_RESULT.md`, pattern `reuse-only-when-necessary`) is not
re-scored here. No held-out inputs are used or opened.

## Question

Across the interface A/B and the causal study the model reimplemented the
retained rule in 6 of 6 eligible tasks when the task text stated it, and the
reimplementation was one short expression. The causal study's engineering
implication was that the lever is the economics of reuse, and that the untested
case is a rule that is possible but expensive to reimplement. This protocol
tests that case. It also separates execution reuse from description reuse: in
the causal study one correct withheld answer took the rule from the inventory's
model-authored summary rather than from executing the artifact.

## Arms

Three configurations run on one case group. They differ only in the
`aljure_contract` block. `stateless` has no library (`{}`). `library` adds the
pinned retained library and `skill_interface: "inspect-v1"`. `library-names`
adds the same library with `skill_interface: "inspect-v1-names"`. Everything
else (model, transport, thinking, effort, rates, limits, images, task limits)
is identical, and all three carry the explicit default execution contract.

- **A**: stateless, long rule. The task text states the full rule.
- **B**: library, long rule. The retained artifact, its inventory with the
  model-authored summary, `artifact_inspect` and `artifact_call` are available.
  Using them is optional.
- **BN**: library with summaries withheld, long rule. The inventory lists each
  artifact's name, arity, hash, call syntax, admission and `summary-withheld
  true`; inspection pages omit the summary too. The verified source, reached
  only through `artifact_inspect`, is the only description of the function.
  Tools, pages, authority and limits are otherwise those of inspect-v1.

`inspect-v1-names` is the one runtime change since `0efefde`: the same
interface with the summary omitted from the inventory and from inspection
pages (`skill_interface.clj`, `external_task.clj`). The B configuration's
prompt and tools are byte-for-byte the causal study's library configuration
on the same text.

## The long rule

The eligible cases state Routing v1 as six ordered clauses (`LONG` in
`benchmark/reuse_economics.py`): blocked=yes means hold; otherwise
age_minutes>=60 means expedite; then four clauses over age_minutes>=30 or <30
crossed with attempts>=3 or <3. On every one of the 2,400 possible records the
six clauses give the label of the retained three-rule classifier
(`test_reuse_economics` checks the full domain), so the retained skill
`route-hold-rules` answers each eligible case in one call, while a correct
fresh implementation is a six-clause expression, or the recognition that the
six clauses collapse to three. The text keeps the retained applicability
predicate's three literals (`blocked=`, `'hold'`, `age_minutes>=60 means
expedite`) so the unchanged predicate admits the artifact. It names no library,
tool or function.

The manipulation is clause count and precedence, not evaluation count: the
fresh implementation remains one expression. If the model still reimplements,
the test says that a sixfold longer rule is not enough to make the skill the
cheap path; it does not say that no rule would be.

## Inputs and schedule

`benchmark/reuse_economics.py` generates eight cases with seed 2026110401: six
eligible long-rule counts (retry 48, hold 56, expedite 44, retry 52, hold 40,
expedite 60 records), one parity case (28 records, new code range), and one
changed-rules case (48 records) whose text states Routing v2 in the same
six-clause form, keeps the predicate's literals, and whose gold differs from
the retained classifier's count by construction. All routing feature tuples
and record texts are disjoint from every earlier development record, panel
record, reuse-interface record and causal record, and from each other.

Twenty-four attempts: every case in all three arms, the arm order rotating
with the case index (A B BN, B BN A, BN A B, ...). Each attempt starts a new
JVM, conversation and isolated worker. Only the fixed retained library
persists. No retries, replacements, resumption, extra seeds, or edits after
outcomes. Every failed or unattempted case stays in the denominator.

## Attribution levels

The eight levels of `REUSE_CAUSAL_PROTOCOL.md` apply unchanged, computed by the
same `attribution` function: library-present, exposed, admitted, inspected,
attempted, executed, useful, used. Textual similarity never establishes a level
above 5; copying inspected source into fresh code is at most level 4; the
automatic report is provisional until the trace review confirms task-data use
and the absence of counter manipulation. Each attempt also records the number
of evaluations, evaluation errors, inspections and artifact calls from the tool
results, as the measure of fresh computation.

## Endpoints

Primary: number of the six B eligible tasks with level 8 and a correct answer.
Secondary: the same count in BN; eligible tasks inspected in B and BN;
correctness, requests, evaluations, cost and wall time of the eligible tasks in
A, B and BN; first-request prompt tokens and tool-schema bytes per arm.
Negative transfer: parity must refuse execution and stay correct in B and BN;
changed rules must stay correct in B and BN with no execution of the old
classifier. Costs include every request, inspection, error and cache charge;
unknown reservations are kept.

Frozen outcome mapping, computed by `summarize`:

- `reuse-under-long-rules`: at least 3 of the 6 B eligible tasks reach level 8
  and are correct. Reuse is an economics question; the harness should make
  the skill the cheap path.
- `occasional-reuse-under-long-rules`: 1 or 2 of 6. The lever exists but is
  weak at this length; a stronger manipulation or a larger sample is needed
  before any design decision.
- `reimplementation-regardless-of-length`: 0 of 6. A sixfold longer rule does
  not change the choice; the retained-skill mechanism should be judged on
  necessity cases alone.

Summary effect, recorded beside the pattern: `none` when neither B nor BN
reaches level 8 on an eligible task; `summary-mediated` when B reaches it on
more eligible tasks than BN; `execution-independent-of-summary` otherwise. A
BN task that reaches level 8 can only have learned the function's meaning from
its name, its call syntax or its inspected source, so this separates what the
summary buys.

- `NEGATIVE-CONTROL-FAILURE`: any negative control executes the classifier in
  any arm, or is wrong in a library arm. No pattern is assigned.
- `INCOMPLETE`: fewer than twenty-four complete, safe, fully accounted attempts.

None of these is a GO. The gate is `COMPLETE-PENDING-ATTRIBUTION-REVIEW` or a
failure; the pattern is a diagnosis to be confirmed by trace review. With one
trial per cell nothing here is a statistical claim; the three-of-six threshold
is a preregistered reading, not a test.

## Cost and safety

Same pinned Sonnet 5.5 subscription transport, adaptive thinking, medium
effort, rates, images and task limits as the causal study. No API fallback. At
most 12 requests per task, 288 across twenty-four tasks, 32768 output tokens
per request, 300 seconds per task, $5 per-task API-rate-equivalent ceiling, and
a **$6 hard aggregate equivalent ceiling**. Before each task, known cost plus
unknown reservations must leave the full $5 task allowance, so the run stops
before a new task once prior cost exceeds $1. The causal study cost $0.2185 for
twenty attempts at $0.0105 to $0.0124 per task; the expected total here is
about $0.30. Report new expenditure once; the $0.025166 historical acquisition
overhead is shown separately.

Before live execution: verify frozen source and protocol hashes, suite and
library bytes, all three configuration files, the exact SCI image, current
sandbox and artifact-path proofs, acquisition regression proof, subscription
relay proof, reuse relay proof, and the economics fixture proof. Require 6 GiB
free disk before each task. Refuse a pending Docker restart. Stop on
infrastructure, cleanup, accounting or source-integrity failures. Do not
repeat a paid attempt after a runner crash. No reward, instruction to prefer
reuse, automatic application, benchmark-specific instruction, or privileged
shortcut to the answer is added in any arm. The withheld-summary inventory
says only that summaries are withheld on this task.

Commands are `python3 -m benchmark.reuse_economics prepare|plan|preflight|run`
and `python3 -m benchmark.reuse_economics_fixture --suite ... --out ...`. The
run command requires `--authorize-subscription-plan <exact-new-plan-hash>`
after explicit approval, through the host launcher
`python3 var/host-policy-20261103/run_guarded.py economics --approve <hash>`.
Freeze from a clean committed checkout; archive results in a separate later
commit.
