import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from benchmark import line_process
from benchmark.line_process import LineProcess


class LineProcessCloseTests(unittest.TestCase):
    def test_group_that_exits_between_poll_and_kill_is_confirmed_closed(self):
        # The ten-case rerun stopped on this race: the helper exited after
        # poll(), and killpg on the exited group raised EPERM on macOS.
        for error in (PermissionError(1, 'Operation not permitted'), ProcessLookupError(3, 'No such process')):
            peer = LineProcess([sys.executable, '-c', 'import sys; sys.stdin.read()'])
            def exit_then_fail(pid, sig):
                peer.process.stdin.close()
                peer.process.wait(timeout=5)
                raise error
            with patch.object(peer.process, 'poll', return_value=None), \
                 patch.object(line_process.os, 'killpg', side_effect=exit_then_fail):
                peer.close()
            self.assertIsNotNone(peer.process.returncode)

    def test_unconfirmed_exit_still_fails_cleanup(self):
        peer = LineProcess([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            with patch.object(line_process.os, 'killpg', side_effect=PermissionError(1, 'Operation not permitted')), \
                 patch.object(peer.process, 'wait', side_effect=subprocess.TimeoutExpired('helper', 5)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    peer.close()
        finally:
            os.killpg(peer.process.pid, 9)
            peer.process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
