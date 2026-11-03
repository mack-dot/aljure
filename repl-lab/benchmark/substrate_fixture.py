"""Scripted substrate fixture through the real gateway, external adapter and both isolated
workers. Zero inference. Developer-written programs solve one case of every family in each
language, which also checks the generator's gold independently in two implementations."""
import argparse
import json
import os
from pathlib import Path
import re

from . import paired
from .gateway_client import GatewayClient
from .oolong import digest, encoded, jsonl, require
from .relay_fixture import ALJURE_TOOLS, Script, call, response
from .reuse_interface import files, write
from .substrate import ARMS, PROOF, ROOT, configs_of, verify_suite
from . import substrate_tasks as tasks


class SubstrateScript(Script):
    def __init__(self, config, steps):
        super().__init__('aljure', provider=config['provider'], config=config)
        self.steps, self.bodies = steps, []

    def __call__(self, body, _):
        require([t['name'] for t in body['tools']] == ALJURE_TOOLS, 'Wrong tool inventory')
        self.check_aljure_tools(body, 'root')
        self.bodies.append(body)
        require(len(self.bodies) <= len(self.steps), 'Unexpected fixture request')
        step = self.steps[len(self.bodies) - 1]
        return response(call(step[0], **step[1]), body['model'], signed=True)


def param(pattern, question):
    found = re.search(pattern, question)
    require(found, 'Question shape changed: ' + pattern)
    return found.groups()


CLJ_TREE = '''(def tokens (fn [s] (re-seq #"\\(|\\)|[a-z]+|-?\\d+" s)))
(def parse-tree (fn parse-tree [ts] (let [t (first ts)] (if (= t "(") (let [op (second ts) [a r1] (parse-tree (drop 2 ts)) [b r2] (parse-tree r1)] [[op a b] (rest r2)]) [(if (re-matches #"-?\\d+" t) (parse-long t) t) (rest ts)]))))
(def tree (first (parse-tree (tokens (subs (first (filter #(clojure.string/starts-with? % "E@@K@@: ") context-lines)) (count "E@@K@@: "))))))
(def render (fn render [t] (if (vector? t) (str "(" (first t) " " (render (second t)) " " (render (nth t 2)) ")") (str t))))
(def simplify (fn simplify [t] (if (vector? t) (let [[op a b] t a (simplify a) b (simplify b) i (if (= op "add") 0 1)] (cond (= a i) b (= b i) a :else [op a b])) t)))
(def evaluate (fn evaluate [t env] (if (vector? t) (let [a (evaluate (second t) env) b (evaluate (nth t 2) env)] (if (= (first t) "add") (+ a b) (* a b))) (if (string? t) (get env t) t))))
nil'''
PY_TREE = '''import re
line = next(l for l in context_lines if l.startswith('E@@K@@: '))[len('E@@K@@: '):]
tokens = re.findall(r'\\(|\\)|[a-z]+|-?\\d+', line)
def parse_tree(ts, i=0):
    if ts[i] == '(':
        a, j = parse_tree(ts, i + 2)
        b, k = parse_tree(ts, j)
        return [ts[i + 1], a, b], k + 1
    t = ts[i]
    return (int(t) if re.fullmatch(r'-?\\d+', t) else t), i + 1
tree = parse_tree(tokens)[0]
def render(t):
    return '(' + t[0] + ' ' + render(t[1]) + ' ' + render(t[2]) + ')' if isinstance(t, list) else str(t)
def simplify(t):
    if not isinstance(t, list):
        return t
    op, a, b = t[0], simplify(t[1]), simplify(t[2])
    i = 0 if op == 'add' else 1
    return b if a == i else a if b == i else [op, a, b]
def evaluate(t, env):
    if isinstance(t, list):
        a, b = evaluate(t[1], env), evaluate(t[2], env)
        return a + b if t[0] == 'add' else a * b
    return env[t] if isinstance(t, str) else t'''


