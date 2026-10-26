# Decisions

- 2026-10-26: The workspace was empty and was not a Git repository. Create
  `repl-lab/`; do not touch production apps, infrastructure, or global settings.
- Pin Clojure 1.11.3 and data.json 2.5.0, which are cached locally. Use Java 21.
  The offline launcher reads these exact jars and never downloads dependencies.
  Standard `deps.edn` remains the connected-machine setup path.
- Pin SCI 0.10.49 for the isolated worker. Its API was checked against the tagged
  official README/API. It is absent from this machine's Maven cache.
- Use Python's SQLite bridge for durability because sqlite-jdbc is not cached.
  Record the actual Python and SQLite runtime versions in manifests.
- Docker access is denied in this sandbox. Maven DNS resolution also fails.
  Generated-code execution must fail closed. Continue trusted fixture tests.
- Order simultaneous events by failure, recovery, then completion, then stable
  event sequence. Dispatch happens only after pending events at the current time.
- Use keyed SHA-256 workload values. Policies cannot alter the random stream.
- Keep baselines outside the initial learner library. Use fixtures only to test
  evolution plumbing. Do not attribute their authorship to an experimental model.

Official references checked on 2026-10-26:

- https://clojure.org/reference/deps_edn — pinned dependency coordinates.
- https://clojure.github.io/data.json/ — `read-str` and `write-str`.
- https://github.com/babashka/sci/blob/v0.10.49/API.md — `init`, `eval-string*`.
- https://github.com/babashka/sci/blob/v0.10.49/README.md — classes and permissions.
- https://docs.docker.com/engine/containers/resource_constraints/ — resource flags.
