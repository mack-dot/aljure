"""Pinned native Claude OAuth contract. No login, refresh, or API-key fallback.

This module never searches credential stores. The operator must select one
private file or Keychain entry. Only the trusted host reads its contents.
"""
import copy
import json
import os
from pathlib import Path
import time

PROVIDER = 'claude-oauth-subscription'
VERSION = 'native-claude-oauth-v1'
IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
# This string is deliberately invalid. It activates the pinned native OAuth
# serialization path inside a network-isolated worker; it cannot authenticate.
SENTINEL = 'sk-ant-oat-ALJURE-OFFLINE-SENTINEL-NOT-A-CREDENTIAL'
PUBLIC_HEADERS = {
    'anthropic-version': '2023-06-01',
    'accept': 'application/json',
    'anthropic-dangerous-direct-browser-access': 'true',
    'anthropic-beta': 'claude-code-20250219,oauth-2025-04-20',
    'user-agent': 'claude-cli/2.1.281',
    'x-app': 'cli',
}
KEYCHAIN_TIMEOUT_SECONDS = 5
KEYCHAIN_OUTPUT_BYTES = 1024**2


def prepare_body(body, *, native=False):
    """Keep native serialization intact; give Aljure the same OAuth identity."""
    if native:
        blocks = body.get('system')
        if not (isinstance(blocks, list) and blocks and
                blocks[0].get('type') == 'text' and blocks[0].get('text') == IDENTITY):
            raise ValueError('Native OAuth identity contract is missing')
        return body
    result = copy.deepcopy(body)
    system = result.get('system', [])
    if isinstance(system, str):
        system = [{'type': 'text', 'text': system}]
    if not isinstance(system, list):
        raise ValueError('Invalid system prompt')
    result['system'] = [{'type': 'text', 'text': IDENTITY}, *system]
    return result


def validate_public_headers(headers):
    # This pinned model uses eager_input_streaming, so no extra tool beta is
    # needed. Refuse unexpected changes instead of silently rewriting requests.
    if headers != PUBLIC_HEADERS:
        raise ValueError('Native OAuth public header contract differs from the pinned provider')
    return dict(PUBLIC_HEADERS)


def _keychain_document(service, account):
    """Read one bounded document, then reap the utility's normal exit.

    A credential line is not an exit signal. Closing LineProcess immediately
    after that line can send SIGKILL to macOS security during normal teardown,
    which can raise EPERM despite a successful credential read.
    """
    from .line_process import LineProcess
    deadline = time.monotonic() + KEYCHAIN_TIMEOUT_SECONDS
    peer = LineProcess(['/usr/bin/security', 'find-generic-password', '-a', account,
                        '-s', service, '-w'], limit=KEYCHAIN_OUTPUT_BYTES)
    try:
        # Keep both buffers intact so the limit covers all stdout plus stderr,
        # including trailing output. This also accepts multiline JSON documents.
        while peer.selector.get_map():
            try:
                peer.pump(deadline)
            except EOFError:
                pass  # pump unregisters the closed stream; drain the other one.
        status = peer.process.wait(timeout=max(0, deadline - time.monotonic()))
        if status != 0:
            raise RuntimeError('Credential utility failed')
        return json.loads(peer.output)
    finally:
        # Successful reads already waited for exit. Kill only on a failed or
        # timed-out read where the utility still has not terminated.
        peer.close()


def _credential_document(environ):
    path_value = environ.get('REPL_LAB_CLAUDE_OAUTH_FILE')
    service = environ.get('REPL_LAB_CLAUDE_KEYCHAIN_SERVICE')
    account = environ.get('REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT')
    if path_value and not service and not account:
        path = Path(path_value)
        info = path.stat()
        if info.st_size > 1024**2 or info.st_mode & 0o077:
            raise ValueError('Private file required')
        return json.loads(path.read_text())
    if service and account and not path_value:
        return _keychain_document(service, account)
    raise ValueError('Select exactly one explicit credential source')


def _load(*, environ=None, now=None):
    """Read only an explicitly selected private file; expiry is epoch millis.

    Supported shapes are pinned Prime auth.json and Claude Code credential JSON.
    Refresh tokens are ignored. Expired credentials require operator renewal.
    Errors never contain the path, parsed content, or token.
    """
    environ = os.environ if environ is None else environ
    now = time.time() if now is None else now
    try:
        document = _credential_document(environ)
        if isinstance(document.get('anthropic'), dict):
            credentials = document['anthropic']
            if credentials.get('type') != 'oauth':
                raise ValueError('OAuth required')
            access, expiry = credentials.get('access'), credentials.get('expires')
        else:
            credentials = document['claudeAiOauth']
            access, expiry = credentials.get('accessToken'), credentials.get('expiresAt')
            scopes = credentials.get('scopes')
            if scopes is not None and 'user:inference' not in scopes:
                raise ValueError('Inference scope required')
        if not (isinstance(access, str) and access.startswith('sk-ant-oat') and access != SENTINEL and
                type(expiry) in (int, float) and expiry / 1000 > now + 60):
            raise ValueError('Valid unexpired OAuth credential required')
        return access, expiry
    except Exception:
        raise RuntimeError('Configure an explicit private unexpired Claude OAuth credential source; no API fallback or automatic refresh') from None


def load_access_token(**kwargs):
    return _load(**kwargs)[0]


def credential_status(**kwargs):
    """Explicit read-only operator check. Never called by benchmark preflight."""
    _, expiry = _load(**kwargs)
    return {'configured': True, 'credential_type': 'claude-oauth', 'expires_at_ms': expiry,
            'refresh_attempted': False, 'model_calls': 0, 'api_fallback': False}
