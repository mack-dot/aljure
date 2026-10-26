#!/usr/bin/env python3
"""Trusted SQLite transport. Requests are from the controller, never the worker."""
import json
import sqlite3
import sys
from pathlib import Path

request = json.load(sys.stdin)
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(path, timeout=10) as db:
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, value TEXT NOT NULL)")
    op, key = request["op"], request.get("key")
    if op == "read":
        row = db.execute("SELECT revision,value FROM records WHERE key=?", (key,)).fetchone()
        answer = {"revision": row[0], "value": row[1]} if row else {"revision": 0, "value": None}
    elif op == "cas":
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM records WHERE key=?", (key,)).fetchone()
        revision = row[0] if row else 0
        success = revision == request["revision"]
        if success:
            db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET revision=excluded.revision,value=excluded.value",
                       (key, revision + 1, request["value"]))
        db.commit()
        answer = {"success": success, "revision": revision + (1 if success else 0)}
    elif op == "keys":
        answer = {"keys": [row[0] for row in db.execute("SELECT key FROM records ORDER BY key")]}
    else:
        raise ValueError("Unknown store operation")
print(json.dumps(answer))
