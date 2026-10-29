"""In-container offline HTTP provider fixture. No external network or credentials.

This exercises Prime's actual Anthropic transport, not its faux provider. The
scripted server and its files are fixture diagnostics, not a trusted live gateway.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

request = json.loads(sys.stdin.buffer.readline(65537))
if set(request) != {"mode", "prompt", "context", "script"} or request["mode"] != "http-fixture":
    raise ValueError("Only explicit offline HTTP fixtures are allowed")
for key in tuple(os.environ):
    if "API_KEY" in key or "TOKEN" in key or key == "PRIME_AGENT_FAUX_SCRIPT":
        raise ValueError("Credentials or faux provider must not enter this fixture")

MODEL = "fixture-anthropic-v1"
Path('/work/agent').mkdir(exist_ok=True)
Path('/work/sessions').mkdir(exist_ok=True)
Path('/work/context.json').write_text(json.dumps(request['context']))
lock = threading.Lock()
counters = {"root": 0, "aggregate": 0}
receipts = []


def frames(content, call_id):
    tool = isinstance(content, dict)
    block = ({"type": "tool_use", "id": "tool_" + call_id, "name": "ipython", "input": {}} if tool
             else {"type": "text", "text": ""})
    delta = ({"type": "input_json_delta", "partial_json": json.dumps(content['content'][0]['arguments'])} if tool
             else {"type": "text_delta", "text": content})
    usage = {"input_tokens": 1000, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    # Follow the documented API shape: initial usage nested inside message;
    # final delta contains cumulative output usage, not a new input charge.
    events = [
        {"type": "message_start", "message": {"id": call_id, "type": "message", "role": "assistant",
            "model": MODEL, "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {**usage, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": block},
        {"type": "content_block_delta", "index": 0, "delta": delta},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 20}},
        {"type": "message_stop"}]
    body = ''.join('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n' for event in events).encode()
    return body, usage


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        if self.path != '/v1/messages' or not 0 < size <= request.get('request_bytes', 1048576):
            self.send_error(400)
            return
        self.connection.settimeout(10)
        body = json.loads(self.rfile.read(size))
        if body.get('model') != MODEL or body.get('stream') is not True:
            self.send_error(400)
            return
        first_user = next((row.get('content') for row in body['messages'] if row.get('role') == 'user'), '')
        lane = 'aggregate' if 'Aggregate /work/child-context.json' in json.dumps(first_user) else 'root'
        with lock:
            index = counters[lane]
            counters[lane] += 1
            if sum(counters.values()) > 8:
                self.send_error(429)
                return
            script = request['script'] if lane == 'root' else request['script']['children'][lane]
            responses = script['responses']
            response = responses[min(index, len(responses) - 1)]
            call_id = 'fixture_' + lane + '_' + str(index)
            wire, usage = frames(response, call_id)
            receipts.append({'call_id': call_id, 'lane': lane, 'request': body, 'response_body': wire.decode(),
                             'usage': usage, 'evidence': 'FIXTURE', 'model_calls': 0})
            Path('/work/http-receipts.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in receipts))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(wire)))
        self.send_header('request-id', call_id)
        self.end_headers()
        self.wfile.write(wire)
        self.wfile.flush()


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
models = {'providers': {'fixture-http': {
    'api': 'anthropic-messages', 'baseUrl': 'http://127.0.0.1:' + str(server.server_port),
    'apiKey': 'fixture-no-credential',
    'models': [{'id': MODEL, 'name': MODEL, 'reasoning': False, 'input': ['text'],
                'contextWindow': 200000, 'maxTokens': 4096,
                'cost': {'input': 2, 'output': 10, 'cacheRead': 0.2, 'cacheWrite': 2.5}}]}}}
Path('/work/agent/models.json').write_text(json.dumps(models))
try:
    status = subprocess.run(['/usr/local/bin/prime-agent', '--mode', 'json', '--print',
                             '--provider', 'fixture-http', '--model', MODEL,
                             '--session-dir', '/work/sessions', request['prompt']], stdin=subprocess.DEVNULL).returncode
finally:
    server.shutdown()
    server.server_close()
print(json.dumps({'type': 'aljure_fixture_complete', 'native_exit_code': status}), flush=True)
time.sleep(30)
