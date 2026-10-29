# Elastic execution: controller-owned asynchronous children

**Status:**
- Phase A is built: the ledger state machine and the executor, in
  `src/repl_lab/elastic.clj`, tested offline in `test/repl_lab/elastic_test.clj`.
- Phases B–E are designed (`ELASTIC_IMPLEMENTATION_PLAN.md`).
- Off by default: the switch is `[:config :contract :elastic-children]`.
- Nothing model-facing has changed.

**Why it exists.** It is the substrate for controller-dispatched computation:
blind review (`CONTROLLER_VERIFICATION_DESIGN.md`) and independent replication
(`COMPUTE_SCALING_EXPERIMENT_PLAN.md`). A model-facing spawn tool is a second,
separately switched client. The evidence predicts that models rarely use it
(`ELASTIC_ARCHITECTURE_GAP_ANALYSIS.md`).

## 1. Operations

| Operation | Controller API | Model tool (phase C, own switch `elastic_tools`) | Semantics |
| --- | --- | --- | --- |
| spawn | `spawn! store run caller spec` | `agent_spawn {id, task, context?, quota?}` | Admits a child and returns at once. Idempotent for the same id, parent and spec; a changed spec is refused |
| status | `status store run caller id` | `agent_status {id}` | Read-only view; parent only. A non-terminal child shows `:status :pending` and no result |
| collect | `collect! store run caller id` | `agent_collect {id, wait_ms?}` | Returns the bounded result of a terminal child and marks it collected (idempotent). `wait_ms` is capped by the parent's remaining wall time, and on timeout returns the pending view, never an error |
| cancel | `cancel! store run caller id` | `agent_cancel {id}` | Any ancestor may cancel. Cascades to the subtree. A call in flight is never interrupted |
| — | `recover! store run` | — | Exclusive restart: unknown, orphaned and unconfirmed states, with no retry |
| — | `launch!`, `sweep!`, `shutdown!` | — | Executor: one thread per child, a watchdog, parent exit |

`agent_call` stays exactly as it is. It is synchronous, shares the run budget,
and remains the comparison point (`runtime.clj:129-139`).

**Spec** (strict keys; anything else is refused):
- `:id` must match `[a-z0-9][a-z0-9_-]{0,63}`;
- `:task` is 1–8,192 characters;
- `:context` is at most 8 handles that exist in the run;
- `:profile` must be in the plan's authorized set; the default is `:inherit`;
- `:quota` is a subset of `{:calls :tokens :usd :wall-ms}`, each at most the
  per-child maximum (`elastic.clj:21-31`, `:121-184`).

## 2. State machine

```
spawned ──start──► running ──finish──► completed | failed | budget-exhausted
   │                 │  │
   │ cancel/expire   │  └─call outcome unknown──► unknown ──operator receipt──► failed(:resolved-unknown)
   ▼                 ▼
cancelled|timed-out  cancelling (a call in flight) ──call settles/released──► cancelled | timed-out
                                                  └─call unknown──► unknown
restart or parent exit: active child without a call ──► orphaned;  call in flight ──► unknown
```

- **Terminal states:** `completed failed cancelled timed-out budget-exhausted orphaned`.
- **`unknown`** is neither active nor terminal. The child cannot run, and its
  reservation is held.
- **Terminal states never change.** A late result is recorded as
  `:elastic-late-result-discarded` and changes nothing else (`elastic.clj:271-291`).
- **A finishing child stops its own subtree** (`:parent-finished`), so no
  orphan subtree can remain.

## 3. Budget: shared pool, atomic admission, no overspend

- **One pool.** Children reserve from the run's own `:reserved` and `:spent`
  counters. Those are the counters the root's `c/reserve!` checks, so the root
  and its children see each other's reservations at once.
- **One transaction per admission** (`admit-call`, `elastic.clj:192-213`). It
  checks:
  1. the run limit, less the **root floor**, for calls, tokens and cost;
  2. the quota of the child **and of every elastic ancestor**, against their
     subtree `used + held`.

  It then reserves. The store's compare-and-set makes this atomic across
  threads and processes (`store.clj:77-87`).
- **Root floor.** Children can never take the last `root-floor` of the run
  budget, so the root can always collect and finish. The root's own calls
  ignore the floor.
