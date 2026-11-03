"""Versioned external comparison. Planning is offline; API execution is opt-in.

This is a full-harness comparison, not a language-only experiment. A subscription
approval never enables Anthropic API billing. No fixture answers enter this path.
"""
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import time
from decimal import Decimal

from .oolong import account, checked_file, compare, digest, encoded, jsonl, money, read_suite, require, write_jsonl
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


SCI_DEFAULTS = {'surface': 'raw', 'results': 'raw', 'worker_output_bytes': 65536}


TASK_LIMIT_DEFAULTS = {'task_seconds': 120, 'request_bytes': 1048576, 'task_output_bytes': 4194304, 'session_steps': 64}


def task_limits(config):
    """Per-task limits shared by both harnesses. Omitted keys keep the original
    defaults, so earlier plans and their capability hashes mean the same thing."""
    limits = {**TASK_LIMIT_DEFAULTS, **{k: config[k] for k in TASK_LIMIT_DEFAULTS if k in config}}
    require(all(type(v) is int for v in limits.values()), 'Task limits must be integers')
    require(120 <= limits['task_seconds'] <= 3600, 'Task deadline must be 120-3600 s')
    require(1048576 <= limits['request_bytes'] <= 4 * 1048576, 'Request bound must be 1-4 MiB')
    require(4194304 <= limits['task_output_bytes'] <= 64 * 1048576, 'Task output bound must be 4-64 MiB')
    require(64 <= limits['session_steps'] <= 1000, 'Aljure session steps must be 64-1000')
    return limits


ALJURE_CONTRACT_DEFAULTS = {'truncated_turn_retries': 0, 'terminal_text_answer': False,
                            'structured_labels': False, 'uncertainty_audit': False, 'targeted_review': False,
                            'answer_format': None}


VERIFICATION_CAPABILITIES = {
    'structured_labels': 'SCI show-items; prompt asks for one recorded label per item and answers computed from them',
    'uncertainty_audit': 'SCI audit-labels and :unknown labels (coverage, conflicts, unknowns, count ranges; not label correctness)',
    'targeted_review': 'prompt asks to reread and decide open items before done; at most once, a root done with an open audit '
                       'is answered with that audit and the next done is accepted'}


SUPPLY_CAPABILITY = (
    'positive control: after preload, the controller applies the applicable functions (a cascade in library order) '
    'to every record line and binds library-labels (one label or nil per record); the note says so; counts are recorded')
LEDGER_CAPABILITY = (
    '; bookkept: for a count question the controller also binds library-ledger, the record indexes the library marked '
    'positive, negative and unresolved for the asked label (three states; unresolved is never negative), and the note '
    'gives the three counts and asks the model to judge only the unresolved records')
ARTIFACTS_CAPABILITY = (
    'controller discovers the approved entries of pinned library version {sha}; each entry\'s predicate runs '
    'in the root SCI worker on public input only (question, context; never gold); applicable functions are '
    'preloaded into every session worker and a task-message note names them; refusals, preloads and '
    'invocations (by code hash) are recorded; no artifact tools; no model call for checks; Aljure-only (Prime unchanged)')


ACQUISITION_MODES = {
    'optional': 'one optional proposal turn (task tools plus propose_artifact and skip_proposal; declining costs nothing)',
    'structured': ('one structured acquisition turn: told that later tasks share the record format and many labels, the '
                   'model reviews its session code and proposes a function, or declines with a one-sentence reason'),
    'capture': ('one capture turn: the controller reads (never runs) the session code, lists the one-argument text tests the '
                'model defined (verbatim, with inlined session definitions; session data and literal data sets excluded); '
                'the model keeps one (naming the label of a true/false test and an applicability predicate) or declines '
                'with a reason; no turn when nothing is eligible'),
    'capture-selected': ('one capture turn as in capture, but the model names only the labels the function decides and the '
                         'controller writes the applicability contract from them (the context header must name those labels; '
                         'adapter label-header-v1, recorded as controller-generated), then validates as usual')}


def acquisition_capability(acquisition):
    mode = acquisition.get('mode', 'optional')
    text = ACQUISITION_CAPABILITY.format(arm=acquisition['arm'])
    return text if mode == 'optional' else text.replace(ACQUISITION_MODES['optional'], ACQUISITION_MODES[mode])


ACQUISITION_CAPABILITY = (
    'arm {arm}: after the root answer is recorded, one optional proposal turn (task tools plus propose_artifact and '
    'skip_proposal; declining costs nothing); its provider call is acquisition cost, apart from task inference; '
    'promotion happens outside the task, after its answer is recorded; Aljure-only (Prime unchanged)')


PROGRAM_TOOLS = {'context_query': 'read', 'context_metadata': 'read',
                 'service_list': 'read', 'service_get': 'read', 'service_update': 'effect'}
PROGRAM_CEILINGS = {'max_ops_per_program': 1024, 'max_ops_per_task': 20000, 'max_program_ms': 600000, 'max_programs': 256}
PROGRAM_DEFAULTS = {'max_ops_per_program': 256, 'max_ops_per_task': 2000, 'max_program_ms': 60000, 'max_programs': 64}


def programs_switch(value):
    """aljure_contract.programs (research/PROGRAMMATIC_EXECUTION.md): absent or null is off. On, it is
    the grant: the typed tools a program may ask the controller for (deny by default; an effect tool
    needs approval "preapproved"), the budgets, and which model tools exist (program_run and/or the
    same tools one operation per turn). The controller (src/repl_lab/programs.clj) validates the
    same grant again and enforces it; a plan cannot authorize more than that namespace enforces."""
    require(isinstance(value, dict) and set(value) <= {'tools', 'program_tool', 'direct_tools', *PROGRAM_CEILINGS},
            'programs takes tools, program_tool, direct_tools and the max_* budgets')
    tools = value.get('tools')
    require(isinstance(tools, list) and tools and all(isinstance(t, dict) and set(t) - {'max_calls', 'approval'} == {'name'}
                                                     and t['name'] in PROGRAM_TOOLS for t in tools)
            and len({t['name'] for t in tools}) == len(tools),
            'programs.tools must list distinct known tools: ' + ', '.join(sorted(PROGRAM_TOOLS)))
    for tool in tools:
        calls = tool.get('max_calls', 1000)
        require(type(calls) is int and 1 <= calls <= 20000, 'max_calls must be 1-20000')
        require(tool.get('approval') in (None, 'preapproved'), 'approval must be absent or "preapproved"')
        require(PROGRAM_TOOLS[tool['name']] == 'read' or tool.get('approval') == 'preapproved',
                f"effect tool needs approval \"preapproved\": {tool['name']}")
    for key, ceiling in PROGRAM_CEILINGS.items():
        require(type(value.get(key, 1)) is int and 1 <= value.get(key, 1) <= ceiling, f'{key} must be 1-{ceiling}')
    program_tool, direct_tools = value.get('program_tool', True), value.get('direct_tools', False)
    require(type(program_tool) is bool and type(direct_tools) is bool and (program_tool or direct_tools),
            'programs needs program_tool and/or direct_tools true')
    return value


def programs_capability(programs):
    budgets = {**PROGRAM_DEFAULTS, **{k: programs[k] for k in PROGRAM_CEILINGS if k in programs}}
    tools = '; '.join(f"{t['name']} ({PROGRAM_TOOLS[t['name']]}, at most {t.get('max_calls', 1000)} calls"
                      + (', preapproved' if t.get('approval') else '') + ')' for t in programs['tools'])
    surfaces = [s for s, on in (('program_run', programs.get('program_tool', True)),
                                ('direct one-operation tools', programs.get('direct_tools', False))) if on]
    return ('programmatic tool bridge: SCI code calls (tool name input); the controller authorizes each operation '
            f'against this grant, denies every other tool, records request, decision, result and error; tools: {tools}; '
            f"budgets: {budgets['max_ops_per_program']} operations per program, {budgets['max_ops_per_task']} per task, "
            f"{budgets['max_program_ms']} ms per program, {budgets['max_programs']} programs per task; effects need an "
            'idempotency key (a repeated key is not re-executed; an uncertain outcome is never retried); sequential; '
            f"model surface: {' and '.join(surfaces)}; Aljure-only (no Prime counterpart)")


