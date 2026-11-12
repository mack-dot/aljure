# Controlled executable-learning study — design v1, 2026-11-02

This preregisters the study design before held-out task inspection. It is not an
executable or approved paid plan. The development lifecycle must pass first.
Adapters, dataset revision, exact manifests, and isolation proofs must then be
bound into a separate execution freeze. No held-out task content was opened to
write this design. Any design change before deployment needs a versioned record.

## Primary question and controls

Compare the same model, task tools, budgets, and presentation in three arms:

| Arm | Cross-task state |
| --- | --- |
| A | None; stateless execution |
| CS | Exact cache of previously computed inputs/results and exact task-signature functions; no generalization |
| ES | Model-proposed executable skills admitted by fixed independent development validation |

CS and ES receive matched structured acquisition framing and the same opportunity
to decline. All proposal, validation, retrieval, and fallback costs count. An
artifact named in a prompt does not establish reuse; require actual code-hash
invocations. A text skill summary alone does not count as executable learning.

The earlier requested Prime and trajectory-memory arms remain extension controls:
Prime with its pinned native memory/skills; Aljure with prior acquisition
trajectories but no retained executable library. Freeze them only after tool
parity and memory boundaries can be demonstrated. Do not mix their incomplete
results with the primary three-arm contrast or claim an Aljure/Prime win.

## Held-out source and separation

Use the official SkillEvolBench acquisition/deployment role distinction. Its
public description identifies 180 tasks in 30 procedural families: canonical,
enriched, and variant acquisition roles, then context-shift, adversarial, and
composition deployment roles. See the [project specification](https://skillevolbench.github.io/)
and [official repository](https://github.com/AIoT-MLSys-Lab/SkillEvolBench).

Inspect code, schemas, and acquisition assets first. Have the import step seal
deployment assets and verifier inputs without displaying their contents. Record
upstream commit, bytes, hashes, role IDs, provenance, and an exposure ledger.
Public availability means pretraining contamination cannot be excluded.

Use all 30 families, selected by manifest membership rather than outcomes.
Run three independent model replicates per arm. Within each family use the three
acquisition roles in their canonical order, freeze state, start new processes,
then run its three deployment roles. No updates or evaluator feedback during
deployment. Reset mutable task state for every attempt.

For the primary causal study, isolate libraries by family. No state crosses
families, arms, or replicates. This is a declared deviation from the upstream
environment-wide library protocol. It supports 30 independent family blocks and
tests within-family cross-task learning. It does not test cross-family curriculum
learning. Report composition limitations caused by that scope explicitly.

Verify task/record identity separation from development and acquisition where
the task format permits it. Exact cache matches must be reported. A distinct task
ID alone is not evidence of distinct contents. If independent validation tasks
for a skill cannot be obtained from acquisition/development assets, block that
skill or family as an integration failure; never validate on deployment assets.
Retain such failures in the full intended-sample accounting.

## Endpoints and statistical rules

Primary endpoints are deployment success and total model cost per successful
deployment task. Charge acquisition and all unsuccessful attempts in the cost
numerator. Also report deployment-only cost, worker validation/runtime seconds,
latency p50/p95, tool errors, unknown reservations, exact-cache hit rate, proposal
yield, promotion yield, applicable-skill activation, successful invocations,
reuse per acquisition dollar, and performance by deployment role.

There are 90 deployment tasks per arm/replicate and 180 total tasks per
arm/replicate; the full primary design is 1,620 task attempts. Replicates and the
three related deployment roles do not create additional independent families.
Keep all failures in the denominator. Report missing/unattempted rows separately;
an incomplete design supports descriptive results only.

Compare ES to A and CS with paired family blocks. Average repeats within each
family first. Use 20,000 paired cluster-bootstrap resamples of the 30 families,
seed 20261102. Recompute aggregate cost/success ratios within each resample.
Zero-success ratios remain infinite. Report 99% intervals for each of the four
primary contrasts (two accuracy differences and two cost ratios); these are
conservative intervals for the four comparisons. Report the raw per-family and
per-replicate values so instability remains visible.

An accuracy-superiority statement requires a positive lower interval bound for
the specified comparison. A cost advantage requires an upper cost-ratio bound
below 1 and an accuracy-difference lower bound above -0.02. Call that a cost
advantage within the stated accuracy tolerance, not general superiority.
If intervals overlap the thresholds, the result is inconclusive. A larger study
would require a new protocol and untouched tasks, not repeated looks at this set.

## Frozen decisions and remaining execution gates

Before deployment, freeze source, model, prompts, tool schemas, environment
images, input manifests, development validators, skill-selection rules, arm
state boundaries, replicate schedule, and the analysis code. Suggested fixed
execution ceilings are $5 per task and $150 aggregate API-rate-equivalent, with
the full next-task reservation required before dispatch. These ceilings are
design limits, not spending approval or a reliable cost estimate. If the complete
design cannot fit, revise its size using development cost evidence before any
deployment access, then freeze the new version.

No semantic adapter for these general service/file tasks is currently proved for
Aljure's classifier-only acquisition path. Do not relabel the old 18-task OOLONG
suite as independent held-out data, substitute service-simulation scores, or
pretend the existing Prime service adapter exists. Implement only the minimum
adapter justified after the development gate. If this changes the learned
artifact class, demonstrate its lifecycle on development tasks again first.

After all gates pass, request a separate approval of the exact execution plan.
Do not inspect deployment failures to alter prompts, validators, schemas, or
skills. Preserve the first-run result and every failure; publish limitations and
negative or inconclusive results alongside successful cases.
