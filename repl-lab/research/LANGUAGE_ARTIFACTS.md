# Shared executable artifact contract

Status: **FIXTURE** container validation passed for both languages, including new
JVMs and interpreters. No model has acquired a retained skill in these
tests. No language advantage or held-out transfer result is established.

## Reused controller

Both backends use the existing artifact store, dependency hashes, immutable
versions, broker, SQLite sessions, promotion transaction, frozen-state gate and
bundle whitelist. No second controller or memory database was added. A run selects
`:execution-language :clojure` or `:python`. `:command-format :json` selects the new
common model command envelope. Legacy runs keep their EDN contract by default.

The JSON instructions have one common file and one language appendix. Context
queries, child calls, messages, artifact calls, staging and completion use the same
command shapes. Clojure patch paths and replacement values are EDN strings inside
JSON, to preserve symbols and list/vector distinctions. Python uses JSON AST
objects and array paths. Workflow source uses the same JSON representation for
both conditions; the controller converts it to its existing declarative data.

`artifact/subtree` supplies the canonical subtree hash. `artifact/patch` requires
the base artifact hash, explicit path and expected subtree hash. Stale targets
fail. `artifact/call` resolves only the session's pinned approved dependency closure
and executes its export in a fresh worker. The controller records arguments,
result, artifact hash and declared dependency hashes. This records an export call;
it does not prove that every declared dependency executed internally.

## Language-specific behavior

| Property | Clojure | Python |
|---|---|---|
| Stored representation | EDN-readable function forms | Python module AST with node/fields objects |
| Export contract | One explicit `fn` with fixed positional arity | One named top-level `def` with fixed positional arity; other module code is permitted |
| Syntax validation | Bounded EDN reader in controller; no host evaluation | Parse and compile, never execute, in a separate verified Docker worker |
| Structural rendering | `pr-str`, followed by a fresh parse | `ast.unparse`, followed by AST round-trip validation |
| Dependencies | Named definitions loaded in topological order | Module definitions loaded in topological order |
| Transient computation | SCI built-ins; generated source can return through broker | AST, compile/exec, classes, generated modules, higher-order functions |
| Saved comments | Removed in canonical export | Removed in canonical export |
| Docstrings/embedded data | Literals are listed by export audit | Docstrings and string/numeric/encoded literals are listed by export audit |

Python parsing uses a separate worker so a task's Python code cannot monkey-patch
the parser used for acceptance. Execution never occurs in the controller. Syntax
and interface validation are not correctness tests. Top-level Python statements
execute only when the module loads in an isolated execution worker.

Dependency validation rejects missing artifacts, mixed execution languages and
conflicting exported names. The language marker is optional for historical Clojure
artifacts, preserving their existing hashes. Verification checks both the content
hash and agreement between source, forms and the exported interface.

Bundle schema 2 adds the optional language marker. The loader still accepts schema
1. Exported files contain only forms, interface, category, dependency hashes,
language and provenance. They omit source conversations, session IDs and parent
receipts. Restoration creates new envelopes and remaps dependency hashes. Manifest
hashes detect accidental changes; these locally writable files are not tamper-proof.
Literal audits are inspection aids, not proofs that code contains no memorized data.

## Promotion rules

The existing paired scheduling rule remains the default. A separately selected
`:objective :verified-cases` rule accepts explicit independently checked boolean
outcomes. It requires no regression on any paired development case and a
preregistered minimum increase in verified cases. The controller recomputes evidence
against its frozen rule before activating an artifact. The model has no promotion
command. This adds a language-neutral acceptance mechanism; it does not complete
the four-condition continual-learning experiment.

The library-locked control in `artifact-parity` tests refusal of retention
commands while ordinary task-local REPL code still works. It is not the complete
frozen acquisition condition. The existing scheduling acquisition runner permits
task-local proposals in both arms and discards the frozen arm's artifacts at the
task boundary. The future four-condition language runner must preserve that
within-task capability parity; simply disabling proposals in its frozen arm would
change more than cross-task retention.

## Reproduction and limits

```sh
source var/worker.env
source var/python-worker.env
make artifact-parity OUT=var/benchmarks/artifact-parity-unique
make artifact-compare RUN=var/benchmarks/artifact-parity-unique
```

This command runs hand-written correct and incorrect functions in real workers.
It tests staging, a structural patch, dependency composition, independent
development checks, promotion, denied calls to unapproved code, frozen task-local
execution, export, a new JVM, new interpreter processes, a fresh scripted model
conversation, invocation records and a contract-compatible removal control.
Fixture transfer inputs differ from its development inputs. They are developer
test cases, not a sealed held-out experiment. No provider inference is used.

The first run at `var/benchmarks/artifact-parity-20261026` passed acquisition checks
for both languages, then failed in the Clojure cold process with `Worker wall-time
limit`. Its artifacts and failure log are preserved. Full unit suites and a large
Docker image download/unpack were active concurrently. Contention is a possible
cause, not an established diagnosis. The 10-second expression limit was not raised.

The serial run at `var/benchmarks/artifact-parity-20261026-serial` passed every
gate. Both languages retained a composed fixture function through a new JVM,
new interpreter and fresh scripted conversation. Each returned correct outputs
for four new fixture inputs. Contract-compatible fallback functions returned
zero correct outputs on those four inputs. An independent Python checker verified
the arithmetic, paired development acceptance, exported file hashes and fresh
invocation events. Its report is `independent-comparison.json` in that run.
This is an engineering control with known hand-written answers, not learned transfer.

Remaining limitations:

- Python syntax validation currently starts fresh workers repeatedly. This has
  extra local overhead. It must be measured or reduced before economic comparison.
- Source is bounded to 32 KiB and worker messages to 64 KiB. Python's verbose AST
  can hit the wire limit before a similarly sized Clojure function does. Current
  small fixtures do not establish parity for large generated programs.
- Python AST rendering requires a canonical parse/unparse round trip. Some
  hand-constructed noncanonical ASTs are rejected even if Python can compile them.
- Python module globals and Clojure definitions have different semantics. An export
  call is evidence of execution, not proof of purity or all dependency invocations.
- Per-worker CPU and peak-memory accounting is not yet complete. Reported limits
  are enforced controls, not measured resource consumption.
- Live instructions, neutral task promotion, repeated acquisitions and the full
  four-condition learning study still need real-model validation and authorization.
