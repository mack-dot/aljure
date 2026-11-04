#!/usr/bin/env python3
"""Host observation v1 (var/host-policy-20261103). Observe only: never creates, stops or removes
anything. Samples host memory, swap, load, Docker Desktop session, container counts by owner and
docker stats for running containers; records every container event the daemon reports. Each docker
query carries its own timeout, and a timeout is itself recorded as evidence of a stalled daemon.

usage: host_monitor.py <out.jsonl> [--interval 5]   (stop with SIGTERM/SIGINT)"""
import json, os, re, signal, subprocess, sys, threading, time

WORKER_PATTERN = re.compile(r"^repl-lab-[0-9a-f]{32}$")
EVENT_ACTIONS = {"create", "start", "die", "oom", "kill", "destroy", "exec_die"}


def docker(*args, timeout=5):
    try:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__


def host_sample():
    sample = {}
    try:
        sample["load"] = list(os.getloadavg())
    except OSError:
        pass
    try:
        text = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        page = int(re.search(r"page size of (\d+)", text).group(1))
        pages = {m.group(1): int(m.group(2)) for m in re.finditer(r"^(Pages [a-z ]+?|Pageouts|Swapins|Swapouts):\s+(\d+)", text, re.M)}
        sample["mem_free_mb"] = round((pages.get("Pages free", 0) + pages.get("Pages speculative", 0)) * page / 2**20)
        sample["mem_compressed_mb"] = round(pages.get("Pages occupied by compressor", 0) * page / 2**20)
        sample["pageouts"] = pages.get("Pageouts")
    except Exception as error:
        sample["vm_stat_error"] = type(error).__name__
    try:
        swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
        used, total = re.search(r"used = ([\d.]+)M", swap).group(1), re.search(r"total = ([\d.]+)M", swap).group(1)
        sample["swap_used_mb"], sample["swap_total_mb"] = round(float(used)), round(float(total))
    except Exception as error:
        sample["swap_error"] = type(error).__name__
    return sample


def docker_sample():
    sample = {}
    code, out = docker("desktop", "status", timeout=15)
    if code == 0:
        fields = dict(line.split(None, 1) for line in out.splitlines()[1:] if len(line.split(None, 1)) == 2)
        sample["desktop"] = {"status": fields.get("Status", "").strip(), "session": fields.get("SessionID", "").strip()}
    else:
        sample["desktop"] = {"error": out if code is None else "nonzero-exit"}
    code, out = docker("ps", "--all", "--format", "{{.Names}}\t{{.State}}\t{{.Image}}")
    if code == 0:
        counts = {"worker_running": 0, "worker_exited": 0, "other_running": 0, "other_exited": 0}
        running = []
        for line in out.splitlines():
            name, state, image = (line.split("\t") + ["", ""])[:3]
            owner = "worker" if WORKER_PATTERN.match(name) else "other"
            counts[f"{owner}_{'running' if state == 'running' else 'exited'}"] += 1
            if state == "running":
                running.append(name)
        sample["containers"] = counts
        if running:
            code, stats = docker("stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}", timeout=10)
            sample["stats"] = stats.splitlines() if code == 0 else {"error": stats if code is None else "nonzero-exit"}
    else:
        sample["containers"] = {"error": out if code is None else "nonzero-exit"}
    return sample


def main():
    out, interval = sys.argv[1], float(sys.argv[sys.argv.index("--interval") + 1]) if "--interval" in sys.argv else 5.0
    stop = threading.Event()
    lock = threading.Lock()
    handle = open(out, "a")

    def write(record):
        with lock:
            handle.write(json.dumps({"t": round(time.time(), 3), **record}) + "\n")
            handle.flush()

    def events():
        since = str(int(time.time()))
        proc = subprocess.Popen(["docker", "events", "--since", since, "--filter", "type=container", "--format", "{{json .}}"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            for line in proc.stdout:
                if stop.is_set():
                    break
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                action = e.get("Action", "")
                if action in EVENT_ACTIONS:
                    attrs = e.get("Actor", {}).get("Attributes", {})
                    name = attrs.get("name", "")
                    write({"kind": "event", "action": action, "name": name, "image": attrs.get("image"),
                           "exit_code": attrs.get("exitCode"), "owner": "worker" if WORKER_PATTERN.match(name) else "other"})
        finally:
            proc.kill()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    write({"kind": "monitor-started", "interval_s": interval, "pid": os.getpid()})
    thread = threading.Thread(target=events, daemon=True)
    thread.start()
    while not stop.is_set():
        write({"kind": "sample", "host": host_sample(), "docker": docker_sample()})
        stop.wait(interval)
    write({"kind": "monitor-stopped"})
    handle.close()


if __name__ == "__main__":
    main()
