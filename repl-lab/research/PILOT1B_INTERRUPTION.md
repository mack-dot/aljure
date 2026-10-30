# Pilot 1b interruption record (2026-10-30)

This record documents an infrastructure failure during Pilot 1b and its consequences for plan
identity. It does not alter any frozen plan, proof, or run output. The original run directories
stay as they were written.

## What happened

| Time (local) | Event |
| --- | --- |
| Oct 30 ~00:50 | S run 1 and D run 1 completed (28 rows each) under the frozen plans at commit `98fc07c`. |
| Oct 30 01:03–01:20 | P run 1 ran all 28 tasks. The host disk reached 100% during the run. Task `…18000254` failed with `OSError`; task `…18000228` failed with an unclassified error. The run still wrote `results.jsonl` and `report.json` (26 completed, 2 error rows). |
| Oct 30 (day) | The Docker daemon stopped answering. Root cause (inferred): the VM disk file is sparse, so the Linux VM's writes failed when the host had no space, and `dockerd` hung. |
| Oct 30 (day) | A separate Claude session, working on an unrelated project, ran `docker image prune -a -f`. The pruned set included both images that the Pilot 1b plans pin. |
| Oct 30 ~19:30 | A graceful Docker Desktop quit hung inside the stuck backend. With operator approval, the backend was force-killed and Docker Desktop relaunched. The daemon answered after about one minute. |

Spend recorded so far for Pilot 1b: known USD 1.6107, unknown reservations 0. The per-pilot stop
level is USD 25.

## State of the pinned images after recovery

| Image | Pinned identity | State |
| --- | --- | --- |
| Prime native worker | `sha256:f3e30aaa…446ad` | **Restored** from the sealed archive `var/prime-image-recovery/rebuilt-20261027-v1` after verifying the manifest against the committed hash in `research/evidence/prime-image-recovery-v1/seal.json`. The loaded image has the same 11 layers, the same config, and the same architecture as the sealed identity. |
| SCI worker (Aljure) | `sha256:58550c92…56f1` | **Lost.** The only SCI archive on disk (`var/sci-image-recovery/v7`) holds a different image (`4e65f5bb…`, tag `repl-lab-worker:v7-pinned`). No archive or build report for `58550c92…` exists on this machine. |

A rebuilt worker image from the same source and the same pinned base digest gets a new image
identity, because the build records creation times in its config. The frozen Pilot 1b plans pin
the SCI image by identity, and preflight refuses a run whose isolation proof names a different
image. Therefore the remaining Pilot 1b runs (R run 1 and all run 2s) cannot execute under the
plans the operator authorized at `98fc07c`.

Observation on the restore tool: `scripts/prime_image_recovery.py restore` loaded the image
correctly but then raised, because the sealed manifest's `Id` (`0dac4e17…`) is the identity the
old daemon reported, while the current daemon reports the config digest (`f3e30aaa…`). The
layer and config comparison passed by hand. The tool should compare `RootFS` and `Config`
rather than `Id`. That change is not made here.

## What the completed evidence shows

| Run | Rows | Completed | Mean score (Aljure) | Accounting |
| --- | --- | --- | --- | --- |
| reuse-1b-S-r1 | 28 | 23 | 0.232 | complete |
| reuse-1b-D-r1 | 28 | 26 | 0.310 | complete |
| reuse-1b-P-r1 | 28 | 26 | 0.345 | complete, but 2 rows failed under disk pressure |

These are one run per arm with no R arm. The preregistered Pilot 1b rule needs two runs per
arm. No conclusion is drawn from this table. P run 1 ran under a disk-full condition, so its
two error rows are an infrastructure failure, not a harness or model outcome.

## Options for the operator

1. **Re-freeze Pilot 1b at `98fc07c` with a rebuilt SCI image.** Same commit, same seed, same
   task selection, same S/D/P/R mechanisms, same subscription-only route, same caps. Only
   `execution_images.sci` and therefore the four plan hashes change. Run 1 evidence for S, D and
   P stays as it is. Run 2 and the R arm would execute under the new hashes, so the pairing of
   run 1 with run 2 crosses an image rebuild. The rebuild is from identical source and an
   identical pinned base, so the behavioral difference is expected to be nil, but that is an
   assumption to state in the results, not a measured fact. This needs a new authorization of
   the four new plan hashes.
2. **Restart Pilot 1b from scratch under the new hashes.** Cleanest identity, about twice the
   remaining spend. Existing run 1 directories stay as superseded evidence.
3. **Stop Pilot 1b here** and treat the three run 1 outputs as a descriptive record only.

No option is taken here. The resume script in the session scratchpad stays unexecuted.

## Protective steps taken

- The pinned Prime image is restored. No Pilot 1b plan needs a Prime rebuild.
- `var/worker.env` and the proofs in the `98fc07c` checkout are untouched. The dev repo's own
  worker image is rebuilt separately for the programmatic-execution work; see
  `research/PROGRAMMATIC_EXECUTION.md`.
- Recommended before any further live run: archive the SCI worker image with a sealed
  manifest, as the Prime image already is, so an image prune cannot destroy plan identity again.
