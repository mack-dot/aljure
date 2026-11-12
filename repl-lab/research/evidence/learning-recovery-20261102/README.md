# Evidence index — executable learning recovery

No new model calls. No held-out task content was opened. Existing live results
were read without changing their answers, scores, plans, or artifacts.

- `acquisition-audit-v2.json`: current forensic audit, with matched responses,
  receipts, prompt properties, and source hashes. The earlier audit remains;
  v2 removes tool-call IDs from instruction grouping and adds per-arm counts.
- `historical-learning-report-v2.json`: current post-hoc accounting/reuse report.
  The earlier report remains as a superseded analysis attempt. It incorrectly
  applied the new three-trajectory development gate to the old nine-trajectory
  study and called it incomplete. V2 marks that gate NOT_APPLICABLE. All nine
  historical trajectories are complete. V2 also separates promotion-process
  time from actual candidate validation time and counts missing tool results.
- `historical-summary.json`: pooled descriptive metrics from the original runs.
- `pilot1b/`: recovery report, regenerated plans/preflights, proofs, historical
  file hashes, and the seal for the separately stored rebuilt worker image.
- `mechanism/`: real-worker isolation, transport, promotion and reuse proofs;
  the relay responses are scripted fixtures, not autonomous learning evidence.
- `verification-summary.json` and test logs: tests and initial test-attempt
  failures. Those failures changed no historical model results.

The acquisition fixture passes 16 checks, including new-process reuse on an
unseen record and an exact-cache miss on that record. The subscription relay
passes all 15 checks. Both made zero real model requests.

The image archive stays under the recovery checkout's ignored `var/` directory;
it is about 600 MB and is not committed. Its exact path and digest are in the
image seal. `index.json` hashes the files in this directory except itself.
