"""Q-SUBSTRATE task families (research/Q_SUBSTRATE_PROTOCOL.md): synthetic, seeded, language-neutral
external-context tasks with controller-side gold computed here, never by a model. Ten families
follow the brief's list: large collection processing, structured filtering and aggregation,
exact counting, parsing and normalization, algorithm construction, error recovery, persistent
task-local state, program inspection, symbolic transformation, verified execution of transformed
programs. Development and held-out splits differ only by seed; the held-out seed is used only
under explicit authorization."""
import heapq
import random
import re

FAMILIES = ['collection', 'aggregation', 'counting', 'parsing', 'algorithm', 'recovery',
            'state', 'inspection', 'transformation', 'verified-execution']
REGIONS = ['east', 'west', 'north', 'south', 'central']
STATUSES = ['active', 'closed', 'pending', 'archived']
WORDS = ('alpha beta gamma delta omega sigma theta kappa lambda river stone cloud ember forest harbor '
         'signal matrix vector tensor quartz copper silver cobalt nickel meadow canyon summit valley').split()
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ANSWER_RULE = ' Answer with exactly that and nothing else.'


def records(rng, n):
    rows = []
    for i in range(n):
        rows.append({'id': f'R{i + 1:04}', 'region': rng.choice(REGIONS), 'status': rng.choice(STATUSES),
                     'value': rng.randrange(0, 100), 'tags': ','.join(rng.sample(WORDS[:8], rng.randrange(1, 4)))})
    return rows


def record_line(r):
    return f"id={r['id']} region={r['region']} status={r['status']} value={r['value']} tags={r['tags']}"


def record_context(rows, header):
    return header + '\n' + '\n'.join(record_line(r) for r in rows) + '\n'


HEADER = 'One record per line: id=<id> region=<region> status=<status> value=<integer> tags=<comma-separated>.'


def collection(rng):
    rows = records(rng, 1600)
    region, status, bound = rng.choice(REGIONS), rng.choice(STATUSES), rng.randrange(20, 80)
    gold = sum(1 for r in rows if r['region'] == region and r['status'] == status and r['value'] > bound)
    return {'context': record_context(rows, HEADER),
            'question': f"How many records have region={region}, status={status} and value greater than {bound}? Answer with the integer only." + ANSWER_RULE,
            'answer': str(gold), 'kind': 'exact'}


def aggregation(rng):
    rows = records(rng, 1600)
    status = rng.choice(STATUSES)
    totals = {}
    for r in rows:
        if r['status'] == status:
            totals[r['region']] = totals.get(r['region'], 0) + r['value']
    best = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return {'context': record_context(rows, HEADER),
            'question': f"Among records with status={status}, which region has the largest total value, and what is that total? Answer as '<region> <total>' (ties: the alphabetically first region)." + ANSWER_RULE,
            'answer': f'{best[0]} {best[1]}', 'kind': 'exact'}


def counting(rng):
    lines = []
    target = rng.choice(WORDS[8:])
    for _ in range(1400):
        lines.append(' '.join(rng.choice(WORDS) for _ in range(rng.randrange(5, 12))).capitalize() + '.')
    # Decoys: the target inside another word must not count.
    for _ in range(40):
        lines[rng.randrange(len(lines))] += f' {target}s and un{target}.'
    gold = sum(1 for line in lines if re.search(r'\b' + target + r'\b', line, re.IGNORECASE))
    return {'context': 'One sentence per line.\n' + '\n'.join(lines) + '\n',
            'question': f"How many lines contain the whole word '{target}' (case-insensitive; '{target}s' and 'un{target}' do not count)? Answer with the integer only." + ANSWER_RULE,
            'answer': str(gold), 'kind': 'exact'}


