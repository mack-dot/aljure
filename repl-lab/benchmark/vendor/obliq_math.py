"""OBLIQ-Bench, Math Meta-Program subset (arXiv 2605.06235; HF dianetc/OBLIQ-Bench, CC BY 4.0): nDCG@10 on the
gold qrels with the dataset card's per-query exclusions, plus the pooled qrels as a sensitivity score.

This is our own task framing, not Prime Intellect's (their OBLIQ environment is not public): the agent receives
the whole corpus as its context, one problem per line as "ID: <id> || <text>", and the query problem; it returns
up to ten corpus ids, one per line, most relevant first. nDCG@10 follows trec_eval's ndcg_cut.10: gain = the
qrels grade (every gold judgement in this subset is 2), discount 1/log2(rank+1), ideal DCG from the graded gold
list cut at 10. Excluded ids (snippets from the query's own source article) are removed from the ranking and
from the gold before scoring, as the dataset card instructs."""
import math
import re

K = 10
MARKERS = re.compile(r'^(?:\[answer\]|answer:|final answer:|label:|[-*]|\(?\d{1,3}[.)]|\d{1,3}\s*[-:])\s*', re.IGNORECASE)


def parse_ranking(output):
    """Corpus ids in the output, one per line, first occurrence kept, in order. A line is an id when, after a
    leading list marker or answer marker is removed, the rest holds the two '___' separators of a corpus id
    (ids may contain spaces, so the whole remaining line is the id). Other lines are ignored."""
    seen, ranking = set(), []
    for raw in str(output or '').splitlines():
        line = raw.strip().strip('`"\'')
        line = MARKERS.sub('', line).strip().strip('`"\'')
        if line.startswith('ID:'):
            line = line[3:].strip()
        if line.count('___') >= 2 and '||' not in line and line not in seen:
            seen.add(line)
            ranking.append(line)
    return ranking


def ndcg_at_k(relevance, ranking, k=K):
    dcg = sum(relevance.get(item, 0) / math.log2(rank + 2) for rank, item in enumerate(ranking[:k]))
    ideal = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(sorted(relevance.values(), reverse=True)[:k]))
    return dcg / ideal if ideal > 0 else 0.0


def score(gold, pooled, excluded, output):
    """gold and pooled: {corpus_id: grade}; excluded: ids to drop. Returns the gold nDCG@10 as the score."""
    ranking = [r for r in parse_ranking(output) if r not in set(excluded)]
    gold = {k: v for k, v in gold.items() if k not in set(excluded)}
    pooled = {k: v for k, v in pooled.items() if k not in set(excluded)}
    return {'score': ndcg_at_k(gold, ranking), 'pooled_ndcg_at_10': ndcg_at_k(pooled, ranking) if pooled else None,
            'returned': len(ranking), 'hits_at_10': sum(1 for r in ranking[:K] if r in gold),
            'parse_confidence': 'ranked-ids' if ranking else 'no-id-found', 'attempted_parse': ', '.join(ranking[:K])}