- **Quotas are ceilings, not escrow.** Nothing is reserved at spawn, so idle
  budget is never locked. A spawn is refused when the run has no call left
  above the floor.
- **Settle** charges the receipt and moves `held` to `used` up the chain.
  - A receipt above its reservation fails the child, halts elastic work and
    sets the run to `:budget-overrun`, as `c/reconcile!` does (`controller.clj:129-143`).
  - A call provably never sent (`:outcome :not-dispatched`) is released
    without charge.
- **Gateway layer.** The gateway reserves the whole declared window per
  request (`gateway.clj:68-76`). For Opus that is 1M input tokens at $8/M plus
  32,768 output tokens at $20/M, so **$8.66 per request in flight**. With a
  $100 arm cap, at most 11 requests can be in flight in one arm. This is a
  latent concurrency limit (compare `PRIME_PARITY_MATRIX.md` row 3b). Phase C
  sets `max-active` so that `(1 + max-active) × 8.66 ≤ usd_per_arm`.
- **Tested:** 4 concurrent children each try to take 20 calls from a 40-call
  run with a floor of 4.
  - With the in-process write lock: exactly 36 are settled.
  - With compare-and-set alone: never more than 36.
  - Either way the root can still take 4 calls, and a 5th is refused
    (`elastic_test.clj`, `concurrent-children-never-overspend-the-shared-budget`).

## 4. Isolation and bounded context

- **Worker.** Each child has its own SCI worker with the same image, proof gate
  and limits as a root worker (`isolation.clj:46-74`). It is opened by an
  injected function and closed exactly once through a lease. Phase A records
  the lease states `:none → :open → :closed | :close-failed`.
- **Context grant.** A child may read only the handles in its spec, and a
  nested child only a subset of its parent's (`:context-amplification` is
  refused).
  - Phase B makes this real: the child's worker initializer binds only the
    granted blocks, not the whole `external-context` (`external_task.clj:65-81`).
  - The broker refuses `context/query` on any handle outside the grant.
- **Task, not history.** A child receives its task text (at most 8 KiB) and
  the granted handles, never the parent's messages or worker.
- **Bounded results.** A result keeps at most `result-chars` (default 4,000;
  at most 65,536), plus its full length and SHA-256.
  - Phase B stores the full text as an immutable context block
    (`controller.clj:164-175`), so a parent can page through it by handle
    instead of taking it into its history.
- **Profiles.** `:profile` names an authorized per-child model/effort setting.
  - Phase A accepts only names in the plan's set, which always contains
    `:inherit`.
  - Phase C maps a profile to pinned settings only when the gateway config
    also lists it. `validate-request!` (`gateway.clj:34-41`) would otherwise
    refuse the request, which fails closed.
  - Opus 5.5 effort values must come from the provider documentation and be
    verified by a fixture before any profile is authorized.

## 5. Limits

| Limit | Setting | Enforced at |
| --- | --- | --- |
| Depth | `:max-depth` ≤ `[:limits :recursion-depth]` | spawn |
| Active children per task | `:max-active`; `unknown` children count as active (fail closed) | spawn |
| Total children per task | `:max-children` | spawn |
| Calls, tokens, cost per child (subtree) | `:child-calls :child-tokens :child-usd`, or less on request | each admission |
| Wall time per child | `:child-wall-ms`. A nested default shrinks to the parent's remaining time; an explicit request for more is refused | spawn, admission, `sweep!` |
| Root floor | `:root-floor {:calls :tokens :usd}` | each child admission |
| Steps per child | the existing `session-steps` (phase B, when children run `run-session!`) | session loop |
| Result size | `:result-chars` | finish |
| Run wall | `within-time!` | spawn, admission |

## 6. Provenance and receipts

**Events.** Every transition is a ledger event:
- `elastic-spawned` {spec-hash, task-sha256, context, profile, quota};
- `elastic-state` {child, state, reason};
- `elastic-call-admitted`, `elastic-call-settled`, `elastic-call-released`,
  `elastic-call-unknown`;
