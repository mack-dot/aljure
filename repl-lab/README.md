# REPL Lab

A local Clojure experiment for executable skill retention. The simulator, artifact
registry, controller, and offline fixture demo run today. The SCI and real-model
paths are implemented but **not validated on this machine**. Docker socket access
is denied, SCI is not cached, and no live spending budget was supplied.

**No experimental model has produced a retained skill. No model has changed its
harness. No model benefit has been shown to survive cold boot.** H1 and H2 remain
untested. The dashboard and recorded measurements are SYNTHETIC FIXTURE results.

## Setup

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
make replay RUN_ID=fixture-1793035647201
make evaluate EXPORT=var/runs/fixture-1793035647201/export PROFILE=heldout
make cold-boot EXPORT=var/runs/fixture-1793035647201/export
make demo RUN_ID=fixture-1793035647201
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
node check-render.mjs ../var/runs/fixture-1793035647201
```

Fixture evaluation resolves only exact, compiled developer fixture forms. Any
other source must use SCI isolation. Fixture cold boot starts a new JVM and reads
only the exported executable library for skill state. It is a process-recovery
test, not an H2 model experiment. Baseline policies remain separate from that library.

## Isolated worker

On a machine with working Docker, select a **digest-pinned Clojure/JDK 21 image**
that includes the Clojure CLI. Build the worker locally:

```sh
docker build -f worker/Dockerfile --build-arg BASE_IMAGE='<image>@sha256:<digest>' -t repl-lab-worker .
export REPL_LAB_WORKER_IMAGE="$(docker image inspect --format '{{.Id}}' repl-lab-worker)"
make isolation-test
```

The supervisor never pulls an image. It verifies the local image ID and Docker
resource controls, creates a restricted container, checks its settings, and kills
the entire container on timeout. No host paths or provider keys are mounted.
The image contains only the worker and dependencies. SCI has no host evaluator,
filesystem, network, process, or unrestricted Java access.

The negative suite tests loops, allocation, oversized results, file reads/writes,
process and network access, evaluator access, and reader evaluation. Missing
isolation returns **UNVERIFIED with exit 2**, never a passing result. Live evolution
requires a successful proof for the same image ID.

## Live commands — explicit authorization required

The only live provider adapter currently implemented is Anthropic Messages.
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
controller budget. Errors and exhaustion save a checkpoint and approved export.

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

Each `var/runs/<id>/` contains:

- `manifest.edn`: configuration, runtime, source hashes, dependency versions.
- `controller.sqlite`: durable sessions, mailbox, budgets, events, promotions.
- `artifacts/<sha256>.edn`: immutable source, forms, interfaces, dependencies,
  parent and author provenance. Controller receipts hold lifecycle/test evidence.
- `episodes/*.edn` and `*.jsonl`: worlds, observations, actions, metrics, hashes.
  Full world records are evaluator-only; learners receive a separate whitelist.
- `events.jsonl`: controller event export.
- `report.edn` / `report.json`: fixture paired comparisons and costs.
- `export/`: executable whitelist, complete file list, hashes, and literal audit.

The initial recorded fixture finished every case. Mean simulated makespan was
209.56 serial, 82.67 retained fixture, 91.00 FIFO, and 81.22 estimate baseline.
The retained fixture does not beat every baseline. Its advantage over the serial
fixture survives a fresh JVM, but that is not evidence of model learning.
Provider calls and spend are zero; scripted adapter calls are reported separately.
Do not treat tasks from one library as independent learning runs.

Read [ARCHITECTURE.md](ARCHITECTURE.md), [THREAT_MODEL.md](THREAT_MODEL.md),
[EXPERIMENTS.md](EXPERIMENTS.md), [DECISIONS.md](DECISIONS.md),
[PROGRESS.md](PROGRESS.md), and [ACCEPTANCE.md](ACCEPTANCE.md) for scope and evidence.

The highest-value next experiment is one capped, independently repeated live
learning protocol after the SCI negative suite passes. Test both the retained
policy and changed workflow against frozen controls, then use the separate
cold-boot split and compatible fallback. Report improvement, regression, or no effect.
