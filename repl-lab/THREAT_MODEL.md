# Threat model — version 1

Written before any generated candidate execution.

The development agent implements and tests this repository. Experimental agents
are untrusted users of the broker. Their code, tool arguments, source comments,
messages, and provider responses can be hostile or malformed. An agent must not
read hidden durations, future faults, final seeds, provider credentials, other
runs, host files, or acceptance logic. It must not promote its own artifacts.

Trust the operator, fixed controller code, JVM/SCI dependencies, container runtime,
and host kernel. Protect host availability with memory, CPU, process, disk, output,
and wall limits. This is a bounded prototype, not protection against all kernel or
runtime exploits. Locally writable hashes and logs are not tamper-proof.

Use a local immutable image ID. Run generated code as UID 65534, with no network,
no capabilities, no new privileges, no secrets or forwarded environment, no host
mounts, read-only root, and a size-limited scratch tmpfs. Limit memory plus swap,
CPU quota, process count, output bytes, and wall time. Kill the whole container on
timeout or output overflow. Refuse execution when these controls cannot be
verified. A timed-out controller future is not isolation.

SCI has no Java classes, unrestricted require, host eval, shell, filesystem, or
network functions. Reader-time execution is off. Source/form validation is only
defense in depth. Never evaluate submitted source in the controller JVM.

The learner receives only explicit observation/context records. It sends commands
over bounded IPC. The controller validates identities, schemas, versions, quotas,
and artifact references. It owns all promotion and final-evaluation operations.
Messages are at least once with transactional acknowledgement/effects. Provider
requests can have unknown outcomes after a crash; do not silently retry them.

Required negative tests: loops, allocation, output overflow, file reads/writes,
process launch, network access, and evaluator access. Tests that cannot execute
under verified isolation remain unverified. They must not be reported as passed.

Current host constraints are recorded in PROGRESS.md. Trusted fixtures may run
without isolation. There is no flag that treats model source as a trusted fixture.
