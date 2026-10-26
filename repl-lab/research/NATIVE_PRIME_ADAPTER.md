# Native Prime offline adapter

Status: **FIXTURE**. The pinned release image, native isolation suite and one exact
matched task passed. No provider inference was dispatched. This is not a live
model comparison or continual-learning result.

The builder archives the clean pinned source rather than modifying it. Rust
1.98.1 matches the pinned upstream CI. Both base images are digest-pinned. Cargo
uses `--locked`; Python uses the committed runtime `uv.lock`, uv 0.8.2 and pinned
Pillow 12.0.0. The native default Python package set is also installed from
`default-packages.lock`, with hashes and constraints exported from the upstream
runtime lock. Bundled Python skills are installed unchanged. The final image
contains an installed-package inventory and retains upstream license files.

```sh
make prime-worker-setup
source var/prime-worker.env
make prime-isolation-test
make prime-fixture OUT=var/benchmarks/prime-native-unique RUN=var/benchmarks/language-pilot-20261026-json
make prime-doctor
```

The native fixture uses Prime's own `PRIME_AGENT_FAUX_SCRIPT` integration seam.
It runs the original Rust model loop and native Python tool with scripted provider
responses. Context resides in a file in the disposable workspace. The Python tool
must write an answer artifact. The external aggregate evaluator scores that file;
the final assistant message is not an oracle. This tests the adapter, not a model
or Prime's competitive ability. The shared Aljure pilot uses the same task family
and independent aggregate evaluator. The adapter extracts the exact public input
from both Aljure arms of a passing JSON pilot and verifies their saved answers
before running native Prime on that input. A matched multi-task Prime pilot is
still due. Prompts and file/broker access differ; this is a competitive harness
integration fixture, not a language-isolation experiment.

The container has no host mounts, provider credentials or network. It has the same
256 MiB memory/swap ceiling, one CPU and 32-process limit as the computation
workers. Its Rust controller shares those resources with its Python kernels;
Aljure's JVM controller is outside its worker limits. Native Prime also has a
bounded 8 MiB workspace in addition to the 8 MiB temporary directory. These are
material architecture/resource differences, not strict economic parity.

The workspace permits native shell commands, generated Python modules and local
files. Reading image files is allowed; host files and hidden evaluator files are
not mounted. The isolation suite checks actual loop termination, excessive
allocation/output, host-file and root-write refusal, disabled networking,
evaluator absence, process count and fresh-workspace reset. Inspecting Docker
limits is supplemented by these probes, not described as a general security proof.

The external watchdog bounds the full native task to 120 seconds. Per-expression
timeout parity with SCI's 10-second bound is not yet verified. The native Rust
process emits JSON events. A fixed bootstrap holds the container briefly after
Prime exits so tmpfs artifacts can be collected before removal. The collector
does not load dill snapshots, restore symlinks or execute collected code. The
collector archives from inside the container's live mount namespace; Docker cp
alone did not capture the tmpfs files. The container is removed in a finally block;
uncertain cleanup uses the existing
quarantine mechanism.

No live mode exists in this fixture adapter. A trusted external provider gateway
must reserve root, child, refinement, compaction and retry calls, pin models and
settings, reconcile usage and hide real credentials from generated code. Prime's
native usage totals alone cannot enforce a global spending cap. Native retained
state also needs a validated executable-only export before continual-learning
parity can be claimed. A Docker snapshot is diagnostic evidence, not such an export.

The first native attempt at `var/benchmarks/prime-native-20261026` failed. Prime's
kernel rejected the image because its required default scientific packages were
missing. Its final scripted assistant message still claimed completion; the
independent output check rejected the run. Raw events preserve the real tool error.
Artifact collection also omitted tmpfs content when using Docker cp. The revised
in-container collector passed an actual marker-file control. Both corrections
retain the original failed attempt. Image changes require a new isolation proof.

The corrected image is
`sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
Its nine negative/reset/process controls passed. Native `--version` reports
`0.10.1`. The final fixture record is
`var/benchmarks/prime-native-20261026-resource-manifest`. It used the exact eight
external records from Aljure's `aggregate-0` fixture. Both Aljure backends and native
Prime produced IDs `node-3`, `node-5`, `node-6`, `node-7` and total weight 78.
The independent evaluator checked these values. The final assistant message was
ignored. All REPL Lab containers were removed.

That record contains the source snapshot, requested task, script, image, actual
limits, raw JSON events, native session-state archive, answer, file hashes and
synthetic usage evidence. Prime's faux provider reports tokenizer estimates and
zero costs; these are not provider measurements and must not be compared with
Aljure's zero-token fixture counters. The adapter receipt is tied to source and
image hashes. `prime-doctor` reports its valid FIXTURE evidence but still exits 2
for the missing live gateway and retention export.

Before the final resource manifest, one metadata-initialization attempt failed
because of a wrong local source path. It never started Prime. The log and empty
attempt directory remain preserved; the path was corrected. Successful earlier
fixture runs also remain unchanged. These are engineering attempts, not selected
live benchmark results.
