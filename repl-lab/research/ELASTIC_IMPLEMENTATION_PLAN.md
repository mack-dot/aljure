# Elastic execution and controller verification: implementation plan

The work comes in small phases. Each one can be reviewed and tested on its own,
and each sits behind a switch that is off by default. With every switch off:
- prompts, tool definitions, capabilities, frozen plans and ledgers are
  byte-identical;
- the existing suites pass unchanged.

**Order of value:**
1. Phase A (done);
2. V-A and V-B: controller verification, deterministic, no extra model calls
   by default;
3. B and C: runtime and transport integration for controller-dispatched
   children;
4. V-C and V-D: blind review and frozen plans;
5. D: the model-facing spawn tools, only if V3 shows value;
6. E: skill reuse.

**Gate legend:**
- **offline** means a single test namespace or pytest file. It may run while
  the live chain runs.
- **suite** means `make test` and `python3 -m pytest -q test_python`, after
  the chain ends.
- **docker** means isolation, the SCI contract proof and fixtures, after the
  chain ends.

## Phase A: controller ledger state machine and executor (DONE)

**Files:**
- `src/repl_lab/elastic.clj` (new, 486 lines);
- `test/repl_lab/elastic_test.clj` (new);
- `test/repl_lab/test_runner.clj` (namespace added).

**Switch:** `[:config :contract :elastic-children]`, a settings map. With it
absent, every operation refuses before writing.

**Tests (offline):** 11 tests, 163 assertions. Each was run 3 times while the
live chain was running.
- off-by-default byte identity;
- settings validation;
- spawn admission, escape and amplification refusals;
- subtree quotas and the root floor;
- a concurrent overspend race, with and without the in-process lock;
- cancellation, including a call in flight;
- unknown outcomes;
- restart recovery;
- deadlines, monotonicity and bounded collection;
- the executor with stub workers: concurrency, lease closure, unknown
  transport, an invalid receipt, refused dispatch, the watchdog, cancel in
  flight, parent exit.

**Not touched:** `controller.clj`, `runtime.clj`, `model_protocol.clj`,
`external_task.clj`, prompts, the runner, plans.

## Phase V-A: verification core, pure functions (offline)

**Files:**
- `src/repl_lab/verification.clj` (new):
  - `answer-contract-check`;
  - typed-evidence validation (`:evidence/version 1`);
  - the linking rule;
  - stop-rule counters as pure transitions;
  - the stratified sampler (seeded with `sha256`);
  - the stratified estimate.
- `src/repl_lab/verifiers/generic.clj` and `oolong_label_count.clj` (new):
  trusted, gold-free maps.
- `resources/verification-probe.edn` (new): the read-only extraction source.

**Tests:** `test/repl_lab/verification_core_test.clj`.
- **Fixtures:** the 33 recorded L0–L2 Aljure `repl_eval` sources and `done`
  summaries (copied from `evidence/controller-verification/`, not read
  live).
- **Contract:** it rejects all 3 recorded multi-line answers and accepts the 30
  single-line ones.
- **Linking:** it links on the recorded literal-id arms.
- **Sampler:** deterministic for a fixed seed.
- **Gold:** a test that no verifier namespace resolves an answers path.

**Gate:** offline.

## Phase V-B: wire verification at root `done` (offline)

**Files:**
- `src/repl_lab/runtime.clj`: one call at the existing gate point (`:315`),
  taken only when `[:contract :controller-verification]` is present. With it
  absent, the code path is unchanged.
- `src/repl_lab/external_task.clj`: pass the verifier, and the scope from the
  public context.
- `benchmark/paired.py`: an `aljure_contract.controller_verification` map,
  validated, and declared in capabilities only when on, in the style of
  `VERIFICATION_CAPABILITIES`.
- `scripts/contract_audit.py`: rules for each notice kind:
  - at most once;
  - root `done` only;
  - switch on;
  - no notice after acceptance.

**Tests:**
- `test/repl_lab/controller_verification_test.clj`, with scripted providers and
  stub workers (`execute-script`, as in `verification_test.clj`):
  - the format notice fires once, and the second `done` is accepted;
  - the evidence request fires once;
  - linked evidence passes without a call;
  - the counters bound every loop;
  - the answer is never changed;
  - with the switch off: identical messages, ledger and spend.
- `test_python/test_aljure_sci.py`: the switch is validated and declared only
  when on.
- `test_python/test_contract_audit.py`: conformant and violating ledgers.

**Gates:** offline (single namespaces), then suite.

## Phase B: runtime integration of elastic children (offline)

**Files:**
- `src/repl_lab/elastic.clj`: `run-child!` (a body that runs the existing
  `runtime/run-session!` loop for the child) and a child provider wrapper.
  The wrapper routes reservations through `admit-call!`, `settle-call!` and
  `call-unknown!` instead of `c/reserve!`, `c/reconcile!` and the run-global
  `c/recover!`.
- `src/repl_lab/external_task.clj`: an `ElasticExternalProvider` record. It is
  new; the existing record stays unchanged.
- `src/repl_lab/runtime.clj`:
  - when the switch is on, the broker refuses `context/query` outside a
    child's grant;
  - the child's worker initializer binds only the granted blocks;
  - an elastic child gets its own format-correction counter;
  - when the switch is on, `finish-session!` calls for elastic sessions use
    monotonic transitions.

