"""Trusted host HTTP worker. Never launched in a generated-code container.

The parent enforces a total deadline and terminates this process on cancellation.
Credentials stay in the inherited private host environment, never stdin/argv/logs.
"""
import base64
import json
import sys

from .gateway_client import (AnthropicMessagesTransport, ClaudeSubscriptionTransport,
                             ProviderTransportFailure, transport_detail)


def main():
    def observe(detail, chunk):
        frame = {'chunk': base64.b64encode(chunk).decode('ascii')} if chunk is not None else {'progress': transport_detail(detail)}
        print(json.dumps(frame), flush=True)
    try:
        wire = sys.stdin.buffer.readline(2 * 1024**2 + 1)
        if len(wire) > 2 * 1024**2:
            raise ValueError('Request limit')
        request = json.loads(wire)
        transport = {'anthropic-api': AnthropicMessagesTransport,
                     'claude-oauth-subscription': ClaudeSubscriptionTransport}[request['transport']]
        result = transport(authorized=True)._http(request['body'], request['timeout'], observer=observe)
        print(json.dumps({'response': result}), flush=True)
    except ProviderTransportFailure as error:
        print(json.dumps({'error': error.detail}), flush=True)
    except Exception:
        print(json.dumps({'error': {'stage': 'host', 'category': 'worker'}}), flush=True)


if __name__ == '__main__':
    main()
