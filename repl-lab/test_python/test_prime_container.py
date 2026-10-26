import io
import json
import sys
import tarfile
import unittest

from benchmark.prime.container import bounded_process, regular_files


class PrimeSupervisorTests(unittest.TestCase):
    def test_timeout_includes_a_child_that_never_reads_input(self):
        result = bounded_process([sys.executable, '-c', 'import time; time.sleep(10)'],
                                 b'x' * 65536, seconds=0.2)
        self.assertEqual(result['failure'], 'wall-time-limit')
        self.assertLess(result['wall_ms'], 3000)

    def test_output_overflow_is_bounded_while_draining(self):
        result = bounded_process([sys.executable, '-c', "print('x' * 200000)"], max_output=4096, seconds=2)
        self.assertEqual(result['failure'], 'output-limit')
        self.assertLessEqual(len(result['stdout']) + len(result['stderr']), 4096)

    def test_completion_marker_is_a_top_level_record(self):
        source = ("import json,time; print(json.dumps({'type':'tool_result','value':{'type':'done'}}), flush=True); "
                  "print(json.dumps({'type':'done','native_exit_code':0}), flush=True); time.sleep(10)")
        result = bounded_process([sys.executable, '-c', source], seconds=2, completion_type='done')
        self.assertIsNone(result['failure'])
        self.assertEqual(result['completion'], {'type': 'done', 'native_exit_code': 0})
        self.assertEqual(len(result['stdout'].splitlines()), 2)

    def archive(self, name, content=b'data', link=False):
        target = io.BytesIO()
        with tarfile.open(fileobj=target, mode='w') as archive:
            item = tarfile.TarInfo(name)
            if link:
                item.type = tarfile.SYMTYPE
                item.linkname = '/etc/passwd'
                archive.addfile(item)
            else:
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
        return target.getvalue()

    def test_collection_reads_regular_data_without_restoring_executable_state(self):
        self.assertEqual(regular_files(self.archive('./answer.json', b'{"answer":42}')),
                         {'answer.json': b'{"answer":42}'})
        for name, link in [('../escape', False), ('/absolute', False), ('link', True)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                regular_files(self.archive(name, link=link))


if __name__ == '__main__':
    unittest.main()
