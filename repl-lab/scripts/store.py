#!/usr/bin/env python3
"""Trusted SQLite transport. Requests are from the controller, never the worker.

One request on stdin, or with --serve one JSON request per line until EOF, so a
controller keeps one store process instead of starting one per read or write."""
import json
import sqlite3
import sys
from pathlib import Path


def handle(db, request):
    op, key = request["op"], request.get("key")
    if op == "read":
        row = db.execute("SELECT revision,value FROM records WHERE key=?", (key,)).fetchone()
        return {"revision": row[0], "value": row[1]} if row else {"revision": 0, "value": None}
    if op == "revision":
        row = db.execute("SELECT revision FROM records WHERE key=?", (key,)).fetchone()
        return {"revision": row[0] if row else 0}
    if op == "cas":
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM records WHERE key=?", (key,)).fetchone()
        revision = row[0] if row else 0
        success = revision == request["revision"]
        if success:
            db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET revision=excluded.revision,value=excluded.value",
                       (key, revision + 1, request["value"]))
        db.commit()
        return {"success": success, "revision": revision + (1 if success else 0)}
    if op == "keys":
        return {"keys": [row[0] for row in db.execute("SELECT key FROM records ORDER BY key")]}
    raise ValueError("Unknown store operation")


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, value TEXT NOT NULL)")
    return db


def serve(path):
    db = inode = None
    for line in sys.stdin:
        try:
            # A file deleted or replaced at this path gets a new connection, not
            # writes to the unlinked file.
            if db is None or not path.exists() or path.stat().st_ino != inode:
                if db is not None:
                    db.close()
                db = None
                db = connect(path)
                inode = path.stat().st_ino
            answer = handle(db, json.loads(line))
        except Exception as error:
            if db is not None and db.in_transaction:
                db.rollback()
            answer = {"error": type(error).__name__ + ": " + str(error)}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()
    if db is not None:
        db.close()


if __name__ == "__main__":
    if sys.argv[2:] == ["--serve"]:
        serve(Path(sys.argv[1]))
    else:
        database = connect(Path(sys.argv[1]))
        try:
            with database:
                print(json.dumps(handle(database, json.load(sys.stdin))))
        finally:
            database.close()
