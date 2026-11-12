#!/bin/zsh
cd /Users/mackianni/aljure/repl-lab || exit 9
HASH=62ac8890430e87b04d7e5aea1c7e0d8b3fe5e21424775c1534e03aac5df0b385
DEADLINE=$(( $(date +%s) + 90*60 ))
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
    echo "WATCHER: swap clear at $frac; launching run_guarded h2h-b --approve $HASH"
    python3 var/host-policy-20261103/run_guarded.py h2h-b --approve "$HASH"
    rc=$?
    echo "WATCHER: run_guarded exit=$rc"
    if (( rc == 2 )); then echo "WATCHER: gate refused; waiting 60 s and retrying"; sleep 60; continue; fi
    exit $rc
  fi
  sleep 20
done
