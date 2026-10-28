# Computational compaction hypothesis

**Question.** Do agents become more efficient, reliable or scalable when they
exchange immutable references to computation and exact results, instead of
repeatedly transmitting large text?

Two mechanisms that must not be conflated:

- **Lossless result compaction (systems).** A large exact value travels by
  reference: paging, a handle, or a file. Its content is unchanged. This
  removes transport failures and model-context copies. It cannot make an agent
  reason better.
- **Semantic computational compaction (learning).** Repeated reasoning is
  replaced by a reusable program or verified procedure. This is a learning
  claim, tested by Q-LEARNING (`EXECUTABLE_LEARNING_EXPERIMENT.md`), and must
  pay for its acquisition and validation.

## Related mechanisms (not new)

- Native Prime: a persistent Python REPL with a filesystem. The final answer is
  a file the harness collects (already lossless and out of model context).
  Prime also has asynchronous subagents, skills, and refine and compaction of
  its own prompt state (`PRIME_PARITY_MATRIX.md`).
- Aljure today:
  - content-hashed immutable code artifacts (`src/repl_lab/artifact.clj`),
    with inspect, subtree, patch and call operations;
  - bounded results with `full-result` paging (`SCI_EXECUTION_CONTRACT.md`);
  - and, after this branch, paged answer delivery.
- General precedents: content-addressed storage, futures and promises as
  handles, and program caching. Any novelty must come from **verification and
  selection of reusable computation**, not from references themselves.

## Falsifiable hypotheses

| ID | Hypothesis | Falsified if |
| --- | --- | --- |
| HC1 (transport) | Exact delivery by paging or handle removes answer-size failures without changing scores on small-answer tasks. | Any large-answer task still fails to deliver an answer the worker computed, or small-answer scores change beyond run-to-run variance. |
| HC2 (handles vs paging) | Immutable host-side handles add value over paging only through durability (survive worker loss) or sharing (cross-session). | On the same tasks, handles show no difference from paging in completion, cost or latency. In that case: keep paging and drop handles. |
| HC3 (recursion) | Parent and child exchanging artifact references beats a single agent with handles on decomposable tasks. | A single agent with handles matches or beats it on accuracy, cost and latency (expected on OOLONG, where no harness used children). |
| HC4 (semantic) | Verified reusable programs reduce cost per solved held-out task after break-even. | Q-LEARNING falsification rules (C not above A; C equal to B; negative transfer; break-even never reached). |

## Claim boundaries

- A transport fix that raises scores on large-answer tasks is a **systems
  correction**, not improved intelligence. Report it separately from reasoning
  effects (`RECURSIVE_COMPACTION_ABLATION.md`).
- A hash or receipt proves identity and integrity only. It never proves
  semantic correctness unless that property was tested or proved, and it is
  labelled as such (`ARTIFACT_SECURITY_CONTRACT.md`).
