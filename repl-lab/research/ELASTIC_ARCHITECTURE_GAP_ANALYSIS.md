# Elastic architecture: Aljure against Prime, from source

**Scope:** recursion, asynchronous children, budgets, failure handling,
compaction, refinement and skills, as implemented.
- **Aljure:** branch `claude/sonnet-pair-v7` at `17853f2`, plus the phase A
  commit. Aljure paths are relative to `repl-lab/`.
- **Prime:** pinned commit `c4c238ca…`, read-only checkout at
  `var/upstream/prime-agent` (`P:` below).
- **Behaviour:** recorded traces (`OPUS_CAPABILITY_GAP_ANALYSIS.md`,
  `MULTINLI_COUNT_FAILURE_ANALYSIS.md`, and
  `CONTROLLER_VERIFICATION_DESIGN.md` §1).

No model calls were made.

## Summary

1. **Neither harness gains from recursion on the measured tasks.**
   - Prime spawned children in 1 of 42 arms; 5 of its 6 children failed.
   - Aljure's `agent_call` was used in 2 of 33 L0–L2 arms (MultiNLI chunking).
   - The measured gaps are delivery format and shared semantic bias, not
     compute or concurrency (`CONTROLLER_VERIFICATION_DESIGN.md` F2, F4).
2. **Aljure's controller already has the hard parts Prime lacks:**
   - atomic reservation before dispatch;
   - durable compare-and-set (CAS) ledger state;
   - fail-closed handling of unknown outcomes;
   - isolated per-session workers.
3. **It lacks the asynchronous parts:**
   - non-blocking spawn and collect;
   - per-child quotas and a root floor;
   - per-request (not run-global) uncertainty;
   - monotonic terminal states;
   - bounded child context and results;
   - a concurrent reply path to the gateway.

   Phase A (`src/repl_lab/elastic.clj`) adds the ledger half of these, behind a switch.
4. **Optional, prose-described capabilities are not used by either model run**
   (L2: 0 of 11 arms). The main client of elastic children is therefore the
   **controller** (blind review, replication), not the model.

## Capability matrix

Status codes: **E** exists and works; **N** missing; **U** exists but is not
reliably used, or cannot be reached.

