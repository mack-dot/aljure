# Artifact security contract

Requirements for any mechanism that moves exact values between the SCI worker,
the trusted controller and the scorer: strategy B (paged delivery, implemented)
and C (handles, designed). They extend `SCI_EXECUTION_CONTRACT.md`.
**Nothing here relaxes the existing sandbox:** no filesystem, network, process
or host access for generated code; 256 MiB, 1 CPU and 32 pids per worker; 10 s
per expression; and the proven per-reply output bound.

## 1. Isolation and capabilities

- Generated code never receives a host path, file handle or store reference.
  It sees only values in its own worker and the bounded metadata the controller
  returns.
- All storage writes happen in the trusted controller, after its checks.
- Handles are task-scoped. An id from another task is refused, even when its
  bytes exist.

## 2. Bounded, backpressured transport

- A worker reply never exceeds the proven bound. Paging reads at most bound/8
  characters per request, so 4-byte characters and escaping cannot exceed it.
- The controller checks the declared length against the cap (8 MiB per value)
  **before** reading any page. It never builds an unbounded value in memory.
- Each page is a separate request under the 10 s expression limit and the task
  deadline. A stalled page fails the delivery; nothing is retried silently.

## 3. Integrity

- Strategy B checks the assembled length and the worker-side Clojure hash. A
  mismatch fails the delivery (`Answer delivery failed its length or hash
  check`), and the SHA-256 is recorded (`answer-delivered` event).
- The Clojure hash is a **transport check against corruption and missing
  pages**, not a defence against an adversary. Content identity uses SHA-256 on
  the host.
- C: an artifact's id is its SHA-256. A stored artifact is never mutated or
  replaced. `done artifact:` delivers exactly the bytes behind that id.

## 4. What a receipt means

| Label | Meaning | Required evidence |
| --- | --- | --- |
| structural | The bytes are complete and unchanged in transport | length and hash check |
| tested | The value or program passed named tests | stored test results, referenced by id |
| proved | A formal property holds | out of scope |

A hash or receipt is **never** reported as semantic correctness.

## 5. Failure and recovery

| Case | Required behaviour | Test |
| --- | --- | --- |
| Value over the cap | refused before any page is read | unit (`8 MiB`) |
| Not a string | refused; session continues | unit |
| Worker dies during paging | delivery fails as a tool error; worker retired; next call fresh | real-worker recovery check (extend to paging) |
| Hash or length mismatch | delivery fails; nothing written | unit (pending) |
| Partial or interrupted transfer | no answer written; event records failure | unit (pending) |
| Stale or invalid id (C) | refused with a clear error | design |
| Cross-session or cross-task id (C) | cross-task refused; same-task sessions allowed | design |
| Resource exhaustion (heap) | worker OOM is a worker death (retired); controller unaffected | isolation allocation control |
| Cancellation during composition (D) | not applicable until D exists | — |

A transport failure that the controller can recover deterministically must not
become a reasoning problem for the model. Retry a page once on a clean
re-read before reporting failure. *(Proposed; not implemented.)*
