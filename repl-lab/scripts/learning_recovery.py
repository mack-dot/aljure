#!/usr/bin/env python3
"""Offline recovery only. This entry point has no inference/run command.

Every attempt has a new directory. Failed attempts, original plans, and live
results stay unchanged. Docker work is serial and uses bounded existing proofs.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'var/learning-recovery-20261102'
OLD = Path('/Users/mackianni/aljure-unblock-v4/repl-lab')
PILOT = WORK / 'pilot1b-source/repl-lab'
COMMIT = '98fc07c11177f499efd052c2ce1f784f9ccb5d9d'
BASE = 'clojure@sha256:e3faac65b894d75b36670204a6d6b69bee5efc81e4d2dda5f1eded996614836e'
SCI = 'sha256:40f003647de0937980e2be1f3e715e17741f4ee84fc39d915191ceab208c233f'
PRIME = 'sha256:f3e30aaa1ce3de92d381f05f597e84f9d1738a15c4a6453fdbd13bd4739446ad'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def snapshot(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.name.endswith(('-wal', '-shm'))}


class Recovery:
    def __init__(self, phase, config=None):
        self.phase = phase
        self.root = PILOT if phase == 'pilot1b' else ROOT
        if config is not None and phase != 'mechanism':
            raise ValueError('Custom proof config applies only to mechanism verification')
        self.config = Path(config).resolve() if config else ROOT / 'config/learning-development-sonnet.json'
        self.out = self.root / 'var/learning-recovery-attempts' / f'{phase}-{time.time_ns()}'
        self.out.mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items()
                    if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
        self.env.update(REPL_LAB_WORKER_IMAGE=SCI, REPL_LAB_PRIME_IMAGE=PRIME,
                        REPL_LAB_WORKER_OUTPUT_BYTES='65536')
        self.report = {'phase': phase, 'status': 'INCOMPLETE', 'model_calls': 0, 'authorized_inference': False,
                       'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'root': str(self.root), 'attempt': str(self.out), 'steps': []}

    def run(self, name, command, timeout=600):
        # Defense against accidentally adding a live command to this offline driver.
        if any(x in command for x in ('paired-run', 'trajectory-run', '--authorize-api-plan',
                                      '--authorize-subscription-plan', 'smoke', 'evolve')):
            raise ValueError('Inference is forbidden in the recovery driver')
        if shutil.disk_usage(self.root).free < 6 * 2**30:
            raise RuntimeError('Host free disk is below the 6 GiB floor')
        print(name, flush=True)
        started = time.monotonic()
        with (self.out / f'{name}.log').open('xb') as log:
            result = subprocess.run(command, cwd=self.root, env=self.env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        self.report['steps'].append({'name': name, 'command': command, 'exit_code': result.returncode,
                                     'seconds': round(time.monotonic() - started, 3)})
        write(self.out / 'report.json', self.report)
        if result.returncode:
            raise RuntimeError(f'{name} failed; preserve {self.out / (name + ".log")}')
        return (self.out / f'{name}.log').read_text()

    def proofs(self, config, *, reuse=False):
        previous = self.out / 'previous-proofs'
        previous.mkdir()
        for path in (self.root / 'var').glob('*proof*.json'):
            shutil.copy2(path, previous / path.name)
        self.run('isolation', ['python3', 'scripts/isolation.py', 'test'])
        for mode in ('contract', 'artifacts', 'acquisition'):
            self.run('sci-' + mode, ['python3', 'scripts/clj.py', '-m', 'repl-lab.sci-contract'] +
                     ([] if mode == 'contract' else [mode]))
        self.run('prime-isolation', ['python3', '-m', 'benchmark.prime.isolation'])
        self.run('subscription-relay', ['python3', '-m', 'benchmark', 'paired-relay-fixture',
                 '--provider', 'claude-oauth-subscription', '--config', str(config),
                 '--out', str(self.out / 'subscription-relay')], timeout=1200)
        if reuse:
            self.run('reuse-relay', ['python3', '-m', 'benchmark', 'reuse-fixture',
                     '--provider', 'claude-oauth-subscription', '--config', str(config),
                     '--out', str(self.out / 'reuse-relay')], timeout=1200)
        else:
            self.run('acquisition-relay', ['python3', '-m', 'benchmark', 'trajectory-acquisition-fixture',
                     '--provider', 'claude-oauth-subscription', '--config', str(config),
                     '--out', str(self.out / 'acquisition-relay')], timeout=1800)
        current = self.out / 'proofs'
        current.mkdir()
        for name in ('isolation', 'sci-contract', 'artifact-path', 'acquisition', 'prime-isolation',
                     'subscription-relay', 'reuse-relay' if reuse else 'acquisition-relay'):
            path = self.root / f'var/{name}-proof.json'
            shutil.copy2(path, current / path.name)

    def pilot1b(self):
        head = self.run('source', ['git', 'rev-parse', 'HEAD']).strip()
        if head != COMMIT:
            raise ValueError('Pilot 1b recovery needs the exact original source commit')
        history = OLD / 'var/reuse-pilot-1b'
        before = snapshot(history)
        write(self.out / 'historical-files-before.json', before)
        self.run('build', ['docker', 'build', '-f', 'worker/Dockerfile', '--build-arg', 'BASE_IMAGE=' + BASE,
                          '-t', 'repl-lab-worker:pilot1b-recovery-20261102', '.'], timeout=1800)
        image = self.run('image', ['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                  'repl-lab-worker:pilot1b-recovery-20261102']).strip()
        if len(image) != 71 or not image.startswith('sha256:'):
            raise ValueError('Invalid worker identity')
        self.env['REPL_LAB_WORKER_IMAGE'] = image
        archive = self.out / 'worker-image.tar'
        self.run('archive', ['docker', 'image', 'save', '-o', str(archive), image], timeout=600)
        write(self.out / 'image-seal.json', {'image': image, 'base': BASE, 'source_commit': head,
                                           'archive': str(archive), 'sha256': digest(archive)})
        (self.root / 'var/worker.env').write_text('export REPL_LAB_WORKER_IMAGE=' + image + '\n')
        (self.root / 'var/prime-worker.env').write_text('export REPL_LAB_PRIME_IMAGE=' + PRIME + '\n')
        suite = self.root / 'var/official/reuse-pilot-1b-validation-v1'
        if not suite.exists():
            shutil.copytree(OLD / 'var/official/reuse-pilot-1b-validation-v1', suite)
        for arm in 'SDPR':
            config = json.loads((self.root / f'config/reuse-pilot-1b-{arm}.json').read_text())
            config['execution_images']['sci'] = image
            write(self.out / f'config-{arm}.json', config)
        self.proofs(self.out / 'config-P.json', reuse=True)
        for arm in 'SDPR':
            plan = self.out / f'plan-{arm}.json'
            self.run('plan-' + arm, ['python3', '-m', 'benchmark', 'paired-plan', '--suite', str(suite),
                     '--config', str(self.out / f'config-{arm}.json'), '--out', str(plan)])
            self.run('preflight-' + arm, ['python3', '-m', 'benchmark', 'paired-preflight',
                     '--suite', str(suite), '--plan', str(plan)])
        after = snapshot(history)
        self.report.update(image=image, historical_files_checked=len(before), historical_files_unchanged=before == after,
                           plans={a: json.loads((self.out / f'plan-{a}.json').read_text())['plan_sha256'] for a in 'SDPR'})
        if before != after:
            raise RuntimeError('Historical Pilot 1b files changed during recovery')

    def mechanism(self):
        self.proofs(self.config)

    def execute(self):
        try:
            getattr(self, self.phase)()
            self.report['status'] = 'PASSED'
        except Exception as error:
            self.report.update(status='FAILED', failure=f'{type(error).__name__}: {error}')
        write(self.out / 'report.json', self.report)
        print(json.dumps(self.report, indent=2), flush=True)
        return 0 if self.report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('pilot1b', 'mechanism'))
    parser.add_argument('--config', type=Path, help='Mechanism fixture configuration; no inference command exists')
    args = parser.parse_args()
    sys.exit(Recovery(args.phase, args.config).execute())
