#!/bin/zsh
cd /Users/mackianni/aljure/repl-lab || exit 9
HASH=135230e46c5c5d2f0de75d491d954d2e4379c8693cd0afde4aaeae4a9b5d1d83
DEADLINE=$(( $(date +%s) + 360*60 ))
set -a; source var/worker.env; source var/prime-worker.env; set +a
export REPL_LAB_WORKER_OUTPUT_BYTES=65536
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
while :; do
  now=$(date +%s)
  if (( now > DEADLINE )); then echo "WATCHER: deadline reached; swap never dropped below 88%; not launched"; exit 4; fi
  frac=$(sysctl -n vm.swapusage | awk '{gsub("M","",$3); gsub("M","",$6); printf "%.3f", $6/$3}')
  echo "$(date '+%H:%M:%S') swap_used_fraction=$frac"
  if (( frac < 0.88 )); then
    echo "WATCHER: swap clear at $frac; launching run_guarded verify --approve $HASH"
    python3 var/host-policy-20261103/run_guarded.py verify --approve "$HASH"
    rc=$?
    echo "WATCHER: run_guarded exit=$rc"
    if (( rc == 2 )); then echo "WATCHER: gate refused; waiting 60 s and retrying"; sleep 60; continue; fi
    exit $rc
  fi
  sleep 20
done