- `elastic-cancel-requested` {by, ids};
- `elastic-expired`, `elastic-collected`, `elastic-worker` {lease};
- `elastic-halted`, `elastic-recovered`, `elastic-late-result-discarded`;
- `elastic-denied` {op, reason, resource}.

  The last one exists so that refused actions count as an experiment endpoint.

**Receipt.** A child's receipt is its ledger record:
- spec and spec hash;
- quota, used and held;
- every request with its provider receipt;
- result hash, worker lease, state and reason.

The contract auditor (phase C) re-derives `used` from the settled requests and
checks that the sum over children equals the elastic share of `:spent`.

## 7. Failures

| Failure | Handling | Retried? |
| --- | --- | --- |
| Spawn request repeated (model or controller retry) | Same id, parent and spec: no-op; otherwise refused | idempotent |
| Admission refused (quota, run budget, deadline, halted, not running) | `elastic-denied` event; the executor maps a quota or budget refusal to `budget-exhausted` | no |
| Provider call fails after dispatch, or its receipt is invalid | That request becomes `unknown`; its reservation is held; that child becomes `unknown`; elastic work halts for the task. **Sibling calls are untouched**, unlike `c/recover!` | **never** |
| Call refused before dispatch | Released, no charge; the child's body sees the error | no |
| Child body throws | `failed`, error text bounded to 500 characters | no |
| Worker open fails | `failed`; no lease to close | no (phase C may allow one retry before any model call, as prewarm does) |
| Worker close fails | Lease `close-failed`; elastic work halts (`worker-cleanup-unconfirmed`), like the runner's cleanup stop rule | no |
| Cancel | Ancestor only; cascades. A child with a call in flight goes to `cancelling`, then to `cancelled` when the call settles, and the call is charged. Workers of stopped children are closed | — |
| Deadline | `sweep!` expires it; same in-flight rule; its worker is closed; a late result is discarded | no |
| Parent exit | `shutdown!`: cancel the root's children, wait out the grace period, close every lease, then mark calls in flight `unknown` and remaining active children `orphaned` | no |
| Controller crash | On restart, `recover!` marks pending calls `unknown` (held), active children `orphaned`, and leases still open `unconfirmed`. Halts. The supervisor reaps containers on stdin EOF and has its own deadline (`isolation.clj:75-85`) | no |
| Concurrent ledger writes | Compare-and-set; an in-process per-run lock avoids retry storms; a settle is retried until it lands, because the call already happened | settle only |

## 8. Transport (phase C)

The host Relay already accepts concurrent requests keyed by id
(`benchmark/gateway_client.py:470-515`). Aljure's side is the blocker
(`external_task.clj:50-52`). The change:
- one stdin reader thread;
- a promise per request id;
- `emit!` under a lock;
- an unknown reply id fails the task.

With the switch off, the code path stays byte-identical: the existing
`ExternalProvider` is unchanged, and the elastic provider is a separate
record.

## 9. Interaction with existing mechanisms

- **Format corrections.** An elastic child gets its own correction counter.
  The task-wide counter (`runtime.clj:256-268`) stays for the root and for
  `agent_call` children.
- **The evidence gate and controller verification** stay root-only. A
  reviewer child is never gated.
- **Delegation by a reviewer child.** A reviewer may not spawn: its
  `max-depth` budget is spent by construction, because the controller
  dispatches it at the deepest permitted level, or with a quota of
  `{:calls 2}`.

## 10. Decisions for the operator

1. **Concurrency cap per arm.** Two limits apply in the current Opus plans:
   - the gateway admits at most `concurrent_requests` (8) requests at once,
     through `session!` (`gateway.clj:174`; `controller.clj:32`);
   - each request holds $8.66 against `usd_per_arm`.

   So `max-active ≤ min(concurrent_requests − 1, floor(usd_per_arm / 8.66) − 1)`,
   which is 7 at $100. The proposal is `max-active 3` for the first experiments,
   which keeps cost exposure small. The other option is a tighter reservation
   from a verified input-size bound; it is not proposed here.
2. **Whether a model-facing `agent_spawn` is worth building before
   controller-dispatched review has shown value.** The recommendation is
   no: build V-A to V-C first.
3. **Profile authorization.** None is proposed until a provider-documented
   Opus 5.5 effort setting is verified by a fixture.
