"""Versioned external comparison. Planning is offline; API execution is opt-in.

This is a full-harness comparison, not a language-only experiment. A subscription
approval never enables Anthropic API billing. No fixture answers enter this path.
"""
import json
import os
from pathlib import Path
import subprocess
import time

from .oolong import checked_file, compare, digest, encoded, money, read_suite, require, write_jsonl
from .gateway_client import AnthropicMessagesTransport, GatewayClient, Relay
from .prime import container as native

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'external-paired-v1'
RATE_KEYS = {'input': 'input_tokens', 'output': 'output_tokens', 'cache-read': 'cache_read_input_tokens',
             'cache-write-5m': 'cache_creation_5m_input_tokens', 'cache-write-1h': 'cache_creation_1h_input_tokens'}
CAPABILITIES = {
    'claim': 'complete-harness comparison; no language-only causal claim',
    'shared': {'context': 'identical complete public text, external to model prompt',
               'network': 'no worker egress; host-only Messages gateway',
               'memory_mb': 256, 'cpus': 1, 'pids': 32, 'task_seconds': 120,
               'inference': 'same model/settings, per-arm caps; descendants/refinement/compaction included',
               'library': 'fresh initial state; no prior benchmark transcripts or learned answers'},
    'aljure': {'language': 'Clojure SCI', 'context_access': 'external-context binding and line query broker',
                'tools': 'existing EDN broker', 'children': 'synchronous recursive sessions',
                'filesystem': 'SCI has no filesystem/process/network capability',
                'skills': 'task-local code; empty retained library; no benchmark development evaluator',
                'expression_seconds': 10, 'expression_output_bytes': 65536,
                'history': 'existing bounded history; no model-based compaction'},
    'prime': {'language': 'native Python', 'context_access': '/work/context.txt',
              'tools': 'unmodified pinned native tools, skills, refinement, subagents and messaging',
              'children': 'native asynchronous orchestration',
              'filesystem': 'read-only image plus bounded /tmp and /work; native shell tools retained',
              'expression_seconds': None, 'task_output_bytes': 4194304,
              'provider_usage_attribution': 'all requests charged; individual native ancestry/purpose unverified',
              'output_request': 'native per-request choice, often model output ceiling / 3'},
    'known_differences': ['Harness prompts/tool schemas differ and are recorded.',
                          'Output token allowance matches; actual requested max_tokens may differ.',
                          'Native Python packages/process tools exceed SCI capabilities.',
                          'Prime has 8MiB additional writable /work for native state.',
                          'Aljure worker initialization has per-chunk overhead; Prime loads one file.',
                          'Gateway buffers bounded SSE responses; timing differs from direct streaming.',
                          'No continual-learning or refinement-benefit claim follows from a fresh-task pilot.']}


def source_snapshot():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    files = {name: digest((ROOT / name).read_bytes()) for name in names
             if (ROOT / name).is_file() and not name.startswith(('var/', '__pycache__/'))}
    return {'commit': commit, 'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
            'files': files, 'sha256': digest(encoded(files))}


