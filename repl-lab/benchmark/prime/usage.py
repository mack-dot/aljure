"""Audit native transcript counters. These are not trusted billing receipts.

The append-only assistant message rows contain the original request usage.
child_usage_attributed rows carry additional, overlapping aggregate views.
The external gateway must still account for every real provider request.
"""
import json

COUNTERS = ("input", "output", "cacheRead", "cacheWrite")


def counts(usage):
    result = {key: usage.get(key) for key in COUNTERS}
    if not all(type(value) is int and value >= 0 for value in result.values()):
        raise ValueError("Native transcript has missing or invalid usage counters")
    return result


def audit_transcripts(files):
    sessions = []
    calls = []
    attributions = []
    seen_sessions = set()
    total = dict.fromkeys(COUNTERS, 0)
    for path, body in sorted(files.items()):
        if not path.endswith(".jsonl"):
            continue
        entries = [json.loads(line) for line in body.splitlines() if line.strip()]
        if not entries or entries[0].get("type") != "session":
            continue
        session_id = entries[0].get("id")
        if not isinstance(session_id, str) or not session_id or session_id in seen_sessions:
            raise ValueError("Missing or duplicate native session identity")
        seen_sessions.add(session_id)
        sessions.append({"id": session_id, "path": path})
        assistant = {}
        row_ids = set()
        for entry in entries[1:]:
            row_id = entry.get("id")
            if not row_id or row_id in row_ids:
                raise ValueError("Missing or duplicate native transcript row identity")
            row_ids.add(row_id)
            message = entry.get("message", {})
            if entry.get("type") == "message" and message.get("role") == "assistant":
                usage = counts(message.get("usage", {}))
                assistant[row_id] = dict(usage)
                calls.append({"session_id": session_id, "row_id": row_id, "model": message.get("model"),
                              "provider": message.get("provider"), "usage": usage})
                for key in COUNTERS:
                    total[key] += usage[key]
            if entry.get("type") == "child_usage_attributed":
                target = entry.get("targetId")
                if target not in assistant:
                    raise ValueError("Child attribution has no preceding assistant row")
                child = counts(entry.get("childUsage", {}))
                expected = {key: assistant[target][key] + child[key] for key in COUNTERS}
                if expected != counts(entry.get("aggregateUsage", {})):
                    raise ValueError("Child attribution aggregate does not reconcile")
                assistant[target] = expected
                attributions.append({"session_id": session_id, "row_id": row_id, "target_id": target,
                                     "origin": entry.get("origin"), "child_usage": child})
    if not calls:
        raise ValueError("No native assistant usage rows were preserved")
    return {"evidence": "FIXTURE" if all(row['provider'] == 'faux' for row in calls) else "IMPLEMENTED / UNVERIFIED",
            "trusted_provider_accounting": False, "provider_billing_usd": None,
            "note": "Transcript diagnostic only; excludes overlapping child aggregate rows. Not a billing source.",
            "sessions": sessions, "assistant_rows": calls, "child_attributions": attributions,
            "distinct_assistant_row_counters": total}