def solutions(family, question):
    """[(clojure steps), (python steps)] for one case: repl_eval sources, then done with source answer."""
    if family == 'collection':
        region, status, bound = param(r'region=(\w+), status=(\w+) and value greater than (\d+)', question)
        clj = [f'(def answer (str (count (filter (fn [l] (and (clojure.string/starts-with? l "id=") (clojure.string/includes? l " region={region} ") (clojure.string/includes? l " status={status} ") (> (parse-long (second (re-find #"value=(\\d+)" l))) {bound}))) context-lines))))']
        py = [f"import re\nanswer = str(sum(1 for l in context_lines if l.startswith('id=') and ' region={region} ' in l and ' status={status} ' in l and int(re.search(r'value=(\\d+)', l).group(1)) > {bound}))"]
    elif family == 'aggregation':
        status, = param(r'with status=(\w+), which region', question)
        clj = [f'(def answer (let [sel (filter #(and (clojure.string/starts-with? % "id=") (clojure.string/includes? % " status={status} ")) context-lines) totals (reduce (fn [m l] (update m (second (re-find #"region=(\\w+)" l)) (fnil + 0) (parse-long (second (re-find #"value=(\\d+)" l))))) {{}} sel) best (first (sort-by (fn [[k v]] [(- v) k]) totals))] (str (key best) " " (val best))))']
        py = [f"import re\ntotals = {{}}\nfor l in context_lines:\n    if l.startswith('id=') and ' status={status} ' in l:\n        r = re.search(r'region=(\\w+)', l).group(1)\n        totals[r] = totals.get(r, 0) + int(re.search(r'value=(\\d+)', l).group(1))\nbest = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[0]\nanswer = f'{{best[0]}} {{best[1]}}'"]
    elif family == 'counting':
        target, = param(r"whole word '(\w+)'", question)
        clj = [f'(def answer (str (count (filter #(re-find (re-pattern "(?i)\\\\b{target}\\\\b") %) context-lines))))']
        py = [f"import re\nanswer = str(sum(1 for l in context_lines if re.search(r'\\b{target}\\b', l, re.I)))"]
    elif family == 'parsing':
        clj = ['(def answer (let [rows (filter #(re-find #"^P\\d{4} \\| " %) context-lines)'
               ' march? (fn [d] (or (re-find #"^2024-03-" d) (re-find #"^\\d\\d/03/2024$" d) (re-find #"^Mar " d)))'
               ' cents (fn [a] (let [digits (clojure.string/replace (second (re-find #"([\\d,]+\\.\\d\\d)" a)) "," "") [whole frac] (clojure.string/split digits #"\\.")] (+ (* 100 (parse-long whole)) (parse-long frac))))'
               ' total (reduce + 0 (for [l rows :let [[_ d a] (re-find #"^P\\d{4} \\| ([^|]+) \\| (.+)$" l)] :when (march? (clojure.string/trim d))] (cents a)))'
               ' m (mod total 100)] (str (quot total 100) "." (if (< m 10) "0" "") m)))']
        py = ["import re\ntotal = 0\nfor l in context_lines:\n    m = re.match(r'^P\\d{4} \\| ([^|]+) \\| (.+)$', l)\n    if not m:\n        continue\n    d = m.group(1).strip()\n    if re.match(r'^2024-03-', d) or re.match(r'^\\d\\d/03/2024$', d) or d.startswith('Mar '):\n        digits = re.search(r'([\\d,]+\\.\\d\\d)', m.group(2)).group(1).replace(',', '')\n        whole, frac = digits.split('.')\n        total += int(whole) * 100 + int(frac)\nanswer = f'{total // 100}.{total % 100:02}'"]
    elif family == 'algorithm':
        src, dst = param(r'from N(\d+) to N(\d+)', question)
        clj = [f'(def answer (let [edges (keep #(when-let [[_ a b w] (re-find #"^N(\\d+) -- N(\\d+) weight (\\d+)$" %)] [(parse-long a) (parse-long b) (parse-long w)]) context-lines)'
               f' adj (reduce (fn [m [a b w]] (-> m (update a (fnil conj []) [b w]) (update b (fnil conj []) [a w]))) {{}} edges)]'
               f' (loop [dist {{{src} 0}} visited #{{}}] (let [candidates (remove (fn [[n _]] (visited n)) dist)]'
               f' (if (empty? candidates) "unreachable" (let [[u du] (apply min-key second candidates)] (if (= u {dst}) (str du)'
               f' (recur (reduce (fn [d [v w]] (if (< (+ du w) (get d v 1000000000)) (assoc d v (+ du w)) d)) dist (get adj u [])) (conj visited u)))))))))']
        py = [f"import re, heapq\nadj = {{}}\nfor l in context_lines:\n    m = re.match(r'^N(\\d+) -- N(\\d+) weight (\\d+)$', l)\n    if m:\n        a, b, w = (int(x) for x in m.groups())\n        adj.setdefault(a, []).append((b, w)); adj.setdefault(b, []).append((a, w))\ndist = {{{src}: 0}}\nheap = [(0, {src})]\nwhile heap:\n    d, u = heapq.heappop(heap)\n    if d > dist.get(u, 10**9):\n        continue\n    for v, w in adj.get(u, []):\n        if d + w < dist.get(v, 10**9):\n            dist[v] = d + w\n            heapq.heappush(heap, (d + w, v))\nanswer = str(dist[{dst}])"]
    elif family == 'recovery':
        status, = param(r'have status=(\w+)\?', question)
        clj = [f'(def answer (str (count (filter #(and (re-matches #"id=R\\d{{4}} region=\\w+ status=\\w+ value=\\d+ tags=[\\w,]+" %) (clojure.string/includes? % " status={status} ")) context-lines))))']
        py = [f"import re\nanswer = str(sum(1 for l in context_lines if re.fullmatch(r'id=R\\d{{4}} region=\\w+ status=\\w+ value=\\d+ tags=[\\w,]+', l) and ' status={status} ' in l))"]
    elif family == 'state':
        digit, = param(r'ends in the digit (\d)', question)
        clj = ['(def rows (filter #(clojure.string/starts-with? % "id=") context-lines))',
               '(def parsed (map (fn [l] {:id (second (re-find #"id=(R\\d+)" l)) :value (parse-long (second (re-find #"value=(\\d+)" l))) :tags (clojure.string/split (second (re-find #"tags=(\\S+)" l)) #",")}) rows))',
               f'(def answer (str (count (set (mapcat :tags parsed))) "," (:id (first (sort-by (fn [r] [(- (:value r)) (:id r)]) parsed))) "," (reduce + 0 (map :value (filter #(clojure.string/ends-with? (:id %) "{digit}") parsed)))))']
        py = ["rows = [l for l in context_lines if l.startswith('id=')]",
              "import re\nparsed = [{'id': re.search(r'id=(R\\d+)', l).group(1), 'value': int(re.search(r'value=(\\d+)', l).group(1)), 'tags': re.search(r'tags=(\\S+)', l).group(1).split(',')} for l in rows]",
              f"tags = len({{t for r in parsed for t in r['tags']}})\nlargest = sorted(parsed, key=lambda r: (-r['value'], r['id']))[0]['id']\ntotal = sum(r['value'] for r in parsed if r['id'].endswith('{digit}'))\nanswer = f'{{tags}},{{largest}},{{total}}'"]
    elif family == 'inspection':
        k, = param(r'For E(\d+):', question)
        clj = [CLJ_TREE.replace('@@K@@', k),
               '(def answer (let [nodes (fn nodes [t] (if (vector? t) (+ 1 (nodes (second t)) (nodes (nth t 2))) 1))'
               ' depth (fn depth [t] (if (vector? t) (inc (max (depth (second t)) (depth (nth t 2)))) 0))'
               ' idents (fn idents [t] (if (vector? t) (let [[op a b] t i (if (= op "add") 0 1)] (+ (if (or (= a i) (= b i)) 1 0) (idents a) (idents b))) 0))]'
               ' (str (idents tree) "," (nodes tree) "," (depth tree))))']
        py = [PY_TREE.replace('@@K@@', k),
              "def nodes(t):\n    return 1 + nodes(t[1]) + nodes(t[2]) if isinstance(t, list) else 1\ndef depth(t):\n    return 1 + max(depth(t[1]), depth(t[2])) if isinstance(t, list) else 0\n"
              "def idents(t):\n    if not isinstance(t, list):\n        return 0\n    i = 0 if t[0] == 'add' else 1\n    return (1 if t[1] == i or t[2] == i else 0) + idents(t[1]) + idents(t[2])\nanswer = f'{idents(tree)},{nodes(tree)},{depth(tree)}'"]
    elif family == 'transformation':
        k, = param(r'Simplify E(\d+) by', question)
        clj = [CLJ_TREE.replace('@@K@@', k), '(def answer (render (simplify tree)))']
        py = [PY_TREE.replace('@@K@@', k), 'answer = render(simplify(tree))']
    elif family == 'verified-execution':
        k, = param(r'Simplify E(\d+) as in', question)
        envs = re.findall(r'x=(-?\d+) y=(-?\d+) z=(-?\d+)', question)
        clj_envs = ' '.join('{"x" %s "y" %s "z" %s}' % e for e in envs)
        py_envs = ', '.join("{'x': %s, 'y': %s, 'z': %s}" % e for e in envs)
        clj = [CLJ_TREE.replace('@@K@@', k), f'(def answer (clojure.string/join "," (map #(str (evaluate (simplify tree) %)) [{clj_envs}])))']
        py = [PY_TREE.replace('@@K@@', k), f"answer = ','.join(str(evaluate(simplify(tree), e)) for e in [{py_envs}])"]
    else:
        raise ValueError(family)
    return {'clojure': [('repl_eval', {'source': s}) for s in clj] + [('done', {'source': 'answer'})],
            'python': [('repl_eval', {'source': s}) for s in py] + [('done', {'source': 'answer'})]}


