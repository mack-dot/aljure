"""Host-only asynchronous transport through the existing durable Clojure gateway.

Provider credentials are read only after explicit API authorization. No worker
receives them. Fixture transports exercise this same admission/completion path.
"""
from concurrent.futures import Future, ThreadPoolExecutor
import base64
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
from queue import Queue, Empty
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid

from .line_process import LineProcess

ROOT = Path(__file__).resolve().parents[1]
RESPONSE_LIMIT = 4 * 1024**2


def transport_detail(value):
    """Whitelist diagnostic data. Never persist exception text or HTTP headers."""
    result = {}
    for key, allowed in {
        'stage': {'host', 'credentials', 'connect', 'response', 'cleanup'},
        'category': {'deadline', 'cancelled', 'dns', 'tls', 'network', 'incomplete',
                     'decode', 'response-limit', 'credential', 'worker', 'transport', 'cleanup'},
        'content_type': {'application/json', 'text/event-stream', 'other'},
    }.items():
        if isinstance(value.get(key), str) and value[key] in allowed:
            result[key] = value[key]
    for key in ('elapsed_ms', 'response_bytes', 'task_elapsed_ms', 'task_remaining_ms'):
        item = value.get(key)
        if type(item) in (int, float) and math.isfinite(item) and item >= 0:
            result[key] = item
    status = value.get('http_status')
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    for key, pattern in [('provider_request_id', r'req_[A-Za-z0-9_-]{1,120}'),
                         ('response_sha256', r'[0-9a-f]{64}')]:
        item = value.get(key)
        if isinstance(item, str) and re.fullmatch(pattern, item):
            result[key] = item
    return result


class ProviderTransportFailure(RuntimeError):
    def __init__(self, detail, response=None):
        self.detail = transport_detail(detail)
        self.response = response
        super().__init__('Provider transport failed; retain the full reservation')


class GatewayCleanupFailure(RuntimeError):
    pass


def failure_category(error, stage):
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    if isinstance(error, TimeoutError):
        return 'deadline'
    if isinstance(error, socket.gaierror):
        return 'dns'
    if isinstance(error, ssl.SSLError):
        return 'tls'
    if isinstance(error, http.client.IncompleteRead):
        return 'incomplete'
    if isinstance(error, UnicodeDecodeError):
        return 'decode'
    if stage == 'credentials':
        return 'credential'
    return 'network' if isinstance(error, OSError) else 'transport'


