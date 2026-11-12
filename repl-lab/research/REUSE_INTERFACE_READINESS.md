# Reuse interface A/B: readiness record — 2026-11-03

No live inference has run. This record covers the repair audit, offline
validation, execution-environment restoration and the frozen inputs for the
development A/B in `REUSE_INTERFACE_PROTOCOL.md`. The six-task result in
`LEARNING_MINIMAL_RESULTS.md` remains NO-GO and unchanged.

## Commits

| Commit | Content |
| --- | --- |
| `cfa37dc` | Stale test assertion from 46b8507 (unrelated to the repair; found by the first full Python run) |
| `a6ccdb6` | The `inspect-v1` repair, audit, protocol, A/B driver and fixture |
| `f1c09a5` | Three defects the fixture found before freeze (below) |

The plan is generated from the clean checkout after the evidence commit that
follows this record. Its hash is reported in `var/reuse-interface-20261103/plan.json`
and in the approval request; it is archived with the results, never before.

## Audit of the repair (Phase 1)

Verified by reading the code and by the scripted fixture:

- `artifact_inspect` is read-only. It reads the controller's snapshot of the
  verified approved library taken before the first model call. A hash is never
  a path; unknown hashes, non-hex input, paths and invalid page bounds fail
  closed. Pages are at most 4096 characters; responses are capped at 32768 bytes.
  It never evaluates source, including source that requests a host effect.
- `artifact_call` reaches only this task's admitted export set, by the immutable
  artifact hash, through the existing `artifact/call` → `executable/invoke!`
  isolated path against the pinned library. Arity, dependency closure, language
  and deadline checks are unchanged. Code hash, call sequence and origin are
  recorded on every call.
- Approved artifacts refused by the applicability predicate are inspectable and
  not callable. Dependencies are inspectable and never receive a call grant.
  Quarantined, unknown, corrupt and missing library states fail before any
  provider request.
- With the switch absent, the tool list, inventory, error text and execution path
  are byte-identical: the fixture replays the three historical post-restart tasks
  and compares the first provider request byte for byte with the frozen result.
- The inventory says use is optional, that summaries are model-authored, and that
  a passed predicate does not prove the task's rules match. Nothing rewards reuse
  or applies an artifact automatically.

## Defects found by the fixture before freeze (fixed in `f1c09a5`)

1. The isolated `artifact_call` worker lacked the assisted prelude, so the
   retained classifier failed on `parse-long`. Validation and every session
   worker load that prelude. The isolated worker now runs the same initializer.
2. The Routing v2 control was refused by the retained predicate, which is a
   shallow text match. The v2 header now truthfully names the superseded v1 rule,
   so the old classifier is admitted while the current rules differ. The gold
   count (4) still differs from the legacy classifier's count (30). The suite was
   regenerated; the superseded suite manifest is kept in the evidence directory.
3. Fixture-only: gateway open/close discipline and the prompt-cache check with
   two appended tools.

The first suite and the three failed fixture attempts are preserved in
`evidence/reuse-interface-readiness-20261103/fixture-attempts/`.

## Offline validation (Phase 2)

| Check | Result |
| --- | --- |
| Clojure suite (`repl-lab.test-runner`) | 204 tests, 3104 assertions, 0 failures; plus skill-interface 4 tests, 44 assertions |
| Python suite (`pytest test_python`) | 239 passed, 77 subtests |
| Interface fixture | 27/27 checks, 0 model calls |

## Execution environment (Phase 3)

Both pinned images were absent from the daemon at the start of the session.
Both were restored from archives whose hashes were verified against committed
records before loading, and the loaded identities equal the frozen pins:

| Image | Pinned identity | Archive | Trusted record |
| --- | --- | --- | --- |
| SCI worker | `sha256:40f00364…c233f` | `var/learning-minimal-20261102/worker-image.tar` | `learning-minimal-freeze-20261102/freeze.json` |
| Prime | `sha256:f3e30aaa…46ad` | `var/prime-image-recovery/rebuilt-20261027-v1` | `prime-image-recovery-v1/seal.json` |

The Prime manifest records the Id the sealing daemon assigned; the current
image store assigns the frozen pin to the same bytes. RootFS layers and Config
are byte-equal to the manifest. No image was rebuilt, pruned or substituted.
Record: `evidence/reuse-interface-readiness-20261103/docker-restore.json`.

The full proof chain then passed on the final source: isolation gate, SCI
contract, artifact-path (now attesting `skill_interface.clj`), acquisition,
Prime isolation, subscription relay and acquisition relay. The chain was run
once before and once after the fixture-found fixes; both reports are archived.

## Frozen inputs (Phase 4)

Suite `var/reuse-interface-20261103/suite`, copied to the evidence directory.
Generator seed 2026110202. Library pin
`f273cf89770402469f31d549a51c7c25a5d955940706b202565fdd3adc5b2c88`
(the exact library the live run produced). Arm A is the e6d17fe model-visible baseline; arm B adds
only `skill_interface: "inspect-v1"`. Ten paired attempts, A/B, B/A, A/B, B/A, A/B.

GO (development) requires: all ten attempts complete with accounting and
cleanup evidence; all five arm-B answers correct; at least one eligible arm-B
task with source-attributed reuse; no classifier execution on either negative
control; attribution review resolved. Hard aggregate cap USD 6
(API-rate-equivalent); per task USD 5, 12 requests, 300 s.

## Not done

No live run, no plan approval, no held-out access. The plan hash must be
approved explicitly before `run`.