| # | Capability | Prime | Aljure | Status |
| --- | --- | --- | --- | --- |
| 1 | Create a child | `rlm.spawn(prompt, name, model, thinking)` returns once admitted; the child runs in a detached task (`P:prime-agent-runtime/src/rlm/__init__.py:179-202`; `P:crates/pa-daemon/src/rlm_children/host.rs:198-298`) | `agent_call` blocks the parent until the child's `done` (`src/repl_lab/runtime.clj:129-139`) | Aljure: synchronous only (E). Asynchronous spawn added in phase A (`elastic.clj:142-184`), not model-facing |
| 2 | Wait or collect | `collect(targets, timeout_ms)`: snapshots, a shared deadline, never an error on timeout (`P:…/rlm/__init__.py:409-443`; `P:…/host.rs:604-633`) | `:agent/await` and `:agent/cancel` exist in broker schemas (`runtime.clj:12`, `:146-152`). They are **not** native tools, which are only the five tools at `model_protocol.clj:105-138` | **U**: cannot be reached in tool mode |
| 3 | Cancel | `delete_subagent` kills mid-run; `close_children` cascades on teardown (`P:…/host.rs:429-563`; `P:crates/pa-daemon/src/rlm_children/registry.rs:237-322`) | `c/cancel!` cascades over sessions (`controller.clj:55-63`). `finish-session!` overwrites any status, so a cancelled child that later errs becomes `:failed` (`controller.clj:47-53`; `runtime.clj:348-350`) | E with a defect: terminal states are not monotonic. Phase A makes them monotonic (`elastic.clj:271-291`) |
| 4 | Child model and effort | Inherit by default; otherwise resolve against an allowlist, "loudly, never a fallback" (`P:crates/pa-daemon/src/rlm_child_model.rs:45-61`, `:76-116`). Thinking defaults to the parent's; an unsupported level fails the spawn (`:125-159`) | The gateway pins model, `thinking` and `output_config` on **every** request (`gateway.clj:34-41`) | **N, by design.** Needs an authorized profile set in the plan and in the gateway (phase A records `:profile`; only `:inherit` exists) |
| 5 | Hard budget before dispatch | **None.** A goal's token budget is soft: it marks the goal `budget_limited` and asks the model to wrap up (`P:crates/pa-core/src/goals.rs:379`). No caps on plain `rlm.spawn`; only the opt-in factory has `max_parallel` and `max_children` (`P:prime-agent-runtime/src/rlm/factory.py:65-73`) | Reserve before every call in one CAS transaction (`controller.clj:114-127`; `store.clj:77-87`). The gateway reserves the whole context window at the highest input rate (`gateway.clj:68-76`) | **Aljure better.** Gap: no per-child quota and no root floor, so one child can spend the root's whole budget. Added in phase A (`elastic.clj:192-213`) |
| 6 | Usage attribution | Child usage is folded idempotently into the parent row; repeated report ids return `Existing` (`P:crates/pa-core/src/session_engine/rlm_usage.rs:76-147`). Errored turns are not billed (`P:crates/pa-daemon/src/rlm_child_usage.rs:56-77`) | All calls charge the one run ledger; children are sessions of the same run (`controller.clj:129-143`) | Both E. Prime's "not billed on error" can undercount; Aljure keeps an unknown reservation held |
| 7 | Uncertain provider outcome | Turn error → child `error` (`P:…/rlm_children/lifecycle.rs:463-501`) | `recover!` marks **every** pending request in the run unknown (`controller.clj:145-152`). External and API providers call it on any exception (`external_task.clj:63`; `provider.clj:104`) | E for one sequential request; **wrong under concurrency**: it would mislabel siblings' calls. Phase A is per request (`elastic.clj:259-269`) |
| 8 | Concurrent transport | The host Relay multiplexes requests by id and never serializes children (`benchmark/gateway_client.py:470-515`) | `ExternalProvider` writes one request and blocks on `read-line` for its reply (`external_task.clj:50-52`) | **N**: one request in flight per Aljure task process. Needs a reply demultiplexer (phase C) |
| 9 | Child context | The child gets only `[task from parent]` and no parent transcript (`P:…/host.rs:208`; `P:…/rlm_children/lifecycle.rs:87-107`) | Every worker, child workers included, is bound to the **whole** external context (`external_task.clj:65-81`, `:134-135`). Handles are run-global, with no per-session grant (`controller.clj:194-201`). `agent_call :context` is a list of strings without capability meaning (`model_protocol.clj:131-132`) | **N**: no bounded context. Phase A grants handles per child and refuses amplification (`elastic.clj:165-170`) |
| 10 | Child result size | Preview 160 characters; answer text at most 65,536 (`P:…/rlm_child_model.rs:13-22`) | The child's `done` summary returns to the parent unbounded, up to the 8 MiB answer limit (`runtime.clj:23-24`, `:137-139`) | **N**. Phase A bounds and hashes results (`elastic.clj:283-288`) |
| 11 | Depth and fan-out | Depth 2 by default, refused at spawn (`P:crates/pa-core/src/session_engine/rlm_host.rs:265`; `P:…/host.rs:85-90`) | `recursion-depth 8`; `concurrent-subagents` = the plan's `concurrent_requests` (`benchmark/paired.py:430-432`, `:449-452`), enforced at `session!` (`controller.clj:22-35`) | E. Elastic adds limits on total children, active children and per-child wall time |
| 12 | Corrections shared with children | — | One format correction per **task**, children included (`runtime.clj:256-268`) | E, but a child's bad reply spends the root's only correction. The elastic design gives elastic children their own counter |
| 13 | Orphans | A supervisor closes children when the parent dies, with retries (`P:crates/pa-daemon/src/supervisor_parent_death.rs:1-60`). A restarted parent rebuilds from the spawn ledger (`P:…/registry.rs:485-526`) | Root exit closes every task worker (`runtime.clj:351-358`). Stdin EOF makes the supervisor reap the container, and it keeps its own deadline (`isolation.clj:75-85`) | Aljure E for workers. Async children need recorded worker leases and restart recovery; phase A adds these (`elastic.clj:333-361`, `:407-486`) |
| 14 | Deadlock-free host bridge | Host replies bypass the kernel queue (`P:prime-agent-runtime/src/rlm/repl.py:1526-1533`) | Not needed: the controller, not generated code, issues children | Aljure avoids the problem by construction |
| 15 | Compaction | Automatic at 95% of the window; summary prompt with "Outstanding Work" (`P:crates/pa-core/src/session_engine/compaction.rs:12-17`, `:455-463`) | None; native tool history is append-only (`external_task.clj:116-120`) | N; no arm came near the window (`PRIME_PARITY_MATRIX.md` row 1c) |
| 16 | Harness refinement | Model-proposed edits are applied automatically. The only check is an LLM review gate; rollback uses snapshots (`P:crates/pa-core/src/refinement/planner.rs:10-12`, `:505-545`) | Promotion needs frozen paired evidence, CAS on the parent and a safe session boundary. Rollback goes only to an approved hash (`artifact.clj:103-153`) | **Aljure stricter** |
| 17 | Executable skills | Discovered by `SKILL.md` description; every skill is imported at startup; no version check on disk (`P:crates/pa-core/src/skills/discovery.rs:225-230`; `P:crates/pa-core/src/kernel/bootstrap/runtime_code.rs:89-193`) | Content-hashed immutable artifacts (`artifact.clj:27-62`). Descriptions are reviewed per exact hash (`skills.clj:17-42`). Only the approved library can be called (`runtime.clj:180-189`) | E, but **U** in tool mode: `skills/list`, `artifact/call` and `policy/select` are not native tools. No input-contract tests and no invalidation |
| 18 | Verification and the completion gate | None. The answer file is collected; the run ends on a text reply | `sci-verify` helpers and an evidence gate that fires only on the model's own open audit (`runtime.clj:276-295`) | **U**: L2 used the helpers 0 times in 11 arms. See `CONTROLLER_VERIFICATION_DESIGN.md` |
| 19 | Delegation guidance | About 1.5K tokens of prompt (`P:crates/pa-core/src/prompts/layers/core.md:33`; `P:…/layers/usage.md:16-17`, `:29-34`) | One sentence (`resources/external-tools-assisted.txt:3`) | Both rarely used. Prompt length did not make Prime delegate (1 of 42 arms) |

