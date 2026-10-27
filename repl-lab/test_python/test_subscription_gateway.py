"""Fake credentials and local HTTP only. No subscription/model requests."""
from concurrent.futures import Future
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request

from benchmark.gateway_client import ClaudeSubscriptionTransport, Relay
from benchmark import paired
from benchmark.subscription_protocol import (IDENTITY, PROVIDER, PUBLIC_HEADERS, SENTINEL,
                                             credential_status, load_access_token, prepare_body)

FAKE = 'sk-ant-oat-FAKE-UNIT-TEST-NOT-A-REAL-CREDENTIAL'


class SubscriptionGatewayTests(unittest.TestCase):
    def test_authorization_is_separate_and_precedes_credential_access(self):
        with patch('benchmark.subscription_protocol._credential_document') as read:
            with self.assertRaises(ValueError):
                ClaudeSubscriptionTransport()
            plan = {'config': {'provider': PROVIDER}, 'plan_sha256': 'frozen'}
            with patch('benchmark.paired.read_plan', return_value=(plan, {}, {})), patch('benchmark.paired.preflight') as preflight:
                with self.assertRaises(ValueError):
                    paired.run('unused', 'unused', 'unused', authorize_api_plan='frozen')
                with self.assertRaises(ValueError):
                    paired.run('unused', 'unused', 'unused', authorize_subscription_plan='wrong')
                with self.assertRaises(ValueError):
                    paired.run('unused', 'unused', 'unused', authorize_subscription_plan='frozen', authorize_api_plan='frozen')
                preflight.assert_not_called()
            read.assert_not_called()

    def test_private_file_shapes_expiry_and_no_api_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'private.json'
            path.touch(mode=0o600)
            env = {'REPL_LAB_CLAUDE_OAUTH_FILE': str(path), 'ANTHROPIC_API_KEY': 'API-MUST-NOT-BE-USED'}
            shapes = [{'anthropic': {'type': 'oauth', 'access': FAKE, 'refresh': 'unused', 'expires': 200000}},
                      {'claudeAiOauth': {'accessToken': FAKE, 'refreshToken': 'unused', 'expiresAt': 200000,
                                         'scopes': ['user:inference']}}]
            for shape in shapes:
                path.write_text(json.dumps(shape))
                self.assertEqual(load_access_token(environ=env, now=100), FAKE)
                status = credential_status(environ=env, now=100)
                self.assertEqual(status['expires_at_ms'], 200000)
                self.assertNotIn(FAKE, json.dumps(status))
                with self.assertRaises(RuntimeError):
                    load_access_token(environ=env, now=150)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                load_access_token(environ=env, now=100)
            with self.assertRaises(RuntimeError):
                load_access_token(environ={'ANTHROPIC_API_KEY': 'API-MUST-NOT-BE-USED'}, now=100)

    def test_keychain_is_explicit_bounded_read_only_and_errors_are_redacted(self):
        env = {'REPL_LAB_CLAUDE_KEYCHAIN_SERVICE': 'FAKE-SERVICE', 'REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT': 'FAKE-ACCOUNT'}
        with patch('benchmark.line_process.LineProcess') as process:
            process.return_value.read.return_value = {'claudeAiOauth': {'accessToken': FAKE, 'expiresAt': 200000}}
            self.assertEqual(load_access_token(environ=env, now=100), FAKE)
            process.assert_called_once_with(['/usr/bin/security', 'find-generic-password', '-a', 'FAKE-ACCOUNT',
                                             '-s', 'FAKE-SERVICE', '-w'], limit=1024**2)
            process.return_value.read.assert_called_once_with(seconds=5)
            process.return_value.close.assert_called_once()
            process.return_value.read.side_effect = RuntimeError(FAKE)
            with self.assertRaises(RuntimeError) as error:
                load_access_token(environ=env, now=100)
            self.assertNotIn(FAKE, str(error.exception))
            for invalid in ({}, {**env, 'REPL_LAB_CLAUDE_OAUTH_FILE': 'conflicting'},
                            {'REPL_LAB_CLAUDE_KEYCHAIN_SERVICE': 'FAKE-SERVICE'}):
                process.reset_mock()
                with self.assertRaises(RuntimeError):
                    load_access_token(environ=invalid, now=100)
                process.assert_not_called()

    def test_oauth_never_accepts_api_keys_sentinel_or_missing_scope(self):
        for access, scopes in [('sk-ant-api-fake', ['user:inference']), (SENTINEL, ['user:inference']),
                               (FAKE, []), (FAKE, ['user:profile'])]:
            with patch('benchmark.subscription_protocol._credential_document', return_value={
                    'claudeAiOauth': {'accessToken': access, 'expiresAt': 200000, 'scopes': scopes}}):
                with self.assertRaises(RuntimeError):
                    load_access_token(environ={}, now=100)

    def test_identity_headers_tools_and_signed_history_are_preserved(self):
        class Gateway:
            def __init__(self):
                self.bodies = []
            def submit(self, route, body):
                self.bodies.append((route, body))
                return Future()
        body = {'system': [{'type': 'text', 'text': IDENTITY, 'cache_control': {'type': 'ephemeral'}},
                           {'type': 'text', 'text': 'native system'}],
                'messages': [{'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'x', 'signature': 'FAKE-SIGNED'},
                                                              {'type': 'tool_use', 'id': 'x', 'name': 'Read', 'input': {}}]}],
                'tools': [{'name': 'Read', 'input_schema': {'type': 'object'}}], 'stream': True}
        before = copy.deepcopy(body)
        gateway = Gateway()
        relay = Relay(gateway, 'prime', provider=PROVIDER)
        relay({'type': 'external_provider_request', 'id': 'native', 'body': body, 'public_headers': PUBLIC_HEADERS}, 10)
        self.assertEqual(gateway.bodies, [('prime', before)])
        self.assertEqual(body, before)
        self.assertIs(prepare_body(body, native=True), body)
        for bad in ({}, {**PUBLIC_HEADERS, 'authorization': FAKE}, {**PUBLIC_HEADERS, 'user-agent': 'other'}):
            with self.assertRaises(ValueError):
                Relay(gateway, 'prime', provider=PROVIDER)({'type': 'external_provider_request', 'id': 'bad',
                                                          'body': body, 'public_headers': bad}, 10)
        self.assertEqual(len(gateway.bodies), 1)
        plain = {'messages': [{'role': 'user', 'content': 'task'}], 'stream': False}
        Relay(gateway, 'aljure', provider=PROVIDER)({'type': 'external_provider_request', 'id': 'aljure', 'body': plain}, 10)
        self.assertEqual(gateway.bodies[-1][1]['system'], [{'type': 'text', 'text': IDENTITY}])
        self.assertNotIn('system', plain)

    def test_local_http_preserves_json_and_sse_and_uses_bearer_only(self):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                observed.append(({k.lower(): v for k, v in self.headers.items()}, json.loads(body)))
                data = b'event: ping\ndata: {}\n\n' if self.path == '/stream' else b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream' if self.path == '/stream' else 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        try:
            with patch('benchmark.subscription_protocol.load_access_token', return_value=FAKE), patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'NEVER-USE'}):
                for stream in (False, True):
                    body = prepare_body({'model': 'claude-sonnet-5-5', 'messages': [], 'stream': stream})
                    def opener(request, timeout):
                        self.assertEqual(request.full_url, 'https://api.anthropic.com/v1/messages')
                        local = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + ('/stream' if stream else '/json'),
                                                       data=request.data, headers=dict(request.header_items()), method='POST')
                        return urllib.request.urlopen(local, timeout=timeout)
                    value = ClaudeSubscriptionTransport(authorized=True, opener=opener)(body, 2)
                    self.assertEqual(value['body'], 'event: ping\ndata: {}\n\n' if stream else '{"ok":true}')
                    headers, sent = observed[-1]
                    self.assertEqual(sent, body)
                    self.assertEqual(headers['authorization'], 'Bearer ' + FAKE)
                    self.assertNotIn('x-api-key', headers)
                    self.assertEqual({k: headers[k] for k in PUBLIC_HEADERS}, PUBLIC_HEADERS)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_oauth_redirect_cannot_forward_credentials(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/must-not-receive-credential')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        try:
            request = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + '/redirect',
                                             headers={'Authorization': 'Bearer ' + FAKE})
            with self.assertRaises(urllib.error.HTTPError):
                ClaudeSubscriptionTransport(authorized=True).open_request(request, 2)
            self.assertEqual(seen, ['/redirect'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