def artifact_library(value):
    """aljure_contract.artifacts: absent or null is off. On, it names a library root (relative
    to repl-lab) and the sha256 of one immutable version file, <library>/libraries/<sha256>.edn.
    Optional supply "applied" (Pilot 1 positive control): the controller also applies the
    applicable functions to every record and binds the labels; "bookkept" (Pilot 1b arm R) adds a
    three-state ledger for the asked label; absent, nothing is applied."""
    require(isinstance(value, dict) and set(value) - {'supply'} == {'library', 'library_sha256'} and
            value.get('supply', 'applied') in ('applied', 'bookkept') and
            isinstance(value['library'], str) and
            re.fullmatch(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*', value['library']) is not None and
            '..' not in value['library'].split('/') and isinstance(value['library_sha256'], str) and
            re.fullmatch(r'[0-9a-f]{64}', value['library_sha256']) is not None,
            'artifacts must be null or {library: relative path, library_sha256: 64 lowercase hex}')
    return value


def acquisition_switch(value, artifacts):
    """aljure_contract.acquisition (thesis pilot, arms C and E): absent or null is off. On, the
    root gets one optional proposal turn after its recorded answer; it needs a pinned library."""
    require(isinstance(value, dict) and set(value) - {'mode', 'experimental_capture'} == {'arm'} and value['arm'] in ('C', 'E') and
            value.get('mode', 'optional') in ACQUISITION_MODES and
            (value['arm'] == 'E' or value.get('mode', 'optional') in ('optional', 'structured')),
            'acquisition must be arm C or E; C supports optional/structured, E also supports capture modes')
    # Capture reads model code with a whole-form local-name approximation and renames reader gensyms;
    # until those are proven semantics-preserving it is experimental and must be switched on explicitly.
    require(value.get('mode', 'optional') not in ('capture', 'capture-selected') or value.get('experimental_capture') is True,
            'capture modes are experimental: set acquisition.experimental_capture to true explicitly')
    require(artifacts is not None, 'acquisition needs aljure_contract.artifacts (the pinned library)')
    return value


def aljure_contract(config):
    """Execution-contract switches for Aljure, each separately ablatable.
    Absent: the original contract (no transport retry; text is never an answer).
    'artifacts' and 'acquisition' appear in the result only when on, so earlier contracts are unchanged."""
    value = config.get('aljure_contract', {})
    require(isinstance(value, dict) and set(value) <= set(ALJURE_CONTRACT_DEFAULTS) | {'artifacts', 'acquisition', 'programs', 'skill_interface'},
            'Unknown Aljure contract setting')
    contract = {**ALJURE_CONTRACT_DEFAULTS, **value}
    artifacts = contract.pop('artifacts', None)
    acquisition = contract.pop('acquisition', None)
    programs = contract.pop('programs', None)
    interface = contract.pop('skill_interface', None)
    if artifacts is not None:
        contract['artifacts'] = artifact_library(artifacts)
    if interface is not None:
        require(interface == 'inspect-v1' and artifacts is not None,
                'skill_interface must be inspect-v1 and needs the existing pinned artifact library')
        contract['skill_interface'] = interface
    if acquisition is not None:
        contract['acquisition'] = acquisition_switch(acquisition, artifacts)
    if programs is not None:
        # Prime has no counterpart of the service tools yet: a programs plan is Aljure-only.
        require(aljure_only(config) is not None, 'programs needs aljure_only (no Prime counterpart of the bridge tools)')
        contract['programs'] = programs_switch(programs)
    require(type(contract['truncated_turn_retries']) is int and 0 <= contract['truncated_turn_retries'] <= 2,
            'Truncated-turn retries must be 0-2')
    for key in ('terminal_text_answer', 'structured_labels', 'uncertainty_audit', 'targeted_review'):
        require(type(contract[key]) is bool, f'{key} must be true or false')
    # Nested levels: an audit needs recorded labels, and review acts on the audit.
    require(contract['structured_labels'] or not contract['uncertainty_audit'], 'uncertainty_audit needs structured_labels')
    require(contract['uncertainty_audit'] or not contract['targeted_review'], 'targeted_review needs uncertainty_audit')
    # A declared, gold-free answer contract: at most max_lines lines and max_chars characters.
    form = contract['answer_format']
    require(form is None or (isinstance(form, dict) and set(form) == {'max_lines', 'max_chars'}
                             and type(form['max_lines']) is int and 1 <= form['max_lines'] <= 20
                             and type(form['max_chars']) is int and 16 <= form['max_chars'] <= 4096),
            'answer_format must be null or {max_lines: 1-20, max_chars: 16-4096}')
    return contract


def aljure_sci(config):
    """Explicit SCI settings for the Aljure arm; absent means the 64 KB raw control."""
    settings = {**SCI_DEFAULTS, **config.get('aljure_sci', {})}
    require(set(settings) == set(SCI_DEFAULTS) and settings['surface'] in ('raw', 'assisted') and
            settings['results'] in ('raw', 'bounded') and settings['worker_output_bytes'] in (65536, 1048576) and
            (settings['results'] == 'raw' or settings['surface'] == 'assisted'),
            'Unsupported Aljure SCI settings')
    return settings


def learning_library_sha256(config, harness='aljure'):
    """The retained library an arm saw: the pinned version for Aljure with the artifacts
    switch on, otherwise sha256 of [] (the empty library every earlier plan recorded)."""
    artifacts = aljure_contract(config).get('artifacts')
    return artifacts['library_sha256'] if artifacts and harness == 'aljure' else digest(encoded([]))


def artifact_library_check(artifacts, sci_image, bound, root=ROOT):
    """Read-only: the pinned version's bytes match its hash, and a passing artifact-path proof
    (python3 scripts/clj.py -m repl-lab.sci-contract artifacts) covers this worker image,
    output bound and the current controller sources."""
    root = Path(root)
    version = root / artifacts['library'] / 'libraries' / (artifacts['library_sha256'] + '.edn')
    require(version.is_file() and not version.is_symlink(), 'pinned library version is missing')
    require(digest(version.read_bytes()) == artifacts['library_sha256'], 'library version bytes differ from the pin')
    proof_path = root / ('var/artifact-path-proof.json' if bound == 65536 else f'var/artifact-path-proof-{bound}.json')
    require(proof_path.is_file(), 'artifact-path proof missing; run python3 scripts/clj.py -m repl-lab.sci-contract artifacts')
    proof = json.loads(proof_path.read_text())
    sources = {'executable-sha256': 'src/repl_lab/executable.clj', 'external-task-sha256': 'src/repl_lab/external_task.clj',
               'skills-sha256': 'src/repl_lab/skills.clj', 'runtime-sha256': 'src/repl_lab/runtime.clj',
               'skill-interface-sha256': 'src/repl_lab/skill_interface.clj'}
    require(proof.get('status') == 'TESTED' and proof.get('image') == sci_image and proof.get('output-bytes') == bound and
            all(proof.get(key) == digest((root / path).read_bytes()) for key, path in sources.items()),
            'artifact-path proof is stale; run python3 scripts/clj.py -m repl-lab.sci-contract artifacts')
    return {'library_sha256': artifacts['library_sha256'], 'proof_sha256': digest(encoded(proof))}


def sci_proof_path(config):
    bound = aljure_sci(config)['worker_output_bytes']
    return ROOT / ('var/isolation-proof.json' if bound == 65536 else f'var/isolation-proof-{bound}.json')


def sci_contract_proof_path(config):
    bound = aljure_sci(config)['worker_output_bytes']
    return ROOT / ('var/sci-contract-proof.json' if bound == 65536 else f'var/sci-contract-proof-{bound}.json')


def capabilities(config):
    base = _capabilities(config)
    if 'aljure_contract' in config:
        contract = aljure_contract(config)
        base = {**base, 'aljure': {**base['aljure'], 'execution_contract': {
            'truncated_turn_retries': contract['truncated_turn_retries'],
            'terminal_text_answer': ('root session, only in reply to the FINAL ANSWER correction, exactly one line'
                                     if contract['terminal_text_answer'] else False),
            # Declared only when on, so earlier contracts keep identical capabilities.
            **{key: text for key, text in VERIFICATION_CAPABILITIES.items() if contract[key]},
            **({'answer_format': f"root done: at most {contract['answer_format']['max_lines']} line(s) and "
                                 f"{contract['answer_format']['max_chars']} characters; one fixed notice, never rewritten; "
                                 "Aljure-only (Prime unchanged)"} if contract['answer_format'] else {}),
            **({'artifacts': ARTIFACTS_CAPABILITY.format(sha=contract['artifacts']['library_sha256']).replace(
                    'no artifact tools', 'bounded inspection and admitted isolated calls' if 'skill_interface' in contract else 'no artifact tools')}
               if 'artifacts' in contract else {}),
            **({'artifacts_supply': SUPPLY_CAPABILITY + (LEDGER_CAPABILITY if contract['artifacts']['supply'] == 'bookkept' else '')}
               if contract.get('artifacts', {}).get('supply') else {}),
            **({'acquisition': acquisition_capability(contract['acquisition'])}
               if 'acquisition' in contract else {}),
            **({'skill_interface': 'inspect-v1: bounded read-only artifact_inspect and authorized isolated artifact_call; '
                                  'existing verified library and provenance; optional use, no automatic application'}
               if 'skill_interface' in contract else {}),
            **({'programs': programs_capability(contract['programs'])}
               if 'programs' in contract else {})}}}
        if 'artifacts' in contract:
            base['aljure']['skills'] = ('controller-preloaded approved functions from the pinned library version; '
                                        'task-local code otherwise; no benchmark development evaluator')
    if not any(k in config for k in TASK_LIMIT_DEFAULTS):
        return base
    limits = task_limits(config)
    return {**base, 'shared': {**base['shared'], 'task_seconds': limits['task_seconds'],
                               'request_bytes': limits['request_bytes']},
            'aljure': {**base['aljure'], 'session_steps': limits['session_steps']},
            'prime': {**base['prime'], 'task_output_bytes': limits['task_output_bytes']}}


def _capabilities(config):
    if 'aljure_sci' in config:
        sci = aljure_sci(config)
        aljure = {**CAPABILITIES['aljure'], 'sci': sci,
                  'expression_output_bytes': sci['worker_output_bytes'],
                  'history': 'append-only full history in tool mode; ledger records appended messages; no model-based compaction'}
        base = {**CAPABILITIES, 'aljure': aljure}
    else:
        base = CAPABILITIES
    if config['provider'] != SUBSCRIPTION:
        return base
    from .subscription_protocol import IDENTITY, PUBLIC_HEADERS
    return {**base, 'subscription_protocol': {
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
    aljure_sci(config)
    aljure_contract(config)
    task_limits(config)
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


def prime_reference(config, manifest):
    """Aljure-only plans compare against recorded, unchanged Prime arms, cited by hash.
    Every cited run must be on this suite, with the pinned Prime and the same model;
    its plan, results and report must still hash to the recorded values."""
    ref = config.get('prime_reference')
    if ref is None:
        return None
    require(isinstance(ref, dict) and set(ref) == {'runs', 'disclosure'} and isinstance(ref['runs'], list) and ref['runs']
            and isinstance(ref['disclosure'], str) and 'non-contemporaneous' in ref['disclosure'],
            'prime_reference needs runs and a non-contemporaneous disclosure')
    verified = []
    for cited in ref['runs']:
        require(set(cited) == {'plan_sha256', 'run_dir', 'results_sha256', 'report_sha256'}, 'Malformed Prime reference')
        run = Path(cited['run_dir'])
        require(run.is_absolute() and run.is_dir(), 'Prime reference run is missing')
        recorded = json.loads((run / 'plan.json').read_text())
        require(recorded['plan_sha256'] == cited['plan_sha256'] and recorded['suite_sha256'] == manifest['suite_sha256'],
                'Prime reference plan or suite differs')
        require(digest((run / 'results.jsonl').read_bytes()) == cited['results_sha256'] and
                digest((run / 'report.json').read_bytes()) == cited['report_sha256'], 'Prime reference evidence changed')
        rows = [json.loads(line) for line in (run / 'results.jsonl').read_text().splitlines() if line.strip()]
        prime = {r['task_id']: r for r in rows if r['harness'] == 'prime'}
        require(set(prime) == set(manifest['task_ids']) and all(r['harness_revision'] == native.PIN for r in prime.values())
                and all(r['model_config']['model'] == config['model'] for r in prime.values()),
                'Prime reference must cover every task with the pinned Prime and the same model')
        verified.append({**cited, 'prime_arms': len(prime)})
    return {'runs': verified, 'disclosure': ref['disclosure']}


def aljure_only(config):
    """Aljure-only plans with no Prime counterpart (Pilot 1 of research/UNBLOCK_ACQUISITION.md):
    an explicit disclosure that no Prime comparison is made. Exclusive with prime_reference."""
    value = config.get('aljure_only')
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {'disclosure'} and isinstance(value['disclosure'], str) and
            'no Prime comparison' in value['disclosure'] and 'prime_reference' not in config,
            'aljure_only needs {disclosure: "... no Prime comparison ..."} and excludes prime_reference')
    return value


def harnesses(config):
    return ('aljure',) if 'prime_reference' in config or aljure_only(config) else ('aljure', 'prime')


def expected_sequence(manifest, config):
    if harnesses(config) == ('aljure',):
        return [{'task_id': task, 'harness': 'aljure'} for task in manifest['task_ids']]
    return [{'task_id': task, 'harness': harness} for i, task in enumerate(manifest['task_ids'])
            for harness in (('aljure', 'prime') if i % 2 == 0 else ('prime', 'aljure'))]


def plan(suite, config_path, output):
    manifest, tasks, _ = read_suite(suite)
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    if manifest['suite'] == 'service-sim':
        # The programmatic-execution development benchmark (research/PROGRAMMATIC_EXECUTION.md): synthetic,
        # Aljure-only, and only under a programs grant. It is not an official input and never a Prime comparison.
        require(manifest['input_provenance'] == 'synthetic-service-fixture' and aljure_only(config) is not None
                and 'programs' in aljure_contract(config), 'A service-sim plan needs aljure_only and aljure_contract.programs')
    else:
        require(manifest['input_provenance'] == 'verified-pinned-upstream', 'Live planning requires authenticated official inputs')
    # Window suites are fixed by their pinned profile (validate_provenance); others start at one, then ten.
    require(len(tasks) in (1, 10) or manifest['selection'].get('method') in ('seeded-sample-per-window', 'whole-window-label-count',
                                                                            'reuse-pilot-v1', 'reuse-pilot-labels-v1', 'service-sim-v1'),
            'Start with one case, then ten cases')
    sequence = expected_sequence(manifest, config)
    require(money(config['usd_per_arm']) * len(sequence) <= money(config['total_usd']),
            'Sum of disjoint task allowances exceeds the global ceiling')
    reference = prime_reference(config, manifest)
    value = {'version': VERSION, 'evidence': 'IMPLEMENTED / UNVERIFIED', 'authorized': False,
             'suite_sha256': manifest['suite_sha256'], 'config': config, 'source': source_snapshot(),
             'runtime_source': runtime_snapshot(),
             'prime_commit': native.PIN, 'capabilities': capabilities(config),
             'capability_sha256': digest(encoded(capabilities(config))), 'sequence': sequence,
             **({'prime_reference': reference} if reference else {}),
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
    expected = expected_sequence(manifest, value['config'])
    require(value['sequence'] == expected, 'Plan omitted, repeated or reordered a case')
    # A cited Prime reference must still verify, byte for byte, before any arm runs.
    require(value.get('prime_reference') == prime_reference(value['config'], manifest), 'Prime reference changed after plan freeze')
    require(money(value['config']['usd_per_arm']) * len(expected) <= money(value['config']['total_usd']), 'Global allocation exceeded')
    require(value['source']['sha256'] == source_snapshot()['sha256'], 'Source changed after plan freeze')
    require(value['runtime_source'] == runtime_snapshot(), 'Runtime inputs changed after plan freeze')
    require(value['capabilities'] == capabilities(value['config']) and value['prime_commit'] == native.PIN, 'Capability/source pins changed')
    return value, manifest, tasks


def worker_isolation_refused(out):
    """Whether any SCI worker in this arm was refused by its isolation preflight."""
    return any(not json.loads(path.read_text()).get('ready', True)
               for path in Path(out).glob('worker-audit/preflight/*.json'))


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
    return readiness(value, value['config'])


def readiness(value, config, *, native_prime=True, acquisition=False):
    """Read-only checks of a frozen plan. Paired plans use the defaults; an Aljure-only
    trajectory plan skips native Prime and, for arms C and E, requires the artifact-path and
    acquisition proofs of the current sources."""
    blockers, checks = [], {}
    contract = config.get('verified_model_contract', {})
    if not (contract.get('verified') is True and contract.get('source') and
            contract.get('model') == config['model'] and contract.get('context_window') == config['context_window'] and
            contract.get('rates') == config['rates']):
        blockers.append('Exact provider model/context bound and all cache rates require primary-source verification')
    # These read-only checks never execute agent code or contact a model.
    if native_prime:
        from .prime.isolation import require_tested
        try:
            checks['prime_isolation'] = require_tested()
            if 'execution_images' in config:
                require(checks['prime_isolation']['image'] == config['execution_images']['prime'],
                        'Native image differs from frozen plan')
        except Exception as error:
            blockers.append('Native Prime isolation: ' + str(error))
    try:
        bound = str(aljure_sci(config)['worker_output_bytes'])
        result = subprocess.run(['python3', 'scripts/clj.py', '-e',
                                 "(require '[repl-lab.isolation :as i]) (i/require-tested!) (println :tested) (shutdown-agents)"],
                                cwd=ROOT, capture_output=True, timeout=25,
                                env={**os.environ, 'REPL_LAB_WORKER_OUTPUT_BYTES': bound})
        require(result.returncode == 0, 'strict SCI isolation proof unavailable')
        proof = json.loads(sci_proof_path(config).read_text())
        require(str(proof.get('output-bytes')) == bound, 'SCI proof is for another output bound')
        require(proof.get('gate_version', proof.get('gate-version', 0)) >= 2,
                'same-worker readiness gate must be merged and validated')
        if 'execution_images' in config:
            require(proof['image'] == config['execution_images']['sci'], 'SCI image differs from frozen plan')
        checks['sci_isolation'] = {'image': proof['image'], 'proof_sha256': digest(encoded(proof))}
        if aljure_sci(config)['surface'] == 'assisted':
            # Everything the assisted surface advertises must be verified against this worker.
            contract = json.loads(sci_contract_proof_path(config).read_text())
            current = {'contract-sha256': 'resources/sci-contract.json', 'prelude-sha256': 'resources/sci-prelude.edn',
                       'model-protocol-sha256': 'src/repl_lab/model_protocol.clj', 'verify-sha256': 'resources/sci-verify.edn'}
            require(contract.get('status') == 'TESTED' and contract.get('image') == proof['image'] and
                    str(contract.get('output-bytes')) == bound and
                    all(contract.get(key) == digest((ROOT / path).read_bytes()) for key, path in current.items()),
                    'SCI contract proof is missing or stale; run python3 scripts/clj.py -m repl-lab.sci-contract')
            checks['sci_contract'] = {'proof_sha256': digest(encoded(contract))}
    except Exception as error:
        blockers.append('SCI isolation: ' + str(error))
    artifacts = aljure_contract(config).get('artifacts')
    if artifacts:
        try:
            checks['artifact_library'] = artifact_library_check(artifacts, checks.get('sci_isolation', {}).get('image'),
                                                                aljure_sci(config)['worker_output_bytes'])
        except Exception as error:
            blockers.append('Artifact library: ' + str(error))
    if artifacts and aljure_only(config):
        # Pilot 1: the scripted reuse fixture (python3 -m benchmark reuse-fixture) for this runtime, image and library.
        try:
            proof = json.loads((ROOT / 'var/reuse-relay-proof.json').read_text())
            require(proof.get('evidence') == 'FIXTURE' and proof.get('status') == 'PASSED' and
                    proof.get('checks') and all(proof['checks'].values()), 'missing passed reuse fixture')
            require(proof.get('runtime_source') == value['runtime_source'] and
                    proof.get('library', {}).get('library_sha256') == artifacts['library_sha256'] and
                    proof.get('sci_image') == checks.get('sci_isolation', {}).get('image') and
                    proof.get('transport_contract') == transport_contract(config),
                    'reuse fixture is for other runtime inputs, library, worker image or transport')
            checks['reuse_fixture'] = {'sha256': digest(encoded(proof))}
        except Exception as error:
            blockers.append('Reuse fixture: ' + str(error))
    if acquisition:
        try:
            checks['acquisition'] = acquisition_proof_check(checks.get('sci_isolation', {}).get('image'),
                                                            aljure_sci(config)['worker_output_bytes'])
        except Exception as error:
            blockers.append('Acquisition: ' + str(error))
    # The new native relay must be exercised with actual root/child/tool events
    # through the same bridge before this command can dispatch live traffic.
    subscription = config['provider'] == SUBSCRIPTION
    proof_path = ROOT / ('var/subscription-relay-proof.json' if subscription else 'var/external-relay-proof.json')
    try:
        proof = json.loads(proof_path.read_text())
        require(proof.get('evidence') == 'FIXTURE' and proof.get('status') == 'PASSED', 'missing completed relay fixture')
        require(proof.get('transport_contract') == transport_contract(config), 'Relay model/settings/rates/budgets differ from plan')
        require(proof.get('runtime_source') == value['runtime_source'], 'relay fixture runtime/config inputs differ')
        require((not native_prime or proof.get('prime_image') == checks.get('prime_isolation', {}).get('image')) and
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
                       'usd': config['usd_per_arm'], 'wall-ms': task_limits(config)['task_seconds'] * 1000,
                       'concurrent-subagents': config['concurrent_requests']},
            **({'request-bytes': task_limits(config)['request_bytes']} if 'request_bytes' in config else {})}


def public_input(suite, task):
    text = checked_file(Path(suite) / 'public', task['context_path'], task['context_sha256']).read_text()
    require(len(text.encode()) <= 1500000, 'Public context exceeds declared adapter limit')
    data = {'task': {'task_id': task['task_id'], 'question': task['question']}, 'context': text}
    if 'service_fixture_path' in task:
        # A service task (research/PROGRAMMATIC_EXECUTION.md): the pinned fixture seeds the task's
        # synthetic service. Its expected final state is controller-side gold and never travels.
        fixture = checked_file(Path(suite) / 'public', task['service_fixture_path'], task['service_fixture_sha256'])
        data['service_fixture'] = json.loads(fixture.read_text())
    return data


def run_arm(harness, data, out, config, gateway, readiness, *, fixture_native_commands=False):
    relay = Relay(gateway, harness, provider=config.get('provider', 'anthropic-api'))
    def preserve(result):
        (out / 'stdout.jsonl').write_bytes(result['stdout'])
        (out / 'stderr.txt').write_bytes(result['stderr'])
        (out / 'execution.json').write_bytes(encoded({k: v for k, v in result.items() if k not in ('stdout', 'stderr')}))
    if harness == 'aljure':
        limits = {'recursion-depth': 8, 'history-records': 24, 'message-bytes': 32768, 'context-bytes': 65536,
                  'messages': 100, 'candidates': 0, 'evaluation-episodes': 0, 'event-budget': 10000,
                  **({'session-steps': task_limits(config)['session_steps']} if 'session_steps' in config else {}),
                  **gateway_config(config, harness)['limits']}
        sci = aljure_sci(config)
        contract = aljure_contract(config)
        body = {**data, 'config': {'limits': limits, 'sci': {'surface': sci['surface'], 'results': sci['results']},
                                   **({'contract': {k.replace('_', '-'): v for k, v in contract.items()}}
                                      if 'aljure_contract' in config else {})},
                'gateway-config': gateway_config(config, harness), 'model-config': {'model': config['model']}}
        environment = {k: v for k, v in os.environ.items()
                       if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
        environment['REPL_LAB_WORKER_AUDIT_DIR'] = str(out / 'worker-audit')
        environment['REPL_LAB_WORKER_OUTPUT_BYTES'] = str(sci['worker_output_bytes'])
        if 'task_seconds' in config:
            # Lets SCI sessions live as long as the plan's task deadline; the default stays 120 s.
            environment['REPL_LAB_SESSION_SECONDS'] = str(task_limits(config)['task_seconds'])
        result = native.bounded_process(['python3', 'scripts/clj.py', '-m', 'repl-lab.external-task', str(out / 'agent')],
                                        encoded(body) + b'\n', seconds=task_limits(config)['task_seconds'],
                                        max_output=task_limits(config)['task_output_bytes'], max_input=2 * 1024**2,
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
                'auth_mode': config.get('provider', 'anthropic-api'),
                **({'task_seconds': task_limits(config)['task_seconds'], 'request_bytes': task_limits(config)['request_bytes']}
                   if any(k in config for k in ('task_seconds', 'request_bytes')) else {})}
        source = (ROOT / 'benchmark/prime/relay_bootstrap.py').read_text()
        with native.container(readiness['checks']['prime_isolation']['image'], ['-c', source],
                              entrypoint='/opt/venv/bin/python') as (name, _):
            result = native.execute(name, encoded(body) + b'\n', max_input=2 * 1024**2,
                                    seconds=task_limits(config)['task_seconds'],
                                    max_output=task_limits(config)['task_output_bytes'],
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
        # A worker isolation preflight that failed closed is a gate failure: stop the plan.
        if worker_isolation_refused(out):
            stop = True
            failure, status = 'IsolationPreflightFailed', 'error'
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
               'learning_library_sha256': learning_library_sha256(config, harness), 'failure': failure}
        for label, path in [('trace', trace), ('usage', usage)] + ([('answer', out / 'answer.txt')] if status == 'completed' else []):
            row[label + '_path'] = str(path.relative_to(output))
            row[label + '_sha256'] = digest(path.read_bytes())
        results.append(row)
        write_jsonl(output / 'results.jsonl', results)
    report = compare(suite, output / 'results.jsonl', harnesses=harnesses(config))
    report['limitations'] = CAPABILITIES['known_differences']
    report['billing'] = ('API-rate-equivalent subscription usage; no API credit fallback; actual subscription invoices unknown'
                         if subscription else 'API usage at configured rates; provider invoices are not measured')
    (output / 'report.json').write_bytes(encoded(report))
    return report


# ---------------------------------------------------------------------------------------
# Thesis pilot: sequential trajectory mode (research/THESIS_PILOT_PROTOCOL.md). Used only by
# plans made with plan_trajectory; paired plans, their checks and their hashes are unchanged.

TRAJECTORY_VERSION = 'thesis-trajectory-v1'
# The empty library version exactly as skills/write-library! writes it.
EMPTY_LIBRARY = b'{:entries [], :parent nil, :schema :aljure-library-v1}\n'
EMPTY_LIBRARY_SHA256 = digest(EMPTY_LIBRARY)
ARM_STATE = {
    'A': 'stateless: no library and no proposal turn',
    'C': ('exact reuse only: an item-text memo (sha256 of trimmed record text -> label) and functions keyed by the exact '
          'task question; promoted without validation; no generalization'),
    'E': ('validated artifacts: proposals promoted only by the preregistered development-panel rule; structural patch and '
          'composition by exact hash; applicability predicates refuse other inputs')}
ARM_STATE.update({
    'CS': 'exact cache as arm C; structured acquisition turn with a reasoned decline',
    'ES': 'validated artifacts as arm E; structured acquisition turn (research/UNBLOCK_ACQUISITION.md mechanism B)',
    'EX': 'validated artifacts as arm E; controller-assisted capture turn (research/UNBLOCK_ACQUISITION.md mechanism C)',
    'EXS': 'validated artifacts as arm E; capture with controller-selected applicability (mechanism D)'})
# Pilot 2 (research/UNBLOCK_ACQUISITION.md): arm id -> arm E's acquisition mode.
E_MODES = {'ES': 'structured', 'EX': 'capture', 'EXS': 'capture-selected'}
TRAJECTORY_ARMS = (['A', 'C', 'E'], ['A', 'E', 'ES', 'EX'], ['A', 'E', 'ES', 'EX', 'EXS'],
                   ['ES'], ['A', 'CS', 'ES'])


def base_arm(arm):
    if arm == 'CS':
        return 'C'
    return 'E' if arm in E_MODES else arm


def arm_acquisition(arm):
    mode = 'structured' if arm == 'CS' else E_MODES.get(arm)
    return {'arm': base_arm(arm), **({'mode': mode} if mode else {}),
            **({'experimental_capture': True} if mode in ('capture', 'capture-selected') else {})}


TRAJECTORY_KEYS = {'version', 'arms', 'ordering_seeds', 'f2_positions', 'cold_restart_after', 'spend_cap_usd',
                   'spend_check_margin_usd', 'promotion_rule', 'validation_seconds'}
RULE_KEYS = {'schema', 'min_precision', 'min_coverage', 'min_panel_gain', 'statement'}
PARENT = re.compile(rb':parent (nil|"([0-9a-f]{64})"), :schema :aljure-library-v1\}\n\Z')


def acquisition_proof_check(sci_image, bound, root=ROOT):
    """Read-only: current artifact-path and acquisition proofs (sci-contract artifacts and
    acquisition, Docker) cover this worker image, output bound and the current sources."""
    root = Path(root)
    found = {}
    for name, sources in (('artifact-path', ('executable', 'external-task', 'skills', 'runtime')),
                          ('acquisition', ('acquisition', 'executable', 'external-task', 'skills', 'runtime'))):
        path = root / (f'var/{name}-proof.json' if bound == 65536 else f'var/{name}-proof-{bound}.json')
        require(path.is_file(), f'{name} proof missing; run python3 scripts/clj.py -m repl-lab.sci-contract '
                                f'{"artifacts" if name == "artifact-path" else "acquisition"}')
        proof = json.loads(path.read_text())
        files = {key + '-sha256': f'src/repl_lab/{key.replace("-", "_")}.clj' for key in sources}
        require(proof.get('status') == 'TESTED' and proof.get('image') == sci_image and proof.get('output-bytes') == bound and
                all(proof.get(key) == digest((root / file).read_bytes()) for key, file in files.items()),
                f'{name} proof is stale for the current sources, image or bound')
        found[name] = digest(encoded(proof))
    return found


def trajectory_spec(config):
    spec = config.get('trajectory')
    require(isinstance(spec, dict) and set(spec) == TRAJECTORY_KEYS and
            spec['version'] in (TRAJECTORY_VERSION, 'learning-development-v1'),
            'trajectory needs exactly: ' + ', '.join(sorted(TRAJECTORY_KEYS)))
    require(spec['arms'] in TRAJECTORY_ARMS, 'Unsupported preregistered trajectory arms')
    seeds = spec['ordering_seeds']
    if spec['version'] == 'learning-development-v1':
        require(spec['arms'] == ['ES'] and seeds == [101] and spec['f2_positions'] == [6]
                and spec['cold_restart_after'] == 2, 'Minimal development: ES-s101, six tasks, restart after task 2')
    else:
        require(isinstance(seeds, list) and len(seeds) == 3 and all(type(s) is int for s in seeds) and len(set(seeds)) == 3,
                'Three distinct integer ordering seeds')
        require(spec['f2_positions'] == [8, 11, 14, 17] and spec['cold_restart_after'] == 9,
                'F2 at positions 8, 11, 14 and 17; cold restart after task 9 (preregistered)')
    rule = spec['promotion_rule']
    v2 = isinstance(rule, dict) and rule.get('schema') == 'aljure-promotion-rule-v2'
    require(isinstance(rule, dict) and (set(rule) == RULE_KEYS and rule['schema'] == 'aljure-promotion-rule-v1' or
                                        v2 and set(rule) == RULE_KEYS | {'label_abstention'} and
                                        type(rule['label_abstention']) is bool) and
            all(isinstance(rule[k], list) and len(rule[k]) == 2 and all(type(x) is int and x > 0 for x in rule[k]) and
                rule[k][0] <= rule[k][1] for k in ('min_precision', 'min_coverage')) and
            type(rule['min_panel_gain']) is int and rule['min_panel_gain'] >= 0 and isinstance(rule['statement'], str),
            'Invalid promotion rule')
    require(money(spec['spend_cap_usd']) > 0 and money(spec['spend_cap_usd']) <= money(config['total_usd']) and
            money(spec['spend_check_margin_usd']) >= 0, 'Spend cap must be positive and within total_usd')
    require(type(spec['validation_seconds']) is int and 30 <= spec['validation_seconds'] <= 1800, 'Validation seconds 30-1800')
    require('prime_reference' not in config and not ({'artifacts', 'acquisition', 'programs'} & set(config.get('aljure_contract', {}))),
            'The trajectory runner owns artifacts and acquisition; no programs; no Prime arm')
    return spec


def trajectory_order(manifest, seed, f2_positions):
    """One seeded order: F1 tasks shuffled into the positions F2 does not take, F2 shuffled into
    its preregistered positions. The same order serves arms A, C and E."""
    if manifest['selection'].get('method') == 'learning-development-v1':
        return manifest['task_ids']
    families = manifest['selection']['families']
    rng = random.Random(f'thesis-order-v1:{seed}')
    f1 = rng.sample(sorted(families['F1']), len(families['F1']))
    f2 = rng.sample(sorted(families['F2']), len(families['F2']))
    total = len(f1) + len(f2)
    require(len(f2) == len(f2_positions) and all(1 <= p <= total for p in f2_positions), 'F2 positions do not fit the suite')
    first, second = iter(f1), iter(f2)
    return [next(second) if position in f2_positions else next(first) for position in range(1, total + 1)]


def trajectory_capabilities(config, arm, spec):
    base = capabilities(config)
    state = {'version': TRAJECTORY_VERSION, 'arm': arm, 'state': ARM_STATE[arm],
             'order': ('seeded; F2 at positions 8, 11, 14, 17; same order for arms '
                       + ' and '.join([', '.join(spec['arms'][:-1]), spec['arms'][-1]])),
             'cold_restart': 'after task 9: new runner process, new JVM, new conversation; state only from the trajectory directory',
             'library': ('none' if arm == 'A' else
                         'one content-addressed library per (arm, ordering); task k+1 gets exactly the pin committed after task k')}
    if arm != 'A':
        state['proposal'] = acquisition_capability(arm_acquisition(arm))
    if base_arm(arm) == 'E':
        state['promotion'] = {'rule': spec['promotion_rule'],
                              'panel': 'controller-only item gold from windows disjoint from every task window; no model call'}
    if spec['version'] == 'learning-development-v1':
        state.update(order='six fixed synthetic development tasks; no task or record repeats',
                     cold_restart='after task 2: new runner process, JVM, worker and conversation; verified library only',
                     acquisition_schedule='proposal/promotion on tasks 1-2 only; frozen library on tasks 3-6')
    return {**base, 'trajectory': state}


def trajectory_contract(config, arm, library=None, pin=None):
    """The per-task config: arm A is the plan's own; C and E add the pinned library and the proposal switch."""
    if arm == 'A':
        return config
    return {**config, 'aljure_contract': {**config.get('aljure_contract', {}),
                                          'artifacts': {'library': library, 'library_sha256': pin},
                                          'acquisition': arm_acquisition(arm)}}


def panel_file(suite, manifest):
    path = Path(suite) / 'controller/panel.json'
    expected = manifest.get('files', {}).get('controller/panel.json')
    require(expected and path.is_file() and not path.is_symlink() and digest(path.read_bytes()) == expected,
            'Development panel is missing or changed after suite preparation')
    return path


def expected_trajectories(manifest, spec):
    return [{'id': f'{arm}-s{seed}', 'arm': arm, 'seed': seed, 'order': trajectory_order(manifest, seed, spec['f2_positions']),
             'initial_library_sha256': None if arm == 'A' else EMPTY_LIBRARY_SHA256}
            for seed in spec['ordering_seeds'] for arm in spec['arms']]


def plan_trajectory(suite, config_path, output):
    manifest, tasks, _ = read_suite(suite)
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    spec = trajectory_spec(config)
    if spec['version'] == 'learning-development-v1':
        from .learning_development import verify
        verify(suite)
    else:
        require(manifest['input_provenance'] == 'verified-pinned-upstream' and
                manifest['selection'].get('method') == 'thesis-pilot-v1', 'Trajectory plans need the pinned thesis-pilot suite')
    panel = panel_file(suite, manifest)
    trajectories = expected_trajectories(manifest, spec)
    caps = {arm: trajectory_capabilities(config, arm, spec) for arm in spec['arms']}
    value = {'version': TRAJECTORY_VERSION, 'evidence': 'IMPLEMENTED / UNVERIFIED', 'authorized': False,
             'suite_sha256': manifest['suite_sha256'], 'panel_sha256': digest(panel.read_bytes()), 'config': config,
             'source': source_snapshot(), 'runtime_source': runtime_snapshot(), 'prime_commit': None,
             'capabilities': caps, 'capability_sha256': {arm: digest(encoded(c)) for arm, c in caps.items()},
             'trajectories': trajectories, 'promotion_rule_sha256': digest(encoded(spec['promotion_rule'])),
             'allocation': {'per_task_usd_cap': config['usd_per_arm'], 'spend_cap_usd': spec['spend_cap_usd'],
                            'spend_check_margin_usd': spec['spend_check_margin_usd'],
                            'task_runs': len(trajectories) * len(manifest['task_ids']),
                            'cap_rule': ('a task starts only if recorded spend plus unknown reservations of every trajectory '
                                         'under the output root, plus the margin, is within the spend cap'),
                            'borrowing': False},
             'model_calls': 0,
             'approval_scope': ('NEW direct Claude subscription usage; API-rate-equivalent caps; approve this exact plan hash'
                                if config['provider'] == SUBSCRIPTION else
                                'NEW Anthropic API billing, not Claude subscription usage; approve this exact plan hash')}
    value['plan_sha256'] = digest(encoded(value))
    with Path(output).open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    return value


def read_trajectory_plan(path, suite):
    value = json.loads(Path(path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    manifest, tasks, _ = read_suite(suite)
    require(value['version'] == TRAJECTORY_VERSION and value['suite_sha256'] == manifest['suite_sha256'], 'Plan/suite mismatch')
    validate_config(value['config'])
    spec = trajectory_spec(value['config'])
    if spec['version'] == 'learning-development-v1':
        from .learning_development import verify
        verify(suite)
    require(digest(panel_file(suite, manifest).read_bytes()) == value['panel_sha256'], 'Development panel changed after plan freeze')
    require(value['trajectories'] == expected_trajectories(manifest, spec), 'Plan omitted, repeated or reordered a trajectory task')
    require(value['capabilities'] == {arm: trajectory_capabilities(value['config'], arm, spec) for arm in spec['arms']},
            'Capability pins changed')
    require(value['source']['sha256'] == source_snapshot()['sha256'], 'Source changed after plan freeze')
    require(value['runtime_source'] == runtime_snapshot(), 'Runtime inputs changed after plan freeze')
    return value, manifest, tasks, spec


def trajectory_preflight(plan_path, suite):
    value, _, _, spec = read_trajectory_plan(plan_path, suite)
    ready = readiness(value, value['config'], native_prime=False, acquisition=True)
    blockers = list(ready['blockers'])
    try:
        # The scripted end-to-end acquisition control (python3 -m benchmark trajectory-acquisition-fixture).
        proof = json.loads((ROOT / 'var/acquisition-relay-proof.json').read_text())
        require(proof.get('evidence') == 'FIXTURE' and proof.get('status') == 'PASSED' and all(proof.get('checks', {}).values()),
                'missing passed acquisition relay fixture')
        require(proof.get('runtime_source') == value['runtime_source'] and
                proof.get('transport_contract') == transport_contract(value['config']) and
                proof.get('provider') == value['config']['provider'] and
                proof.get('sci_image') == ready['checks'].get('sci_isolation', {}).get('image'),
                'acquisition relay fixture is for other runtime inputs, transport or worker image')
        ready['checks']['acquisition_relay_fixture'] = {'sha256': digest(encoded(proof))}
    except Exception as error:
        blockers.append('Acquisition relay fixture: ' + str(error))
    return {**ready, 'ready': not blockers, 'blockers': blockers,
            'trajectories': [t['id'] for t in value['trajectories']], 'panel_sha256': value['panel_sha256']}


def trajectory_ledger(out):
    path = Path(out) / 'trajectory.jsonl'
    return list(jsonl(path)) if path.exists() else []


def append_ledger(out, row):
    with (Path(out) / 'trajectory.jsonl').open('ab') as stream:
        stream.write(encoded(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def verify_library_chain(library, rows, initial):
    """Fail closed. Every committed pin's bytes hash to the pin and name, as parent, the pin in
    force when it was promoted; a rollback targets a pin committed earlier. Returns the pin in force."""
    if initial is None:
        require(not any(r['type'] in ('rollback',) or r.get('status') == 'committed' for r in rows), 'Arm A has no library')
        return None
    root = Path(library) / 'libraries'

    def check(pin):
        path = root / f'{pin}.edn'
        require(path.is_file() and not path.is_symlink(), 'Pinned library version is missing')
        data = path.read_bytes()
        require(digest(data) == pin, 'Library version bytes changed after commit')
        return data
    require(check(initial) == EMPTY_LIBRARY, 'Initial library is not the empty version')
    pin, committed = initial, [initial]
    for row in rows:
        if row['type'] == 'promotion' and row['status'] == 'committed':
            require(row['pin_before'] == pin, 'Promotion was made against another pin')
            parent = PARENT.search(check(row['pin_after']))
            require(parent and parent.group(2) and parent.group(2).decode() == pin, 'Library version parent differs from the pin in force')
            pin = row['pin_after']
            committed.append(pin)
        elif row['type'] == 'rollback':
            require(row['from'] == pin and row['to'] in committed, 'Rollback target was never committed')
            check(row['to'])
            pin = row['to']
    return pin


def pilot_spend(output):
    """Recorded spend plus unknown reservations of every trajectory under the pilot root."""
    total = Decimal(0)
    for results in sorted(Path(output).glob('*/results.jsonl')):
        for row in jsonl(results):
            usage = account(list(jsonl(results.parent / row['usage_path'])), row['pricing_usd_per_m'])
            total += money(usage['known_model_cost_usd']) + money(usage['reserved_unknown_usd'])
    return total


class PromotionStageFailed(Exception):
    """The promotion stage itself failed (gate, panel, worker, an approved entry) or an integrity check
    failed (proposal hash, receipt, promoted version, pin): not the candidate's failure. Stops the trajectory."""


def promote_process(request_path, environment, seconds):
    """The controller's promotion step in a fresh JVM: no model call; the E panel runs in a fresh isolated SCI worker."""
    return subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.acquisition', 'promote', str(request_path)],
                          cwd=ROOT, capture_output=True, timeout=seconds + 120, env=environment)


def promote_task(out, entry, value, spec, task_out, position, task_id, pin, panel_path, environment):
    """Runs strictly after the task's answer and result row are recorded. The pin in force
    advances only on a complete approved receipt whose version verifies; anything else,
    including a crash, keeps the previous pin. Files a crash left behind are listed, never deleted."""
    config = value['config']
    base = {'type': 'promotion', 'position': position, 'task_id': task_id, 'pin_before': pin, 'pin_after': pin,
            'model_calls': 0}
    try:
        acquisition = json.loads((task_out / 'agent/result.json').read_text()).get('acquisition') or {}
    except Exception:
        acquisition = {}
    proposal = task_out / 'agent/proposal.edn'
    if not proposal.is_file():
        return {**base, 'status': 'no-proposal', 'decision': acquisition.get('decision', 'not-offered')}
    request = {'arm': base_arm(entry['arm']), 'library': str(out / 'library'), 'pin': pin, 'proposal': str(proposal),
               'proposal_sha256': digest(proposal.read_bytes()), 'task_id': task_id, 'position': position,
               'rule': spec['promotion_rule'], 'panel': str(panel_path), 'panel_sha256': value['panel_sha256'],
               'assisted': aljure_sci(config)['surface'] == 'assisted', 'structured_labels': False,
               'seconds': spec['validation_seconds']}
    request_path = task_out / 'promotion-request.json'
    request_path.write_bytes(encoded(request))
    started, receipt, receipt_sha, failure = time.monotonic(), {}, None, None
    try:
        if request['proposal_sha256'] != acquisition.get('proposal-sha256'):
            raise PromotionStageFailed('Proposal changed after the task')
        completed = promote_process(request_path, environment, spec['validation_seconds'])
        (task_out / 'promotion-stdout.txt').write_bytes(completed.stdout or b'')
        (task_out / 'promotion-stderr.txt').write_bytes(completed.stderr or b'')
        reply = json.loads((completed.stdout or b'{}').decode().strip().splitlines()[-1])
        # A stage-level fault is not a candidate failure: it is recorded and stops the trajectory.
        if completed.returncode == 3 or reply.get('fatal'):
            raise PromotionStageFailed(str(reply.get('error'))[:300])
        require(completed.returncode == 0 and isinstance(reply.get('receipt-sha256'), str), 'Promotion did not complete')
        receipt_path = out / 'library/receipts' / f"{reply['receipt-sha256']}.json"
        if not (receipt_path.is_file() and digest(receipt_path.read_bytes()) == reply['receipt-sha256']):
            raise PromotionStageFailed('Receipt missing or changed')
        receipt, receipt_sha = json.loads(receipt_path.read_text()), reply['receipt-sha256']
        if not (receipt.get('parent-pin') == pin and receipt.get('task-id') == task_id and receipt.get('position') == position):
            raise PromotionStageFailed('Receipt belongs to another task or pin')
        if receipt.get('decision') == 'approved':
            new = receipt['pin-after']
            data = (out / 'library/libraries' / f'{new}.edn').read_bytes()
            parent = PARENT.search(data)
            if not (digest(data) == new and parent and parent.group(2) and parent.group(2).decode() == pin):
                raise PromotionStageFailed('Promoted version does not verify against the pin in force')
            status, after = 'committed', new
        else:
            if receipt.get('pin-after') != pin:
                raise PromotionStageFailed('A rejected promotion changed the pin')
            status, after = receipt.get('decision'), pin
    except PromotionStageFailed as error:
        failure, status, after = 'PromotionStageFailed', 'stage-failed', pin
        base['stage_error'] = str(error)
    except Exception as error:
        failure = type(error).__name__
        status, after = 'crashed', pin
    row = {**base, 'status': status, 'pin_after': after, 'decision': receipt.get('decision'),
           'reasons': receipt.get('reasons'), 'receipt_sha256': receipt_sha,
           'validation_seconds': time.monotonic() - started, 'validation_ms': receipt.get('validation-ms'),
           'proposal_decision': acquisition.get('decision')}
    if failure:
        committed = {EMPTY_LIBRARY_SHA256} | {r['pin_after'] for r in trajectory_ledger(out) if r.get('status') == 'committed'}
        row['failure'] = failure
        row['orphans'] = sorted(p.stem for p in (out / 'library/libraries').glob('*.edn') if p.stem not in committed)
    return row


def rollback_trajectory(output, trajectory, to_pin, reason):
    """Explicit rollback between tasks: the next task gets to_pin, which must have been committed."""
    out = Path(output) / trajectory
    rows = trajectory_ledger(out)
    require(rows and rows[0]['type'] == 'start' and rows[0]['initial_library_sha256'], 'Only a C or E trajectory has a library')
    require(isinstance(reason, str) and reason.strip(), 'A rollback needs a recorded reason')
    current = verify_library_chain(out / 'library', rows, rows[0]['initial_library_sha256'])
    verify_library_chain(out / 'library', rows + [{'type': 'rollback', 'from': current, 'to': to_pin}],
                         rows[0]['initial_library_sha256'])
    row = {'type': 'rollback', 'from': current, 'to': to_pin, 'reason': reason, 'after_position':
           max([r['position'] for r in rows if r['type'] == 'task'] or [0])}
    append_ledger(out, row)
    return row


def trajectory_status(execution, out):
    """A recorded answer stands even if the optional proposal turn then hit the task deadline."""
    status, failure = arm_status(execution, (out / 'answer.txt').exists())
    recorded = out / 'agent/answer-recorded.json'
    if status == 'timeout' and recorded.is_file() and (out / 'agent/answer.txt').is_file():
        if json.loads(recorded.read_text()).get('sha256') == digest((out / 'agent/answer.txt').read_bytes()):
            (out / 'answer.txt').write_bytes((out / 'agent/answer.txt').read_bytes())
            return 'completed', 'ProposalTurnDeadline'
    return status, failure


def run_trajectory(plan_path, suite, output, trajectory, *, authorize_api_plan=None, authorize_subscription_plan=None):
    """One phase of one (arm, ordering) trajectory. Phase 1 runs tasks 1-9 and stops at the
    preregistered cold restart; calling again in a new process resumes from the trajectory
    directory alone and runs tasks 10-18. Per task: run on the pin in force, record the
    answer and result row, then (C, E) promote, then commit the new pin or keep the old one."""
    value, manifest, tasks, spec = read_trajectory_plan(plan_path, suite)
    subscription = value['config']['provider'] == SUBSCRIPTION
    approval = authorize_subscription_plan if subscription else authorize_api_plan
    other = authorize_api_plan if subscription else authorize_subscription_plan
    require(other is None and approval == value['plan_sha256'],
            'Approve this exact frozen trajectory plan, then pass only its --authorize-subscription-plan or --authorize-api-plan hash')
    entry = next((t for t in value['trajectories'] if t['id'] == trajectory), None)
    require(entry is not None, 'Unknown trajectory')
    ready = trajectory_preflight(plan_path, suite)
    require(ready['ready'], 'Live run refused: ' + '; '.join(ready['blockers']))
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT), 'Trajectory output must be under repl-lab: libraries are pinned by relative path')
    out = output / trajectory
    rows = trajectory_ledger(out)
    cold = spec['cold_restart_after']
    if not rows:
        require(not out.exists(), 'Output exists; prior evidence must remain unchanged')
        out.mkdir(parents=True)
        (out / 'plan.json').write_bytes(encoded(value))
        (out / 'preflight.json').write_bytes(encoded(ready))
        if entry['initial_library_sha256']:
            (out / 'library/libraries').mkdir(parents=True)
            (out / 'library/libraries' / f'{EMPTY_LIBRARY_SHA256}.edn').write_bytes(EMPTY_LIBRARY)
        append_ledger(out, {'type': 'start', 'trajectory': trajectory, 'arm': entry['arm'], 'seed': entry['seed'],
                            'plan_sha256': value['plan_sha256'], 'initial_library_sha256': entry['initial_library_sha256']})
        positions = range(1, cold + 1)
    else:
        require(rows[-1]['type'] == 'cold-restart' and rows[-1]['plan_sha256'] == value['plan_sha256'] and
                sum(r['type'] == 'task' for r in rows) == cold,
                'A trajectory resumes only at its preregistered cold restart, under the same plan')
        if spec['version'] == 'learning-development-v1':
            require(rows[-1].get('runner_pid') != os.getpid(), 'Development resume needs a new runner process')
        (out / 'preflight-resume.json').write_bytes(encoded(ready))
        positions = range(cold + 1, len(entry['order']) + 1)
    config = value['config']
    library = str((out / 'library').relative_to(ROOT)) if entry['initial_library_sha256'] else None
    panel = panel_file(suite, manifest)
    families = {t: f for f, ids in manifest['selection']['families'].items() for t in ids}
    results = list(jsonl(out / 'results.jsonl')) if (out / 'results.jsonl').exists() else []
    model = {'provider': config['provider'], 'model': config['model'], 'thinking': 'adaptive/summarized; effort=medium',
             'temperature': 'provider-default', 'max_output_tokens': config['max_output_tokens']}
    pricing = {RATE_KEYS[k]: v for k, v in config['rates'].items()}
    images = [ready['checks']['sci_isolation']['image']]
    stop = False
    for position in positions:
        # Fail closed before every task: the plan's panel and every committed pin must still verify.
        require(shutil.disk_usage(ROOT).free >= 6 * 2**30,
                'Host free disk is below the 6 GiB floor; no further task starts')
        require(digest(panel.read_bytes()) == value['panel_sha256'], 'Development panel changed during the trajectory')
        pin = verify_library_chain(out / 'library', trajectory_ledger(out), entry['initial_library_sha256'])
        require(not stop, 'Trajectory stopped: an earlier provider, isolation or cleanup failure')
        require(pilot_spend(output) + money(spec['spend_check_margin_usd']) <= money(spec['spend_cap_usd']),
                'Pilot spend cap reached; no further task starts')
        task_id = entry['order'][position - 1]
        task = tasks[task_id]
        task_out = out / f'{position:02}-aljure'
        task_out.mkdir()
        task_config = trajectory_contract(config, entry['arm'], library, pin)
        frozen_development = spec['version'] == 'learning-development-v1' and position > cold
        if frozen_development:
            task_config['aljure_contract'].pop('acquisition')
        started, status, failure, gateway = time.monotonic(), 'error', None, None
        try:
            before = docker_state(images)
            (task_out / 'docker-before.json').write_bytes(encoded(before))
            if docker_blockers(before):
                failure, stop = 'DockerNotReady', True
            else:
                data = public_input(suite, task)
                (task_out / 'public-input.json').write_bytes(encoded(data))
                transport = ClaudeSubscriptionTransport if subscription else AnthropicMessagesTransport
                gateway = GatewayClient(task_out / 'gateway', gateway_config(task_config, 'aljure'),
                                        transport(authorized=True), evidence='LIVE MODEL RUN')
                execution = run_arm('aljure', data, task_out, task_config, gateway, ready)
                status, failure = trajectory_status(execution, task_out)
                after = docker_state(images)
                (task_out / 'docker-after.json').write_bytes(encoded(after))
                if after['session'] != before['session']:
                    failure, status, stop = 'DockerRestartedDuringArm', 'error', True
        except Exception as error:
            failure, stop = type(error).__name__, True
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception as error:
                    stop, failure, status = True, type(error).__name__, 'error'
        usage = task_out / 'gateway/usage.jsonl'
        if not usage.exists():
            require(gateway is None, 'Cannot record a task without recovering the gateway ledger')
            (task_out / 'gateway').mkdir(exist_ok=True)
            usage.write_bytes(b'')
        receipts = list(jsonl(usage))
        if any(row['status'] == 'unknown' for row in receipts):
            stop, failure, status = True, 'ProviderOutcomeUnknown', 'error'
        if worker_isolation_refused(task_out):
            stop, failure, status = True, 'IsolationPreflightFailed', 'error'
        trace = task_out / 'trace.json'
        trace.write_bytes(encoded({'status': status, 'failure': failure, 'case': {'task_id': task_id, 'harness': 'aljure'},
                                   'artifacts': {str(p.relative_to(task_out)): digest(p.read_bytes())
                                                 for p in task_out.rglob('*') if p.is_file()}}))
        row = {'task_id': task_id, 'harness': 'aljure', 'suite_sha256': manifest['suite_sha256'],
               'task_sha256': task['task_sha256'], 'provenance': 'recorded-model-run', 'fresh_session': True,
               'model_config': model, 'budget_usd': config['usd_per_arm'], 'pricing_usd_per_m': pricing,
               'harness_revision': value['source']['commit'], 'status': status,
               'wall_time_ms': (time.monotonic() - started) * 1000,
               'capability_sha256': value['capability_sha256'][entry['arm']], 'source_sha256': value['source']['sha256'],
               'learning_library_sha256': pin if pin else digest(encoded([])), 'failure': failure,
               'trajectory': trajectory, 'arm': entry['arm'], 'seed': entry['seed'], 'position': position,
               'family': families[task_id]}
        for label, path in [('trace', trace), ('usage', usage)] + ([('answer', task_out / 'answer.txt')] if status == 'completed' else []):
            row[label + '_path'] = str(path.relative_to(out))
            row[label + '_sha256'] = digest(path.read_bytes())
        results.append(row)
        write_jsonl(out / 'results.jsonl', results)
        # The answer and its row are recorded; only now may this task's proposal be promoted.
        append_ledger(out, {'type': 'task', 'position': position, 'task_id': task_id, 'pin_seen': pin, 'status': status,
                            'answer_sha256': row.get('answer_sha256')})
        if entry['initial_library_sha256'] and not stop and not frozen_development:
            environment = {k: v for k, v in os.environ.items()
                           if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
            environment['REPL_LAB_WORKER_AUDIT_DIR'] = str(task_out / 'promotion-worker-audit')
            environment['REPL_LAB_WORKER_OUTPUT_BYTES'] = str(aljure_sci(config)['worker_output_bytes'])
            promotion = promote_task(out, entry, value, spec, task_out, position, task_id, pin, panel, environment)
            append_ledger(out, promotion)
            if promotion['status'] in ('stage-failed', 'crashed'):
                stop = True  # fail closed: no later task may run with a broken validation stage
    require(not stop, 'Trajectory stopped: an earlier provider, isolation or cleanup failure')
    if positions[-1] == cold:
        pin = verify_library_chain(out / 'library', trajectory_ledger(out), entry['initial_library_sha256'])
        append_ledger(out, {'type': 'cold-restart', 'after': cold, 'pin': pin, 'plan_sha256': value['plan_sha256'],
                            **({'runner_pid': os.getpid()} if spec['version'] == 'learning-development-v1' else {})})
        return {'status': 'cold-restart-required', 'trajectory': trajectory, 'pin': pin, 'model_calls_in_controller': 0}
    report = compare(suite, out / 'results.jsonl', harnesses=('aljure',))
    (out / 'report.json').write_bytes(encoded(report))
    return report


COUNT_QUESTION = re.compile(r"classified as label '([^']+)'")
SYMBOL_EDGE = r"[\w\-?!*+<>=/.]"


def declared_number(text):
    found = re.search(r'Answer:\s*\[?\s*(-?\d+)', text or '')
    return int(found.group(1)) if found else None


def _numbers(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [x for v in value.values() for x in _numbers(v)]
    if isinstance(value, list):
        return [x for v in value for x in _numbers(v)]
    return []


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def source_attributed_reuse(events, answer_text):
    """Reuse read from the task's own record (research/PILOT1_RESULTS.md: the eligible-reuse heuristic
    misses answers the model types). Model-directed reuse: a root repl_eval names a preloaded export.
    Its value entered the answer if an evaluation that named one returned the delivered number. Reads
    of controller-supplied library-labels are counted apart. Calls and results pair in order."""
    names = {f.get('name') for e in events if e['type'] == 'artifact-preloaded' for f in e['payload'].get('functions', [])
             if str(f.get('role', '')).lstrip(':') == 'export'}
    sources = [e['payload']['command'].get('source') or '' for e in events if e['type'] == 'tool-call'
               and e['payload'].get('session') == 'root' and e['payload']['command'].get('op') == 'repl/eval']
    values = [(e['payload'].get('result') or {}).get('value') for e in events if e['type'] == 'tool-result'
              and e['payload'].get('session') == 'root' and e['payload'].get('op') == 'repl/eval']
    patterns = [re.compile(f'(?<!{SYMBOL_EDGE}){re.escape(n)}(?!{SYMBOL_EDGE})') for n in names if n]
    named = [v for src, v in zip(sources, values) if any(p.search(src) for p in patterns)]
    number = declared_number(answer_text)
    return {'model_directed': bool(named), 'value_in_answer': number is not None and any(number in _numbers(v) for v in named),
            'reads_supplied': any('library-labels' in src for src in sources)}


def new_record_windows(rows, contexts, gold, panel_texts):
    """The new-record endpoint's records (research/THESIS_PILOT_PROTOCOL.md section 6): for task k,
    the records of its window whose trimmed text neither the panel nor the window of any of tasks
    1..k-1 in this order held. rows: one trajectory's result rows; contexts: task id -> (question,
    public context); gold: task id -> item gold. Windows are grouped by the pin in force at task k;
    a task on the empty library has nothing to score and forms no window."""
    from .official import record_texts
    seen, cases, groups = set(panel_texts), [], {}
    for row in sorted(rows, key=lambda r: r['position']):
        question, context = contexts[row['task_id']]
        items = gold[row['task_id']]
        new = [item for item in items if item['text'].strip() not in seen]
        seen |= set(record_texts(context))
        pin, name = row['learning_library_sha256'], f"p{row['position']:02}"
        cases.append({'position': row['position'], 'task_id': row['task_id'], 'family': row['family'], 'pin': pin,
                      'records': len(items), 'new_records': len(new)})
        if new and pin != EMPTY_LIBRARY_SHA256:
            groups.setdefault(pin, []).append(
                {'id': name, 'question': question, 'context': context,
                 'items': [{'case': f'{name}-{n}', 'text': item['text'], 'label': item['label']} for n, item in enumerate(new)]})
    return cases, groups


def score_process(request_path, environment, seconds):
    """One committed version on new records in a fresh JVM and a fresh isolated SCI worker; no model call."""
    return subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.acquisition', 'score', str(request_path)],
                          cwd=ROOT, capture_output=True, timeout=seconds + 120, env=environment)


def pooled_new_records(cases, rule):
    """Exact counts over the scored tasks, and whether they meet the promotion rule's thresholds."""
    scored = [c for c in cases if c['scored']]
    n, decided, correct = (sum(c[k] for c in scored) for k in ('new_records', 'decided', 'correct'))
    (pn, pd), (cn, cd) = rule['min_precision'], rule['min_coverage']
    return {'tasks': len(scored), 'new_records': n, 'decided': decided, 'correct': correct,
            'coverage': [decided, n], 'precision': [correct, decided],
            'meets_promotion_thresholds': bool(decided and decided * cd >= cn * n and correct * pd >= pn * decided)}


def trajectory_new_records(plan_path, suite, output):
    """Offline, after the runs: each arm-E task's pin in force, scored on that task's new records
    against the controller-only item gold of the task windows. Zero model calls. Writes
    <output>/new-records.json once; prior evidence is never overwritten."""
    value = json.loads(Path(plan_path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    manifest, tasks, _ = read_suite(suite)
    panel_path = panel_file(suite, manifest)
    require(value['suite_sha256'] == manifest['suite_sha256'] and digest(panel_path.read_bytes()) == value['panel_sha256'],
            'Plan/suite mismatch')
    items_path = Path(suite) / 'controller/task-items.json'
    require(items_path.is_file() and not items_path.is_symlink() and
            digest(items_path.read_bytes()) == manifest['files'].get('controller/task-items.json'),
            'Task-window item gold is missing or changed after suite preparation')
    by_context = {w['context_sha256']: w['items'] for w in json.loads(items_path.read_text())['windows']}
    output = Path(output).resolve()
    target = output / 'new-records.json'
    require(not target.exists(), 'new-records.json exists; prior evidence must remain unchanged')
    config, spec = value['config'], trajectory_spec(value['config'])
    panel_texts = {item['text'].strip() for w in json.loads(panel_path.read_text())['windows'] for item in w['items']}
    contexts = {t: (task['question'], checked_file(Path(suite) / 'public', task['context_path'], task['context_sha256']).read_text())
                for t, task in tasks.items()}
    gold = {t: by_context[task['context_sha256']] for t, task in tasks.items()}
    environment = {k: v for k, v in os.environ.items()
                   if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
    environment['REPL_LAB_WORKER_OUTPUT_BYTES'] = str(aljure_sci(config)['worker_output_bytes'])
    result = {'schema': 'thesis-new-records-v1', 'plan_sha256': value['plan_sha256'], 'suite_sha256': manifest['suite_sha256'],
              'model_calls': 0, 'arm': 'E', 'trajectories': {}}
    for entry in (t for t in value['trajectories'] if base_arm(t['arm']) == 'E'):
        out = output / entry['id']
        rows = list(jsonl(out / 'results.jsonl')) if (out / 'results.jsonl').exists() else []
        if len(rows) != len(entry['order']):
            result['trajectories'][entry['id']] = {'complete': False}
            continue
        verify_library_chain(out / 'library', trajectory_ledger(out), entry['initial_library_sha256'])
        cases, groups = new_record_windows(rows, contexts, gold, panel_texts)
        # Also every task's whole window under its pin in force: which labels the version decides there,
        # so count error can be split by whether it decides the asked label (research/PILOT1_RESULTS.md).
        for case in cases:
            if case['pin'] != EMPTY_LIBRARY_SHA256:
                question, context = contexts[case['task_id']]
                name = f"a{case['position']:02}"
                groups.setdefault(case['pin'], []).append(
                    {'id': name, 'question': question, 'context': context,
                     'items': [{'case': f'{name}-{n}', 'text': item['text'], 'label': item['label']}
                               for n, item in enumerate(gold[case['task_id']])]})
        directory = out / 'new-records'
        directory.mkdir(mode=0o700)
        scored = {}
        for pin, windows in groups.items():
            panel = directory / f'{pin}-panel.json'
            panel.write_bytes(encoded({'schema': 'aljure-panel-v1', 'windows': windows}))
            panel.chmod(0o600)
            request = {'library': str(out / 'library'), 'pin': pin, 'panel': str(panel), 'panel_sha256': digest(panel.read_bytes()),
                       'assisted': aljure_sci(config)['surface'] == 'assisted', 'structured_labels': False,
                       'seconds': spec['validation_seconds']}
            request_path = directory / f'{pin}-request.json'
            request_path.write_bytes(encoded(request))
            environment['REPL_LAB_WORKER_AUDIT_DIR'] = str(directory / f'{pin}-worker-audit')
            completed = score_process(request_path, environment, spec['validation_seconds'])
            (directory / f'{pin}-stdout.txt').write_bytes(completed.stdout or b'')
            (directory / f'{pin}-stderr.txt').write_bytes(completed.stderr or b'')
            reply = json.loads((completed.stdout or b'{}').decode().strip().splitlines()[-1])
            require(completed.returncode == 0 and reply.get('pin') == pin and reply.get('model-calls') == 0 and
                    [w['window'] for w in reply.get('windows', [])] == [w['id'] for w in windows],
                    f"Scoring version {pin} failed: {str(reply.get('error'))[:300]}")
            scored.update({w['window']: w for w in reply['windows']})
        for case in cases:
            window = scored.get(f"p{case['position']:02}")
            whole = scored.get(f"a{case['position']:02}")
            asked = COUNT_QUESTION.search(contexts[case['task_id']][0])
            case.update({'scored': window is not None, 'decided': window['decided'] if window else 0,
                         'correct': window['correct'] if window else 0, 'admitted': window['admitted'] if window else 0,
                         'errors': window['errors'] if window else 0,
                         'window_labels': (whole or {}).get('labels', {}), 'asked_label': asked.group(1) if asked else None,
                         'decides_asked_label': bool(asked and whole and whole.get('labels', {}).get(asked.group(1)))})
        result['trajectories'][entry['id']] = {'complete': True, 'cases': cases}
    complete = [t['cases'] for t in result['trajectories'].values() if t['complete']]
    result['pooled'] = {family: pooled_new_records([c for cases in complete for c in cases if c['family'] == family],
                                                   spec['promotion_rule'])
                        for family in ('F1', 'F2')}
    result['complete_trajectories'] = len(complete)
    with target.open('xb') as stream:
        stream.write(encoded(result) + b'\n')
    return result


def _acquisition_ids(task_dir):
    try:
        acquisition = json.loads((task_dir / 'agent/result.json').read_text()).get('acquisition') or {}
        return set(acquisition.get('spend', {}).get('provider-ids', []))
    except Exception:
        return set()


def trajectory_report(output, suite):
    """Endpoints from recorded evidence only (research/THESIS_PILOT_PROTOCOL.md section 6).
    Task inference includes every root and child call, so the model's handling of records the
    library left unresolved (fallback) is charged there; the proposal turn is acquisition cost."""
    from .official import score_answer, record_texts
    manifest, tasks, answers = read_suite(suite)
    output = Path(output)
    trajectories = {}
    for out in sorted(p for p in output.iterdir() if (p / 'trajectory.jsonl').is_file()):
        ledger = trajectory_ledger(out)
        rows = list(jsonl(out / 'results.jsonl')) if (out / 'results.jsonl').exists() else []
        promotions = {r['position']: r for r in ledger if r['type'] == 'promotion'}
        families = {t: f for f, ids in manifest['selection']['families'].items() for t in ids}
        # Which family proposed each promoted function (by code hash); the arm-C memo is 'memo'.
        origin = {}
        for receipt_path in sorted((out / 'library/receipts').glob('*.json')) if (out / 'library/receipts').is_dir() else []:
            receipt = json.loads(receipt_path.read_text())
            if receipt.get('decision') == 'approved' and (receipt.get('candidate') or {}).get('code-hash'):
                origin[receipt['candidate']['code-hash']] = families.get(receipt.get('task-id'))
        cases, seen = [], set()
        for row in sorted(rows, key=lambda r: r['position']):
            task_dir = out / f"{row['position']:02}-aljure"
            usage = list(jsonl(out / row['usage_path']))
            ids = _acquisition_ids(task_dir)
            total = account(usage, row['pricing_usd_per_m'])
            acquisition = account([u for u in usage if u.get('provider_request_id') in ids], row['pricing_usd_per_m'])
            output_text = (out / row['answer_path']).read_text() if row['status'] == 'completed' else ''
            score = float(score_answer(manifest['suite'], answers[row['task_id']], output_text)['score']) if output_text else 0.0
            try:
                result = json.loads((task_dir / 'agent/result.json').read_text())
            except Exception:
                result = {}
            reuse = result.get('artifact-reuse') or {}
            events_path = task_dir / 'agent/events.jsonl'
            attributed = source_attributed_reuse(list(jsonl(events_path)) if events_path.is_file() else [], output_text)
            asked = COUNT_QUESTION.search(tasks[row['task_id']]['question'])
            gold_count = declared_number('Answer: ' + re.sub(r'[\[\]]', '', answers[row['task_id']]['answer'])) if asked else None
            declared = declared_number(output_text) if asked else None
            records = set(record_texts(checked_file(Path(suite) / 'public', tasks[row['task_id']]['context_path'],
                                                    tasks[row['task_id']]['context_sha256']).read_text()))
            promotion = promotions.get(row['position'], {})
            cases.append({'position': row['position'], 'task_id': row['task_id'], 'family': row['family'], 'status': row['status'],
                          'score': score, 'verified': score == 1.0, 'pin_seen': row['learning_library_sha256'],
                          'total_usd': total['model_cost_usd'], 'acquisition_usd': acquisition['model_cost_usd'],
                          'task_inference_usd': (None if total['model_cost_usd'] is None or acquisition['model_cost_usd'] is None
                                                 else total['model_cost_usd'] - acquisition['model_cost_usd']),
                          'validation_seconds': promotion.get('validation_seconds'), 'promotion': promotion.get('status'),
                          'activation': reuse.get('classification', 'stateless' if row['arm'] == 'A' else 'none'),
                          'refused': reuse.get('refused', []),
                          # A correct refusal: an F2 task refused only functions F1 tasks proposed, or the memo for lack of an exact match.
                          'correct_refusal': bool(row['family'] == 'F2' and reuse.get('refused') and all(
                              origin.get(r.get('code-hash')) == 'F1' or r.get('reason') == 'no-exact-match'
                              for r in reuse.get('refused', []))),
                          'records_seen_earlier_share': (len(records & seen) / len(records)) if records else None,
                          **attributed, 'asked_label': asked.group(1) if asked else None, 'declared': declared,
                          'count_log_error': (abs(math.log((max(declared, 0) + 1) / (gold_count + 1)))
                                              if declared is not None and gold_count is not None else None)})
            seen |= records
        trajectories[out.name] = {'arm': rows[0]['arm'] if rows else None, 'seed': rows[0]['seed'] if rows else None,
                                  'complete': len(rows) == len(manifest['task_ids']), 'cases': cases,
                                  'versions': [{'position': r['position'], 'pin': r['pin_after'], 'receipt': r.get('receipt_sha256')}
                                               for r in ledger if r['type'] == 'promotion' and r['status'] == 'committed'],
                                  'rollbacks': [r for r in ledger if r['type'] == 'rollback']}
    arms = {}
    for name, t in trajectories.items():
        for family in ('F1', 'F2'):
            chosen = [c for c in t['cases'] if c['family'] == family]
            if not chosen:
                continue
            costs = [c['total_usd'] for c in chosen]
            known = None if any(x is None for x in costs) else sum(costs)
            verified = sum(c['verified'] for c in chosen)
            arms.setdefault(t['arm'], {}).setdefault(family, []).append(
                {'trajectory': name, 'mean_score': sum(c['score'] for c in chosen) / len(chosen),
                 'cost_usd_including_acquisition': known, 'verified': verified,
                 'cost_per_verified_solution': (known / verified) if known is not None and verified else None,
                 'acquisition_usd': sum(c['acquisition_usd'] or 0 for c in chosen),
                 'activation': {**{k: sum(c['activation'] == k for c in chosen)
                                   for k in ('eligible-reuse', 'direct-answer', 'no-applicable-artifact',
                                             'invoked-not-in-answer', 'available-not-invoked', 'no-answer', 'stateless')},
                                'correct-refusal': sum(c['correct_refusal'] for c in chosen)},
                 'tasks_with_refusals': sum(bool(c['refused']) for c in chosen),
                 # Reuse read from each task's own code (source-attributed), and count error.
                 'model_directed': sum(c['model_directed'] for c in chosen),
                 'value_in_answer': sum(c['value_in_answer'] for c in chosen),
                 'count_tasks': sum(c['asked_label'] is not None for c in chosen),
                 'count_log_error': _mean([c['count_log_error'] for c in chosen if c['asked_label'] is not None])})
    breakeven = {}
    for name, t in trajectories.items():
        if t['arm'] != 'A':
            base = trajectories.get(f"A-s{t['seed']}")
            if base and t['complete'] and base['complete']:
                net, first = 0.0, None
                for mine, theirs in zip(t['cases'], base['cases']):
                    net += (theirs['total_usd'] or 0) - (mine['total_usd'] or 0)
                    first = (first or mine['position']) if net >= 0 else None
                breakeven[name] = first
    new_records = output / 'new-records.json'
    endpoint = json.loads(new_records.read_text()) if new_records.is_file() else {'status': 'not computed: run trajectory-new-records'}
    require(endpoint.get('suite_sha256', manifest['suite_sha256']) == manifest['suite_sha256'], 'new-records.json is for another suite')
    # Count error split by whether the version in force decides the asked label (new-records step).
    decides = {(name, c['position']): c.get('decides_asked_label')
               for name, t in endpoint.get('trajectories', {}).items() if t.get('complete') for c in t['cases']}
    for name, t in trajectories.items():
        for c in t['cases']:
            c['decides_asked_label'] = decides.get((name, c['position']))
    split = {}
    for name, t in trajectories.items():
        for c in t['cases']:
            if c['family'] == 'F1' and c['asked_label'] is not None:
                key = {True: 'decides', False: 'does_not'}.get(c['decides_asked_label'], 'no_library')
                split.setdefault(t['arm'], {}).setdefault(key, []).append(c['count_log_error'])
    count_error_split = {arm: {k: {'tasks': len(v), 'answered': sum(x is not None for x in v), 'mean_log_error': _mean(v)}
                               for k, v in by.items()} for arm, by in split.items()}
    return {'schema': 'thesis-trajectory-report-v1', 'suite_sha256': manifest['suite_sha256'], 'model_calls': 0,
            'fallback_accounting': 'task inference includes every root and child call, including fallback on unresolved records',
            'trajectories': trajectories, 'arms': arms, 'break_even_position': breakeven, 'new_record_endpoint': endpoint,
            'f1_count_log_error_by_decidability': count_error_split,
            'reuse_measure': ('model_directed / value_in_answer: source-attributed from the root code and results; '
                              'activation keeps the eligible-reuse heuristic, which misses answers the model types')}
