"""LongBench Pro metrics, ported from caskcsg/longcontext LongBench-Pro/modules/utils.py at commit
49ee3192bd2f9176515444370348aa55db5348ce (source sha256 recorded in upstream.lock.json). The repository has no
LICENSE file; its license is unverified. This port therefore re-implements rather than copies: the normalization
helpers, Accuracy, F1_Score, SubEM and Pairwise_Accuracy follow the upstream definitions line for line, and NDCG
re-implements trec_eval's ndcg_cut (which upstream calls through pytrec_eval) with the upstream gains: the answer
list defines relevance len(answers) - i for the item at position i, k = len(answers), and the prediction's own
order is the ranking. The Summary metric (T4, ROUGE-L plus an embedding model) is not ported; T4 is excluded.
benchmark audit holds this file to upstream behaviour on a fixed probe set (test_python/test_exploratory.py)."""
import math
from itertools import combinations


def get_answer_area(text):
    if "[Answer]" in text or "[答案]" in text:
        if "[Answer]" in text:
            start = text.rfind('[Answer]')
            if start != -1:
                text = text[start + 8:]
        else:
            start = text.rfind('[答案]')
            if start != -1:
                text = text[start + 4:]
    return text.strip()


def fix_space(text):
    return ' '.join(text.split())


def normalize_answers(answers):
    return [fix_space(a.lower().strip()) for a in answers]


def normalize_prediction(prediction):
    return [fix_space(p.strip()) for p in get_answer_area(prediction).lower().split("\n")]


def Accuracy(answers, prediction):
    answers, predictions = normalize_answers(answers), normalize_prediction(prediction)
    if not answers or not predictions:
        return 0.0
    return 1.0 if answers[0] == predictions[0] else 0.0


def F1_Score(answers, prediction):
    answers, predictions = normalize_answers(answers), normalize_prediction(prediction)
    answer_set, prediction_set = set(answers), set(predictions)
    common = answer_set & prediction_set
    if not common or not prediction_set or not answer_set:
        return 0.0
    precision, recall = len(common) / len(prediction_set), len(common) / len(answer_set)
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def SubEM(answers, prediction):
    answers, predictions = normalize_answers(answers), normalize_prediction(prediction)
    if not answers or not predictions:
        return 0.0
    return sum(1.0 for a in answers if a in predictions) / len(answers)


def _ndcg_cut(relevance, ranking, k):
    """trec_eval ndcg_cut.k: DCG over the first k ranked items with gain = relevance (0 if unjudged),
    discount 1/log2(rank+1); ideal DCG from the relevance values sorted descending, cut at k."""
    dcg = sum(relevance.get(item, 0) / math.log2(rank + 2) for rank, item in enumerate(ranking[:k]))
    ideal = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(sorted(relevance.values(), reverse=True)[:k]))
    return dcg / ideal if ideal > 0 else 0.0


def NDCG(answers, prediction):
    answers, predictions = normalize_answers(answers), normalize_prediction(prediction)
    if not answers or not predictions:
        return 0.0
    k = len(answers)
    relevance = {a: len(answers) - i for i, a in enumerate(answers)}
    # pytrec_eval ranks the run by its scores, len(predictions) - i, so the prediction order is the ranking;
    # a repeated line keeps the score of its last occurrence in upstream's dict, which equals its last position.
    ranked = {p: len(predictions) - i for i, p in enumerate(predictions)}
    ranking = [p for p, _ in sorted(ranked.items(), key=lambda kv: (-kv[1], kv[0]))]
    return _ndcg_cut(relevance, ranking, k)


def Pairwise_Accuracy(answers, prediction):
    answers, predictions = normalize_answers(answers), normalize_prediction(prediction)
    if len(answers) < 2 or len(predictions) < 2:
        return 0.0
    n_total = len(predictions) * (len(predictions) - 1) // 2
    index = {p: i for i, p in enumerate(predictions)}
    n_correct = 0
    for a, b in combinations(answers, 2):
        if a in index and b in index and index[a] < index[b]:
            n_correct += 1
    return n_correct / n_total


METRICS = {
    "T1.1 Global Cohesive Retrieval": NDCG, "T1.2 Key-Snippet Retrieval": NDCG,
    "T2.1 Global Timeline Reconstruction": Pairwise_Accuracy, "T2.2 Local Causal Chain Sorting": Pairwise_Accuracy,
    "T3.1 Multi-Doc Integration QA": Accuracy, "T3.2 Single-Hop Fact QA": Accuracy,
    "T5.1 Full-Sentence Citation Alignment": F1_Score, "T5.2 Key-Statement Citation Alignment": F1_Score,
    "T6.1 Large-Scale Document Clustering": SubEM, "T6.2 Targeted Subset Cluster Identification": F1_Score,
    "T6.3 Global Frequency Analysis": Pairwise_Accuracy,
    "T7.1 Global Conflict & Inconsistency Localization": F1_Score, "T7.2 Targeted Rule or Condition Violation Detection": F1_Score,
    "T7.3 Comprehensive Error & Anomaly Sweep": F1_Score,
    "T8.1 Structured Multi-Source Consistency Verification": SubEM, "T8.2 Single-Source Targeted Aggregation": SubEM,
    "T8.3 Long-Context Procedural State Tracking": SubEM,
    "T9.1 Dependency-Aware Multi-Version Impact Analysis": F1_Score, "T9.2 Localized Interface Change Detection": F1_Score,
    "T10.1 Large-Scale In-Context Rule Induction": SubEM, "T10.2 Targeted Example-Based Rule Induction": SubEM,
    "T11.1 Long-Range Entity & Commitment Tracking": Accuracy, "T11.2 Short-Range Reference Resolution & State Query": Accuracy,
}


def score(secondary_task, answers, prediction):
    """Upstream calculate_metric: an empty prediction scores 0; the metric is chosen by the secondary task."""
    if prediction == "" or secondary_task not in METRICS:
        return 0.0
    value = METRICS[secondary_task](answers, prediction)
    assert 0.0 <= value <= 1.0
    return value
