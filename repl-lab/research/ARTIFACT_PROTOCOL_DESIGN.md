# Artifact protocol design (result handles)

A minimal typed, immutable, capability-safe interface for exact values, built
on what exists. **Status: design.** Only strategy B (paged answer delivery) is
implemented. Build C (handles) only if the ablation shows it adds value over
paging (`RECURSIVE_COMPACTION_ABLATION.md`). Security requirements are in
`ARTIFACT_SECURITY_CONTRACT.md`.

## What exists and is reused

| Mechanism | Where | Reuse |
| --- | --- | --- |
| Content-addressed immutable code artifacts (hash, provenance, parent, dependencies), tamper detection | `src/repl_lab/artifact.clj` | Same hashing (`u/sha`), immutability and provenance fields for data artifacts |
| `artifact/inspect`, `artifact/subtree` (bounded view of a path) | `src/repl_lab/runtime.clj` | Same shape for inspect and page |
| Bounded results; `full-result` and `page` inside the worker | `resources/sci-prelude.edn` | In-worker paging stays; handles add a host-side copy |
| Paged answer delivery (strategy B): `[length hash]`, pages of at most bound/8 chars, host-side length and hash check, `answer-delivered` event with SHA-256 | `src/repl_lab/runtime.clj` (`:done/eval`) | The transport for creating a handle |

## Interface (C)

| Operation | Input | Effect | Model sees |
| --- | --- | --- | --- |
| `result/keep` | SCI source (as in `repl_eval`) | Evaluate once in the worker. The controller reads the value out in pages (strategy B), checks length and transport hash, and stores the bytes under `sha256` in the task's artifact store. | `{id, type, chars, bytes, sha256, state: :structural}` plus a bounded preview |
| `result/inspect` | `id` | Metadata only | as above, plus provenance (session, call, source hash) |
| `result/page` | `id, offset, n` (n ≤ preview limit) | Host-side slice | the slice |
| `result/load` | `id` | Rebind the value into the session's worker, also after a worker restart, through bounded paged writes | `#'user/<name>` |
| `done` | `artifact: id` | The final answer is the stored bytes. Nothing is retyped or re-evaluated. | — |

**Types:** `string` (UTF-8 text) only in the first version. EDN data can be
added later with a schema field. **Validation state:** `:structural`
(length and hash match) by default. `:tested` only with a recorded
test-evidence reference. `:proved` is out of scope.

## Specification

1. **Identity and immutability:** `id = sha256(bytes)`. A write never
   overwrites. The same bytes give the same id.
2. **Type and schema:** a `type` field. Strings are UTF-8, and `chars` and
   `bytes` are both recorded.
3. **Hashing:** SHA-256 on the host, plus the worker-side Clojure hash used
   only as a transport check.
4. **Ownership:** artifacts belong to one task (run) and record the creating
   session. Any session of the same task may read them. Cross-task access is
   refused (no shared store across runs).
5. **Budgets:** at most 8 MiB per artifact (the answer limit), 32 MiB per task,
   and a count limit of 64 (*proposed*).
6. **Execution and serialization:** pages of at most bound/8 chars, so each
   worker reply stays within the proven bound. A value is never serialized in
   one piece.
7. **Validation evidence:** the state field is upgraded only with a reference
   to stored evidence (test results). It is never inferred from a hash.
8. **Dependencies:** record the source hash and the ids of loaded artifacts
   (provenance). Cycles are impossible, because ids are content hashes of
   immutable bytes.
9. **Lifetime:** task-scoped. Deleted with the task's scratch after its
   evidence is exported. The final answer is kept as evidence.
10. **Recovery:** artifacts live on the host, so they survive worker
    termination. `result/load` rebuilds a worker's state.
11. **Replay:** content-addressed bytes plus the recorded source hash. Exact
    re-evaluation is not guaranteed, because the model's code may be
    nondeterministic; the bytes are the record.
12. **Exact final delivery:** `done artifact:` writes the stored bytes to
    `answer.txt` and records the SHA-256 in the events.

## Recursive composition (D): deferred

A child's `done` could return `{artifact: id}` instead of text, so the parent
receives metadata rather than content. Do not build this until HC3 has a task
family where children are actually used and text transfer is measured as a
cost. No such case has been observed (`ARTIFACT_DATAFLOW_AUDIT.md`).
