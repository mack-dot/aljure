# Harness latency (Aljure against native Prime)

Where Aljure's wall time went in A1, what was changed, and what was measured
after. Offline evidence only; no live run has used the changes yet. Related:
`PRIME_PARITY_MATRIX.md` row 4b, `SCI_EXECUTION_CONTRACT.md`.

## 1. A1 breakdown

Source: A1 (`sci-ablation-bounded-64k`, plan `d5038fe2…`), cases 1–8, from
each arm's `gateway/transport.jsonl` and worker audits. Totals over 8 arms:

| | Aljure | Prime |
| --- | --- | --- |
| Wall time | 805 s | 444 s |
| Before the first model request | 60 s | 76 s |
| Model requests | 345 s | 295 s |
| **Harness time between model requests** | **345 s** | **51 s** |
| After the last model response | 54 s | 22 s |

Model time was similar. Aljure lost its time between model calls:

1. **Cold SCI workers: 5.9–15 s each** to reach readiness. The image ran
   `clojure.main` from source, so every worker compiled the worker and all of
   SCI on its one CPU. Loading the context took about 0.1 s, and model
   expressions took 3–500 ms.
2. **Ledger: 1.6–3.8 s per model step.** Every store read and write started a
   new `python3` process, and every write re-read, parsed, canonicalized and
   rewrote the whole ledger (0.5 MB after 7 steps). One model step makes about
   7 writes and 5 reads: about 1.2 s at load 4, and more at A1's load of 21.
3. **Restarts from the delivery bug**: 4–5 cold workers in each failed arm
   (fixed by paged delivery).

Prime's kernel stays warm in its container, and its gaps were about 1 s.

## 2. Changes (commit `0c4c2d5`)

| Change | Effect, measured offline |
| --- | --- |
| One long-lived store process per ledger, with a cache checked against the stored revision. Writes stay compare-and-set; a value that could not be read back is refused at write time. | One step's ledger work: about 1.2 s → 0.18 s (real A1 ledger, load 4). Reads under 1 ms. |
| Worker image `58550c92…`: worker and SCI compiled ahead of time, plus a class-data-sharing archive. Sandbox flags, deny list and SCI configuration unchanged. | Cold start to readiness: 5.7 s → 1.15 s (median of 5, real sandbox flags). Isolation 9/9 with exact boundaries at 64 KiB and 1 MiB; SCI contract passes at both. |
| Prewarm (benchmark tasks only): the root worker opens during the first model call; a retired worker's replacement opens at once. | Worker start overlaps the model call. |

## 3. Scripted end-to-end check (relay fixture, zero model calls)

The same scripted flow through the real gateway, relay and containers.

| Run | Aljure wall | Prime wall | Aljure gaps between calls |
| --- | --- | --- | --- |
| `step1` (before) | 27.7 s | 18.8 s | 1.3, 9.5, 1.9, 8.7, 2.1 s |
| `ablation/bounded-64k` (before) | 30.4 s | 17.7 s | 1.5, 10.1, 1.7, 10.1, 2.3 s |
| `speed` (`0c4c2d5`, load 13) | **5.8 s** | 13.6 s | 0.21, 1.38, 0.13, 1.72, 0.25 s |

O1 delivery benchmark (`repl-lab.delivery-benchmark`; one cold worker per
row, start included). Paged delivery was exact at every size both times.

| Answer (characters) | Paged, image `4e65f5bb…` | Paged, image `58550c92…` |
| --- | --- | --- |
| 10,000 | 6.3 s | 2.3 s |
| 100,000 | 5.7 s | 1.6 s |
| 500,000 | 6.5 s | 2.2 s |
| 2,000,000 | 7.0 s | 2.9 s |
| 8,000,000 | 10.5 s | 5.2 s |

## 4. Still open

- **No live measurement.** Model time (about 43% of A1's Aljure wall time)
  is unchanged. A live run must confirm the gain.
- **Compute boundary** (parity row 4). The ledger and controller run on the
  host; Prime's loop shares its 1-CPU container. Part of this gain is host
  work, so disclose it with any timing claim.
- Each worker start still runs `docker info` twice (controller check and
  supervisor preflight), 0.1–0.9 s each. Prewarm hides this for the first
  worker.
- Each ledger write still serializes the whole ledger (30–40 ms at 0.5 MB),
  and the ledger grows with every tool result.
- End-of-task cleanup still waits for container removal (2–10 s in A1).
