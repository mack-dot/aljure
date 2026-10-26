# REPL Lab

A local Clojure experiment for executable skill retention. The simulator, artifact
registry, controller, and offline fixture demo run today. The local Docker worker
passed its SCI positive control and all nine negative isolation tests in the host
terminal. The live subscription smoke passed all 12 checks on 2026-10-26:
external context, model-written Clojure in SCI, a real recursive model session,
and the parent consuming its result. Run `smoke-1793049211459` used six calls,
12,455 input tokens, and 509 output tokens ($0.03 at the requested API rates;
actual subscription charges remain unknown). Docker and login now work here.

**No experimental model has produced a retained skill. No model has changed its
harness. No model benefit has been shown to survive cold boot.** H1 and H2 remain
untested. The dashboard learning measurements remain SYNTHETIC FIXTURE results.

## Setup

The computational-substrate extension is tracked in
[research/BASELINE_AUDIT.md](research/BASELINE_AUDIT.md),
[research/PRIME_ARCHITECTURE.md](research/PRIME_ARCHITECTURE.md), and
[research/EXPERIMENT_PROTOCOL.md](research/EXPERIMENT_PROTOCOL.md). The pinned
Prime checkout is unmodified. Its Python-specific skills, prompts and snapshots
prevent a narrow kernel-only swap. The causal experiment uses Aljure's shared
controller; native Prime remains a separate competitive comparison.

Use Java 21, Python 3.10+, Clojure CLI, Make, and Node 20+ for the dashboard.
Versions are pinned in `deps.edn`, `worker/deps.edn`, and `dashboard/package.json`.
The controller uses Python's standard-library SQLite driver.

On a connected machine, populate the Maven cache with:

```sh
cd repl-lab
clojure -P
cd dashboard
npm ci --ignore-scripts
cd ..
```

The Make targets use `scripts/clj.py`. It reads the exact pinned jars from the
Maven cache. Set `REPL_LAB_M2` to use a different cache. It never downloads jars or
changes global settings. On this machine, all controller jars were already cached.
`node scripts/bootstrap-dashboard.mjs` can install the pinned dashboard packages
from verified local npm cache entries when registry metadata is unavailable.
`dashboard/offline-dependencies.json` records their SHA-512 integrity values.

## Offline commands

Run these from `repl-lab/`:

```sh
make doctor
make test
make fixture-demo
```

The last command prints the run ID and export path. Substitute those exact values:

```sh
make replay RUN_ID=fixture-1793043550408
make evaluate EXPORT=var/runs/fixture-1793043550408/export PROFILE=heldout
make cold-boot EXPORT=var/runs/fixture-1793043550408/export
make demo RUN_ID=fixture-1793043550408
```

Open `dashboard/dist/index.html` locally. The page needs no server or network.
`make demo` packages existing records; it does not invent a run. It shows a DAG,
attempt timeline, controller messages, exact policy observations and responses,
code/forms, acceptance/rejection evidence, and cost meters. See [DEMO.md](DEMO.md).

Additional checks:

```sh
python3 -m unittest discover -s test_python -v
cd dashboard
npm run typecheck
npm run build
node check-render.mjs ../var/runs/fixture-1793043550408
```

Fixture evaluation resolves only exact, compiled developer fixture forms. Any
other source must use SCI isolation. Fixture cold boot starts a new JVM and reads
only the exported executable library for skill state. It is a process-recovery
test, not an H2 model experiment. Baseline policies remain separate from that library.

## Isolated worker

Docker Desktop must be running and accessible from the terminal. To pull the
official base image, pin its digest, build the worker, and run the actual SCI
positive control plus all nine negative tests, run:

```sh
make worker-setup
source var/worker.env
```

Setup makes no model calls and needs no API credential. It writes
`var/worker-setup.json` with the last stage and result. On success it also saves
`var/isolation-proof.json` and the exact image selection in `var/worker.env`.
It archives any old isolation proof before testing, so a failed rerun cannot use
an earlier pass. It does not change Docker permissions or remove other containers.

On a machine with working Docker, select a **digest-pinned Clojure/JDK 21 image**
that includes the Clojure CLI. Build the worker locally:

```sh
docker build -f worker/Dockerfile --build-arg BASE_IMAGE='<image>@sha256:<digest>' -t repl-lab-worker .
export REPL_LAB_WORKER_IMAGE="$(docker image inspect --format '{{.Id}}' repl-lab-worker)"
make isolation-test
```

If no base image is available, these setup commands select a published official
Clojure/JDK 21 tag, pull it, and resolve its immutable digest before building.
Run them in a host terminal with Docker access, from `repl-lab/`:

