# Prime architecture and kernel substitution audit

Pinned repository: [PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent/tree/c4c238ca025e382d96fb5f37e6328ca77fb82ef3).
Commit: `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`.
Local detached checkout: `var/upstream/prime-agent`. `git status --porcelain` is
empty. No upstream source was modified. The checkout retains its MIT license.
No Prime implementation code was vendored into Aljure source. The native Docker
build uses a clean archive of this unchanged checkout and preserves its license.

The [research paper](https://arxiv.org/abs/2608.23552) motivates programmable
context, recursive agents, and a continual harness. The implementation at this
pin is authoritative for the adapter. In particular, `rlm/repl.py` implements a
CPython/asyncio cell runtime; its wire contract is not an IPython/Jupyter socket.
An IPython-branded host tool name does not imply the Jupyter kernel protocol.

## Actual execution path

| Layer | Pinned source | Contract |
|---|---|---|
| Provider-independent turn loop | `crates/pa-agent/src/agent_loop/{run,response,tools}.rs` | Streaming assistant turns, tool execution, steering, stop/abort boundaries |
| Model tool | `crates/pa-core/src/tools/ipython.rs` | `python_repl` code string; structured results/errors/output; `IpythonKernelProvisioner` |
| Kernel lifecycle | `crates/pa-core/src/kernel/manager/{mod,startup,requests,execution,teardown,snapshot}.rs` | Start/reuse, handshake, request ordering, interruption, output caps, snapshot/restore, teardown |
| Process boundary | `kernel/manager/startup.rs:168` | Launches resolved Python with `-m rlm.repl`, piped stdin/stdout/stderr |
| Kernel protocol | `prime-agent-runtime/src/rlm/repl.md`, host `kernel/protocol.rs` | Version 3 newline-delimited JSON, request IDs, ready/done events, host requests/replies |
| Runtime | `prime-agent-runtime/src/rlm/repl.py` | Persistent `__main__` namespace, AST compilation, top-level await, output capture, errors, dill snapshots |
| Recursive host bridge | `crates/pa-core/src/session_engine/rlm_host.rs`, `rlm/__init__.py` | Spawn, collect, list/delete children, progress, resident sessions, model selection |
| Inline/headless children | `crates/pa-cli/src/print_rlm.rs` | Descendant tree, direct messaging, quiescence, cleanup; daemonless limitations are explicit |
| Harness state | `rlm/harness.py`, `pa-core/src/refinement/` | Local/global CRUD, structured entries, refinement proposals/history, rollback |
| Skills | `rlm/skill.py`, `pa-core/src/skills/`, `kernel/bootstrap/venv/skills.rs` | Python package imports, callable references, environment provisioning |
| Persistence and usage | `pa-core/src/session/`, `session_engine/rlm_usage.rs` | Append-only session history; idempotent child attribution folded into parent totals |
| Headless flags | `crates/pa-cli/src/args.rs` | `--mode json`, `--print`, `--provider`, `--model`, `--thinking`, `--session-dir`; runtime verification still pending |

The kernel emits `ready`, stdout/stderr, result, display, host_request, error, and
done events. Requests include execute, interrupt, host_reply, snapshot, restore,
list_names, MCP status, bash activity, and shutdown. Host replies bypass the
ordinary execution queue so an awaiting cell cannot deadlock its own reply.
User code output and raw file-descriptor writes use separate captured channels.

Snapshot semantics are Python-specific: per-variable dill serialization, live
globals repair, size skips, pruning rules, and guarded file-handle restoration.
This is session recovery. It is not an executable-only cold-boot export: it can
retain task data, caches, and conversation-derived variables.

## Narrowest intervention and feasibility decision

The narrowest process seam is the kernel-manager launch plus protocol-3 request
and event implementation. A Clojure executable could implement that wire format.
That alone does not preserve the model-facing capabilities.

| Capability | Native Python dependency | Required Clojure work |
|---|---|---|
| External context and persistent bindings | Python namespace and bootstrap variables | Value conversion, persistent SCI namespace, matched context API |
| Recursive calls/results | Async `rlm.spawn`/`collect` host requests | Equivalent IDs, host bridge, cancellation and waiting semantics |
| Direct messaging | Executable `agent_message` skill and host controller | Equivalent callable surface and delivery receipts |
| Files/tools/MCP | Python executable skills, bash helpers, Python modules | Implement equivalent selected operations; document ecosystem differences |
| Harness CRUD/refinement | Python `rlm.harness` and Rust refinement state | Port callable bridge and preserve local/global scope, history, rollback |
| Executable skills | `reference.type == "python"`, Python import/call pattern | Change validators, provisioning, skill representation, discovery and prompt inventory |
| Errors/output/cancellation | Python tracebacks, async cell interruption | New error formatting and cancellation semantics under the same host events |
| Reset/recovery | dill snapshots of Python objects | New format and tested migration/reset contract; cannot load dill into SCI |
| Resource accounting | Host provider loop plus descendant attribution | Retain provider accounting; include any bridge/refinement work |
| Model contract | `prompts/layers/core.md`, usage rules and Python examples | Change static instructions, examples, tool description, skill documentation |

**Decision: not a clean kernel-only substitution at this pin.** A complete swap
would modify prompts, skill validation/loading, persistence, bootstrap, and runtime
semantics. Keeping Python underneath a thin Clojure wrapper would also confound
the substrate test. No incomplete fork is labeled a controlled language-only arm.
Use Aljure's shared backends for the primary causal experiment. Keep native Prime
for the separate competitive experiment. Revisit a narrowly scoped Prime bridge
only after these comparisons work; it must retain an auditable patch.

## Native adapter requirements still open

Source inspection confirms the headless flags. A pinned Docker build and an
offline native fixture adapter now pass an actual matched task. See
`NATIVE_PRIME_ADAPTER.md` for source/image pins, isolation controls and failure
history. `make prime-doctor` reports image/proof state separately and exits 2
while the live gateway and retention export remain missing.
The built image preserves bundled native skills and the default Python packages.
The first root task captured native events and session files in a disposable
restricted environment. Complete descendant/refinement coverage still needs
testing. No host inference credentials may be available to generated code.

The JSON stream alone is not a global hard-budget gate. A trusted provider gateway
outside generated-code reach must reserve all root, child, refinement, compaction,
failed, and retry calls before dispatch. `--goal-token-budget` is not that gateway.
The gateway must also verify the requested/returned model and report cache charges.
Do not sum child transcripts together with already aggregated parent usage.

For continual learning, isolate the agent directory, session directory, project
skills and global skills. Freeze a reviewed executable artifact set, not a dill
namespace or the entire session directory. Until export and freeze are validated,
native continual-learning parity is unverified. Native print mode's inability to
create resident daemon sessions also needs a condition-level capability note.
