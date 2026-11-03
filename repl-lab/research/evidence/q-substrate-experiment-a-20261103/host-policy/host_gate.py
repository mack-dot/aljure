#!/usr/bin/env python3
"""Host execution gate v1 (var/host-policy-20261103). Decides whether the host is safe to run ONE
frozen experiment now. It never rebuilds, pulls, removes or weakens anything; a refusal names what
the operator must inspect. The only thing it starts is the optional positive startup probe: one
worker per language through the frozen supervisor (scripts/isolation.py), exactly as the isolation
gate does, so the measured readiness time is the real one.

usage: host_gate.py --plan <plan.json> --out <run dir that must not exist> [--probe] [--credential-hours H]
exit 0 ready, 2 refused."""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import isolation                       # noqa: E402  frozen supervisor (read-only use)
from benchmark import paired           # noqa: E402
from benchmark import subscription_protocol  # noqa: E402

DISK_FLOOR_GB = 10
PROBE_REFUSAL_MS = 20000               # the supervisor limit is 30000 ms; refuse while the host is this slow
WORKER = re.compile(r"^repl-lab-[0-9a-f]{32}$")


def docker(*args, timeout=5):
    try:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__


def containers():
    code, out = docker("ps", "--all", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}")
    if code != 0:
        return None
    rows = [line.split("\t") for line in out.splitlines() if line]
    return {"orphan_workers": [r[0] for r in rows if WORKER.match(r[0])],
            "running_other": [r[0] for r in rows if not WORKER.match(r[0]) and r[1] == "running"],
            "total": len(rows)}


def host():
    text = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
    page = int(re.search(r"page size of (\d+)", text).group(1))
    free = sum(int(m.group(1)) for m in re.finditer(r"^Pages (?:free|speculative):\s+(\d+)", text, re.M))
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
    used, total = float(re.search(r"used = ([\d.]+)M", swap).group(1)), float(re.search(r"total = ([\d.]+)M", swap).group(1))
    return {"load": list(os.getloadavg()), "cpus": os.cpu_count(), "mem_free_mb": round(free * page / 2**20),
            "swap_used_mb": round(used), "swap_total_mb": round(total), "swap_used_fraction": round(used / total, 3) if total else None}


