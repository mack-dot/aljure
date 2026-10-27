# First real acquisition and transfer run

Status: provider path prepared and actual-worker rehearsal passed as **FIXTURE**.
The operator explicitly approved one real acquisition and transfer experiment on
2026-10-27 UTC ("yes rip it"). Execution status and outcomes are recorded in
`FIRST_LIVE_RESULTS.md`. No additional experiments are authorized by that approval.
This file does not enable inference. No new scheduler or controller is required.

The first Docker rehearsal exhausted the unchanged 120-second task limit before
any scripted model response. Large development traces made every controller
transaction expensive. The fix keeps immutable traces in separate records in the
same SQLite database. Query permissions, response bounds, task deadlines and SCI
isolation stayed unchanged during the successful rerun. See `PROGRESS.md` for the
failed attempt and rerun. Four acquisition tasks and six fresh-process evaluation
episodes completed with zero real model calls. This demonstrates plumbing only.

Question: can the fixed model create a reusable executable policy and a workflow,
have the controller independently accept them, and use the accepted computation
on new tasks after process and conversation reset?

Use the existing scheduling environment for this initial mechanism check. It is
supplementary research evidence, not OOLONG, a language comparison or a Prime win.
An accepted scheduling policy is skill acquisition. A changed workflow hash alone
does not establish improved orchestration. Report those outcomes separately.

## Fixed proposed configuration

- Model: `claude-sonnet-5-5`, using the operator's existing Claude subscription
  login. Returned ID must match. The direct Anthropic API remains an optional
  path with privately configured credentials; do not switch providers mid-run.
- Rates: operator-specified $2/M input and $10/M output. With the subscription,
  caps are standard API-rate equivalents, not subscription invoice amounts. Cache
  is disabled in the bounded CLI transport and unexpected cache usage is rejected.
- Approved caps: acquisition $15, held-out $10, cold boot $10; total $35.
  Keep the earlier smoke's full $1 allowance inside acquisition. The first new
  acquisition command therefore uses $14, as recorded in `config/live-proposal.edn`.
  Do not recycle unused smoke allowance or uncertain reservations into this run.
- Acquisition: one trajectory, three learning tasks per arm, six development cases.
  Frozen and evolving arms get identical capabilities and equal nontransferable
  task budgets. Both can construct and use temporary code. Only evolving retains
  approved artifacts between tasks. Root and child calls share each task's cap.
- Evaluation: eight paired held-out tasks, then eight separate paired cold-boot
  tasks, including declared distribution shifts. Each phase has its own cap.
- Actual SCI isolation gate, existing memory/CPU/process/expression limits, fixed
  source and split hashes, and the current promotion rule remain mandatory.
- Live acquisition allows 300 seconds per task, equally for both arms. This was
  set before any real acquisition: the successful no-inference rehearsal used
  about 109 seconds for each task that validated a candidate, leaving only
  11 seconds of the former 120-second allowance for model requests. SCI still
  allows 10 seconds per expression and 120 seconds per worker session. Final
  evaluation keeps its 120-second task allowance. Call, token and dollar caps
  are unchanged. The recorded rehearsal used the stricter 120-second task cap.
- Unknown provider outcomes retain reservations. Failed tasks remain failures.
  No automatic retry, model switch, threshold change, or tuning on final cases.

The learner sees permitted observations and development feedback. The controller
keeps final and cold-boot worlds outside the broker. Freeze source before
acquisition and keep it frozen until both evaluation phases finish.

## Commands after explicit approval and private credential configuration

From `repl-lab`, using the existing private Claude login:

```sh
source var/worker.env
export INPUT_USD_PER_M=2 OUTPUT_USD_PER_M=10
export INFERENCE_PROVIDER=claude-subscription
make evolve LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=14
```

Use the actual export path printed by acquisition for both later commands:

```sh
make evaluate LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=<printed-export-path> PROFILE=heldout
make cold-boot LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=10 EXPORT=<printed-export-path>
```

The angle-bracket value is a placeholder, not a literal shell argument. Inspect
acquisition evidence before using final splits. If the model creates no accepted
candidate, report that result. Do not label developer fixtures or an unchanged
initial library as learned code. The earlier subscription smoke does not authorize
this run. The reused subscription adapter now supports an explicit learning and
evaluation scope. It retains the same model, rates, maximum output, isolation
checks, per-request reservation ceiling and no-retry rules. The three live
commands still require explicit `LIVE=1` and positive phase caps.

The EDN learner prompt now documents all 16 existing broker operations, including
artifact inspection, subtree hashes, structural patches and approved invocation.
Its workflow example specifies the active workflow parent and policy dependency.
All 17 command examples pass the broker schema check; the workflow shape passes
artifact validation after replacing placeholder hashes. This is **FIXTURE**
contract validation. Whether a real model can use it effectively remains untested.

## Required outcome card

Report yes/no/unknown with artifact and trace references for each item:

1. A real model authored executable code and a workflow proposal.
2. Independent development checks accepted or rejected the proposal.
3. A strategy field changed: context selection or delegation, separately from policy.
4. The accepted policy/workflow actually ran on unseen inputs.
5. The same approved computation ran after a new process and conversation.
6. Retention improved verified outcomes or inference cost against frozen conditions.
7. A compatible removal test reduced the measured benefit.

Current promotion judges scheduler behavior, not workflow inference cost. This
first run can reveal a mechanism or a failure; it cannot isolate the cause of a
whole-harness gain. One acquired library is one learning run, not eight independent
learning replications. A subsequent workflow ablation is required before attributing
an improvement specifically to changed orchestration.
