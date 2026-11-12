#!/usr/bin/env python3
"""Run pinned, cached Clojure jars without changing the user's Maven cache.

This offline launcher never downloads dependencies. Use clojure -P on a connected
machine to populate the cache, or set REPL_LAB_M2 to an existing Maven cache.
"""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
m2 = Path(os.environ.get("REPL_LAB_M2", str(Path.home() / ".m2/repository")))
coordinates = [
    ("org/clojure/clojure", "1.11.3"),
    ("org/clojure/spec.alpha", "0.3.218"),
    ("org/clojure/core.specs.alpha", "0.2.62"),
    ("org/clojure/data.json", "2.5.0"),
]
jars = [m2 / group / version / (group.split("/")[-1] + "-" + version + ".jar")
        for group, version in coordinates]
missing = [str(p) for p in jars if not p.is_file()]
if missing:
    sys.exit("Missing pinned dependencies. Run clojure -P first:\n" + "\n".join(missing))
os.chdir(root)
# worker/src holds the worker's pure-Clojure bridge half (repl-lab.bridge), which the
# controller's tests drive directly; the SCI worker itself only runs in its image.
classpath = os.pathsep.join(map(str, [root / "src", root / "resources", root / "test", root / "worker/src", *jars]))
os.execvp("java", ["java", "-Xmx512m", "-Dfile.encoding=UTF-8", "-cp", classpath,
                   "clojure.main", *sys.argv[1:]])