class AnthropicMessagesTransport:
    endpoint = 'https://api.anthropic.com/v1/messages'
    mode = 'anthropic-api'

    def __init__(self, *, authorized=False, opener=None):
        if not authorized:
            raise ValueError('New Anthropic API inference needs explicit operator authorization; subscription approval is not API approval')
        self.opener = opener
        self.cancelled = threading.Event()

    def __call__(self, body, remaining):
        return self.request(body, remaining)

    def request(self, body, remaining, observer=None):
        started = time.monotonic()
        deadline = started + remaining
        latest = {'stage': 'host'}
        if self.cancelled.is_set():
            raise ProviderTransportFailure({**latest, 'category': 'cancelled'})
        if remaining <= 0:
            raise ProviderTransportFailure({**latest, 'category': 'deadline'})
        if self.opener is not None:
            # Test seam only; real traffic always uses the killable host process.
            return self._http(body, remaining, observer=observer)
        peer = LineProcess(['python3', '-m', 'benchmark.api_http_worker'], cwd=ROOT, limit=32 * 1024**2)
        received = 0
        response_hash = hashlib.sha256()
        completed = None
        try:
            peer.send({'body': body, 'timeout': max(0, deadline - time.monotonic()), 'transport': self.mode},
                      seconds=max(.001, deadline - time.monotonic()))
            while time.monotonic() < deadline and not self.cancelled.is_set():
                try:
                    reply = peer.read(seconds=min(.05, max(.001, deadline - time.monotonic())))
                except TimeoutError:
                    continue
                if 'progress' in reply:
                    latest.update(transport_detail(reply['progress']))
                    if observer:
                        observer(transport_detail(latest), None)
                    continue
                if 'chunk' in reply:
                    chunk = base64.b64decode(reply['chunk'], validate=True)
                    received += len(chunk)
                    if received > RESPONSE_LIMIT:
                        raise ProviderTransportFailure({**latest, 'category': 'response-limit'})
                    response_hash.update(chunk)
                    latest.update(response_bytes=received, response_sha256=response_hash.hexdigest())
                    if observer:
                        observer({}, chunk)
                    continue
                if 'error' in reply:
                    raise ProviderTransportFailure(reply['error'])
                if 'response' not in reply:
                    raise ProviderTransportFailure({**latest, 'category': 'worker'})
                completed = reply['response']
                return completed
            raise ProviderTransportFailure({**latest, 'category': 'cancelled' if self.cancelled.is_set() else 'deadline'})
        except ProviderTransportFailure as error:
            error.detail['elapsed_ms'] = (time.monotonic() - started) * 1000
            raise
        except Exception as error:
            raise ProviderTransportFailure({**latest, 'category': failure_category(error, latest['stage']),
                                            'elapsed_ms': (time.monotonic() - started) * 1000}) from None
        finally:
            # This terminates even a peer that drips headers/body indefinitely.
            try:
                peer.close()
            except Exception:
                # Reconcile an already received receipt, but fail this arm and
                # stop further dispatch when helper cleanup is unconfirmed.
                raise ProviderTransportFailure({**latest, 'stage': 'cleanup', 'category': 'cleanup',
                                                'elapsed_ms': (time.monotonic() - started) * 1000},
                                               response=completed) from None

    def cancel_pending(self):
        self.cancelled.set()

    def request_headers(self):
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise RuntimeError('Configure ANTHROPIC_API_KEY privately on the trusted host')
        return {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'x-api-key': key}

    def open_request(self, request, timeout):
        return urllib.request.urlopen(request, timeout=timeout)

    def _http(self, body, remaining, observer=None):
        # Only called after a durable gateway admission, outside every worker.
        started = time.monotonic()
        deadline = started + remaining
        detail, chunks, size = {'stage': 'credentials'}, [], 0
        def progress(**updates):
            detail.update(updates)
            if observer:
                observer(transport_detail({**detail, 'elapsed_ms': (time.monotonic() - started) * 1000}), None)
        try:
            progress()
            request = urllib.request.Request(self.endpoint, data=json.dumps(body).encode(), method='POST',
                                            headers=self.request_headers())
            progress(stage='connect')
            if time.monotonic() >= deadline:
                raise TimeoutError()
            try:
                response = (self.opener or self.open_request)(request, timeout=deadline - time.monotonic())
            except urllib.error.HTTPError as error:
                response = error  # Read bounded error evidence; never retry it.
            with response:
                wire = response.fp if isinstance(response, urllib.error.HTTPError) else response
                content_type = response.headers.get_content_type()
                request_id = response.headers.get('request-id') if hasattr(response.headers, 'get') else None
                progress(stage='response', http_status=response.status, provider_request_id=request_id,
                         content_type=content_type if content_type in ('application/json', 'text/event-stream') else 'other')
                while True:
                    if hasattr(wire, 'isclosed') and wire.isclosed():
                        break  # Content-Length read1 may close fp on the final byte.
                    if self.cancelled.is_set():
                        raise ProviderTransportFailure({**detail, 'category': 'cancelled'})
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Provider response deadline')
                    left = max(.001, deadline - time.monotonic())
                    if hasattr(wire, 'set_read_timeout'):
                        wire.set_read_timeout(left)  # Fake-response test seam.
                    else:
                        wire.fp.raw._sock.settimeout(left)
                    try:
                        part = wire.read1(65536)
                    except http.client.IncompleteRead as error:
                        if size + len(error.partial) <= RESPONSE_LIMIT:
                            chunks.append(error.partial)
                            if observer and response.status == 200 and error.partial:
                                observer({}, error.partial)
                        raise
                    if not part:
                        break
                    size += len(part)
                    if size > RESPONSE_LIMIT:
                        raise ProviderTransportFailure({**detail, 'category': 'response-limit'})
                    chunks.append(part)
                    if observer and response.status == 200:
                        # Preserve partial model receipts, including SSE, before a
                        # later timeout. Error bodies can echo credentials, so
                        # only their safe type/status/hash are retained below.
                        observer({}, part)
                raw = b''.join(chunks)
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                missing = getattr(wire, 'length', None)
                if type(missing) is int and missing > 0:
                    raise http.client.IncompleteRead(b'', missing)
                progress(response_bytes=size, response_sha256=hashlib.sha256(raw).hexdigest())
                if response.status != 200:
                    try:
                        error_type = json.loads(raw).get('error', {}).get('type')
                    except (ValueError, AttributeError, UnicodeError):
                        error_type = None
                    if not isinstance(error_type, str) or error_type not in {'invalid_request_error', 'authentication_error', 'billing_error',
                                          'permission_error', 'not_found_error', 'conflict_error', 'request_too_large',
                                          'rate_limit_error', 'api_error', 'timeout_error', 'overloaded_error'}:
                        error_type = 'unrecognized_provider_error'
                    text = json.dumps({'type': 'error', 'error': {'type': error_type},
                                       'request_id': transport_detail(detail).get('provider_request_id'),
                                       'original_body_sha256': hashlib.sha256(raw).hexdigest(),
                                       'message_omitted': True})
                else:
                    text = raw.decode('utf-8')
                return {'status': response.status, 'content-type': response.headers.get_content_type(),
                        'body': text}
        except Exception as error:
            # Never forward raw request/headers/key-bearing transport exceptions.
            category = error.detail.get('category') if isinstance(error, ProviderTransportFailure) else failure_category(error, detail['stage'])
            raise ProviderTransportFailure({**detail, 'category': category, 'response_bytes': sum(map(len, chunks)),
                                            'response_sha256': hashlib.sha256(b''.join(chunks)).hexdigest(),
                                            'elapsed_ms': (time.monotonic() - started) * 1000}) from None


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


