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

The supervisor now checks removal of the complete execution unit. If removal
fails or times out, it writes a quarantine marker and refuses new workers.
`make isolation-recover` attempts removal only for recorded REPL Lab container
names and verifies absence if removal reports failure. It does not mark isolation
tests as passed. The control has mock coverage and the actual host worker suite
completed with successful cleanup and no quarantine markers. This covers the
tested cases, not every crash scenario. A failed daemon query is not evidence
that a worker is gone.

The optional subscription smoke transport adds the unmodified, version/hash-pinned
Claude Code CLI to the trusted computing base. It is a model transport, not a
generated-code executor. Safe/restricted modes, an empty native-tool set, empty
MCP configuration, disabled hooks, and a fresh empty working directory limit its
ambient capabilities. Managed administrator policy still applies. No permission
bypass flag is used. Normal subscription authentication stays in the operator's
credential store; the helper never extracts or copies OAuth tokens. It strips
inherited API/cloud credentials and custom endpoint routing before launching the
CLI. The actual Docker/SCI gate must pass before dispatch.

Native tool or extra-model evidence causes failure. Unknown provider outcomes keep
their controller reservations. Streams and partial failure evidence are bounded
and preserved. The supervisor terminates the process group on timeout or overflow;
abrupt loss of the supervisor can still leave an uncertain provider outcome.
Subscription dollar figures are labeled API-rate equivalents, not authoritative
billing. The CLI's own dollar threshold can overshoot; it is not a provider-side
hard spending limit. Offline tests of this transport do not establish live CLI,
OAuth, or model behavior.

## Python execution backend

The Python worker runs in a separate digest-pinned container with the same
inspected memory/swap, CPU, PID, wall, output, no-network, no-host-mount, read-only
root and scratch limits as SCI. It receives only source and explicit data over
stdin. No credentials or evaluator code enter the image or environment. Separate
Python image labels and negative-test proof prevent accidental reuse of an SCI
proof. A direct test run archives its previous proof before starting.

Python's AST/compiler APIs and generated modules are legitimate computation tools.
The builtin/import allowlist blocks ordinary file, process and network access,
but Python introspection can defeat interpreter-level restrictions. The container
is the security boundary. The tests establish rejection of the tested direct
operations, not a secure arbitrary-Python interpreter. Worker outputs remain
untrusted data and never establish correctness by assertion.

The Docker supervisor is shared; no Python source is evaluated in the controller.
Pure trusted-fixture evaluators operate on data in the controller. Candidate
programs, including fixtures in the language pilot, run in isolated workers.
Namespace reset occurs by terminating the worker and opening a fresh one.
The native Prime adapter must obtain comparable external isolation before any
Prime-generated Python or shell command may run.

Python artifact parsing and rendering run in separate syntax-only workers. These
workers receive no earlier task code and never execute module statements. This
keeps learner modifications to `ast` or other Python globals out of the acceptance
parser. Source/AST/interface checks still do not establish correctness or purity.
Both syntax and execution workers use the verified image and existing limits.

An approved artifact call loads the session-pinned dependency closure in a fresh
execution worker. Task-local rebinding cannot replace the called export. Returned
values remain untrusted until independently scored. A declared dependency hash
does not by itself prove that the dependency executed. Bundle audits enumerate
literals and docstrings but cannot prove absence of memorized answers.