def runtime_snapshot(root=ROOT):
    """Attest executable/configuration inputs without coupling proof to reports.

    Full provenance and the frozen live plan still use source_snapshot(). This
    scope includes every controller/broker/provider, prompt, worker, gateway,
    importer, scorer, dependency pin and CLI/config input. Tests and research
    output cannot change the attested execution capability.
    """
    root = Path(root)
    names = set()
    for directory in ('src', 'scripts', 'worker', 'benchmark', 'resources', 'config'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.md'):
                names.add(path.relative_to(root))
    for name in ('Makefile', 'deps.edn'):
        if (root / name).is_file():
            names.add(Path(name))
    files = {str(name): digest((root / name).read_bytes()) for name in sorted(names)}
    return {'scope': 'external-execution-v1', 'files': files, 'sha256': digest(encoded(files))}


def validate_config(config):
    require(config.get('provider') == 'anthropic-api',
            'Native Prime subscription Messages/tool/stream parity is unverified; no subscription-to-API fallback')
    require(config.get('model') == 'claude-sonnet-5-5', 'This pilot keeps the requested Sonnet 5.5 model fixed')
    require(config.get('pinned_settings') == {'thinking': {'type': 'adaptive', 'display': 'summarized'}, 'output_config': {'effort': 'medium'}},
            'This native adapter supports adaptive/summarized medium and omitted sampling parameters only')
    for key in ('context_window', 'max_output_tokens', 'calls_per_arm', 'tokens_per_arm', 'concurrent_requests'):
        require(type(config.get(key)) is int and config[key] > 0, f'Missing positive {key}')
    require(config['max_output_tokens'] <= config['context_window'], 'Output ceiling exceeds context bound')
    require(set(config.get('rates', {})) == set(RATE_KEYS), 'All cache/input/output rates are required')
    require(all(money(v) > 0 for v in config['rates'].values()), 'All rates must be positive')
    require(money(config['usd_per_arm']) > 0 and money(config['total_usd']) > 0, 'Hard caps required')


def plan(suite, config_path, output):
    manifest, tasks, _ = read_suite(suite)
    require(manifest['input_provenance'] == 'verified-pinned-upstream', 'Live planning requires authenticated official inputs')
    require(len(tasks) in (1, 10), 'Start with one case, then ten cases')
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    require(money(config['usd_per_arm']) * 2 * len(tasks) <= money(config['total_usd']),
            'Sum of disjoint task allowances exceeds the global ceiling')
    sequence = [{'task_id': task, 'harness': harness}
                for index, task in enumerate(manifest['task_ids'])
                for harness in (('aljure', 'prime') if index % 2 == 0 else ('prime', 'aljure'))]
    value = {'version': VERSION, 'evidence': 'IMPLEMENTED / UNVERIFIED', 'authorized': False,
             'suite_sha256': manifest['suite_sha256'], 'config': config, 'source': source_snapshot(),
             'runtime_source': runtime_snapshot(),
             'prime_commit': native.PIN, 'capabilities': CAPABILITIES,
             'capability_sha256': digest(encoded(CAPABILITIES)), 'sequence': sequence,
             'allocation': {'per_arm_usd': config['usd_per_arm'], 'total_usd': config['total_usd'],
                            'allocated_usd': float(money(config['usd_per_arm']) * len(sequence)),
                            'total_call_ceiling': config['calls_per_arm'] * len(sequence),
                            'total_token_ceiling': config['tokens_per_arm'] * len(sequence),
                            'borrowing': False},
             'model_calls': 0,
             'approval_scope': 'NEW Anthropic API billing, not Claude subscription usage; approve this exact plan hash'}
    value['plan_sha256'] = digest(encoded(value))
    with Path(output).open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    return value


def read_plan(path, suite):
    value = json.loads(Path(path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    manifest, tasks, _ = read_suite(suite)
    require(value['version'] == VERSION and value['suite_sha256'] == manifest['suite_sha256'], 'Plan/suite mismatch')
    validate_config(value['config'])
    expected = [{'task_id': task, 'harness': harness} for i, task in enumerate(manifest['task_ids'])
                for harness in (('aljure', 'prime') if i % 2 == 0 else ('prime', 'aljure'))]
    require(value['sequence'] == expected, 'Plan omitted, repeated or reordered a case')
    require(money(value['config']['usd_per_arm']) * len(expected) <= money(value['config']['total_usd']), 'Global allocation exceeded')
    require(value['source']['sha256'] == source_snapshot()['sha256'], 'Source changed after plan freeze')
    require(value['runtime_source'] == runtime_snapshot(), 'Runtime inputs changed after plan freeze')
    require(value['capabilities'] == CAPABILITIES and value['prime_commit'] == native.PIN, 'Capability/source pins changed')
    return value, manifest, tasks


def preflight(plan_path, suite):
    value, manifest, _ = read_plan(plan_path, suite)
    config = value['config']
    blockers, checks = [], {}
    contract = config.get('verified_model_contract', {})
    if not (contract.get('verified') is True and contract.get('source') and
            contract.get('model') == config['model'] and contract.get('context_window') == config['context_window'] and
            contract.get('rates') == config['rates']):
        blockers.append('Exact provider model/context bound and all cache rates require primary-source verification')
    # These read-only checks never execute agent code or contact a model.
    from .prime.isolation import require_tested
    try:
        checks['prime_isolation'] = require_tested()
    except Exception as error:
        blockers.append('Native Prime isolation: ' + str(error))
    try:
        result = subprocess.run(['python3', 'scripts/clj.py', '-e',
                                 "(require '[repl-lab.isolation :as i]) (i/require-tested!) (println :tested) (shutdown-agents)"],
                                cwd=ROOT, capture_output=True, timeout=25)
        require(result.returncode == 0, 'strict SCI isolation proof unavailable')
        proof = json.loads((ROOT / 'var/isolation-proof.json').read_text())
        require(proof.get('gate_version', proof.get('gate-version', 0)) >= 2,
                'same-worker readiness gate must be merged and validated')
        checks['sci_isolation'] = {'image': proof['image'], 'proof_sha256': digest(encoded(proof))}
    except Exception as error:
        blockers.append('SCI isolation: ' + str(error))
    # The new native relay must be exercised with actual root/child/tool events
    # through the same bridge before this command can dispatch live traffic.
    proof_path = ROOT / 'var/external-relay-proof.json'
    try:
        proof = json.loads(proof_path.read_text())
        require(proof.get('evidence') == 'FIXTURE' and proof.get('status') == 'PASSED', 'missing completed relay fixture')
        require(proof.get('runtime_source') == value['runtime_source'], 'relay fixture runtime/config inputs differ')
        require(proof.get('prime_image') == checks.get('prime_isolation', {}).get('image') and
                proof.get('sci_image') == checks.get('sci_isolation', {}).get('image'), 'relay fixture worker image differs')
        require(all(proof.get('checks', {}).get(k) is True for k in
                    ('native_root', 'native_child', 'native_tool', 'native_compaction', 'native_refinement',
                     'native_signed_thinking', 'sci_context', 'shared_budget', 'cleanup')),
                'native/common relay fixture coverage incomplete')
        checks['relay_fixture'] = {'sha256': digest(encoded(proof))}
    except Exception as error:
        blockers.append('Common transport validation: ' + str(error))
    return {'ready': not blockers, 'model_calls': 0, 'plan_sha256': value['plan_sha256'],
            'checks': checks, 'blockers': blockers, 'billing_transport': 'Anthropic API; separate authorization required',
            'subscription_native_prime_ready': False, 'strict_language_parity': False}


def gateway_config(config, route):
    return {'model': config['model'], 'context-window': config['context_window'],
            'max-output': config['max_output_tokens'], 'pinned-settings': config['pinned_settings'],
            'rates': config['rates'], 'routes': [route],
            'limits': {'calls': config['calls_per_arm'], 'tokens': config['tokens_per_arm'],
                       'usd': config['usd_per_arm'], 'wall-ms': 120000,
                       'concurrent-subagents': config['concurrent_requests']}}


def public_input(suite, task):
    text = checked_file(Path(suite) / 'public', task['context_path'], task['context_sha256']).read_text()
    require(len(text.encode()) <= 1500000, 'Public context exceeds declared adapter limit')
    return {'task': {'task_id': task['task_id'], 'question': task['question']}, 'context': text}


def run_arm(harness, data, out, config, gateway, readiness):
    relay = Relay(gateway, harness)
    def preserve(result):
        (out / 'stdout.jsonl').write_bytes(result['stdout'])
        (out / 'stderr.txt').write_bytes(result['stderr'])
        (out / 'execution.json').write_bytes(encoded({k: v for k, v in result.items() if k not in ('stdout', 'stderr')}))
    if harness == 'aljure':
        limits = {'recursion-depth': 8, 'history-records': 24, 'message-bytes': 32768, 'context-bytes': 65536,
                  'messages': 100, 'candidates': 0, 'evaluation-episodes': 0, 'event-budget': 10000,
                  **gateway_config(config, harness)['limits']}
        body = {**data, 'config': {'limits': limits}, 'gateway-config': gateway_config(config, harness),
                'model-config': {'model': config['model']}}
        environment = {k: v for k, v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
        environment['REPL_LAB_WORKER_AUDIT_DIR'] = str(out / 'worker-audit')
        result = native.bounded_process(['python3', 'scripts/clj.py', '-m', 'repl-lab.external-task', str(out / 'agent')],
                                        encoded(body) + b'\n', seconds=120, max_input=2 * 1024**2,
                                        completion_type='external_agent_complete', event_handler=relay, environment=environment)
        preserve(result)
        answer = out / 'agent/answer.txt'
        files = {'answer.txt': answer.read_bytes()} if answer.exists() else {}
    else:
        prompt = ('Solve this external-context task using your native tools. The complete public context is at /work/context.txt. '
                  'Write only the requested benchmark answer to /work/answer.txt. Hidden evaluation is unavailable.\n\n' + data['task']['question'])
        body = {'mode': 'external-gateway', 'model': config['model'], 'context_window': config['context_window'],
                'max_output': config['max_output_tokens'], 'prompt': prompt, 'context': data['context'], 'rates': config['rates']}
        source = (ROOT / 'benchmark/prime/relay_bootstrap.py').read_text()
        with native.container(readiness['checks']['prime_isolation']['image'], ['-c', source],
                              entrypoint='/opt/venv/bin/python') as (name, _):
            result = native.execute(name, encoded(body) + b'\n', max_input=2 * 1024**2,
                                    completion_type='external_agent_complete', event_handler=relay)
            preserve(result)  # Save before artifact collection or cleanup can fail.
            files = native.regular_files(native.snapshot(name)) if result['completion'] else {}
            (out / 'native').mkdir()
            for name, content in files.items():
                path = out / 'native' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
    if 'answer.txt' in files:
        (out / 'answer.txt').write_bytes(files['answer.txt'])
    return result


def run(plan_path, suite, output, *, authorize_api_plan=None):
    value, manifest, tasks = read_plan(plan_path, suite)
    require(authorize_api_plan == value['plan_sha256'],
            'New API billing is not authorized. Approve the frozen plan, then pass --authorize-api-plan with its exact hash')
    ready = preflight(plan_path, suite)
    require(ready['ready'], 'Live run refused: ' + '; '.join(ready['blockers']))
    require(not Path(output).exists(), 'Output exists; prior evidence must remain unchanged')
    config = value['config']
    output = Path(output).resolve()
    output.mkdir(parents=True)
    (output / 'plan.json').write_bytes(encoded(value))
    (output / 'preflight.json').write_bytes(encoded(ready))
    transport = AnthropicMessagesTransport(authorized=True)
    results, stop = [], False
    model = {'provider': config['provider'], 'model': config['model'], 'thinking': 'adaptive/summarized; effort=medium',
             'temperature': 'provider-default', 'max_output_tokens': config['max_output_tokens']}
    pricing = {RATE_KEYS[k]: v for k, v in config['rates'].items()}
    for index, entry in enumerate(value['sequence']):
        task, harness = tasks[entry['task_id']], entry['harness']
        out = output / f'{index:02}-{harness}'
        out.mkdir()
        started, status, failure = time.monotonic(), 'error', None
        gateway = None
        try:
            require(not stop, 'Not attempted: an earlier provider/cleanup failure stopped this frozen pilot')
            data = public_input(suite, task)
            (out / 'public-input.json').write_bytes(encoded(data))
            gateway = GatewayClient(out / 'gateway', gateway_config(config, harness), transport, evidence='LIVE MODEL RUN')
            execution = run_arm(harness, data, out, config, gateway, ready)
            status = ('timeout' if execution['failure'] == 'wall-time-limit' else 'completed'
                      if execution.get('completion', {}).get('native_exit_code') == 0 and (out / 'answer.txt').exists() else 'error')
        except Exception as error:
            failure = type(error).__name__  # No secret-bearing exception messages.
            stop = True
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception:
                    stop = True
                    failure, status = 'GatewayRecoveryFailure', 'error'
        usage = out / 'gateway/usage.jsonl'
        if not usage.exists():
            require(gateway is None, 'Cannot export a report without recovering the gateway ledger')
            (out / 'gateway').mkdir(exist_ok=True)
            usage.write_bytes(b'')
        receipts = [json.loads(line) for line in usage.read_text().splitlines() if line]
        if any(row['status'] == 'unknown' for row in receipts):
            stop = True
            failure, status = 'ProviderOutcomeUnknown', 'error'
        trace = out / 'trace.json'
        trace.write_bytes(encoded({'status': status, 'failure': failure, 'case': entry,
                                  'artifacts': {str(p.relative_to(out)): digest(p.read_bytes())
                                                for p in out.rglob('*') if p.is_file()}}))
        row = {**entry, 'suite_sha256': manifest['suite_sha256'], 'task_sha256': task['task_sha256'],
               'provenance': 'recorded-model-run', 'fresh_session': True, 'model_config': model,
               'budget_usd': config['usd_per_arm'], 'pricing_usd_per_m': pricing,
               'harness_revision': value['source']['commit'] if harness == 'aljure' else native.PIN,
               'status': status, 'wall_time_ms': (time.monotonic() - started) * 1000,
               'capability_sha256': value['capability_sha256'], 'source_sha256': value['source']['sha256'],
               'learning_library_sha256': digest(encoded([])), 'failure': failure}
        for label, path in [('trace', trace), ('usage', usage)] + ([('answer', out / 'answer.txt')] if status == 'completed' else []):
            row[label + '_path'] = str(path.relative_to(output))
            row[label + '_sha256'] = digest(path.read_bytes())
        results.append(row)
        write_jsonl(output / 'results.jsonl', results)
    report = compare(suite, output / 'results.jsonl')
    report['limitations'] = CAPABILITIES['known_differences']
    report['billing'] = 'API usage at configured rates; provider invoices are not measured'
    (output / 'report.json').write_bytes(encoded(report))
    return report
