# policy-runtime-diagnostic-v1

Status: authorized for no-inference execution. Freeze this specification before
viewing diagnostic scores. The earlier sealed experiment stays unchanged.

Source model: `claude-sonnet-5-5`. Model requests, tokens and inference allowance:
**zero**. This is direct evaluation of an existing model-authored policy, not new
skill acquisition. Actual runs are labeled HELD-OUT EXPERIMENT / no inference.

Use the exact original policy `aa12262b1989915c4a34dad851efeff75b2040964757825ac41e0d5c3bb90003`
and retained policy `834a4e02cd945ad6f889947c2ad4223e04a0bb175e4d7ba266329f2193a0e4d3`.
Keep the existing worker image, generator, simulator, scoring and resource limits.
Neither policy can be replaced or edited during the run.

Seeds 830000–830005 use 12-job layered graphs, one fault and the ordinary resource
profile. Seeds 830006–830008 use 24-job fanout graphs; seeds 830009–830011 use
24-job chains. Both larger profiles use three faults and mixed resources. Generate
and hash all 12 worlds before execution; reject overlap with the old split hashes.
Run each policy twice on each world, reversing original/retained order in the
second repetition. Alternate the initial order across seeds. There are 48 planned
episodes. Repetitions measure execution reliability, not independent learning.

First pass the existing actual isolation suite. Each fresh worker then evaluates
the same fixed `(+ 20 22)` readiness control before loading either policy. No
timeout or resource limit increases: 256 MiB, one CPU, 32 PIDs, 8 MiB scratch,
10-second response limit, 120-second worker/task ceiling, 10,000-event budget.
The readiness control consumes the same task/session allowance in both arms.
It introduces a documented difference from the old run, where loading the policy
was the first request. New diagnostic scores must not overwrite old scores.

Opt-in supervisor logging records bounded stderr, container state before removal,
OOM/exit fields when available, request/response timings and confirmed cleanup.
When forced removal ends a running worker, its prior `ExitCode` is not interpreted
as a final process exit. The controller separately records startup, code-loading,
execution and cleanup stages, exceptions and attempted policy invocations.
No provider credential or environment dump enters these logs.

Classify code rejection, algorithm/contract failure, resource exhaustion,
infrastructure/transport failure and unresolved failure separately. Preserve every
attempt, penalized score and unattempted slot. Stop on failed startup/readiness,
unconfirmed cleanup or quarantine. Do not retry or replace a failed attempt.
A failed readiness gate means this version cannot establish healthy paired
execution; it is a diagnostic outcome, not permission to loosen a limit.

Report completion and failures for all attempted and planned slots. Report paired
makespan only when both members completed with healthy execution, clearly as a
conditional secondary analysis. Report repeats separately and counts of distinct
worlds. Record local elapsed time but leave local-compute dollars unknown unless
an external rate is supplied. Inference cost is exactly zero.

Commands from `repl-lab/`, with a fresh output path:

```sh
source var/worker.env
python3 scripts/clj.py -m repl-lab.policy-diagnostic prepare var/diagnostics/policy-runtime-diagnostic-v1-20261027
export REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/policy-runtime-diagnostic-v1-20261027/workers"
make isolation-test
python3 scripts/clj.py -m repl-lab.policy-diagnostic run var/diagnostics/policy-runtime-diagnostic-v1-20261027
```

Run only if the full isolation test exits successfully. Preparation and execution
refuse path/seal reuse. No live, acquisition, held-out or cold-boot model command
is part of this diagnostic.