## What Prime gets right

- **Non-blocking spawn with snapshot collect** under one shared deadline, and
  "never an error" on timeout. The parent's turn is never held hostage by a child.
- **Names are reserved before the first await**, so parallel spawns cannot collide (`P:…/host.rs:95-110`).
- **Idempotent usage folding** keyed by report id.
- **Bounded child results** (160 / 65,536 characters).
- **An explicit model allowlist that fails loudly**, with no silent fallback.
- **A cascade close** on teardown and on parent death.
- **Children get a task, not the parent transcript.**

## What Aljure already does better

- **Minimal interface:** five tools and about 1.8K characters of instructions
  (`PRIME_PARITY_MATRIX.md` row 6). Prime's prompt is about 29.8K characters.
- **Explicit computational state:** SCI vars persist in the session. In 22 of
  33 L0–L2 arms the per-item decisions were in worker state, where the
  controller can read them.
- **Durable provenance:** every tool call, result, reservation and notice is a
  ledger event under compare-and-set (`store.clj:77-87`). The contract
  auditor re-checks every arm.
- **Controller-owned hard budgets:** reservation before dispatch, a
  conservative bound, and overrun stops the run (`controller.clj:114-143`).
  Prime has only a soft goal budget.
- **Isolation:** each SCI session runs in its own proven container
  (`isolation.clj:46-61`). Generated code cannot reach the provider, the
  credentials or the host.
- **Fail-closed unknowns:** an uncertain call keeps its reservation and stops
  the plan.

## Exists but not reliably used

| Capability | Evidence of use |
| --- | --- |
| Aljure `agent_call` | 0 in the 21-task runs; 2 of 33 L0–L2 arms (MultiNLI chunking, free-text results) |
| `sci-verify` helpers and the evidence gate | L2: 0 of 11 arms; gate firings: 0 |
| Prime `rlm.spawn` | 1 of 42 arms; 5 of 6 children failed on sandbox or kernel errors |
| Prime skills, refinement, compaction, `bash` | 0 of 42 arms |
| Aljure skills and artifact tools | not reachable in tool mode |

## Consequences for the design

1. **Build the asynchronous substrate for the controller first.** Blind review
   and independent replication are controller-dispatched children. They need
   spawn, quotas, blinding, bounded results and per-request uncertainty. They
   do not need the model to choose to delegate.
2. **Do not expect a model-facing `agent_spawn` to be used** because it exists.
   Treat its activation as the primary endpoint of arm B in
   `COMPUTE_SCALING_EXPERIMENT_PLAN.md`.
3. **Fix the three latent concurrency defects before any child runs
   concurrently:**
   - run-global `recover!`;
   - non-monotonic `finish-session!`;
   - the blocking `receive!`.

   Phase A avoids the first two in its own namespace. Phase C replaces the third.
4. **Do not add per-child effort or model until the plan and gateway both
   authorize a profile set.** Prime's allowlist is the right pattern; its
   missing budget gate is not.