def run(suite, out):
    manifest, cases = verify_suite(suite)
    suite, out = Path(suite), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    configs = configs_of(suite)
    images = {'sci': configs['clojure']['execution_images']['sci'], 'python': configs['python']['execution_images']['python']}
    os.environ['REPL_LAB_WORKER_IMAGE'] = images['sci']
    os.environ['REPL_LAB_PYTHON_IMAGE'] = images['python']
    os.environ['REPL_LAB_WORKER_OUTPUT_BYTES'] = '65536'
    runtime = paired.runtime_snapshot()
    checks, records, tools_bytes, requests = {}, [], {}, {}
    by_id = {c['task_id']: c for c in cases}
    for case in cases:
        if case['index'] != 0:
            continue  # one case per family in each language
        data = json.loads((suite / 'public' / (case['task_id'] + '.json')).read_text())
        steps = solutions(case['family'], data['task']['question'])
        for arm in ARMS:
            name = f"{arm}-{case['task_id']}"
            dest = out / name
            dest.mkdir()
            script = SubstrateScript(configs[arm], steps[arm])
            gateway = GatewayClient(dest / 'gateway', paired.gateway_config(configs[arm], 'aljure'), script, evidence='FIXTURE')
            try:
                execution = paired.run_arm('aljure', data, dest, configs[arm], gateway, {})
            finally:
                gateway.close()
            answer = (dest / 'answer.txt').read_text() if (dest / 'answer.txt').exists() else None
            cleanup = json.loads((dest / 'gateway/cleanup.json').read_text())
            events = list(jsonl(dest / 'agent/events.jsonl')) if (dest / 'agent/events.jsonl').exists() else []
            errors = [e['payload'].get('error') for e in events if e['type'] == 'tool-result' and e['payload'].get('status') != 'ok']
            checks[name + '_completed_clean'] = bool(execution.get('completion')) and cleanup['ok'] and not paired.worker_isolation_refused(dest)
            checks[name + '_correct'] = bool(tasks.score(by_id[case['task_id']], answer)['score'])
            checks[name + '_no_evaluation_errors'] = not errors
            tools_bytes[arm] = len(encoded(script.bodies[0]['tools']))
            requests.setdefault(arm, script.bodies[0])
            records.append({'name': name, 'answer': answer, 'gold': by_id[case['task_id']]['answer'], 'errors': errors[:3], 'files': files(dest)})
    first = {arm: requests[arm] for arm in ARMS}
    checks['tool_inventory_equal'] = [t['name'] for t in first['clojure']['tools']] == [t['name'] for t in first['python']['tools']]
    checks['tool_schemas_equal'] = [t['input_schema'] for t in first['clojure']['tools']] == [t['input_schema'] for t in first['python']['tools']]
    checks['python_tools_in_python_terms'] = not any(w in json.dumps(first['python']['tools']) for w in ('Clojure', 'SCI', 'EDN'))
    checks['clojure_tools_unchanged_terms'] = 'SCI' in json.dumps(first['clojure']['tools']) and 'Python' not in json.dumps(first['clojure']['tools'])
    checks['prompt_overhead_within_5_percent'] = abs(tools_bytes['clojure'] - tools_bytes['python']) <= .05 * max(tools_bytes.values())
    checks['system_prompt_structure_shared'] = (json.dumps(first['clojure']['system']).count('\n') == json.dumps(first['python']['system']).count('\n'))
    require(paired.runtime_snapshot() == runtime, 'Runtime changed during proof')
    proof = {'evidence': 'FIXTURE', 'status': 'PASSED' if all(checks.values()) else 'FAILED', 'model_calls': 0,
             'checks': checks, 'records': records, 'runtime_source': runtime, 'images': images,
             'tools_bytes': tools_bytes, 'suite_sha256': manifest['suite_sha256'],
             'transport_contract': paired.transport_contract(configs['clojure'])}
    write(out / 'proof.json', proof)
    require(all(checks.values()), 'Substrate fixture checks failed; preserve this attempt')
    PROOF.write_bytes(encoded(proof) + b'\n')
    return {k: v for k, v in proof.items() if k not in ('records', 'runtime_source')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.suite, args.out), indent=2))