def parsing(rng):
    lines, gold = [], 0
    for i in range(900):
        y, m, d = 2024, rng.randrange(1, 13), rng.randrange(1, 29)
        cents = rng.randrange(100, 500000)
        form = rng.randrange(3)
        date = f'{y}-{m:02}-{d:02}' if form == 0 else f'{d:02}/{m:02}/{y}' if form == 1 else f'{MONTHS[m - 1]} {d}, {y}'
        amount = f'${cents // 100:,}.{cents % 100:02}' if rng.random() < .5 else f'{cents / 100:.2f} USD'
        lines.append(f'P{i + 1:04} | {date} | {amount}')
        if m == 3:
            gold += cents
    return {'context': 'Payments, one per line: <id> | <date> | <amount>. Dates are YYYY-MM-DD, DD/MM/YYYY or Mon D, YYYY; amounts are $N,NNN.NN or N.NN USD.\n' + '\n'.join(lines) + '\n',
            'question': "What is the total amount of payments dated in March 2024? Answer with the number with exactly two decimals and no currency symbol or thousands separator." + ANSWER_RULE,
            'answer': f'{gold // 100}.{gold % 100:02}', 'kind': 'exact'}


def algorithm(rng):
    n = 60
    edges = []
    for i in range(1, n):  # a connected backbone, then extra edges
        edges.append((rng.randrange(i), i, rng.randrange(1, 20)))
    for _ in range(140):
        a, b = rng.sample(range(n), 2)
        edges.append((a, b, rng.randrange(1, 20)))
    graph = {i: [] for i in range(n)}
    for a, b, w in edges:
        graph[a].append((b, w))
        graph[b].append((a, w))
    source, target = 0, n - 1
    dist = {source: 0}
    heap = [(0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float('inf')):
            continue
        for v, w in graph[u]:
            if d + w < dist.get(v, float('inf')):
                dist[v] = d + w
                heapq.heappush(heap, (d + w, v))
    rng.shuffle(edges)
    return {'context': 'Undirected weighted edges, one per line: N<a> -- N<b> weight <w>.\n' + '\n'.join(f'N{a} -- N{b} weight {w}' for a, b, w in edges) + '\n',
            'question': f"What is the total weight of the shortest path from N{source} to N{target}? Answer with the integer only." + ANSWER_RULE,
            'answer': str(dist[target]), 'kind': 'exact'}


def recovery(rng):
    rows = records(rng, 1500)
    status = rng.choice(STATUSES)
    lines, gold = [], 0
    for r in rows:
        line = record_line(r)
        roll = rng.random()
        if roll < .06:
            line = line.replace(f"value={r['value']}", 'value=n/a')
        elif roll < .10:
            line = re.sub(r' status=\w+', '', line)
        elif roll < .13:
            line = line.replace('id=', 'ID:')
        else:
            gold += r['status'] == status
        lines.append(line)
    return {'context': HEADER + ' Some lines are malformed (a missing field, a non-integer value, or a wrong key format) and must be skipped.\n' + '\n'.join(lines) + '\n',
            'question': f"How many valid records (all five fields present with the exact key format and an integer value) have status={status}? Answer with the integer only." + ANSWER_RULE,
            'answer': str(gold), 'kind': 'exact'}


def state(rng):
    rows = records(rng, 1600)
    distinct = len({tag for r in rows for tag in r['tags'].split(',')})
    largest = sorted(rows, key=lambda r: (-r['value'], r['id']))[0]['id']
    ending = rng.randrange(10)
    total = sum(r['value'] for r in rows if r['id'].endswith(str(ending)))
    return {'context': record_context(rows, HEADER),
            'question': (f"Report three things separated by commas and no spaces: the number of distinct tags over all records, the id of the record "
                         f"with the largest value (ties: the smallest id), and the sum of value over records whose id ends in the digit {ending}." + ANSWER_RULE),
            'answer': f'{distinct},{largest},{total}', 'kind': 'exact'}


def expression(rng, depth, vars_):
    """A random (op a b) tree over add/mul with identity operands sprinkled in."""
    if depth == 0 or rng.random() < .15:
        return rng.choice(vars_) if rng.random() < .6 else rng.randrange(0, 6)
    op = rng.choice(['add', 'mul'])
    left, right = expression(rng, depth - 1, vars_), expression(rng, depth - 1, vars_)
    if rng.random() < .25:  # an identity element on one side
        ident = 0 if op == 'add' else 1
        if rng.random() < .5:
            left = ident
        else:
            right = ident
    return [op, left, right]


def render(tree):
    return str(tree) if not isinstance(tree, list) else '(' + tree[0] + ' ' + render(tree[1]) + ' ' + render(tree[2]) + ')'


def nodes(tree):
    return 1 if not isinstance(tree, list) else 1 + nodes(tree[1]) + nodes(tree[2])


def depth(tree):
    return 0 if not isinstance(tree, list) else 1 + max(depth(tree[1]), depth(tree[2]))


def simplify(tree):
    if not isinstance(tree, list):
        return tree
    op, a, b = tree[0], simplify(tree[1]), simplify(tree[2])
    ident = 0 if op == 'add' else 1
    if a == ident:
        return b
    if b == ident:
        return a
    return [op, a, b]


def evaluate(tree, env):
    if isinstance(tree, list):
        a, b = evaluate(tree[1], env), evaluate(tree[2], env)
        return a + b if tree[0] == 'add' else a * b
    return env[tree] if isinstance(tree, str) else tree


def expression_context(rng):
    vars_ = ['x', 'y', 'z']
    trees = [expression(rng, 7, vars_) for _ in range(12)]
    text = ('Twelve expression trees, one per line as E<k>: <tree>. A tree is a variable (x, y or z), a non-negative integer, '
            'or (op left right) with op add or mul.\n' + '\n'.join(f'E{i + 1}: {render(t)}' for i, t in enumerate(trees)) + '\n')
    return trees, text


def inspection(rng):
    trees, text = expression_context(rng)
    k = rng.randrange(12)
    identities = sum(1 for _ in iter_nodes(trees[k]) if isinstance(_, list) and (_[1] == (0 if _[0] == 'add' else 1) or _[2] == (0 if _[0] == 'add' else 1)))
    return {'context': text,
            'question': (f"For E{k + 1}: how many op nodes have an identity operand (an add with a 0 operand or a mul with a 1 operand), "
                         f"what is the total number of nodes (op nodes plus leaves), and what is the depth (a leaf has depth 0)? Answer as three integers separated by commas and no spaces." + ANSWER_RULE),
            'answer': f'{identities},{nodes(trees[k])},{depth(trees[k])}', 'kind': 'exact'}


def iter_nodes(tree):
    yield tree
    if isinstance(tree, list):
        yield from iter_nodes(tree[1])
        yield from iter_nodes(tree[2])


def transformation(rng):
    trees, text = expression_context(rng)
    k = rng.randrange(12)
    simplified = simplify(trees[k])
    return {'context': text,
            'question': (f"Simplify E{k + 1} by repeatedly replacing (add t 0), (add 0 t), (mul t 1) and (mul 1 t) with t, until no such node remains. "
                         f"Give the simplified tree in the same notation, with single spaces and no line breaks." + ANSWER_RULE),
            'answer': render(simplified), 'kind': 'exact'}


def verified_execution(rng):
    trees, text = expression_context(rng)
    k = rng.randrange(12)
    simplified = simplify(trees[k])
    envs = [{'x': rng.randrange(-5, 6), 'y': rng.randrange(-5, 6), 'z': rng.randrange(-5, 6)} for _ in range(5)]
    values = [evaluate(simplified, e) for e in envs]
    listed = '; '.join(f"x={e['x']} y={e['y']} z={e['z']}" for e in envs)
    return {'context': text,
            'question': (f"Simplify E{k + 1} as in: replace (add t 0), (add 0 t), (mul t 1), (mul 1 t) with t until none remain. Then evaluate the simplified tree "
                         f"at these five assignments, in order: {listed}. Answer with the five integer values separated by commas and no spaces." + ANSWER_RULE),
            'answer': ','.join(str(v) for v in values), 'kind': 'exact'}


GENERATORS = {'collection': collection, 'aggregation': aggregation, 'counting': counting, 'parsing': parsing,
              'algorithm': algorithm, 'recovery': recovery, 'state': state, 'inspection': inspection,
              'transformation': transformation, 'verified-execution': verified_execution}


def generate(seed, cases_per_family):
    """Deterministic cases: family order fixed, one rng stream per case."""
    out = []
    for family in FAMILIES:
        for i in range(cases_per_family):
            rng = random.Random(f'{seed}:{family}:{i}')
            case = GENERATORS[family](rng)
            out.append({'task_id': f'{family}-{i + 1}', 'family': family, 'index': i, **case})
    return out


def score(case, answer):
    """Independent scorer: exact match after trimming; the gold comes from the generator."""
    text = (answer or '').strip()
    return {'score': float(text == case['answer']), 'attempted': text[:200], 'rule': 'exact-trimmed-v1'}
