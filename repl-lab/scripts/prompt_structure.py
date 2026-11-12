"""Structural comparison of the requests both harnesses sent through the gateway.

Reads gateway-request-intent inputs (the same recording point for both routes)
and usage records. Section token counts are estimates: each section's share of
characters times the measured input tokens of that call.

    python3 scripts/prompt_structure.py RUN_DIR OUT.json
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_replay_ablation import records  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def blocks(content):
    return content if isinstance(content, list) else [{"type": "text", "text": content}]


def text_of(block):
    if block.get("type") == "text":
        return block["text"]
    return json.dumps(block, sort_keys=True)


def headings(text):
    """Split markdown text at '#'/'##' headings into (title, chars)."""
    parts, title, start = [], "(preamble)", 0
    for m in re.finditer(r"^#{1,2} (.+)$", text, re.M):
        parts.append((title, len(text[start:m.start()])))
        title, start = m[1].strip(), m.start()
    parts.append((title, len(text[start:])))
    return [p for p in parts if p[1]]


def first_request(arm):
    ev = records(arm / "gateway/events.jsonl")
    return [e["payload"] for e in ev if e["type"] == "gateway-request-intent"][0]["input"]


def usage_rows(arm):
    out = []
    for u in records(arm / "gateway/usage.jsonl"):
        cc = u.get("cache_creation") or {}
        out.append({"input": u.get("input_tokens") or 0,
                    "cache_write_5m": cc.get("ephemeral_5m_input_tokens") or 0,
                    "cache_write_1h": cc.get("ephemeral_1h_input_tokens") or 0,
                    "cache_read": u.get("cache_read_input_tokens") or 0,
                    "output": u.get("output_tokens") or 0, "usd": u.get("estimated_usd") or 0})
    return out


def sections(req):
    """(kind, name, text, cache_control) for every part of a request."""
    out = []
    for i, b in enumerate(blocks(req.get("system") or [])):
        out.append(("system", f"system[{i}]", text_of(b), b.get("cache_control")))
    for t in req.get("tools") or []:
        out.append(("tool", f"tool {t['name']}: description", t.get("description", ""), None))
        out.append(("tool", f"tool {t['name']}: input_schema", json.dumps(t.get("input_schema", {}), sort_keys=True),
                    t.get("cache_control")))
    for mi, m in enumerate(req["messages"]):
        for bi, b in enumerate(blocks(m["content"])):
            out.append(("message", f"messages[{mi}].{bi} {m['role']} {b.get('type')}", text_of(b), b.get("cache_control")))
    return out


def main(run, out):
    run = Path(run)
    arms = sorted(p for p in run.iterdir() if p.name[:2].isdigit())
    report = {"harnesses": {}}
    for harness in ("aljure", "prime"):
        hs = [a for a in arms if a.name.endswith(harness)]
        first = first_request(hs[0])
        secs = sections(first)
        u0 = usage_rows(hs[0])[0]
        measured = u0["input"] + u0["cache_write_5m"] + u0["cache_write_1h"] + u0["cache_read"]
        chars = sum(len(t) for _, _, t, _ in secs)
        per_arm_hash = defaultdict(set)
        for a in hs:
            for kind, name, text, _ in sections(first_request(a)):
                per_arm_hash[name].add(sha(text))
        calls = [u for a in hs for u in usage_rows(a)]
        firsts = [usage_rows(a)[0] for a in hs]
        total = lambda rows, k: sum(r[k] for r in rows)  # noqa: E731
        report["harnesses"][harness] = {
            "arms": len(hs),
            "params": {k: v for k, v in first.items() if k not in ("messages", "system", "tools")},
            "first_call_measured_input_tokens": measured,
            "first_call_chars": chars,
            "sections": [{"kind": k, "name": n, "chars": len(t), "sha256": sha(t)[:16],
                          "est_tokens": round(measured * len(t) / chars), "cache_control": bool(c),
                          "distinct_across_arms": len(per_arm_hash[n])} for k, n, t, c in secs],
            "system_headings": [{"title": t, "chars": c, "est_tokens": round(measured * c / chars)}
                                for b in blocks(first.get("system") or []) for t, c in headings(text_of(b))
                                if len(text_of(b)) > 1000],
            "all_calls": {"calls": len(calls), **{k: total(calls, k) for k in
                          ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output", "usd")}},
            "first_calls": {"calls": len(firsts), **{k: total(firsts, k) for k in
                            ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output", "usd")}},
        }
    Path(out).write_text(json.dumps(report, indent=1))
    for h, r in report["harnesses"].items():
        print(f"== {h}: first call {r['first_call_measured_input_tokens']} input tokens, {r['first_call_chars']} chars")
        for s in r["sections"]:
            print(f"   {s['kind']:8} {s['name'][:60]:60} {s['chars']:6} chars ~{s['est_tokens']:5} tok "
                  f"cache={s['cache_control']} variants={s['distinct_across_arms']}")
        print("   all calls:", r["all_calls"])
        print("   first calls:", r["first_calls"])


if __name__ == "__main__":
    main(*sys.argv[1:3])
