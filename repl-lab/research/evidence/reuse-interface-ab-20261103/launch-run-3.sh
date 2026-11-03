#!/bin/zsh
set -u
cd /Users/mackianni/aljure/repl-lab || exit 97
LOG=/private/tmp/claude-501/-Users-mackianni-aljure/74ec6d75-ae20-42d9-8d9d-1bbeec4ab140/scratchpad/run-3.log
# One launch only: a second invocation of this script is a no-op.
mkdir var/reuse-interface-20261103/.run-3.lock 2>/dev/null || { echo "$(date +%T) duplicate invocation refused" >> "$LOG"; exit 98; }
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
export REPL_LAB_WORKER_IMAGE=sha256:40f003647de0937980e2be1f3e715e17741f4ee84fc39d915191ceab208c233f
export REPL_LAB_PRIME_IMAGE=sha256:f3e30aaa1ce3de92d381f05f597e84f9d1738a15c4a6453fdbd13bd4739446ad
export REPL_LAB_WORKER_OUTPUT_BYTES=65536
echo "$(date +%T) wake engine" >> "$LOG"
docker run --rm "$REPL_LAB_WORKER_IMAGE" true >> "$LOG" 2>&1
for i in {1..45}; do
  st=$(docker desktop status 2>/dev/null | awk '$1=="Status"{print $2}')
  echo "$(date +%T) desktop status: $st" >> "$LOG"
  [ "$st" = "running" ] && break
  sleep 2
done
[ "$st" = "running" ] || { echo "$(date +%T) engine never reported running; no launch" >> "$LOG"; exit 99; }
[ -z "$(git status --porcelain)" ] || { echo "$(date +%T) tree dirty; no launch" >> "$LOG"; exit 96; }
echo "$(date +%T) launching run-3" >> "$LOG"
python3 -m benchmark.reuse_interface run --suite var/reuse-interface-20261103/suite --plan var/reuse-interface-20261103/plan.json --out var/reuse-interface-20261103/run-3 --authorize-subscription-plan 40db9df9422121aa53779bb27461076858530f18078fe1510803b0dd85f45ce4 >> "$LOG" 2>&1
echo "$(date +%T) runner exit=$?" >> "$LOG"
