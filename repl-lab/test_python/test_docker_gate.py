"""V7 gate: refuse an arm unless Docker Desktop is running with no pending
restart and both pinned images present; classify a dead container explicitly.

Fixture only: a fake command runner, no Docker or provider calls.
"""

import subprocess
import unittest

from benchmark import paired

IMAGES = ['sha256:prime', 'sha256:sci']


def fake_run(status='running', session='session-a', restart='false', present=('sha256:prime', 'sha256:sci')):
    def run(argv, **_):
        if argv[:3] == ['docker', 'desktop', 'status']:
            out = f'Name                Value\nStatus              {status}\nSessionID           {session}\n'
            return subprocess.CompletedProcess(argv, 0, stdout=out)
        if argv[0] == 'curl':
            return subprocess.CompletedProcess(argv, 0, stdout=restart)
        if argv[:3] == ['docker', 'image', 'inspect']:
            return subprocess.CompletedProcess(argv, 0 if argv[3] in present else 1)
        raise AssertionError(argv)
    return run


class DockerGateTest(unittest.TestCase):
    def test_ready_docker_has_no_blockers(self):
        state = paired.docker_state(IMAGES, run=fake_run())
        self.assertEqual(state['session'], 'session-a')
        self.assertIs(state['restart_pending'], False)
        self.assertEqual(paired.docker_blockers(state), [])

    def test_each_unsafe_state_blocks_the_arm(self):
        cases = {
            'stopped': fake_run(status='stopped'),
            'pending restart': fake_run(restart='true'),
            'unknown restart': fake_run(restart=''),
            'missing native image': fake_run(present=('sha256:sci',)),
            'missing sci image': fake_run(present=('sha256:prime',)),
        }
        for name, run in cases.items():
            with self.subTest(name):
                self.assertTrue(paired.docker_blockers(paired.docker_state(IMAGES, run=run)))

    def test_unavailable_tools_block_instead_of_passing(self):
        def broken(argv, **_):
            raise FileNotFoundError(argv[0])
        state = paired.docker_state(IMAGES, run=broken)
        self.assertEqual(len(paired.docker_blockers(state)), 4)

    def test_a_restart_changes_the_session(self):
        before = paired.docker_state(IMAGES, run=fake_run(session='session-a'))
        after = paired.docker_state(IMAGES, run=fake_run(session='session-b'))
        self.assertNotEqual(before['session'], after['session'])


class ArmStatusTest(unittest.TestCase):
    def test_v6_dead_container_is_classified_not_crashed(self):
        # V6 native arm: completion None, exit 125; the old code raised AttributeError.
        self.assertEqual(paired.arm_status({'completion': None, 'exit_code': 125, 'failure': None}, False),
                         ('error', 'NativeCompletionMissing'))

    def test_completed_timeout_and_harness_error(self):
        done = {'completion': {'native_exit_code': 0}, 'failure': None}
        self.assertEqual(paired.arm_status(done, True), ('completed', None))
        self.assertEqual(paired.arm_status(done, False), ('error', None))
        self.assertEqual(paired.arm_status({'completion': None, 'failure': 'wall-time-limit'}, False), ('timeout', None))
        self.assertEqual(paired.arm_status({'completion': {'native_exit_code': 2}, 'failure': None}, False), ('error', None))


if __name__ == '__main__':
    unittest.main()
