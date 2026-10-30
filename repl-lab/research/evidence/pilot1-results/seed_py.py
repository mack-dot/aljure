"""The approved seed's decisions re-implemented in Python for descriptive analysis only: A1c arm 08's
lab regexes in order, :ent default and the abstained description label -> None. Checked against the
SCI worker's per-window counts before use."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, '/Users/mackianni/aljure/repl-lab/scripts')
from review_replay_ablation import form, sources
SRC = sources(Path('/Users/mackianni/aljure-sonnet-pair-v7/repl-lab/var/benchmarks/sci-ablation-speed-64k/08-aljure'))[5]
DEFN = form(SRC, SRC.index('(defn lab [t]'))
NAMES = {'abb': 'abbreviation', 'num': 'numeric value', 'hum': 'human being', 'loc': 'location', 'desc': 'description and abstract concept'}
RULES = [(re.compile(p), NAMES[k]) for p, k in re.findall(r'\(re-find #"((?:[^"\\]|\\.)*)" s\) :(\w+)', DEFN)]
ABSTAINED = {'description and abstract concept'}
def seed(text):
    s = text.lower()
    for r, label in RULES:
        if r.search(s):
            return None if label in ABSTAINED else label
    return None
