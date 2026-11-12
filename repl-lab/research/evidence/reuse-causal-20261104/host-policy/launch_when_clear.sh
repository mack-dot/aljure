#!/bin/zsh
# Waits for host swap < 90%, then runs the owner's exact causal launch once.
cd /Users/mackianni/aljure/repl-lab || exit 9
HASH=1d5a4db2f5f730eed81664700a4efad64f58daba326a6aa47d2a055b2b0e4546
DEADLINE=$(( $(date +%s) + 55*60 ))
set -a; source var/python-worker.env; set +a
export REPL_LAB_WORKER_IMAGE=sha256:40f003647de0937980e2be1f3e715e17741f4ee84fc39d915191ceab208c233f
export REPL_LAB_WORKER_OUTPUT_BYTES=65536
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
while :; do
  now=$(date +%s)
  if (( now > DEADLINE )); then echo "WATCHER: deadline reached, swap never dropped below 90%; not launched"; exit 4; fi
  frac=$(sysctl -n vm.swapusage | awk '{gsub("M","",$3); gsub("M","",$6); printf "%.3f", $6/$3}')
  echo "$(date '+%H:%M:%S') swap_used_fraction=$frac"
  if (( frac < 0.90 )); then
    echo "WATCHER: swap clear at $frac; launching run_guarded causal --approve $HASH"
    python3 var/host-policy-20261103/run_guarded.py causal --approve "$HASH"
    rc=$?
    echo "WATCHER: run_guarded exit=$rc"
    exit $rc
  fi
  sleep 20
done
