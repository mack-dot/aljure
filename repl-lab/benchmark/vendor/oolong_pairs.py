"""Official OOLONG-Pairs scoring functions, copied without body changes.

Source: PrimeIntellect-ai/research-environments
Revision: ba10ef5a303943a08e1ccf92f9c0d63b1159b369
Path: environments/long_context/oolong_pairs/oolong_pairs/taskset.py
License: Apache-2.0; see LICENSE.oolong-pairs.
This excerpt removes the Verifiers runtime dependency. Scoring is unchanged.
"""
import re

PROMPT_PREFIX = "The context window contains thousands of general-knowledge questions, one per line. Each line has a User ID, which is not necessarily unique (each User ID can be associated with multiple questions). Each question has an answer that can be described as one of 6 categories: 'numeric value', 'entity', 'location', 'description and abstract concept', 'abbreviation', 'human being' — they are not explicitly labeled, so you must infer the label from the semantics of each question.\n\nYou will be asked to compute exact aggregate label statistics over pairs of users. Do not guess, estimate, or approximate the result — calculate the exact answer.\n\n"


def _strip_think_tags(text: str) -> str:
    """Remove all <think>...</think> sections from the given text."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)


def _parse_pairs(answer) -> set[tuple[int, int]]:
    """Parse user-ID pairs from an answer string (or list of strings), order-normalized."""
    pairs: set[tuple[int, int]] = set()
    items = answer if isinstance(answer, list) else [answer]
    for item in items:
        if not isinstance(item, str):
            continue
        matches = re.findall(r"\((\d+),\s*(\d+)\)", item)
        if not matches:
            matches = re.findall(r"(\d+),\s*(\d+)", item)
        for a, b in matches:
            id1, id2 = int(a), int(b)
            pairs.add((id1, id2) if id1 < id2 else (id2, id1))
    return pairs


def _pair_metrics(predicted: str, gold_pairs: set[tuple[int, int]]) -> dict[str, float]:
    """Compute precision / recall / F1 of predicted pairs against the gold set."""
    pred_pairs = _parse_pairs(_strip_think_tags(predicted or ""))
    if not pred_pairs and not gold_pairs:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    correct = len(pred_pairs & gold_pairs)
    precision = correct / len(pred_pairs) if pred_pairs else 0.0
    recall = correct / len(gold_pairs) if gold_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}
