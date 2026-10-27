# Skill discovery v4: cleanup-confirmed fixture regression

**FIXTURE. Zero additional model inference authorized.**

V3 stopped after 12/20 slots. Every attempted worker started, both ordinary cases
completed across all five conditions, and the first GPU case differentiated blind
reuse (4,999 rejected capacity checks; event budget) from temporary adaptation
(6/6 jobs complete, 42 ticks). Docker removal then timed out after adaptation.
The container state was exited/exit 0; its supervisor raised cleanup quarantine.
The old Clojure close method waited for supervisor exit but did not inspect the
cleanup error. Thus the raw episode says complete/`failure-stage=null`, while its
stderr and worker audit show unconfirmed cleanup. The run correctly stopped on
the quarantine marker. Do not count that episode as cleanup-verified success.
All raw v3 evidence and its eight unattempted slots remain unchanged.

Read-only inspection after the stop confirmed that the named container no longer
existed. Existing recovery verified removal and cleared its marker. V4 changes
only cleanup confirmation and reporting: if `docker rm` errors or times out, a
separate bounded daemon query must prove the exact owned container is absent.
There is no retry of execution and no assumed success. Failed/positive presence
queries still quarantine. The supervisor gives unconfirmed cleanup a distinct
exit status, and the Clojure closer propagates it. Reports distinguish simulator
completion from completion with confirmed cleanup. Strict isolation proof was
rerun and passed after the supervisor change.

V4 uses the **same public fixture worlds, policies, five conditions, image, scoring
and budgets as v3**. This is deliberate regression reproduction after a host-side
repair, not new unseen-task learning evidence. The source revision and output
directory are new. Do not resume, overwrite or change either stopped prior run.
Twenty slots remain planned, arm order rotates, and startup/cleanup failures still
stop the study without retries. The temporary-policy and retained-policy execution
paths remain identical, including same-worker readiness, loading, calls and cleanup.

The fixed applicability checker is a required strong control. Recognizing a
resource-contract mismatch is not learned metareasoning. The developer-authored
selector stand-in remains explicitly labeled FIXTURE, including compute/delegate
branches. A real selector must beat simpler strategies on unseen cases and transfer
beyond this resource example; none of that is established by these controls.

Validation before v4: 12 Python supervisor tests; 6 targeted Clojure tests / 63
assertions. Actual strict gate: positive plus all nine negative cases, each with
same-worker readiness. No CPU/memory/process/network/output/time limit changed.

```sh
source var/worker.env
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/diagnostics/skill-discovery-v4-controls/workers" \
  make skill-discovery-v4-fixtures OUT=var/diagnostics/skill-discovery-v4-controls
```

The external Prime/OOLONG task remains separate. These fixture corrections never
authorize a model request, imply a Prime win, or substitute for official scoring.
