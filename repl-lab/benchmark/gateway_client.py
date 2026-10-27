"""Host-only asynchronous transport through the existing durable Clojure gateway.

Provider credentials are read only after explicit API authorization. No worker
receives them. Fixture transports exercise this same admission/completion path.
"""
from concurrent.futures import Future, ThreadPoolExecutor
import json
import os
from pathlib import Path
from queue import Queue, Empty
import threading
import time
import urllib.request
import uuid

from .line_process import LineProcess

ROOT = Path(__file__).resolve().parents[1]


class AnthropicMessagesTransport:
    endpoint = 'https://api.anthropic.com/v1/messages'
    mode = 'anthropic-api'

    def __init__(self, *, authorized=False, opener=None):
        if not authorized:
            raise ValueError('New Anthropic API inference needs explicit operator authorization; subscription approval is not API approval')
        self.opener = opener
        self.cancelled = threading.Event()

    def __call__(self, body, remaining):
        if self.cancelled.is_set():
            raise RuntimeError('Provider transport is cancelled')
        if self.opener is not None:
            # Test seam only; real traffic always uses the killable host process.
            return self._http(body, remaining)
        deadline = time.monotonic() + min(45, remaining)
        peer = LineProcess(['python3', '-m', 'benchmark.api_http_worker'], cwd=ROOT, limit=9 * 1024**2)
        try:
            peer.send({'body': body, 'timeout': min(45, remaining), 'transport': self.mode}, seconds=max(.001, deadline - time.monotonic()))
            while time.monotonic() < deadline and not self.cancelled.is_set():
                try:
                    reply = peer.read(seconds=min(.05, max(.001, deadline - time.monotonic())))
                except TimeoutError:
                    continue
                if 'response' not in reply:
                    raise RuntimeError('Provider transport failed')
                return reply['response']
            raise TimeoutError('Provider total response deadline')
        except Exception:
            raise RuntimeError('Provider transport failed; retain the full reservation') from None
        finally:
            # This terminates even a peer that drips headers/body indefinitely.
            peer.close()

    def cancel_pending(self):
        self.cancelled.set()

    def request_headers(self):
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise RuntimeError('Configure ANTHROPIC_API_KEY privately on the trusted host')
        return {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'x-api-key': key}

    def open_request(self, request, timeout):
        return urllib.request.urlopen(request, timeout=timeout)

    def _http(self, body, remaining):
        # Only called after a durable gateway admission, outside every worker.
        request = urllib.request.Request(self.endpoint, data=json.dumps(body).encode(), method='POST',
                                        headers=self.request_headers())
        deadline = time.monotonic() + min(45, remaining)
        try:
            with (self.opener or self.open_request)(request, timeout=max(0.1, min(45, remaining))) as response:
                chunks, size = [], 0
                while True:
                    if hasattr(response, 'isclosed') and response.isclosed():
                        break  # Content-Length read1 may close fp on the final byte.
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Provider response deadline')
                    left = max(.001, deadline - time.monotonic())
                    if hasattr(response, 'set_read_timeout'):
                        response.set_read_timeout(left)  # Fake-response test seam.
                    else:
                        response.fp.raw._sock.settimeout(left)
                    part = response.read1(65536)
                    if not part:
                        break
                    size += len(part)
                    if size > 4 * 1024**2:
                        raise ValueError('Provider response limit')
                    chunks.append(part)
                return {'status': response.status, 'content-type': response.headers.get_content_type(),
                        'body': b''.join(chunks).decode('utf-8')}
        except Exception as error:
            # Never forward raw request/headers/key-bearing transport exceptions.
            raise RuntimeError('Provider transport failed; retain the full reservation') from None


class ClaudeSubscriptionTransport(AnthropicMessagesTransport):
    mode = 'claude-oauth-subscription'

    def __init__(self, *, authorized=False, opener=None):
        if not authorized:
            raise ValueError('New subscription inference needs approval of its exact frozen plan; API approval does not apply')
        self.opener = opener
        self.cancelled = threading.Event()

    def request_headers(self):
        from .subscription_protocol import PUBLIC_HEADERS, load_access_token
        return {'Content-Type': 'application/json', **PUBLIC_HEADERS,
                'Authorization': 'Bearer ' + load_access_token()}

    def open_request(self, request, timeout):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args, **_kwargs):
                return None
        # A credential is only sent to the fixed Anthropic endpoint, never to a
        # redirect target. HTTP errors retain the admitted reservation.
        return urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)


