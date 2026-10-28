"""Versioned external comparison. Planning is offline; API execution is opt-in.

This is a full-harness comparison, not a language-only experiment. A subscription
approval never enables Anthropic API billing. No fixture answers enter this path.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .oolong import checked_file, compare, digest, encoded, money, read_suite, require, write_jsonl
from .gateway_client import AnthropicMessagesTransport, ClaudeSubscriptionTransport, GatewayClient, Relay
from .subscription_protocol import PROVIDER as SUBSCRIPTION, VERSION as OAUTH_VERSION
from .prime import container as native

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'external-paired-v1'
RATE_KEYS = {'input': 'input_tokens', 'output': 'output_tokens', 'cache-read': 'cache_read_input_tokens',
             'cache-write-5m': 'cache_creation_5m_input_tokens', 'cache-write-1h': 'cache_creation_1h_input_tokens'}
MODEL_CONTRACTS = {
    'claude-sonnet-5-5': {'context_window': 1000000, 'max_output_tokens': 128000,
                        'rates': {'input': 2, 'output': 10, 'cache-read': .1, 'cache-write-5m': 2.5, 'cache-write-1h': 4}},
    'claude-opus-5-5': {'context_window': 1000000, 'max_output_tokens': 128000,
                      'rates': {'input': 4, 'output': 20, 'cache-read': .2, 'cache-write-5m': 5, 'cache-write-1h': 8}}}
CAPABILITIES = {
    'claim': 'complete-harness comparison; no language-only causal claim',
    'shared': {'context': 'identical complete public text, external to model prompt',
               'network': 'no worker egress; host-only Messages gateway',
               'memory_mb': 256, 'cpus': 1, 'pids': 32, 'task_seconds': 120,
               'inference': 'same model/settings, per-arm caps; descendants/refinement/compaction included',
               'library': 'fresh initial state; no prior benchmark transcripts or learned answers'},
    'aljure': {'language': 'Clojure SCI', 'context_access': 'external-context binding and line query broker',
                'tools': 'existing EDN broker; one provider-native tool per command', 'children': 'synchronous recursive sessions',
                'response_envelope': ('native-tool-v1; exactly one native tool call per response, mapped onto the '
                                      'EDN command schemas; text is never executed'),
                'format_corrections': 'at most one per task including children/resume; same accounted provider and caps',
                'filesystem': 'SCI has no filesystem/process/network capability',
                'skills': 'task-local code; empty retained library; no benchmark development evaluator',
                'expression_seconds': 10, 'expression_output_bytes': 65536,
                'worker_startup': 'separate 30 s bound before any expression clock starts',
                'answer': 'done summary text, or a string computed in the session SCI worker',
                'prompt_caching': 'tools and newest block marked, as in the native request',
                'history': 'append-only full history in tool mode; no model-based compaction'},
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


def capabilities(config):
    if config['provider'] != SUBSCRIPTION:
        return CAPABILITIES
    from .subscription_protocol import IDENTITY, PUBLIC_HEADERS
    return {**CAPABILITIES, 'subscription_protocol': {
        'version': OAUTH_VERSION, 'public_headers': PUBLIC_HEADERS,
        'identity_prefix': IDENTITY, 'identity_source': 'pinned native OAuth serializer; same prefix for Aljure',
        'credentials': 'host-only OAuth; no API fallback; no automatic refresh',
        'billing': 'API-rate-equivalent; actual subscription invoice unknown',
        'native_serialization': 'unchanged OAuth tool names, tool blocks and signed thinking',
        'aljure_serialization': 'JSON response/text EDN loop; previous thinking omitted under Messages rules',
        'cache_difference': 'native cache markers preserved; Aljure identity is not cached explicitly',
        'local_cli': 'not used for inference; private credential source is operator-selected',
        'actual_provider_compatibility': 'UNVERIFIED until separately authorized response'}}


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
    if 'execution_images' in config:
        images = config['execution_images']
        require(isinstance(images, dict) and set(images) == {'sci', 'prime'} and
                all(isinstance(image, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', image)
                    for image in images.values()), 'Freeze both execution images by immutable identity')
    if 'command_contract' in config:
        contract = config['command_contract']
        require(contract.get('version') == 'native-tool-v1' and
                type(contract.get('corrections_per_task')) is int and contract['corrections_per_task'] == 1 and
                contract.get('rejected_fragment_execution') is False,
                'Aljure command-envelope metadata differs from the implemented one-correction contract')
    require(config.get('provider') in ('anthropic-api', SUBSCRIPTION), 'Unsupported provider; no automatic transport fallback')
    if config['provider'] == SUBSCRIPTION:
        require(config.get('subscription_protocol') == OAUTH_VERSION, 'Explicit pinned subscription protocol required')
        require(config.get('billing_basis') == 'API-rate-equivalent; actual subscription invoice unknown',
                'Subscription caps must distinguish equivalents from billing')
    require(config.get('model') in MODEL_CONTRACTS, 'An explicitly supported fixed model is required; no model fallback')
    documented = MODEL_CONTRACTS[config['model']]
    require(config.get('pinned_settings') == {'thinking': {'type': 'adaptive', 'display': 'summarized'}, 'output_config': {'effort': 'medium'}},
            'This native adapter supports adaptive/summarized medium and omitted sampling parameters only')
    for key in ('context_window', 'max_output_tokens', 'calls_per_arm', 'tokens_per_arm', 'concurrent_requests'):
        require(type(config.get(key)) is int and config[key] > 0, f'Missing positive {key}')
    require(config['max_output_tokens'] <= config['context_window'], 'Output ceiling exceeds context bound')
    require(config['context_window'] == documented['context_window'] and
            config['max_output_tokens'] <= documented['max_output_tokens'], 'Model context/output contract differs')
    require(set(config.get('rates', {})) == set(RATE_KEYS), 'All cache/input/output rates are required')
    require(all(money(v) > 0 for v in config['rates'].values()), 'All rates must be positive')
    require(config['rates'] == documented['rates'], 'Use the documented rates for the exact requested model')
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
             'prime_commit': native.PIN, 'capabilities': capabilities(config),
             'capability_sha256': digest(encoded(capabilities(config))), 'sequence': sequence,
             'allocation': {'per_arm_usd': config['usd_per_arm'], 'total_usd': config['total_usd'],
                            'allocated_usd': float(money(config['usd_per_arm']) * len(sequence)),
                            'total_call_ceiling': config['calls_per_arm'] * len(sequence),
                            'total_token_ceiling': config['tokens_per_arm'] * len(sequence),
                            'borrowing': False},
             'model_calls': 0,
             'approval_scope': ('NEW direct Claude subscription usage; API-rate-equivalent caps; approve this exact plan hash'
                                if config['provider'] == SUBSCRIPTION else
                                'NEW Anthropic API billing, not Claude subscription usage; approve this exact plan hash')}
    value['plan_sha256'] = digest(encoded(value))
    with Path(output).open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    return value


def transport_contract(config):
    """A control on one model/rate/budget setting cannot attest another."""
    return {key: config[key] for key in ('model', 'context_window', 'max_output_tokens', 'pinned_settings',
                                        'rates', 'calls_per_arm', 'tokens_per_arm', 'concurrent_requests', 'usd_per_arm')}


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
    require(value['capabilities'] == capabilities(value['config']) and value['prime_commit'] == native.PIN, 'Capability/source pins changed')
    return value, manifest, tasks


DOCKER_BACKEND = Path.home() / 'Library/Containers/com.docker.docker/Data/backend.sock'


def docker_state(images, run=subprocess.run):
    """Docker Desktop session, pending-restart flag and pinned-image presence.

    The session ID changes whenever Docker Desktop restarts, so comparing it
    before and after an arm detects a restart during the arm. V6 lost its
    native arm to a Docker Desktop `RestartVM` settings change mid-task.
    """
    state = {'session': None, 'restart_pending': None, 'images': {}}
    try:
        out = run(['docker', 'desktop', 'status'], capture_output=True, text=True, timeout=15).stdout
        fields = dict(line.split(None, 1) for line in out.splitlines()[1:] if len(line.split(None, 1)) == 2)
        if fields.get('Status', '').strip() == 'running':
            state['session'] = fields.get('SessionID', '').strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        answer = run(['curl', '-s', '--max-time', '5', '--unix-socket', str(DOCKER_BACKEND),
                      'http://localhost/app/settings/do_changes_need_restart'],
                     capture_output=True, text=True, timeout=10).stdout.strip()
        state['restart_pending'] = {'false': False, 'true': True}.get(answer)
    except (OSError, subprocess.SubprocessError):
        pass
    for image in images:
        try:
            state['images'][image] = run(['docker', 'image', 'inspect', image],
                                         capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            state['images'][image] = False
    return state


def docker_blockers(state):
    blockers = []
    if not state['session']:
        blockers.append('Docker Desktop is not running or its session is unknown')
    if state['restart_pending'] is not False:
        blockers.append('Docker Desktop has a pending or unknown restart')
    blockers += [f'pinned image missing: {image}' for image, present in state['images'].items() if not present]
    return blockers


def arm_status(execution, answered):
    """Status and failure for a finished arm; a dead container has no completion."""
    completion = execution.get('completion') or {}
    if execution.get('failure') == 'wall-time-limit':
        return 'timeout', None
    if completion.get('native_exit_code') == 0 and answered:
        return 'completed', None
    return 'error', (None if execution.get('completion') else 'NativeCompletionMissing')


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
        if 'execution_images' in config:
            require(checks['prime_isolation']['image'] == config['execution_images']['prime'],
                    'Native image differs from frozen plan')
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
        if 'execution_images' in config:
            require(proof['image'] == config['execution_images']['sci'], 'SCI image differs from frozen plan')
        checks['sci_isolation'] = {'image': proof['image'], 'proof_sha256': digest(encoded(proof))}
    except Exception as error:
        blockers.append('SCI isolation: ' + str(error))
    # The new native relay must be exercised with actual root/child/tool events
    # through the same bridge before this command can dispatch live traffic.
    subscription = config['provider'] == SUBSCRIPTION
    proof_path = ROOT / ('var/subscription-relay-proof.json' if subscription else 'var/external-relay-proof.json')
    try:
        proof = json.loads(proof_path.read_text())
        require(proof.get('evidence') == 'FIXTURE' and proof.get('status') == 'PASSED', 'missing completed relay fixture')
        require(proof.get('transport_contract') == transport_contract(config), 'Relay model/settings/rates/budgets differ from plan')
        require(proof.get('runtime_source') == value['runtime_source'], 'relay fixture runtime/config inputs differ')
        require(proof.get('prime_image') == checks.get('prime_isolation', {}).get('image') and
                proof.get('sci_image') == checks.get('sci_isolation', {}).get('image'), 'relay fixture worker image differs')
        require(all(proof.get('checks', {}).get(k) is True for k in
                    ('native_root', 'native_child', 'native_tool', 'native_compaction', 'native_refinement',
                     'native_signed_thinking', 'sci_context', 'shared_budget', 'cleanup',
                     'command_correction', 'rejected_fragment_not_executed')),
                'native/common relay fixture coverage incomplete')
        if subscription:
            require(proof.get('provider') == SUBSCRIPTION and proof.get('subscription_protocol') == OAUTH_VERSION and
                    proof.get('checks', {}).get('oauth_protocol') is True, 'Native subscription protocol control missing')
        checks['relay_fixture'] = {'sha256': digest(encoded(proof))}
    except Exception as error:
        blockers.append('Common transport validation: ' + str(error))
    return {'ready': not blockers, 'model_calls': 0, 'plan_sha256': value['plan_sha256'],
            'checks': checks, 'blockers': blockers,
            'billing_transport': ('Claude subscription; API-rate-equivalent limits; separate plan authorization required'
                                 if subscription else 'Anthropic API; separate authorization required'),
            'subscription_native_prime_ready': subscription and not blockers,
            'actual_provider_response': 'UNVERIFIED; preflight sends no inference and reads no credentials',
            'strict_language_parity': False}


def gateway_config(config, route):
    return {'model': config['model'], 'context-window': config['context_window'],
            'max-output': config['max_output_tokens'], 'pinned-settings': config['pinned_settings'],
            'rates': config['rates'], 'routes': [route],
            'billing-transport': config.get('provider', 'anthropic-api'),
            'limits': {'calls': config['calls_per_arm'], 'tokens': config['tokens_per_arm'],
                       'usd': config['usd_per_arm'], 'wall-ms': 120000,
                       'concurrent-subagents': config['concurrent_requests']}}


def public_input(suite, task):
    text = checked_file(Path(suite) / 'public', task['context_path'], task['context_sha256']).read_text()
    require(len(text.encode()) <= 1500000, 'Public context exceeds declared adapter limit')
    return {'task': {'task_id': task['task_id'], 'question': task['question']}, 'context': text}


def run_arm(harness, data, out, config, gateway, readiness, *, fixture_native_commands=False):
    relay = Relay(gateway, harness, provider=config.get('provider', 'anthropic-api'))
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
        environment = {k: v for k, v in os.environ.items()
                       if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
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
                'max_output': config['max_output_tokens'], 'prompt': prompt, 'context': data['context'], 'rates': config['rates'],
                'fixture_session_commands': ['/compact', '/refine'] if fixture_native_commands else [],
                'auth_mode': config.get('provider', 'anthropic-api')}
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


def run(plan_path, suite, output, *, authorize_api_plan=None, authorize_subscription_plan=None):
    value, manifest, tasks = read_plan(plan_path, suite)
    subscription = value['config']['provider'] == SUBSCRIPTION
    approval = authorize_subscription_plan if subscription else authorize_api_plan
    other = authorize_api_plan if subscription else authorize_subscription_plan
    require(other is None and approval == value['plan_sha256'],
            'Approve this exact frozen transport plan, then pass only its --authorize-subscription-plan or --authorize-api-plan hash')
    ready = preflight(plan_path, suite)
    require(ready['ready'], 'Live run refused: ' + '; '.join(ready['blockers']))
    require(not Path(output).exists(), 'Output exists; prior evidence must remain unchanged')
    config = value['config']
    output = Path(output).resolve()
    output.mkdir(parents=True)
    (output / 'plan.json').write_bytes(encoded(value))
    (output / 'preflight.json').write_bytes(encoded(ready))
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
            images = [ready['checks']['prime_isolation']['image'], ready['checks']['sci_isolation']['image']]
            before = docker_state(images)
            (out / 'docker-before.json').write_bytes(encoded(before))
            if docker_blockers(before):
                # Refused before any model call; a paired pilot with a dead arm is not a comparison.
                failure, stop = 'DockerNotReady', True
            else:
                data = public_input(suite, task)
                (out / 'public-input.json').write_bytes(encoded(data))
                transport = ClaudeSubscriptionTransport if subscription else AnthropicMessagesTransport
                gateway = GatewayClient(out / 'gateway', gateway_config(config, harness),
                                        transport(authorized=True), evidence='LIVE MODEL RUN')
                execution = run_arm(harness, data, out, config, gateway, ready)
                status, failure = arm_status(execution, (out / 'answer.txt').exists())
                after = docker_state(images)
                (out / 'docker-after.json').write_bytes(encoded(after))
                if after['session'] != before['session']:
                    failure, status, stop = 'DockerRestartedDuringArm', 'error', True
        except Exception as error:
            failure = type(error).__name__  # No secret-bearing exception messages.
            stop = True
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception as error:
                    stop = True
                    failure, status = type(error).__name__, 'error'
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
    report['billing'] = ('API-rate-equivalent subscription usage; no API credit fallback; actual subscription invoices unknown'
                         if subscription else 'API usage at configured rates; provider invoices are not measured')
    (output / 'report.json').write_bytes(encoded(report))
    return report
