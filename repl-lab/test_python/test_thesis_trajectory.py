"""Thesis-pilot suite, trajectory plans and the trajectory runner (research/THESIS_PILOT_PROTOCOL.md).

FIXTURES, NOT AUTONOMOUS MODEL LEARNING. The runner tests replace the model run, the gateway and
the Clojure promotion step with scripted stand-ins, so they prove only the plumbing: pins carried
forward, cold restart from disk, rollback, crash recovery, A/C/E separation and cost accounting.
No Docker, no model call, no network."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark import official, paired
from benchmark.oolong import digest, encoded, jsonl, read_suite

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config/thesis-pilot-sonnet.json').read_text())
TREC = ['Where is city {} ?', 'Who wrote book {} ?', 'How many legs does animal {} have ?', 'What does ABC{} stand for ?']
TREC_LABELS = ['location', 'human being', 'numeric value', 'abbreviation']
SPAM = [('WIN a free prize {}', 'spam'), ('see you at {}', 'ham'), ('free entry txt {}', 'spam'), ('call me at {}', 'ham')]


class FocusedLearningContractTests(unittest.TestCase):
    def test_development_probe_and_fair_retention_control_use_existing_modes(self):
        for arms in (['ES'], ['A', 'CS', 'ES']):
            config = copy.deepcopy(CONFIG)
            config['trajectory']['arms'] = arms
            self.assertEqual(paired.trajectory_spec(config)['arms'], arms)
        self.assertEqual(paired.arm_acquisition('CS'), {'arm': 'C', 'mode': 'structured'})
        self.assertEqual(paired.arm_acquisition('ES'), {'arm': 'E', 'mode': 'structured'})
        self.assertEqual(paired.arm_acquisition('C'), {'arm': 'C'})
        for arm in ('CS', 'ES'):
            paired.validate_config(paired.trajectory_contract(CONFIG, arm, 'var/library', 'a' * 64))
        invalid = copy.deepcopy(CONFIG)
        invalid['aljure_contract'] = {'acquisition': {'arm': 'C', 'mode': 'capture'}}
        with self.assertRaises(ValueError):
            paired.validate_config(invalid)


def records(dataset, window):
    if dataset == 'spam':
        return [(text.format(window + i), label) for i, (text, label) in enumerate(SPAM)]
    return [(TREC[i].format(window + i), TREC_LABELS[i]) for i in range(4)]


def window_text(dataset, window, labeled):
    header = ("The following lines contain questions. Categories: 'numeric value', 'human being', 'location', 'abbreviation'."
              if dataset != 'spam' else 'The following lines contain text messages. Each can be classified as spam or ham.')
    lines = [f'Date: Jan 01, 2023 || User: {100 + i} || Instance: {text}' + (f' || Label: {label}' if labeled else '')
             for i, (text, label) in enumerate(records(dataset, window))]
    return '\n'.join([header, ''] + lines + ['', 'Calculate the exact answer.'])


def window_rows(dataset, window, length=1024):
    kinds = [('counting', 'TASK_TYPE.NUMERIC_ONE_CLASS'), ('counting', 'TASK_TYPE.NUMERIC_ONE_CLASS'),
             ('counting', 'TASK_TYPE.RELATIVE_FREQ'), ('user', 'TASK_TYPE.MOST_FREQ')]
    return [{'id': window * 10 + i, 'dataset': dataset, 'context_len': length, 'context_window_id': window,
             'context_window_text': window_text(dataset, window, False),
             'context_window_text_with_labels': window_text(dataset, window, True),
             'question': f'In the above data, question {window}.{i}?', 'task_group': group, 'task': task,
             'answer': '[3]', 'answer_type': 'ANSWER_TYPE.NUMERIC', 'input_subset': dataset, 'num_labels': 4}
            for i, (group, task) in enumerate(kinds)]


PROFILE = {'split': 'validation', 'artifacts': ['thesis.parquet'], 'selection': 'thesis-pilot-v1', 'seed': 0,
           'task_group': 'counting',
           'families': {'F1': {'dataset': 'trec_coarse', 'per_window': 2, 'windows': [[1024, w] for w in range(1, 8)]},
                        'F2': {'dataset': 'spam', 'per_window': 2, 'windows': [[1024, 100], [1024, 101]]}},
           'exposed': [['trec_coarse', 1024, 40]],
           'panel': {'windows': [['trec_coarse', 1024, 50], ['spam', 1024, 150]], 'max_items_per_window': 3},
           'count': 18}


class SuiteFixture:
    """A pinned fixture shard, one row group per window, behind patched lock-file pins."""

    def build_suite(self, root, *, heldout_in_group=None):
        import pyarrow as pa
        import pyarrow.parquet as pq
        windows = ([('trec_coarse', w) for w in range(1, 8)] + [('spam', 100), ('spam', 101)] +
                   [('trec_coarse', 40), ('trec_coarse', 50), ('spam', 150)])
        groups = [window_rows(d, w) for d, w in windows]
        if heldout_in_group is not None:
            groups[heldout_in_group].append({**window_rows('alpha', 9)[0], 'dataset': 'alpha'})
        path = Path(root) / 'thesis.parquet'
        schema = pa.Table.from_pylist(groups[0]).schema
        with pq.ParquetWriter(path, schema) as writer:
            for rows in groups:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        data = path.read_bytes()
        pin = {'repository': 'https://huggingface.co/datasets/test/fixture', 'revision': 'f' * 40,
               'path': 'data/thesis.parquet', 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        cache = Path(root) / 'cache'
        cache.mkdir(exist_ok=True)
        (cache / (pin['sha256'] + '-thesis.parquet')).write_bytes(data)
        pins = copy.deepcopy(official.PINS)
        pins['official_artifacts'] = {'thesis.parquet': pin}
        pins['official_profiles']['oolong-synth:thesis-pilot:validation'] = PROFILE
        pins['official_profiles']['oolong-synth:independent-heldout:32768'] = {
            'split': 'test', 'artifacts': [], 'windows': [['alpha', 9]], 'per_window': 1}
        return pins, cache


class ThesisSuiteTests(SuiteFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_suite_selects_by_type_with_a_fixed_seed_and_keeps_the_panel_controller_only(self):
        pins, cache = self.build_suite(self.root)
        with patch.object(official, 'PINS', pins):
            manifest = official.prepare_thesis_pilot(self.root / 'suite', cache=cache, download=False, exposed=set())
            again = official.prepare_thesis_pilot(self.root / 'again', cache=cache, download=False, exposed=set())
            read_suite(self.root / 'suite')
        self.assertEqual(manifest['suite_sha256'], again['suite_sha256'])
        families = manifest['selection']['families']
        self.assertEqual((len(families['F1']), len(families['F2'])), (14, 4))
        answers = {a['task_id']: a for a in jsonl(self.root / 'suite/controller/answers.jsonl')}
        # One NUMERIC_ONE_CLASS (ids x0 or x1) and one other counting question (x2) per window; never the user question.
        for window in [w for _, w in PROFILE['families']['F1']['windows']] + [100, 101]:
            ids = sorted(a['id'] % 10 for a in answers.values() if a['context_window_id'] == window)
            self.assertEqual(len(ids), 2)
            self.assertIn(ids[0], (0, 1))
            self.assertEqual(ids[1], 2)
        panel = json.loads((self.root / 'suite/controller/panel.json').read_text())
        self.assertEqual([w['id'] for w in panel['windows']], ['trec_coarse-1024-50', 'spam-1024-150'])
        self.assertEqual([len(w['items']) for w in panel['windows']], [3, 3])
        self.assertEqual(panel['windows'][0]['derived'], 'header, first 3 of 4 records, footer')
        self.assertEqual(panel['windows'][0]['items'][0], {'case': 'trec_coarse-1024-50-0', 'text': 'Where is city 50 ?',
                                                           'label': 'location'})
        self.assertNotIn('Label:', panel['windows'][0]['context'])
        self.assertEqual((self.root / 'suite/controller/panel.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(manifest['files']['controller/panel.json'], digest((self.root / 'suite/controller/panel.json').read_bytes()))
        # Item gold of every task window, controller-only, keyed by the task's own context hash.
        items_path = self.root / 'suite/controller/task-items.json'
        items = json.loads(items_path.read_text())
        self.assertEqual((items_path.stat().st_mode & 0o777, manifest['files']['controller/task-items.json']),
                         (0o600, digest(items_path.read_bytes())))
        self.assertEqual([w['id'] for w in items['windows']],
                         ['spam-1024-100', 'spam-1024-101'] + [f'trec_coarse-1024-{w}' for w in range(1, 8)])
        self.assertEqual([(i['text'], i['label']) for i in items['windows'][0]['items']], records('spam', 100))
        tasks = {t['task_id']: t for t in jsonl(self.root / 'suite/public/tasks.jsonl')}
        self.assertEqual({w['context_sha256'] for w in items['windows']}, {t['context_sha256'] for t in tasks.values()})
        self.assertEqual(manifest['selection']['task_items'], {'windows': 9, 'items': 36})
        public = b'\n'.join(p.read_bytes() for p in (self.root / 'suite/public').rglob('*') if p.is_file())
        for secret in (b'Label:', b'human being\n', b'answer_type', b'with_labels'):
            self.assertNotIn(secret, public)
        # Task windows, exposed windows and panel windows are disjoint.
        task_windows = {(a['dataset'], a['context_window_id']) for a in answers.values()}
        self.assertFalse(task_windows & {('trec_coarse', 40), ('trec_coarse', 50), ('spam', 150)})

    def test_selection_is_bound_to_its_profile_and_exposure_is_refused(self):
        pins, cache = self.build_suite(self.root)
        with patch.object(official, 'PINS', pins):
            manifest = official.prepare_thesis_pilot(self.root / 'suite', cache=cache, download=False)
            official.validate_provenance(manifest)
            for mutate in (lambda m: m['selection'].update(seed=1),
                           lambda m: m['selection']['families']['F2'].pop(),
                           lambda m: m['selection'].update(panel_windows=[['spam', 1024, 101]]),
                           lambda m: m['files'].pop('controller/panel.json')):
                changed = copy.deepcopy(manifest)
                mutate(changed)
                with self.assertRaises(ValueError):
                    official.validate_provenance(changed)
            with self.assertRaisesRegex(ValueError, 'exposed by a prepared suite'):
                official.prepare_thesis_pilot(self.root / 'exposed', cache=cache, download=False,
                                              exposed={('trec_coarse', 1024, 3)})

    def test_a_row_group_holding_a_held_out_row_is_never_read_past_its_metadata(self):
        import pyarrow.parquet as pq
        pins, cache = self.build_suite(self.root, heldout_in_group=2)  # window 3's row group
        reads, original = [], pq.ParquetFile.read_row_group

        def logged(self_, group, columns=None, **kwargs):
            reads.append((group, tuple(columns or ())))
            return original(self_, group, columns=columns, **kwargs)
        with patch.object(official, 'PINS', pins), patch.object(pq.ParquetFile, 'read_row_group', logged):
            with self.assertRaisesRegex(ValueError, 'missing'):
                official.prepare_thesis_pilot(self.root / 'suite', cache=cache, download=False)
        self.assertTrue(any(g == 2 for g, _ in reads))
        for group, columns in reads:
            if group == 2:
                self.assertFalse({'question', 'answer', 'context_window_text', 'context_window_text_with_labels'} & set(columns))


class TrajectoryFixture(SuiteFixture):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pins, cache = self.build_suite(self.root)
        self.pins = patch.object(official, 'PINS', pins)
        self.pins.start()
        self.addCleanup(self.pins.stop)
        self.suite = self.root / 'suite'
        official.prepare_thesis_pilot(self.suite, cache=cache, download=False, exposed=set())
        config = self.root / 'config.json'
        config.write_text(json.dumps(CONFIG))
        self.plan_path = self.root / 'plan.json'
        self.plan = paired.plan_trajectory(self.suite, config, self.plan_path)
        (ROOT / 'var').mkdir(exist_ok=True)
        self.out = Path(tempfile.mkdtemp(prefix='thesis-trajectory-test-', dir=ROOT / 'var'))
        self.addCleanup(shutil.rmtree, self.out, True)
        self.seen, self.script, self.tokens = [], {}, 1000

    # Scripted stand-ins for the model run, the gateway and the Clojure promotion step.
    def run_arm(self, harness, data, out, config, gateway, readiness):
        contract = config.get('aljure_contract', {})
        self.seen.append(contract.get('artifacts', {}).get('library_sha256'))
        agent = out / 'agent'
        agent.mkdir(parents=True, exist_ok=True)
        (agent / 'answer.txt').write_text('Answer: 3')
        (out / 'answer.txt').write_text('Answer: 3')
        result = {'status': 'completed'}
        if 'acquisition' in contract:
            proposal = agent / 'proposal.edn'
            proposal.write_bytes(b'{:schema :aljure-proposal-v1 :n %d}\n' % len(self.seen))
            result['acquisition'] = {'decision': 'proposed', 'proposal-sha256': digest(proposal.read_bytes()),
                                     'spend': {'provider-ids': [f'p{len(self.seen)}-proposal']}}
        (agent / 'result.json').write_text(json.dumps(result))
        return {'completion': {'native_exit_code': 0}}

    def gateway(self):
        test = self

        class Gateway:
            def __init__(self, output, gateway_config, transport, *, evidence):
                self.output = Path(output)

            def close(self):
                self.output.mkdir(parents=True, exist_ok=True)
                n = len(test.seen)
                # Two task-inference calls (the second handles records the library left unresolved) and, in C/E, the proposal turn.
                ids = [f'p{n}-root', f'p{n}-fallback'] + ([f'p{n}-proposal'] if (self.output.parent / 'agent/proposal.edn').exists() else [])
                (self.output / 'usage.jsonl').write_text(''.join(json.dumps(
                    {'kind': 'provider-call', 'call_id': i, 'session_id': 'request-' + i, 'status': 'complete',
                     'provider_request_id': i, 'model': CONFIG['model'], 'input_tokens': test.tokens, 'output_tokens': 100,
                     'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}) + '\n' for i in ids))
        return Gateway

    def promote_process(self, request_path, environment, seconds):
        request = json.loads(Path(request_path).read_text())
        library = Path(request['library'])
        action = self.script.get(request['position'], 'approve')
        # Real C and E artifacts differ; the scripted version names its arm and position.
        version = b'{:entries [{:artifact "%s-%d"}], :parent "%s", :schema :aljure-library-v1}\n' % (
            request['arm'].encode(), request['position'], request['pin'].encode())
        new = digest(version)
        if action == 'crash':
            raise subprocess.TimeoutExpired('clj', seconds)
        if action == 'bad-receipt':
            # The JVM names a receipt whose bytes do not hash to the name: an integrity failure.
            (library / 'receipts').mkdir(exist_ok=True)
            (library / 'receipts' / ('b' * 64 + '.json')).write_bytes(b'{"decision": "approved"}')
            return subprocess.CompletedProcess([], 0, json.dumps({'receipt-sha256': 'b' * 64}).encode() + b'\n', b'')
        if action == 'stage-fatal':
            return subprocess.CompletedProcess([], 3, b'{"error": "Isolation proof is incomplete", "fatal": true}\n', b'')
        if action in ('approve', 'crash-after-write'):
            (library / 'libraries' / f'{new}.edn').write_bytes(version)
        if action == 'crash-after-write':
            return subprocess.CompletedProcess([], 2, b'{"error": "crash"}\n', b'')
        receipt = {'parent-pin': request['pin'], 'task-id': request['task_id'], 'position': request['position'],
                   'decision': 'approved' if action == 'approve' else 'rejected',
                   'pin-after': new if action == 'approve' else request['pin'],
                   'reasons': [] if action == 'approve' else ['precision-below-minimum'], 'validation-ms': 12.5,
                   'candidate': {'code-hash': f"code-{request['arm']}-{request['position']}"}}
        data = encoded(receipt) + b'\n'
        (library / 'receipts').mkdir(exist_ok=True)
        (library / 'receipts' / f'{digest(data)}.json').write_bytes(data)
        return subprocess.CompletedProcess([], 0, json.dumps({'receipt-sha256': digest(data)}).encode() + b'\n', b'')

    def trajectory(self, name, **extra):
        ready = {'ready': True, 'blockers': [], 'checks': {'sci_isolation': {'image': 's'}}}
        with patch.object(paired, 'trajectory_preflight', return_value=ready), \
             patch.object(paired, 'docker_state', return_value={'session': 'fixed', 'restart_pending': False, 'images': {}}), \
             patch.object(paired, 'GatewayClient', self.gateway()), patch.object(paired, 'run_arm', self.run_arm), \
             patch.object(paired, 'promote_process', self.promote_process), \
             patch.object(paired, 'compare', return_value={'scored': 'stub'}):
            return paired.run_trajectory(self.plan_path, self.suite, self.out, name,
                                         authorize_subscription_plan=self.plan['plan_sha256'], **extra)


class TrajectoryRunnerTests(TrajectoryFixture, unittest.TestCase):
    def test_plan_freezes_orders_rule_panel_and_initial_pin(self):
        value, manifest, _, spec = paired.read_trajectory_plan(self.plan_path, self.suite)
        self.assertEqual([t['id'] for t in value['trajectories']],
                         ['A-s101', 'C-s101', 'E-s101', 'A-s202', 'C-s202', 'E-s202', 'A-s303', 'C-s303', 'E-s303'])
        families = {t: f for f, ids in manifest['selection']['families'].items() for t in ids}
        orders = {}
        for t in value['trajectories']:
            self.assertEqual([p for p, task in enumerate(t['order'], 1) if families[task] == 'F2'], [8, 11, 14, 17])
            self.assertEqual(sorted(t['order']), sorted(manifest['task_ids']))
            orders.setdefault(t['seed'], set()).add(tuple(t['order']))
            self.assertEqual(t['initial_library_sha256'], None if t['arm'] == 'A' else paired.EMPTY_LIBRARY_SHA256)
        self.assertTrue(all(len(o) == 1 for o in orders.values()))  # the same order for A, C and E
        self.assertEqual(len({next(iter(o)) for o in orders.values()}), 3)  # three independent orders
        self.assertNotIn('trajectory', paired.capabilities(CONFIG))
        self.assertEqual(value['capabilities']['E']['trajectory']['promotion']['rule'], CONFIG['trajectory']['promotion_rule'])
        self.assertNotIn('promotion', value['capabilities']['C']['trajectory'])
        self.assertNotIn('proposal', value['capabilities']['A']['trajectory'])
        # A changed panel or plan is refused.
        panel = self.suite / 'controller/panel.json'
        original = panel.read_bytes()
        panel.write_bytes(original.replace(b'location', b'entity', 1))
        with self.assertRaisesRegex(ValueError, 'panel'):
            paired.read_trajectory_plan(self.plan_path, self.suite)
        panel.write_bytes(original)
        tampered = json.loads(self.plan_path.read_text())
        tampered['trajectories'][0]['order'].reverse()
        self.plan_path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError, 'Plan hash mismatch'):
            paired.read_trajectory_plan(self.plan_path, self.suite)

    def test_each_task_sees_the_pin_committed_after_the_previous_task_and_resumes_cold(self):
        self.script = {3: 'reject', 5: 'crash', 6: 'crash-after-write'}
        first = self.trajectory('E-s101')
        self.assertEqual(first['status'], 'cold-restart-required')
        out = self.out / 'E-s101'
        ledger = paired.trajectory_ledger(out)
        self.assertEqual([r['type'] for r in ledger], ['start'] + ['task', 'promotion'] * 9 + ['cold-restart'])
        promotions = [r for r in ledger if r['type'] == 'promotion']
        self.assertEqual([r['status'] for r in promotions],
                         ['committed', 'committed', 'rejected', 'committed', 'crashed', 'crashed',
                          'committed', 'committed', 'committed'])
        # Task k+1 ran on exactly the pin in force after task k; never on its own pending promotion.
        self.assertEqual(self.seen[0], paired.EMPTY_LIBRARY_SHA256)
        for k, promotion in enumerate(promotions[:-1]):
            self.assertEqual(self.seen[k + 1], promotion['pin_after'])
            self.assertEqual(self.seen[k], promotion['pin_before'])
            if promotion['status'] == 'committed':
                self.assertNotEqual(self.seen[k], promotion['pin_after'])
        # Failed and crashed promotions keep the previous pin; what a crash wrote is kept and listed.
        for promotion in promotions:
            if promotion['status'] != 'committed':
                self.assertEqual(promotion['pin_before'], promotion['pin_after'])
        self.assertEqual((promotions[4]['failure'], promotions[4]['orphans']), ('TimeoutExpired', []))
        self.assertEqual(len(promotions[5]['orphans']), 1)
        self.assertTrue((out / 'library/libraries' / f"{promotions[5]['orphans'][0]}.edn").is_file())
        self.assertEqual(promotions[2]['reasons'], ['precision-below-minimum'])
        self.assertEqual(ledger[-1]['pin'], promotions[-1]['pin_after'])
        # Promotion is recorded strictly after its task's answer and result row.
        for task, promotion in zip(ledger[1::2], ledger[2::2]):
            self.assertEqual((task['type'], promotion['type'], task['position']), ('task', 'promotion', promotion['position']))
            self.assertIsNotNone(task['answer_sha256'])
        # The resume is a new runner call that reads only the trajectory directory.
        self.seen.clear()
        second = self.trajectory('E-s101')
        self.assertEqual(second, {'scored': 'stub'})
        self.assertEqual(self.seen[0], ledger[-1]['pin'])
        results = list(jsonl(out / 'results.jsonl'))
        self.assertEqual([r['position'] for r in results], list(range(1, 19)))
        self.assertEqual([r['position'] for r in results if r['family'] == 'F2'], [8, 11, 14, 17])
        self.assertEqual([r['learning_library_sha256'] for r in results[9:]], self.seen)
        with self.assertRaisesRegex(ValueError, 'cold restart'):
            self.trajectory('E-s101')

    def test_a_changed_library_version_or_a_bad_rollback_is_refused_and_a_rollback_is_recorded(self):
        self.trajectory('E-s101')
        out = self.out / 'E-s101'
        committed = [r['pin_after'] for r in paired.trajectory_ledger(out) if r.get('status') == 'committed']
        with self.assertRaisesRegex(ValueError, 'never committed'):
            paired.rollback_trajectory(self.out, 'E-s101', 'a' * 64, 'test')
        row = paired.rollback_trajectory(self.out, 'E-s101', committed[0], 'operator rollback drill')
        self.assertEqual((row['type'], row['from'], row['to'], row['after_position']), ('rollback', committed[-1], committed[0], 9))
        # The rollback row follows the cold restart; the resume refuses until it is the last row again.
        with self.assertRaisesRegex(ValueError, 'cold restart'):
            self.trajectory('E-s101')
        path = out / 'library/libraries' / f'{committed[1]}.edn'
        path.write_bytes(path.read_bytes().replace(b'E-2', b'E-9'))
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            paired.verify_library_chain(out / 'library', paired.trajectory_ledger(out), paired.EMPTY_LIBRARY_SHA256)

    def test_a_rollback_before_a_task_puts_the_earlier_pin_in_force(self):
        self.trajectory('C-s101')
        out = self.out / 'C-s101'
        ledger = paired.trajectory_ledger(out)
        committed = [r['pin_after'] for r in ledger if r.get('status') == 'committed']
        # Drill: roll back, then restore the cold-restart marker the resume needs.
        paired.rollback_trajectory(self.out, 'C-s101', committed[2], 'regression found in review')
        paired.append_ledger(out, {**ledger[-1], 'pin': committed[2]})
        self.seen.clear()
        self.trajectory('C-s101')
        self.assertEqual(self.seen[0], committed[2])
        promotion = next(r for r in paired.trajectory_ledger(out) if r['type'] == 'promotion' and r['position'] == 10)
        self.assertEqual(promotion['pin_before'], committed[2])

    def test_arms_keep_separate_libraries_and_arm_a_has_none(self):
        self.trajectory('A-s101')
        self.trajectory('C-s101')
        self.trajectory('E-s101')
        a, c, e = (self.out / name for name in ('A-s101', 'C-s101', 'E-s101'))
        self.assertFalse((a / 'library').exists())
        self.assertFalse(any(r['type'] == 'promotion' for r in paired.trajectory_ledger(a)))
        self.assertTrue(all(r['learning_library_sha256'] == digest(encoded([])) for r in jsonl(a / 'results.jsonl')))
        self.assertTrue(all(r['arm'] == 'A' for r in jsonl(a / 'results.jsonl')))
        c_pins = {r['pin_after'] for r in paired.trajectory_ledger(c) if r['type'] == 'promotion'}
        e_pins = {r['pin_after'] for r in paired.trajectory_ledger(e) if r['type'] == 'promotion'}
        self.assertEqual(c_pins & e_pins, set())
        self.assertNotEqual((c / 'library').resolve(), (e / 'library').resolve())
        # Each library directory holds only its own trajectory's versions (plus the shared empty start).
        for directory, pins in ((c, c_pins), (e, e_pins)):
            files = {p.stem for p in (directory / 'library/libraries').glob('*.edn')}
            self.assertEqual(files, pins | {paired.EMPTY_LIBRARY_SHA256})
        # The per-task switches: A runs the plan's own config; C and E get their own pinned library.
        task = json.loads((e / '01-aljure/promotion-request.json').read_text())
        self.assertEqual((task['arm'], Path(task['library'])), ('E', e / 'library'))

    def test_costs_charge_fallback_as_task_inference_and_the_proposal_as_acquisition(self):
        self.trajectory('A-s101')
        self.trajectory('A-s101')
        self.trajectory('E-s101')
        self.trajectory('E-s101')
        # F2 task 8 refused the function F1 task 1 proposed: a correct refusal. F1 task 9 refusing it is not.
        for position in (8, 9):
            result = self.out / f'E-s101/{position:02}-aljure/agent/result.json'
            value = json.loads(result.read_text())
            value['artifact-reuse'] = {'classification': 'direct-answer',
                                       'refused': [{'code-hash': 'code-E-1', 'reason': 'inapplicable'}]}
            result.write_text(json.dumps(value))
        report = paired.trajectory_report(self.out, self.suite)
        e, a = report['trajectories']['E-s101'], report['trajectories']['A-s101']
        self.assertTrue(e['complete'] and a['complete'])
        call = (1000 * 2 + 100 * 10) / 1e6
        for case in e['cases']:
            self.assertAlmostEqual(case['acquisition_usd'], call)
            self.assertAlmostEqual(case['task_inference_usd'], 2 * call)  # includes the fallback call
            self.assertAlmostEqual(case['total_usd'], 3 * call)
            self.assertIsNotNone(case['validation_seconds'])
        for case in a['cases']:
            self.assertAlmostEqual(case['acquisition_usd'], 0)
            self.assertAlmostEqual(case['total_usd'], 2 * call)
            self.assertEqual(case['activation'], 'stateless')
        f1 = report['arms']['E']['F1'][0]
        self.assertAlmostEqual(f1['cost_usd_including_acquisition'], 14 * 3 * call)
        self.assertAlmostEqual(f1['acquisition_usd'], 14 * call)
        # E costs more on every task here, so it never breaks even.
        self.assertIsNone(report['break_even_position']['E-s101'])
        self.assertEqual([c['position'] for c in e['cases'] if c['correct_refusal']], [8])
        self.assertEqual(report['arms']['E']['F2'][0]['activation']['correct-refusal'], 1)
        self.assertEqual(report['arms']['E']['F1'][0]['activation']['correct-refusal'], 0)
        self.assertIn('fallback', report['fallback_accounting'])

    def test_new_records_exclude_panel_and_earlier_task_texts_and_skip_the_empty_library(self):
        rows = [{'position': p, 'task_id': t, 'family': 'F1', 'learning_library_sha256': pin}
                for p, t, pin in ((1, 'a', paired.EMPTY_LIBRARY_SHA256), (2, 'b', 'pin-1'), (3, 'c', 'pin-1'), (4, 'd', 'pin-2'))]
        line = 'Date: Jan 01, 2023 || User: 1 || Instance: {}'
        texts = {'a': ['x', 'y'], 'b': ['y', 'z', 'p'], 'c': ['z', 'y'], 'd': ['w ']}
        contexts = {t: (f'question {t}', '\n'.join(line.format(x) for x in xs)) for t, xs in texts.items()}
        gold = {t: [{'case': f'{t}{n}', 'text': x, 'label': 'L'} for n, x in enumerate(xs)] for t, xs in texts.items()}
        cases, groups = paired.new_record_windows(rows, contexts, gold, {'p'})
        # 'y' was held by task 1, 'p' by the panel; task 3 holds nothing new; 'w ' is new once trimmed.
        self.assertEqual([c['new_records'] for c in cases], [2, 1, 0, 1])
        self.assertEqual({pin: [(w['id'], [i['text'] for i in w['items']]) for w in ws] for pin, ws in groups.items()},
                         {'pin-1': [('p02', ['z'])], 'pin-2': [('p04', ['w '])]})
        self.assertEqual(groups['pin-1'][0]['question'], 'question b')

    def test_new_record_endpoint_scores_each_e_pin_once_and_feeds_the_report(self):
        self.trajectory('E-s101')
        self.trajectory('E-s101')
        calls = []

        def score_process(request_path, environment, seconds):
            request = json.loads(Path(request_path).read_text())
            panel = json.loads(Path(request['panel']).read_text())
            calls.append((request['pin'], Path(request['panel']).stat().st_mode & 0o777, environment.get('REPL_LAB_WORKER_AUDIT_DIR')))
            windows = [{'window': w['id'], 'admitted': 1, 'errors': 0, 'items': len(w['items']),
                        'decided': sum(i['text'].startswith(('Where', 'WIN')) for i in w['items']),
                        'correct': sum(i['text'].startswith('Where') for i in w['items']),
                        # The version's own predicted labels, as the real score command reports them.
                        'labels': {k: v for k, v in {'location': sum(i['text'].startswith('Where') for i in w['items']),
                                                     'spam': sum(i['text'].startswith('WIN') for i in w['items'])}.items() if v}}
                       for w in panel['windows']]
            reply = {'pin': request['pin'], 'model-calls': 0, 'windows': windows}
            return subprocess.CompletedProcess([], 0, json.dumps(reply).encode() + b'\n', b'')

        with patch.object(paired, 'score_process', score_process):
            result = paired.trajectory_new_records(self.plan_path, self.suite, self.out)
            with self.assertRaisesRegex(ValueError, 'exists'):
                paired.trajectory_new_records(self.plan_path, self.suite, self.out)
        self.assertEqual((result['model_calls'], result['complete_trajectories']), (0, 1))
        self.assertEqual(result['trajectories']['E-s202'], {'complete': False})
        cases = result['trajectories']['E-s101']['cases']
        tasks = {t['task_id']: t for t in jsonl(self.suite / 'public/tasks.jsonl')}
        first, contexts = set(), set()
        for case in cases:
            if tasks[case['task_id']]['context_sha256'] not in contexts:
                first.add(case['position'])
            contexts.add(tasks[case['task_id']]['context_sha256'])
        # Every window's first task has 4 new records; its second task has none. Task 1 ran on the empty library.
        self.assertEqual([c['new_records'] for c in cases], [4 if c['position'] in first else 0 for c in cases])
        self.assertEqual({c['position'] for c in cases if c['scored']}, first - {1})
        # One scoring call per distinct pin in force (new-record and whole-window panels together).
        self.assertEqual(len(calls), len({c['pin'] for c in cases if c['position'] != 1}))
        # The whole-window scoring says whether the version decides each count task's asked label.
        tasks_by_id = {t['task_id']: t for t in jsonl(self.suite / 'public/tasks.jsonl')}
        for case in cases:
            asked = paired.COUNT_QUESTION.search(tasks_by_id[case['task_id']]['question'])
            self.assertEqual(case['asked_label'], asked.group(1) if asked else None)
            if case['position'] == 1:
                self.assertEqual((case['window_labels'], case['decides_asked_label']), ({}, False))
            elif asked:
                self.assertEqual(case['decides_asked_label'], asked.group(1) in case['window_labels'])
        self.assertTrue(all(mode == 0o600 and audit for _, mode, audit in calls))
        f1 = [c for c in cases if c['scored'] and c['family'] == 'F1']
        self.assertEqual(result['pooled']['F1'], {'tasks': len(f1), 'new_records': 4 * len(f1), 'decided': len(f1),
                                                  'correct': len(f1), 'coverage': [len(f1), 4 * len(f1)],
                                                  'precision': [len(f1), len(f1)], 'meets_promotion_thresholds': True})
        self.assertFalse(result['pooled']['F2']['meets_promotion_thresholds'])
        report = paired.trajectory_report(self.out, self.suite)
        self.assertEqual(report['new_record_endpoint']['pooled'], result['pooled'])
        self.assertIn('f1_count_log_error_by_decidability', report)
        self.assertIn('model_directed', report['arms']['E']['F1'][0])

    def test_a_promotion_stage_fault_is_recorded_and_stops_the_trajectory(self):
        # The promotion JVM reports a stage-level fault (exit 3, fatal) at task 4: not the candidate's failure.
        self.script = {4: 'stage-fatal'}
        with self.assertRaisesRegex(ValueError, 'Trajectory stopped'):
            self.trajectory('E-s101')
        ledger = paired.trajectory_ledger(self.out / 'E-s101')
        promotions = [r for r in ledger if r['type'] == 'promotion']
        self.assertEqual([r['status'] for r in promotions], ['committed', 'committed', 'committed', 'stage-failed'])
        self.assertEqual((promotions[-1]['failure'], promotions[-1]['pin_after']), ('PromotionStageFailed', promotions[-1]['pin_before']))
        self.assertIn('Isolation proof', promotions[-1]['stage_error'])
        # No task 5 ran: the stage fault stops the trajectory, and the ledger records nothing after it.
        self.assertEqual(sum(r['type'] == 'task' for r in ledger), 4)

    def test_a_receipt_integrity_failure_stops_the_trajectory_like_a_stage_fault(self):
        self.script = {2: 'bad-receipt'}
        with self.assertRaisesRegex(ValueError, 'Trajectory stopped'):
            self.trajectory('E-s101')
        promotions = [r for r in paired.trajectory_ledger(self.out / 'E-s101') if r['type'] == 'promotion']
        self.assertEqual([r['status'] for r in promotions], ['committed', 'stage-failed'])
        self.assertEqual(promotions[-1]['stage_error'], 'Receipt missing or changed')
        self.assertEqual(promotions[-1]['pin_after'], promotions[-1]['pin_before'])

    def test_the_spend_cap_stops_new_tasks(self):
        self.tokens = 1_000_000  # $2 per call: one task spends past the cap margin
        with patch.dict(self.plan['config']['trajectory'], {}):
            with self.assertRaisesRegex(ValueError, 'spend cap'):
                for name in ('A-s101', 'A-s202', 'A-s303', 'C-s101'):
                    self.trajectory(name)

    def test_a_recorded_answer_survives_a_proposal_turn_deadline(self):
        out = self.root / 'task'
        (out / 'agent').mkdir(parents=True)
        (out / 'agent/answer.txt').write_text('Answer: 3')
        (out / 'agent/answer-recorded.json').write_text(json.dumps({'sha256': digest(b'Answer: 3')}))
        self.assertEqual(paired.trajectory_status({'failure': 'wall-time-limit'}, out), ('completed', 'ProposalTurnDeadline'))
        self.assertEqual((out / 'answer.txt').read_text(), 'Answer: 3')
        (out / 'agent/answer-recorded.json').write_text(json.dumps({'sha256': 'f' * 64}))
        (out / 'answer.txt').unlink()
        self.assertEqual(paired.trajectory_status({'failure': 'wall-time-limit'}, out)[0], 'timeout')


class ContractSwitchTests(unittest.TestCase):
    def test_acquisition_is_off_by_default_and_needs_a_pinned_library(self):
        base = {k: v for k, v in CONFIG.items() if k != 'trajectory'}
        self.assertNotIn('acquisition', paired.aljure_contract(base))
        self.assertNotIn('execution_contract', paired.capabilities(base)['aljure'])
        with self.assertRaisesRegex(ValueError, 'needs aljure_contract.artifacts'):
            paired.aljure_contract({**base, 'aljure_contract': {'acquisition': {'arm': 'E'}}})
        with self.assertRaisesRegex(ValueError, 'acquisition must be'):
            paired.aljure_contract({**base, 'aljure_contract': {'acquisition': {'arm': 'A'},
                                                                'artifacts': {'library': 'var/x', 'library_sha256': 'a' * 64}}})
        on = paired.trajectory_contract(base, 'E', 'var/x/library', 'b' * 64)
        contract = paired.aljure_contract(on)
        self.assertEqual(contract['acquisition'], {'arm': 'E'})
        self.assertIn('acquisition', paired.capabilities(on)['aljure']['execution_contract'])
        self.assertIs(paired.trajectory_contract(base, 'A'), base)

    def test_existing_configs_keep_their_capabilities(self):
        for path in sorted((ROOT / 'config').glob('*.json')):
            config = json.loads(path.read_text())
            if 'provider' not in config or 'trajectory' in config:
                continue
            caps = paired.capabilities(config)
            self.assertNotIn('trajectory', caps)
            self.assertNotIn('acquisition', json.dumps(caps), path.name)

    def test_the_chain_check_refuses_a_version_whose_parent_is_not_the_pin_in_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'libraries'
            root.mkdir()
            (root / f'{paired.EMPTY_LIBRARY_SHA256}.edn').write_bytes(paired.EMPTY_LIBRARY)
            wrong = b'{:entries [], :parent "%s", :schema :aljure-library-v1}\n' % (b'c' * 64)
            (root / f'{digest(wrong)}.edn').write_bytes(wrong)
            rows = [{'type': 'promotion', 'status': 'committed', 'pin_before': paired.EMPTY_LIBRARY_SHA256,
                     'pin_after': digest(wrong)}]
            with self.assertRaisesRegex(ValueError, 'parent differs'):
                paired.verify_library_chain(Path(tmp), rows, paired.EMPTY_LIBRARY_SHA256)
            # A summary string that imitates a parent cannot satisfy the end-anchored check.
            spoof = (b'{:entries [{:summary ":parent \\"%s\\", :schema :aljure-library-v1}"}], :parent "%s", '
                     b':schema :aljure-library-v1}\n') % (paired.EMPTY_LIBRARY_SHA256.encode(), b'd' * 64)
            (root / f'{digest(spoof)}.edn').write_bytes(spoof)
            with self.assertRaisesRegex(ValueError, 'parent differs'):
                paired.verify_library_chain(Path(tmp), [{**rows[0], 'pin_after': digest(spoof)}], paired.EMPTY_LIBRARY_SHA256)


if __name__ == '__main__':
    unittest.main()