# No new provider request starts with less task time left than this; it could
# not finish, and a cut-off request has an unknown outcome that stops the pilot.
DISPATCH_FLOOR_SECONDS = 10
# A request already sent may finish after the task deadline so its cost is
# known. The task itself still ends at its deadline; the answer is not used.
IN_FLIGHT_GRACE_SECONDS = 60
# The close-time wait is bounded by real wall time, independent of the task clock.
_wall_clock, _wall_sleep = time.monotonic, time.sleep


class GatewayClient:
    """One task ledger; root, child, refinement and compaction share its caps."""
    def __init__(self, output, config, transport, *, evidence='FIXTURE', cwd=ROOT):
        self.output = Path(output)
        self.peer = LineProcess(['python3', 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(output), 'v2'], cwd=cwd)
        self.transport = transport
        self.started = time.monotonic()
        self.deadline = self.started + config['limits']['wall-ms'] / 1000
        self.queue, self.pending = Queue(), {}
        self.evidence_lock = threading.Lock()
        self.cleanup_failed = False
        self.cleanup_failures = set()
        self.unresolved, self.unresolved_lock = 0, threading.Lock()
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
        if self.closed.is_set() or self.error or self.cleanup_failed:
            future.set_exception(RuntimeError('Gateway is closed'))
        else:
            with self.unresolved_lock:
                self.unresolved += 1
            future.add_done_callback(self._resolved)
            self.queue.put(('invoke', identifier, route, body, future))
        return future

    def _resolved(self, _):
        with self.unresolved_lock:
            self.unresolved -= 1

    def _transport(self, identifier, body, request_id):
        started = time.monotonic()
        def record(kind, detail):
            row = {'event': kind, 'transport_id': identifier, 'gateway_request_id': request_id,
                   'time_unix_ms': time.time() * 1000,
                   'task_elapsed_ms': max(0, (time.monotonic()-self.started)*1000), **transport_detail(detail)}
            with self.evidence_lock:
                with (self.output / 'transport.jsonl').open('ab') as stream:
                    stream.write(json.dumps(row, sort_keys=True).encode() + b'\n')
                    stream.flush()
                    os.fsync(stream.fileno())
        def observe(detail, chunk):
            if chunk is not None:
                directory = self.output / 'transport-bodies'
                directory.mkdir(exist_ok=True)
                with (directory / (identifier + '.body')).open('ab') as stream:
                    stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
            else:
                record('progress', detail)
        remaining = self.deadline - time.monotonic()
        if remaining < DISPATCH_FLOOR_SECONDS:
            # Refused before credentials or network: certainly never sent.
            try:
                record('not-dispatched', {'stage': 'host', 'category': 'deadline', 'task_remaining_ms': max(0, remaining*1000)})
            except OSError:
                self.queue.put(('response', identifier, None, True, False, False))
                return
            self.queue.put(('response', identifier, None, True, False, True))
            return
        try:
            record('started', {'stage': 'host', 'task_remaining_ms': remaining*1000})
            allowed = remaining + IN_FLIGHT_GRACE_SECONDS
            if isinstance(self.transport, AnthropicMessagesTransport):
                response = self.transport.request(body, allowed, observer=observe)
            else:
                response = self.transport(body, allowed)
            record('response', {'http_status': response['status'], 'elapsed_ms': (time.monotonic() - started) * 1000})
            self.queue.put(('response', identifier, response, False, False, False))
        except Exception as error:
            detail = error.detail if isinstance(error, ProviderTransportFailure) else {'category': 'transport', 'stage': 'host'}
            captured = error.response if isinstance(error, ProviderTransportFailure) else None
            cleanup_failure = detail.get('category') == 'cleanup'
            if cleanup_failure:
                self.cleanup_failed = True
                self.transport.cancel_pending()
            try:
                record('failed', {**detail, 'elapsed_ms': (time.monotonic() - started) * 1000})
            except OSError:
                pass  # Evidence I/O failure cannot permit reconciliation or another dispatch.
            self.queue.put(('response', identifier, captured, captured is None, cleanup_failure, False))

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
                        _, identifier, response, error, cleanup_failure, not_dispatched = command
                        self.peer.send({'op': 'provider_response', 'transport_id': identifier, 'response': response,
                                        'transport_error': error, 'cleanup_failure': cleanup_failure,
                                        'not_dispatched': not_dispatched})
                    else:
                        self.peer.send({'op': 'close'})
                try:
                    event = self.peer.read(seconds=0.05)
                except TimeoutError:
                    continue
                kind, identifier = event.get('type'), event.get('transport_id')
                if kind == 'provider_request':
                    self.pool.submit(self._transport, identifier, event['body'], event['request_id'])
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
        # Let every submitted request resolve (a sent one within its grace, so its
        # cost is known); only then cancel anything left, which stays unknown.
        waited = _wall_clock() + IN_FLIGHT_GRACE_SECONDS + 5
        while _wall_clock() < waited and not self.error:
            with self.unresolved_lock:
                if not self.unresolved:
                    break
            _wall_sleep(0.1)
        failures = self.cleanup_failures
        if self.cleanup_failed:
            failures.add('http-helper')
        if hasattr(self.transport, 'cancel_pending'):
            self.transport.cancel_pending()
        self.queue.put(('close',))
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            failures.add('gateway-thread')
        try:
            self.peer.close()
        except Exception:
            failures.add('gateway-peer')
        joined = False
        try:
            self.pool.shutdown(wait=True, cancel_futures=True)
            joined = True
        except Exception:
            failures.add('transport-pool')
        # The Clojure finally block preserves unknown admissions on normal close.
        # A killed bridge must be recovered before producing results.
        if not (self.output / 'usage.jsonl').exists():
            import subprocess
            try:
                subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(self.output), 'recover'],
                               cwd=ROOT, check=True, capture_output=True, timeout=20)
            except Exception:
                failures.add('ledger-recovery')
        (self.output / 'cleanup.json').write_text(json.dumps({'ok': not failures, 'failed_stages': sorted(failures),
            'transport_pool_joined': joined, 'gateway_exited': self.peer.process.poll() is not None})+'\n')
        if failures:
            raise GatewayCleanupFailure('Gateway cleanup failed; inspect cleanup.json')


class Relay:
    """Nonblocking container-event adapter; no child request is serialized by I/O."""
    def __init__(self, gateway, route, *, provider='anthropic-api'):
        self.gateway, self.route = gateway, route
        self.provider = provider
        self.pending, self.seen = {}, set()
        self.started = time.monotonic()
        self.event_sequence = 0

    def __call__(self, event, remaining):
        if hasattr(self.gateway, 'output'):
            # Host-observed timing only; raw native events stay in stdout.jsonl.
            # No timing data enters either model's request or tool result.
            record = {'sequence': self.event_sequence, 'type': event.get('type'),
                      'elapsed_ms': (time.monotonic()-self.started)*1000,
                      'remaining_task_ms': max(0,remaining*1000)}
            if event.get('type') == 'native_event' and isinstance(event.get('event'), dict):
                native_event = event['event']
                record.update({key: native_event[key] for key in ('toolCallId', 'toolName') if key in native_event})
                record['native_type'] = native_event.get('type')
            self.event_sequence += 1
            with (self.gateway.output.parent/'event-timing.jsonl').open('ab') as stream:
                stream.write(json.dumps(record).encode()+b'\n')
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
