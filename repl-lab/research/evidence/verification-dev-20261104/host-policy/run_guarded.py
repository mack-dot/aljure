#!/usr/bin/env python3
"""Guarded launcher v1 (var/host-policy-20261103). Runs ONE frozen experiment exactly as frozen, under
the host policy: an exclusive host lock (the two frozen experiments never run concurrently), the host
gate with its startup probes, the host monitor beside the run, and a summary afterwards. It adds no
flag to the frozen command and changes no experimental cap. Without --approve <plan_sha256> it never
reaches the runner; with --dry-run it runs gate and monitor only and never calls the runner.

usage: run_guarded.py substrate|causal|economics|h2h --approve <plan_sha256> [--dry-run SECONDS] [--resume]"""
import argparse, fcntl, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPERIMENTS = {
    "substrate": {"module": "benchmark.substrate", "dir": "var/substrate-20261103", "sci": "clojure", "python": "python"},
    "causal": {"module": "benchmark.reuse_causal", "dir": "var/reuse-causal-20261103", "sci": "library"},
    "economics": {"module": "benchmark.reuse_economics", "dir": "var/reuse-economics-20261104", "sci": "library"},
    "h2h": {"module": "benchmark.headtohead", "dir": "var/h2h-20261104", "sci": "aljure", "resumable": True},
    "h2h-b": {"module": "benchmark.headtohead", "dir": "var/h2h-phase-b-20261104", "sci": "aljure", "resumable": True},
    "verify": {"module": "benchmark.verification_ablation", "dir": "var/verification-dev-20261104", "sci": "A0", "resumable": True},
}


def environment(plan, spec):
    env = dict(os.environ)
    sci_cfg = plan["configs"][spec["sci"]]
    env["REPL_LAB_WORKER_IMAGE"] = sci_cfg["execution_images"]["sci"]
    env["REPL_LAB_PRIME_IMAGE"] = sci_cfg["execution_images"]["prime"]
    env["REPL_LAB_WORKER_OUTPUT_BYTES"] = str(sci_cfg["aljure_sci"]["worker_output_bytes"])
    if "python" in spec:
        env["REPL_LAB_PYTHON_IMAGE"] = plan["configs"][spec["python"]]["execution_images"]["python"]
    env.setdefault("REPL_LAB_CLAUDE_KEYCHAIN_SERVICE", "Claude Code-credentials")
    env.setdefault("REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT", os.environ.get("USER", ""))
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=sorted(EXPERIMENTS))
    parser.add_argument("--approve", required=True, help="the exact plan_sha256 the owner approved")
    parser.add_argument("--run", default="run-1")
    parser.add_argument("--dry-run", type=float, default=None, metavar="SECONDS")
    parser.add_argument("--resume", action="store_true", help="continue an interrupted run of a resumable experiment under the same plan")
    args = parser.parse_args()
    spec = EXPERIMENTS[args.experiment]
    base = ROOT / spec["dir"]
    plan_path, suite, out = base / "plan.json", base / "suite", base / args.run
    plan = json.loads(plan_path.read_text())
    if args.approve != plan["plan_sha256"]:
        print(json.dumps({"refused": "approval does not match the frozen plan", "plan_sha256": plan["plan_sha256"]}))
        return 2
    env = environment(plan, spec)
    lock = open(HERE / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(json.dumps({"refused": "another guarded run holds the host lock"}))
        return 2
    lock.write(f"{os.getpid()} {args.experiment} {time.time()}\n")
    lock.flush()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if args.resume:
        if not spec.get("resumable"):
            print(json.dumps({"refused": "experiment is not resumable"}))
            return 2
        gate_out = out.with_name(out.name + "-resume-" + stamp)
    else:
        gate_out = out
    gate = subprocess.run([sys.executable, str(HERE / "host_gate.py"), "--plan", str(plan_path), "--out", str(gate_out), "--probe"],
                          capture_output=True, text=True, cwd=ROOT, env=env)
    print(gate.stdout.strip() or gate.stderr.strip()[-500:])
    if gate.returncode != 0:
        print(json.dumps({"refused": "host gate", "returncode": gate.returncode}))
        return 2
    monitor_path = HERE / f"monitor-{args.experiment}-{stamp}.jsonl"
    monitor = subprocess.Popen([sys.executable, str(HERE / "host_monitor.py"), str(monitor_path), "--interval", "5"], cwd=ROOT)
    command = [sys.executable, "-m", spec["module"], "run", "--suite", str(suite), "--plan", str(plan_path), "--out", str(out),
               "--authorize-subscription-plan", args.approve] + (["--resume"] if args.resume else [])
    summary = {"policy": "host-policy-v1", "experiment": args.experiment, "plan_sha256": plan["plan_sha256"], "command": command,
               "gate": json.loads(gate.stdout.strip().splitlines()[-1]), "monitor": str(monitor_path), "started": time.time()}
    started = time.monotonic()
    try:
        if args.dry_run is not None:
            summary["dry_run_seconds"], summary["returncode"] = args.dry_run, None
            time.sleep(args.dry_run)
        else:
            result = subprocess.run(command, cwd=ROOT, env=env)
            summary["returncode"] = result.returncode
    finally:
        monitor.send_signal(signal.SIGTERM)
        try:
            monitor.wait(timeout=30)
        except subprocess.TimeoutExpired:
            monitor.kill()
        summary["seconds"] = round(time.monotonic() - started, 1)
        check = subprocess.run(["docker", "ps", "--all", "--filter", "name=^/repl-lab-", "--format", "{{.Names}}"],
                               capture_output=True, text=True, timeout=15)
        summary["orphan_workers_after"] = check.stdout.split()
        summary["results"] = str(out / "results.json") if (out / "results.json").exists() else None
        path = HERE / f"summary-{args.experiment}-{stamp}.json"
        path.write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary[k] for k in ("experiment", "returncode", "seconds", "orphan_workers_after", "results")} | {"summary": str(path)}))
    return 0 if summary["returncode"] in (0, None) else 1


if __name__ == "__main__":
    sys.exit(main())
