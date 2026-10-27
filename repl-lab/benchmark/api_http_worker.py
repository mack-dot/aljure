"""Trusted host HTTP worker. Never launched in a generated-code container.

The parent enforces a total deadline and terminates this process on cancellation.
Credentials stay in the inherited private host environment, never stdin/argv/logs.
"""
import json
import sys

from .gateway_client import AnthropicMessagesTransport, ClaudeSubscriptionTransport


def main():
    try:
        wire = sys.stdin.buffer.readline(2 * 1024**2 + 1)
        if len(wire) > 2 * 1024**2:
            raise ValueError('Request limit')
        request = json.loads(wire)
        transport = {'anthropic-api': AnthropicMessagesTransport,
                     'claude-oauth-subscription': ClaudeSubscriptionTransport}[request['transport']]
        result = transport(authorized=True)._http(request['body'], request['timeout'])
        print(json.dumps({'response': result}), flush=True)
    except Exception:
        print(json.dumps({'error': 'Provider transport failed; outcome may be unknown'}), flush=True)


if __name__ == '__main__':
    main()
