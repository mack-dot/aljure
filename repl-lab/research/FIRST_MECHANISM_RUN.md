# First real acquisition and transfer run

Status: prepared using existing commands; **not authorized or executed**.
This file does not enable inference. No new scheduler or controller is required.

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
- Caps: acquisition $15, held-out $10, cold boot $10; total $35. These remain proposed.
- Acquisition: one trajectory, three learning tasks per arm, six development cases.
  Frozen and evolving arms get identical capabilities and equal nontransferable
  task budgets. Both can construct and use temporary code. Only evolving retains
  approved artifacts between tasks. Root and child calls share each task's cap.
- Evaluation: eight paired held-out tasks, then eight separate paired cold-boot
  tasks, including declared distribution shifts. Each phase has its own cap.
- Actual SCI isolation gate, existing memory/CPU/process/expression limits, fixed
  source and split hashes, and the current promotion rule remain mandatory.
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
make evolve LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=15
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