```sh
docker pull clojure:temurin-21-tools-deps-1.12.6.1673-bookworm-slim
REPL_LAB_BASE_IMAGE="$(docker image inspect --format '{{index .RepoDigests 0}}' clojure:temurin-21-tools-deps-1.12.6.1673-bookworm-slim)"
docker build -f worker/Dockerfile --build-arg BASE_IMAGE="$REPL_LAB_BASE_IMAGE" -t repl-lab-worker .
export REPL_LAB_WORKER_IMAGE="$(docker image inspect --format '{{.Id}}' repl-lab-worker)"
make isolation-test
```

The base tag is listed in the [official Docker image catalog](https://github.com/docker-library/official-images/blob/master/library/clojure).
The host `make worker-setup` run completed this build and its actual isolation
tests. Docker socket access remains denied inside this assistant session.
`.dockerignore` limits the build context to worker source and
dependency files. No provider credential is needed to build or test isolation.

The supervisor never pulls an image. It verifies the local image ID and Docker
resource controls, creates a restricted container, checks its settings, and kills
the entire container on timeout. No host paths or provider keys are mounted.
Only worker source and dependencies are copied into the image. SCI has no host evaluator,
filesystem, network, process, or unrestricted Java access.

The negative suite tests loops, allocation, oversized results, file reads/writes,
process and network access, evaluator access, and reader evaluation. Missing
isolation returns **UNVERIFIED with exit 2**, never a passing result. Live evolution
requires a successful proof for the same image ID. The preflight also rejects a
config that differs from the enforced worker limits.

If worker removal fails, the supervisor writes `var/isolation-quarantine/` markers
and blocks further generated-code execution. After restoring Docker access, run
`make isolation-recover`. It verifies cleanup of only the recorded REPL Lab
containers. Cleanup does not replace `make isolation-test`.

## Live commands — explicit authorization required

The current user proposal is recorded in `config/live-proposal.edn`. It selects
`claude-sonnet-5-5`, input pricing of $2 per million tokens, and output pricing of
$10 per million tokens. The category caps are acquisition $15, held-out $10, and
cold boot $10. **The smoke passed within its original $1 allowance, including
conservative reservations from two earlier quota rejections. Remaining spending
is on hold while the Prime comparison is built.**
No command loads that file as authorization.

The proposed allocation reserves $1 of the acquisition category for the smoke
test and $14 for paired acquisition. Held-out and cold boot retain $10 each, so
the total stays at $35. Only the smoke allocation is approved. Frozen and evolving
arms receive equal per-task allowances within each paired stage.

After approval, private credential setup, and successful isolation tests, run
the capability smoke test before acquisition:

```sh
make smoke LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=1
```

Set the provider credentials and input/output rates as described below. The smoke
command requires the same complete negative-test proof as every other live entry
point. It creates external context, asks the root model to query it and compute a
summary in SCI, sends that result to a real child model, and requires a child SCI
calculation and a matching parent answer. A verifier checks the ordered tool
results, provider receipts, and parent/child evidence. Scripted responses cannot
pass as live model evidence. Failed smoke attempts return an error and preserve
their traces and charges; do not repeat them without accounting for prior spend.

Each smoke directory contains `manifest.edn`, `controller.sqlite`, `context.edn`,
`events.jsonl`, `generated-code.edn`, and `report.edn`/`report.json`. A smoke pass
establishes capabilities only. It does not establish learning or a retained skill.

### Claude subscription smoke

The subscription transport uses the unmodified Claude Code 2.1.310 binary and the
operator's normal Claude login. From the terminal where login and Docker work:

```sh
source var/worker.env
make smoke-subscription LIVE=1 MODEL=claude-sonnet-5-5 MAX_USD=1
```

No API key is needed for this command. `python3 scripts/claude_subscription.py
doctor` checks version and subscription authentication without model inference;
it reports only safe account metadata. The smoke command enforces the actual SCI
gate before provider setup, and the transport checks it again before each call.

The CLI runs with safe/restricted modes, no native tools, no MCP servers, no
custom skills, and no persisted CLI session. The parent and recursive child use
the same controller and SCI broker. Each model request gets a fresh CLI process
and the explicit serialized controller history. The transport strips inherited
API/cloud credentials and routing, uses the ordinary OAuth login, pins the binary
hash for the run, disables retries and prompt caching, and limits each invocation
to one turn and 2,048 output tokens. Source is never executed by the CLI transport.

`transport/<request-id>/` preserves the serialized request, fixed system prompt,
CLI stream, stderr, and completion status. The verifier deduplicates content
blocks by provider message ID and checks final output counts against the stream
and per-model totals. Extra model calls, native tool use, ambiguous usage, and
model mismatches fail the run. No automatic inference retry occurs.

The shared controller reserves tokens and a conservative **API-rate equivalent**
at $2/M input and $10/M output before every root or child call. It retains unknown
reservations and records known consumption before rejecting a failed response.
The report labels this budget basis and leaves `model-cost-usd` and `invoiced-usd`
unknown for subscription runs. CLI cost estimates are not invoices. Its
`--max-budget-usd` is also an estimated-spend stop threshold, not a provider-side
billing guarantee. Account usage-credit settings can affect actual billing.

This adapter is implemented only for the capability smoke. Six live responses
passed its receipt checks in run `smoke-1793049211459`. This is not a native Prime
comparison or a learning result.
Subscription acquisition and final-evaluation adapters remain to be implemented
if this route is retained. Benchmark runs must control for the added CLI runtime.

Sources: [subscription usage](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan),
[CLI flags](https://code.claude.com/docs/en/cli-reference),
[usage semantics](https://code.claude.com/docs/en/agent-sdk/cost-tracking),
[stream events](https://code.claude.com/docs/en/agent-sdk/streaming-output).

### Direct API experiments

Acquisition, final evaluation, and cold boot currently use Anthropic Messages.
It uses API version `2023-06-01`; pin `MODEL` to an exact identifier supported by
the account. The returned identifier must match. Configure credentials in the
operator environment. Never put them in a config file or command argument.

```sh
export ANTHROPIC_API_KEY='<set privately in your shell>'
export INPUT_USD_PER_M='<operator-verified positive input price>'
export OUTPUT_USD_PER_M='<operator-verified positive output price>'
make evolve LIVE=1 MODEL='<pinned-model>' MAX_USD='<positive-cap>'
```

No default model, price, or spending cap is supplied. Token counting and inference
requests occur only after a durable conservative reservation. Uncertain provider
outcomes keep their reservations and are not silently retried. Rates must match
the model and billing tier. No caching, hosted tools, or provider-side execution
is requested. Limits live in `config/experiment.edn`. All children share the
task budget. The acquisition cap covers both frozen and evolving arms. Each
arm/task receives an equal, non-transferable allowance and fresh context. Both
arms may stage and test candidates. Only evolving retains approved code.
Errors and exhaustion save task checkpoints and the approved export.

To resume after a controller interruption, use the original total cap and rates:

```sh
make resume RUN_ID='<model-run>' LIVE=1 MODEL='<same-model>' MAX_USD='<original-total-cap>'
```

Resume skips recorded tasks. It keeps uncertain charges reserved, records an
interrupted task as failed, and never repeats an uncertain provider call. It
continues only unused task allowances. A final-evaluation seal prevents resume.

For a real export, final evaluation also requires `LIVE=1`, the same `MODEL`, and
an explicit new `MAX_USD`. The same commands work for offline fixture exports
without these flags:

```sh
make evaluate EXPORT='<real-export>' PROFILE=heldout LIVE=1 MODEL='<same-model>' MAX_USD='<cap>'
make cold-boot EXPORT='<real-export>' LIVE=1 MODEL='<same-model>' MAX_USD='<cap>'
```

The operator/controller owns these commands. They are absent from learner tools.
Final and cold-boot splits are distinct and sealed before learning. Each arm/case
gets equal caps and a fresh session/database. Both arms can use SCI, recursion,
messages, and a temporary per-task policy. Only approved evolving artifacts cross
tasks. Final scores never return to the learner. Each split has an atomic use
reservation. A failed evaluation leaves its seal; inspect the evidence rather
than rerunning until a favorable result appears. Further tuning needs a new run
and new final split. Real-model end-to-end behavior remains unverified here.

## Records and interpretation

Each `var/runs/<id>/` contains the relevant records below. Evaluation reports
use `var/evaluations/<id>/`; replay and demo accept those IDs too.

- `manifest.edn`: configuration, runtime, source hashes, dependency versions.
- Fixture `controller.sqlite`, or live `tasks/<arm>-<index>/controller.sqlite`:
  durable sessions, mailbox, budgets, events, promotions. Live task directories
  also contain their artifacts, episode records, and checkpoints.
- `artifacts/<sha256>.edn`: immutable source, forms, interfaces, dependencies,
  parent and author provenance. Controller receipts hold lifecycle/test evidence.
- `episodes/*.edn` and `*.jsonl`: worlds, observations, actions, metrics, hashes.
  Full world records are evaluator-only; learners receive a separate whitelist.
- `events.jsonl`: controller event export.
- `report.edn` / `report.json`: paired comparisons, provenance, and costs.
- `export/`: executable whitelist, complete file list, hashes, and literal audit.

The initial recorded fixture finished every case. Mean simulated makespan was
209.56 serial, 82.67 retained fixture, 91.00 FIFO, and 81.22 estimate baseline.
The retained fixture does not beat every baseline. Its advantage over the serial
fixture survives a fresh JVM, but that is not evidence of model learning.
Real provider calls and spend are zero; scripted adapter calls are reported separately.
Do not treat tasks from one library as independent learning runs.

Read [ARCHITECTURE.md](ARCHITECTURE.md), [THREAT_MODEL.md](THREAT_MODEL.md),
[EXPERIMENTS.md](EXPERIMENTS.md), [DECISIONS.md](DECISIONS.md),
[PROGRESS.md](PROGRESS.md), and [ACCEPTANCE.md](ACCEPTANCE.md) for scope and evidence.

The SCI negative suite and live capability smoke have passed. The next step is
to finish the native Prime and Aljure task adapters and common budget enforcement.
Further spending is on hold while the Prime/OOLONG comparison is prepared.
[benchmark/README.md](benchmark/README.md) describes the external input and scoring
tools and the remaining live adapter work. These tools make no model calls.
No real head-to-head or learning result exists yet. The retained-policy/workflow,
frozen-control, cold-boot, and fallback experiments remain required for a learning
claim. Report improvement, regression, or no effect from actual runs.

## Shared language backend and offline benchmark

The broker selects `ClojureExecutionBackend` or `PythonExecutionBackend` from the
run config's `:execution-language` (`:clojure` by default). Both use the existing
controller, context broker, recursive sessions, messages, budgets, and Docker
supervisor. Python permits ASTs, compilation, higher-order functions, classes and
generated modules. Python artifacts now use isolated AST validation and the shared
registry, structural patches, promotion transaction and export path. The main
pilot exercises frozen task-local execution. `artifact-parity` separately checks
retention and fresh-process loading with developer-authored fixtures.
See [the artifact contract](research/LANGUAGE_ARTIFACTS.md) for current evidence
and limits. The full four-condition learning study is still incomplete.

From `repl-lab`, with Docker running:

```sh
make python-worker-setup
source var/worker.env
source var/python-worker.env
make python-isolation-test
make language-parity OUT=var/benchmarks/my-parity
make artifact-parity OUT=var/benchmarks/my-artifacts
make artifact-compare RUN=var/benchmarks/my-artifacts
make benchmark-fixtures OUT=var/benchmarks/my-controls
make benchmark-pilot OUT=var/benchmarks/my-pilot
make benchmark-compare RUN=var/benchmarks/my-pilot
make benchmark-report RUN=var/benchmarks/my-pilot
make prime-doctor
```

Use a new `OUT` directory for each run; existing evidence is not overwritten.
These commands make no provider calls. Parity checks use actual containers.
Run container benchmarks separately from large builds and other test suites.
Worker timeouts remain failures; do not raise the isolation limits to hide them.
The shared language pilot selects `:command-format :json`. Both arms use common
instructions plus a language appendix; historical EDN runs remain supported.
The pilot runs four paired FIXTURE cases through scripted root/child agents,
then scores their executable programs on separate inputs in fresh workers.
Known-correct, known-wrong, and malformed programs test the scorer. The Python
comparison command independently rechecks saved outputs and source/trace hashes.
It prints a reproducible report; it does not claim a model or language win.

`make prime-doctor` verifies the source pin, native image, isolation proof and
source-matched fixture receipt. The native fixture now passes one exact Aljure
task using Prime's original Rust loop and Python kernel. Its provider is scripted.
See [native adapter evidence](research/NATIVE_PRIME_ADAPTER.md).
The doctor still exits 2 for the missing live gateway and retention export. The
`benchmark-live`, `benchmark-learn`, `benchmark-coldboot`, and `benchmark-prime`
targets also exit 2 with an explicit unimplemented message. They never substitute
fixtures for inference. New live work needs a frozen protocol, complete parity,
and explicit operator authorization.

To reproduce the native offline integration with a new output directory:

```sh
source var/prime-worker.env
make prime-fixture OUT=var/benchmarks/my-prime-fixture RUN=var/benchmarks/language-pilot-20261026-json
make prime-recursive-fixture OUT=var/benchmarks/my-prime-child RUN=var/benchmarks/language-pilot-20261026-json
make gateway-fixtures OUT=var/benchmarks/my-gateway-fixture
```

For a fresh installation, run `make prime-worker-setup`, source its generated
environment file, and run `make prime-isolation-test` first. No upstream Prime
source is changed. This command cannot dispatch real provider inference.