class GatewayClient:
    """One task ledger; root, child, refinement and compaction share its caps."""
    def __init__(self, output, config, transport, *, evidence='FIXTURE', cwd=ROOT):
        self.output = Path(output)
        self.peer = LineProcess(['python3', 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(output), 'v2'], cwd=cwd)
        self.transport = transport
        self.deadline = time.monotonic() + config['limits']['wall-ms'] / 1000
        self.queue, self.pending = Queue(), {}
        self.pool = ThreadPoolExecutor(max_workers=config['limits']['concurrent-subagents'])
        self.closed, self.error = threading.Event(), None
        self.peer.send({'evidence': evidence, 'config': config})
        if self.peer.read(seconds=20).get('type') != 'gateway_ready':
            self.peer.close()
            raise RuntimeError('Gateway did not initialize')
        self.thread = threading.Thread(target=self._pump, name='gateway-io', daemon=True)
        self.thread.start()

    def submit(self, route, body):
        future, identifier = Future(), str(uuid.uuid4())
        if self.closed.is_set() or self.error:
            future.set_exception(RuntimeError('Gateway is closed'))
        else:
            self.queue.put(('invoke', identifier, route, body, future))
        return future

    def _transport(self, identifier, body):
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Task deadline')
            response = self.transport(body, remaining)
            self.queue.put(('response', identifier, response, False))
        except Exception:
            self.queue.put(('response', identifier, None, True))

    def _pump(self):
        try:
            while not self.closed.is_set():
                try:
                    command = self.queue.get_nowait()
                except Empty:
                    command = None
                if command:
                    if command[0] == 'invoke':
                        _, identifier, route, body, future = command
                        self.pending[identifier] = future
                        self.peer.send({'op': 'invoke', 'transport_id': identifier, 'route': route, 'body': body})
                    elif command[0] == 'response':
                        _, identifier, response, error = command
                        self.peer.send({'op': 'provider_response', 'transport_id': identifier,
                                        'response': response, 'transport_error': error})
                    else:
                        self.peer.send({'op': 'close'})
                try:
                    event = self.peer.read(seconds=0.05)
                except TimeoutError:
                    continue
                kind, identifier = event.get('type'), event.get('transport_id')
                if kind == 'provider_request':
                    self.pool.submit(self._transport, identifier, event['body'])
                elif kind in ('gateway_result', 'gateway_error'):
                    future = self.pending.pop(identifier, None)
                    if future and not future.done():
                        if kind == 'gateway_result':
                            future.set_result(event['response'])
                        else:
                            future.set_exception(RuntimeError(event['message']))
                elif kind == 'gateway_closed':
                    break
        except Exception as error:
            self.error = type(error).__name__
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError('Gateway closed with unresolved requests'))
            self.closed.set()

    def close(self):
        if hasattr(self.transport, 'cancel_pending'):
            self.transport.cancel_pending()
        self.queue.put(('close',))
        self.thread.join(timeout=15)
        self.peer.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
        # The Clojure finally block preserves unknown admissions on normal close.
        # A killed bridge must be recovered before producing results.
        if not (self.output / 'usage.jsonl').exists():
            import subprocess
            subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(self.output), 'recover'],
                           cwd=ROOT, check=True, capture_output=True, timeout=20)


class Relay:
    """Nonblocking container-event adapter; no child request is serialized by I/O."""
    def __init__(self, gateway, route, *, provider='anthropic-api'):
        self.gateway, self.route = gateway, route
        self.provider = provider
        self.pending, self.seen = {}, set()

    def __call__(self, event, remaining):
        if event.get('type') != 'external_provider_request':
            return None
        identifier = event.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in self.seen:
            raise ValueError('Missing or duplicate relay request ID')
        self.seen.add(identifier)
        body = event['body']
        if self.provider == 'claude-oauth-subscription':
            from .subscription_protocol import prepare_body, validate_public_headers
            if self.route == 'prime':
                validate_public_headers(event.get('public_headers'))
            body = prepare_body(body, native=self.route == 'prime')
        self.pending[identifier] = self.gateway.submit(self.route, body)
        return None

    def poll(self):
        replies = []
        for identifier, future in list(self.pending.items()):
            if future.done():
                del self.pending[identifier]
                try:
                    response = future.result()
                    reply = {'id': identifier, 'response': {k: response[k] for k in ('status', 'content-type', 'body')}}
                except Exception:
                    reply = {'id': identifier, 'error': 'Gateway rejected request or provider outcome is uncertain'}
                replies.append(json.dumps(reply).encode() + b'\n')
        return b''.join(replies)