**Tests (offline):**
- context-grant refusal;
- the initializer binds only granted blocks (stub worker records the bindings);
- the child provider never calls `c/recover!`;
- a cancelled child is never rewritten as `failed`;
- a child's malformed reply does not spend the root's correction;
- off-by-default identity of `run-session!` messages and events.

## Phase C: concurrent transport, controller-dispatched children, runner

**Files:**
- `src/repl_lab/external_task.clj`: a reply demultiplexer, used only by the
  elastic provider: one reader thread, a promise per id, `emit!` under a lock,
  and an unknown id fails the task.
- `benchmark/paired.py`: an `aljure_contract.elastic_children` map, validated
  and declared only when on. With it present: `max-active ≤ min(concurrent_requests − 1, ⌊usd_per_arm / reservation⌋ − 1)`.
- `scripts/contract_audit.py`:
  - elastic event rules;
  - the sum of `used` equals the elastic `:spent`;
  - every lease closed;
  - no request both settled and unknown.
- `benchmark/relay_fixture.py`: a two-child concurrent fixture.

**Tests:**
- **offline:** the demultiplexer with a scripted stdin (out-of-order replies,
  a duplicate id, an unknown id, EOF while requests are pending);
- **python:** switch validation and capability declaration;
- **docker** (after the chain): relay fixture, isolation proof re-run, SCI
  contract.

## Phase V-C: blind reviewer (offline, then docker)

**Files:**
- `src/repl_lab/verification.clj`: dispatches the reviewer as an elastic child
  with no worker, a single call, quota `{:calls 2}`. The reviewer template is
  `resources/reviewer-v1.txt`, hashed. The reviewer reply is validated.
- `scripts/contract_audit.py`: the blinding rule (request body = rendered
  template).

**Tests:**
- **offline:** the reviewer request contains no root answer, label, var or
  history;
- disagreement leads to one targeted notice; agreement leads to acceptance;
- an invalid reviewer reply is recorded as `failed` and does not block;
- a reviewer unknown outcome halts review only;
- the random audit sends no notice.
- **docker:** the review fixture through the real gateway, with a scripted provider.

## Phase V-D: SCI contract probe and frozen plans

- Add the extraction probe to the SCI contract proof:
  - read-only;
  - bounded output;
  - correct on atom-set, map and vector fixtures;
  - no new symbols.
- Freeze the four plans of `CONTROLLER_VERIFICATION_DESIGN.md` §7 at a clean
  commit. Regenerate the gates and run preflight.
- The operator approves the run.

## Phase D: model-facing elastic tools (only if V3 shows value)

**Files:**
- `src/repl_lab/model_protocol.clj`: `agent_spawn`, `agent_status`,
  `agent_collect` and `agent_cancel` tool definitions. They are added only
  when `[:contract :elastic-tools]` is on; the 5-tool list is unchanged
  otherwise.
- `src/repl_lab/runtime.clj`: broker cases that call `elastic/*!`.

**Tests:**
- tool lists are byte-identical when off;
- schema validation;
- `agent_collect` `wait_ms` is capped by the remaining wall time;
- `agent_call` behaviour is unchanged.

## Phase E: executable-skill reuse through the existing artifact system

There is no new memory framework. Each step extends `artifact.clj`,
`skills.clj` and `executable.clj`.

| Need | Existing piece | Change |
| --- | --- | --- |
| Discovery by description and applicability | `skills/inventory`, `skills/compact` with reviewed descriptions per exact hash (`skills.clj:17-50`) | Expose `skills_list` and `skills_describe` as native tools only under a switch. Add `:applicability {:contract … :requires […]}`, already used in `config/skill-descriptions-v1.edn`, to the compact view |
| Load without regeneration | `executable/load!` and `call!` evaluate the approved source in a fresh isolated worker (`executable.clj:6-31`); `artifact/call` limits calls to the approved closure (`runtime.clj:180-189`) | Allow `artifact/call` inside the session's existing worker (load once per session), behind the same approval check |
| Input-contract tests | none | `:contract-tests [[args expected] …]` in artifact metadata, part of the hash. Run by `executable/invoke!` in the isolated worker at promotion. Promotion is refused if any test fails |
| Versioning | content hash plus `:parent` chain, and structural patch with stale-base refusal (`artifact.clj:27-101`) | none |
| Invalidation | rollback to an approved hash only (`artifact.clj:146-153`) | A `:revoked {hash reason}` set in the run ledger. `skills/approved` filters revoked hashes. A revoked hash cannot be called. Revocation is an operator action with an event |
| Approval-gated promotion | `promote!` needs frozen paired evidence, compare-and-set on the parent and safe boundaries (`artifact.clj:103-140`) | Model-generated skills also need an operator approval receipt (hash-bound) in the evidence map before `promote!` accepts them |

**Tests (offline):**
- a contract test that fails blocks promotion;
- a revoked hash cannot be called;
- loading in-session gives the same value as `invoke!`;
- discovery lists only approved, non-revoked hashes.

## Running the suites

When `pgrep -f run_review_levels.sh` returns nothing:
1. run `make test` and `python3 -m pytest -q test_python` on the branch;
2. then run the docker gates for C and V-C.

Each phase is merged only with its suite green and with the byte-identity
tests for every switch off.
