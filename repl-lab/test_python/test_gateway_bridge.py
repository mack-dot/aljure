"""Real controller-process tests. Scripted provider, no network or model calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benchmark.line_process import LineProcess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {'model': 'fixture-model', 'context-window': 1000, 'max-output': 100,
          'pinned-settings': {}, 'routes': ['prime/task'],
          'rates': {'input': 2, 'output': 10, 'cache-read': 0.2, 'cache-write-5m': 2.5, 'cache-write-1h': 4},
          'limits': {'calls': 8, 'tokens': 10000, 'usd': 1, 'wall-ms': 120000, 'concurrent-subagents': 2}}
REQUEST = {'model': 'fixture-model', 'messages': [{'role': 'user', 'content': 'Fixture'}], 'max_tokens': 100}


class BridgeTests(unittest.TestCase):
    def test_reserve_before_transport_and_recover_after_actual_process_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            command = [sys.executable, 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(out)]
            peer = LineProcess(command, cwd=ROOT)
            try:
                peer.send({'evidence': 'FIXTURE', 'config': CONFIG})
                self.assertEqual(peer.read()['type'], 'gateway_ready')
                for index in range(2):
                    peer.send({'op': 'invoke', 'route': 'prime/task', 'body': REQUEST})
                    self.assertEqual(peer.read()['type'], 'provider_request')
                    # Transport starts only after that admission frame.
                    body = {'id': 'fixture-' + str(index), 'model': 'fixture-model',
                            'usage': {'input_tokens': 10, 'output_tokens': 2}}
                    peer.send({'type': 'provider_response', 'response':
                               {'status': 200, 'content-type': 'application/json', 'body': json.dumps(body)}})
                    self.assertEqual(peer.read()['type'], 'gateway_result')
                peer.send({'op': 'invoke', 'route': 'prime/task', 'body': REQUEST})
                self.assertEqual(peer.read()['type'], 'provider_request')
                # Actual SIGKILL while the external provider outcome is uncertain.
            finally:
                peer.close()
            recovered = subprocess.run(command + ['recover'], cwd=ROOT, capture_output=True, text=True,
                                       timeout=20, check=True)
            report = json.loads(recovered.stdout)['report']
            self.assertEqual(report['status'], 'gateway-stopped')
            self.assertEqual(report['spent']['calls'], 2)
            self.assertEqual(report['reserved']['calls'], 1)
            rows = [json.loads(line) for line in (out / 'usage.jsonl').read_text().splitlines()]
            self.assertEqual(sum(row['status'] == 'unknown' for row in rows), 1)

    def test_nonreading_controller_and_output_flood_are_bounded(self):
        for source, value in [('import time; time.sleep(10)', 'x' * 100000),
                              ("print('x'*200000,flush=True)", None)]:
            peer = LineProcess([sys.executable, '-c', source], limit=110000)
            try:
                with self.assertRaises((TimeoutError, ValueError, EOFError)):
                    if value is not None:
                        peer.send(value, seconds=0.2)
                    else:
                        peer.read(seconds=0.2)
            finally:
                peer.close()


if __name__ == '__main__':
    unittest.main()
