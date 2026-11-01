#!/bin/zsh
# Program pilot: plans A (direct tools) and B (program_run), two runs each, serially, from the
# checkout pinned at the freeze commit 0c44178. Operator authorized the exact hashes 2026-10-30.
# Stops: daemon down, < 10 GB free, pinned image missing, spend > $25 known or any unknown
# reservation, any stop-signal failure or unknown provider outcome in a finished run.
set -u
cd /Users/mackianni/aljure-program-pilot/repl-lab || exit 1
SUITE=var/official/service-sim-s1
OUT=var/program-pilot/runs
LOG=var/program-pilot/logs
mkdir -p $OUT $LOG
source var/worker.env
source var/prime-worker.env
unset ANTHROPIC_API_KEY CLAUDE_API_KEY ANTHROPIC_AUTH_TOKEN
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
typeset -A SHA
SHA[A]=9090d1c3f0c34fe2dda8c2d2b4a979af436d9a29a8c876dcd897099479e670f6
SHA[B]=c67f6ab9b21fb87634a0b87e59e10e8885708a7059cf52bbc20052d79abbe888
[ "$(git rev-parse HEAD)" = 0c44178308ad9660cd4003fedba681305e76768a ] && [ -z "$(git status --porcelain)" ] || { echo "STOPPED: checkout is not clean 0c44178"; exit 1; }
timeout 20 docker version --format '{{.Server.Version}}' >/dev/null 2>&1 || { echo "STOPPED: docker daemon not answering"; exit 5; }
free_gb=$(df -g /Users/mackianni | awk 'NR==2{print $4}'); [ "$free_gb" -ge 7 ] || { echo "STOPPED: only ${free_gb} GB free"; exit 5; }
for img in "$REPL_LAB_WORKER_IMAGE" "$REPL_LAB_PRIME_IMAGE"; do
  timeout 20 docker image inspect "$img" --format '{{.Id}}' >/dev/null 2>&1 || { echo "STOPPED: pinned image missing: $img"; exit 6; }
done
echo "$(date +%H:%M:%S) images present; free ${free_gb} GB"
for arm in A B; do
  PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark paired-preflight --suite $SUITE --plan var/program-pilot/plan-$arm.json > $LOG/preflight-$arm.json 2> $LOG/preflight-$arm.err \
    && python3 -c "import json,sys; p=json.load(open('$LOG/preflight-$arm.json')); sys.exit(0 if p.get('ready') is True and p['plan_sha256']=='${SHA[$arm]}' else 1)" \
    || { echo "STOPPED: preflight $arm not ready"; cat $LOG/preflight-$arm.json | head -c 800; exit 7; }
done
echo "$(date +%H:%M:%S) preflight ready for A and B"
spend() {
  PYTHONDONTWRITEBYTECODE=1 python3 -c "
import glob
from benchmark.paired import account
from benchmark.oolong import jsonl
known, unknown = 0.0, 0.0
for results in glob.glob('$OUT/*/results.jsonl'):
    run = results.rsplit('/', 1)[0]
    for row in jsonl(results):
        u = account(list(jsonl(run + '/' + row['usage_path'])), row['pricing_usd_per_m'])
        known += float(u['known_model_cost_usd']); unknown += float(u['reserved_unknown_usd'])
print(f'{known:.6f} {unknown:.6f}')"
}
check_run() {
  PYTHONDONTWRITEBYTECODE=1 python3 -c "
import json, sys
from benchmark.oolong import jsonl
run = '$1'
rows = list(jsonl(run + '/results.jsonl'))
report = json.load(open(run + '/report.json'))
bad = [(r['task_id'], r['failure']) for r in rows if r.get('failure') not in (None, 'NativeCompletionMissing')]
unknown = [r['task_id'] for r in rows for u in jsonl(run + '/' + r['usage_path']) if u.get('status') == 'unknown']
print('rows', len(rows), 'completed', sum(r['status'] == 'completed' for r in rows), 'stop-signals', bad, 'unknown', unknown)
sys.exit(0 if len(rows) == 18 and not bad and not unknown and report.get('suite_sha256') else 3)"
}
for pair in A:1 B:1 A:2 B:2; do
  arm=${pair%%:*}; n=${pair##*:}; name=program-$arm-r$n
  # Resume: a run that already finished and passed its checks is kept as is, never re-run.
  if [ -f $OUT/$name/report.json ] && check_run $OUT/$name >/dev/null 2>&1; then echo "$(date +%H:%M:%S) SKIP $name (complete)"; continue; fi
  [ -e $OUT/$name ] && { echo "STOPPED: $name exists but is incomplete; preserve it and decide"; exit 8; }
  read known unknown <<< "$(spend)"
  echo "$(date +%H:%M:%S) spend before $name: known \$$known unknown \$$unknown"
  if python3 -c "import sys; sys.exit(0 if float('$unknown') == 0 and float('$known') <= 25 else 1)"; then :; else
    echo "STOPPED: spend above \$25 or unknown reservations before $name"; exit 4; fi
  free_gb=$(df -g /Users/mackianni | awk 'NR==2{print $4}'); [ "$free_gb" -ge 6 ] || { echo "STOPPED: only ${free_gb} GB free before $name"; exit 5; }
  echo "$(date +%H:%M:%S) START $name plan ${SHA[$arm]}"
  python3 -m benchmark paired-run --suite $SUITE --plan var/program-pilot/plan-$arm.json --out $OUT/$name \
    --authorize-subscription-plan ${SHA[$arm]} > $LOG/$name.log 2>&1
  code=$?
  echo "$(date +%H:%M:%S) END $name exit=$code"
  if [ $code -ne 0 ]; then echo "STOPPED at $name"; tail -c 1500 $LOG/$name.log; exit $code; fi
  check_run $OUT/$name || { echo "STOPPED: stop signal or unknown outcome in $name"; exit 3; }
done
read known unknown <<< "$(spend)"
echo "PROGRAM PILOT COMPLETE spend known \$$known unknown \$$unknown"