def probe(language, image_env, audit_dir):
    """One real worker start through the frozen supervisor; readiness time and confirmed cleanup."""
    env = {**os.environ, "REPL_LAB_WORKER_AUDIT_DIR": str(audit_dir)}
    request = {"clojure": '{:source "(+ 20 22)" :bindings {}}\n', "python": '{"source": "20 + 22", "bindings": {}}\n'}[language]
    script = "scripts/isolation.py" if language == "clojure" else "scripts/python_isolation.py"
    started = time.monotonic()
    r = subprocess.run([sys.executable, str(ROOT / script), "session"], input=request, capture_output=True, text=True,
                       timeout=isolation.LIMITS["startup_seconds"] + 60, cwd=ROOT, env=env)
    total_ms = round((time.monotonic() - started) * 1000)
    audits = [json.loads(p.read_text()) for p in Path(audit_dir).glob("repl-lab-*.json")]
    ready = [e["startup_ms"] for a in audits for e in a["events"] if e["event"] == "worker-ready"]
    return {"language": language, "returncode": r.returncode, "answered": "42" in r.stdout, "total_ms": total_ms,
            "startup_ms": ready[-1] if ready else None, "cleanup_confirmed": bool(audits) and all(a["cleanup_confirmed"] for a in audits),
            "stderr": r.stderr[-300:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--credential-hours", type=float, default=1.0)
    parser.add_argument("--max-swap", type=float, default=0.9, help="refuse while host swap used fraction exceeds this")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    configs = plan["configs"]
    images = sorted({v for c in configs.values() for v in c["execution_images"].values()})
    languages = sorted({c.get("execution_language", "clojure") for c in configs.values()})
    refusals, warnings = [], []
    report = {"policy": "host-policy-v1", "gate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "plan_sha256": plan["plan_sha256"], "time": time.time()}

    # 1. The frozen allocation is untouched.
    if plan.get("authorized") or plan.get("model_calls"):
        refusals.append("plan file already records authorization or model calls")
    if args.out.exists():
        refusals.append(f"run directory already exists: {args.out}")
    # 2. Worker cleanup state.
    if isolation.QUARANTINE.exists() and any(isolation.QUARANTINE.iterdir()):
        refusals.append("var/isolation-quarantine is not empty")
    # 3. Daemon, images, Desktop session.
    for language in languages:
        check = isolation.preflight(*(("REPL_LAB_WORKER_IMAGE", "repl-lab.worker") if language == "clojure"
                                      else ("REPL_LAB_PYTHON_IMAGE", "repl-lab.python-worker")))
        report[f"preflight_{language}"] = {k: check.get(k) for k in ("ready", "reason", "image")}
        if not check.get("ready"):
            refusals.append(f"{language} isolation preflight: {check.get('reason')}")
    # 4. Positive startup probe through the frozen supervisor. It runs before the Desktop-session check
    #    because Resource Saver reports `stopped` with a stale session while the engine still answers;
    #    a real worker start wakes the engine, and the session is judged afterwards.
    if args.probe and not refusals:
        audit_dir = Path(__file__).parent / "gate-audit" / str(int(time.time()))
        audit_dir.mkdir(parents=True)
        report["probes"] = [probe(language, None, audit_dir) for language in languages]
        for p in report["probes"]:
            if not (p["returncode"] == 0 and p["answered"] and p["cleanup_confirmed"]):
                refusals.append(f"{p['language']} startup probe failed: exit {p['returncode']} {p['stderr'][-120:]!r}")
            elif p["startup_ms"] is None or p["startup_ms"] > PROBE_REFUSAL_MS:
                refusals.append(f"{p['language']} worker readiness took {p['startup_ms']} ms (refusal above {PROBE_REFUSAL_MS} ms)")
    # 5. Desktop session, pending restart, pinned images: exactly the frozen runner's per-task check.
    state = paired.docker_state(images)
    report["docker_state"] = state
    refusals += paired.docker_blockers(state)
    # 6. Nothing else may be running, and no worker may be left behind (including by the probe).
    found = containers()
    report["containers"] = found
    if found is None:
        refusals.append("docker ps did not answer within 5 s")
    else:
        if found["orphan_workers"]:
            refusals.append("orphan worker containers (a supervisor was killed before cleanup): " + ", ".join(found["orphan_workers"]))
        if found["running_other"]:
            refusals.append("containers of another project are running: " + ", ".join(found["running_other"]))
    # 7. Disk and host memory.
    import shutil
    free_gb = shutil.disk_usage(ROOT).free / 2**30
    report["disk_free_gb"] = round(free_gb, 1)
    if free_gb < DISK_FLOOR_GB:
        refusals.append(f"host disk below {DISK_FLOOR_GB} GB free")
    report["host"] = host()
    if report["host"]["swap_used_fraction"] and report["host"]["swap_used_fraction"] > args.max_swap:
        refusals.append(f"host swap used {report['host']['swap_used_fraction']:.0%} exceeds {args.max_swap:.0%}: "
                        "close memory-heavy applications and re-run the gate")
    if report["host"]["mem_free_mb"] < 512:
        warnings.append("under 512 MB free host memory")
    if report["host"]["load"][0] > report["host"]["cpus"]:
        warnings.append("1-minute load exceeds CPU count")
    # 8. Credential metadata (read-only; no inference).
    try:
        status = subscription_protocol.credential_status()
        hours = (status["expires_at_ms"] / 1000 - time.time()) / 3600
        report["credential"] = {**status, "expires_in_hours": round(hours, 2)}
        if hours < args.credential_hours:
            refusals.append(f"OAuth credential expires in {hours:.2f} h, below the required {args.credential_hours} h")
    except Exception as error:
        refusals.append("credential metadata: " + str(error))
    report["warnings"], report["refusals"], report["ready"] = warnings, refusals, not refusals
    path = Path(__file__).parent / f"gate-{int(report['time'])}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"ready": report["ready"], "refusals": refusals, "warnings": warnings, "record": str(path)}))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
