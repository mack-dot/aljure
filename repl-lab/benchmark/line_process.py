"""Bounded JSON-lines transport for a trusted controller subprocess."""
import json
import os
import selectors
import signal
import subprocess
import time


class LineProcess:
    def __init__(self, arguments, *, cwd=None, limit=5 * 1024**2):
        self.process = subprocess.Popen(arguments, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.output = bytearray()
        self.stderr = bytearray()
        self.limit = limit
        for stream, label in [(self.process.stdout, 'stdout'), (self.process.stderr, 'stderr')]:
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, label)
        os.set_blocking(self.process.stdin.fileno(), False)

    def pump(self, deadline, pending=b''):
        if time.monotonic() >= deadline:
            raise TimeoutError('Controller JSON-lines deadline')
        sent = 0
        for key, _ in self.selector.select(min(0.1, max(0, deadline - time.monotonic()))):
            if key.data == 'stdin':
                try:
                    sent = os.write(key.fd, pending[:4096])
                except BlockingIOError:
                    pass
            else:
                data = os.read(key.fd, 65536)
                if not data:
                    self.selector.unregister(key.fileobj)
                    if key.data == 'stdout':
                        raise EOFError('Controller closed its output')
                    continue
                target = self.output if key.data == 'stdout' else self.stderr
                if len(self.output) + len(self.stderr) + len(data) > self.limit:
                    raise ValueError('Controller JSON-lines output limit')
                target.extend(data)
        return sent

    def send(self, value, seconds=10):
        data = json.dumps(value).encode() + b'\n'
        if len(data) > self.limit:
            raise ValueError('Controller JSON-lines input limit')
        deadline = time.monotonic() + seconds
        self.selector.register(self.process.stdin, selectors.EVENT_WRITE, 'stdin')
        try:
            offset = 0
            while offset < len(data):
                offset += self.pump(deadline, data[offset:])
        finally:
            self.selector.unregister(self.process.stdin)

    def read(self, seconds=10):
        deadline = time.monotonic() + seconds
        while b'\n' not in self.output:
            self.pump(deadline)
        line, _, rest = self.output.partition(b'\n')
        self.output = bytearray(rest)
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
