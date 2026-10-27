"""Fixed native Prime HTTP-to-stdio relay. No credentials or outside network.

The parent controls the sole provider route. Native tools, skills, subagents,
refinement and compaction remain available; every Messages request crosses it.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

request = json.loads(sys.stdin.buffer.readline(2 * 1024**2 + 1))
if request.get('mode') != 'external-gateway' or set(request) != {'mode', 'model', 'context_window', 'max_output', 'prompt', 'context', 'rates', 'fixture_session_commands', 'auth_mode'}:
    raise ValueError('Explicit external gateway request required')
if request['auth_mode'] not in ('anthropic-api', 'claude-oauth-subscription'):
    raise ValueError('Unsupported host transport')
oauth = request['auth_mode'] == 'claude-oauth-subscription'
sentinel = 'sk-ant-oat-ALJURE-OFFLINE-SENTINEL-NOT-A-CREDENTIAL'
if request['fixture_session_commands'] not in ([], ['/compact', '/refine']):
    raise ValueError('Only the fixed offline lifecycle control may append session commands')
if any('API_KEY' in k or 'TOKEN' in k or k == 'PRIME_AGENT_FAUX_SCRIPT' for k in os.environ):
    raise ValueError('Credentials or fixture provider entered the native worker')
Path('/work/agent').mkdir(exist_ok=True)
Path('/work/sessions').mkdir(exist_ok=True)
Path('/work/context.txt').write_text(request['context'])
if request['fixture_session_commands']:
    # Short trusted fixture only: retain one token so /compact has an old prefix
    # to summarize. Production comparisons use the untouched native defaults.
    Path('/work/agent/settings.json').write_text(json.dumps({'compaction': {'keepRecentTokens': 1}}))
lock, pending = threading.Lock(), {}
deadline = time.monotonic() + 120


def emit(value):
    with lock:
        print(json.dumps(value), flush=True)


def replies():
    for line in sys.stdin:
        value = json.loads(line)
        with lock:
            waiting = pending.get(value.get('id'))
            if waiting:
                waiting['reply'] = value
                waiting['event'].set()


threading.Thread(target=replies, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        if self.path != '/v1/messages' or not 0 < size <= 1048576:
            self.send_error(400)
            return
        self.connection.settimeout(10)
        body = json.loads(self.rfile.read(size))
        public_headers = None
        if oauth:
            if self.headers.get('Authorization') != 'Bearer ' + sentinel or self.headers.get('x-api-key'):
                self.send_error(400)
                return
            public_headers = {key: self.headers.get(key) for key in
                              ('anthropic-version', 'accept', 'anthropic-dangerous-direct-browser-access',
                               'anthropic-beta', 'user-agent', 'x-app')}
        identifier = str(uuid.uuid4())
        waiting = {'event': threading.Event()}
        with lock:
            pending[identifier] = waiting
        try:
            event = {'type': 'external_provider_request', 'id': identifier, 'body': body}
            if oauth:
                event['public_headers'] = public_headers
            emit(event)
            if not waiting['event'].wait(max(0, deadline - time.monotonic())):
                self.send_error(504)
                return
            reply = waiting['reply']
            if 'response' not in reply:
                self.send_error(429)
                return
            response = reply['response']
            encoded = response['body'].encode()
            if len(encoded) > 4 * 1024**2:
                self.send_error(502)
                return
            self.send_response(response['status'])
            self.send_header('Content-Type', response['content-type'])
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            self.wfile.flush()
        finally:
            with lock:
                pending.pop(identifier, None)


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
models = {'providers': {'benchmark-gateway': {
    'api': 'anthropic-messages', 'baseUrl': 'http://127.0.0.1:' + str(server.server_port),
    'apiKey': sentinel if oauth else 'gateway-placeholder-not-a-provider-credential',
    'models': [{'id': request['model'], 'name': request['model'], 'reasoning': True, 'input': ['text'],
                'contextWindow': request['context_window'], 'maxTokens': request['max_output'],
                'thinkingLevelMap': {'off': None, 'minimal': None, 'low': None, 'medium': 'medium'},
                'cost': {'input': request['rates']['input'], 'output': request['rates']['output'],
                         'cacheRead': request['rates']['cache-read'], 'cacheWrite': request['rates']['cache-write-5m']}}]}}}
Path('/work/agent/models.json').write_text(json.dumps(models))
try:
    process = subprocess.Popen(['/usr/local/bin/prime-agent', '--mode', 'json', '--print',
                                '--provider', 'benchmark-gateway', '--model', request['model'], '--thinking', 'medium',
                                '--session-dir', '/work/sessions', request['prompt'], *request['fixture_session_commands']],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
    with Path('/work/native.jsonl').open('w') as native:
        for line in process.stdout:
            native.write(line)
            native.flush()
            # A tool's printed JSON cannot impersonate a trusted relay frame.
            try:
                emit({'type': 'native_event', 'event': json.loads(line)})
            except ValueError:
                emit({'type': 'native_output', 'text': line})
    status = process.wait()
finally:
    server.shutdown()
    server.server_close()
emit({'type': 'external_agent_complete', 'native_exit_code': status})
time.sleep(30)  # Bounded collection window; the host owns container removal.
