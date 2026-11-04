"""Contract text-answer-v2, Python side: the same deterministic rule as model_protocol/terminal-text-answer-v2,
applied to native Prime's final assistant text when it wrote no answer file, so both harnesses get identical
output semantics. A fixture test holds the two implementations to the same cases.

Rule: the reply ended normally with no tool call; its text is at most 16,384 characters; exactly one line, after
trimming, starts with FINAL ANSWER:, Answer: or Label: (case-sensitive) and no other line contains any marker;
the answer is that line with a FINAL ANSWER: marker stripped; an empty answer or one over 4,096 characters is
refused."""
import glob
import json
import re

MARKERS = ('FINAL ANSWER:', 'Answer:', 'Label:')
VERSION = 'text-answer-v2'
_EMPTY = re.compile(r'(?:FINAL ANSWER|Answer|Label):\s*\Z')


def terminal_text_answer_v2(text, *, stop_reason='end_turn', has_tool_call=False, has_text=True):
    if stop_reason != 'end_turn' or has_tool_call or not has_text or text is None or len(text) > 16384:
        return None
    lines = [line.strip() for line in text.splitlines()]
    marked = [line for line in lines if any(line.startswith(m) for m in MARKERS)]
    mentions = [line for line in lines if any(m in line for m in MARKERS)]
    if len(marked) != 1 or len(mentions) != 1:
        return None
    line = marked[0]
    answer = line[len('FINAL ANSWER:'):].strip() if line.startswith('FINAL ANSWER:') else line
    if not answer or len(answer) > 4096 or _EMPTY.fullmatch(answer):
        return None
    return answer


def prime_final_text(task_out):
    """Native Prime's last assistant message: (text, stop_reason, has_tool_call, has_text), or None."""
    last = None
    for path in sorted(glob.glob(str(task_out / 'native/sessions/*.jsonl'))):
        for raw in open(path, encoding='utf-8', errors='replace'):
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            message = record.get('message') or {}
            if message.get('role') == 'assistant':
                last = message
    if last is None:
        return None
    content = last.get('content') or []
    blocks = content if isinstance(content, list) else [{'type': 'text', 'text': str(content)}]
    texts = [b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text']
    calls = any(isinstance(b, dict) and b.get('type') in ('toolCall', 'tool_use') for b in blocks)
    stop = last.get('stopReason') or last.get('stop_reason')
    stop = {'stop': 'end_turn', 'end_turn': 'end_turn', 'toolUse': 'tool_use', 'tool_use': 'tool_use'}.get(stop, stop)
    return '\n'.join(texts), stop, calls, bool(texts)


def prime_terminal_answer(task_out):
    """The accepted terminal text answer for a Prime arm without an answer file, with provenance, or None."""
    final = prime_final_text(task_out)
    if final is None:
        return None
    text, stop, calls, has_text = final
    answer = terminal_text_answer_v2(text, stop_reason=stop, has_tool_call=calls, has_text=has_text)
    if answer is None:
        return None
    return {'answer': answer, 'provenance': {'version': VERSION, 'origin': 'prime-final-assistant-text',
                                             'lines': len(text.splitlines()), 'stop_reason': stop}}
