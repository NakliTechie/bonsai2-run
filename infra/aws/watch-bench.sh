#!/usr/bin/env bash
# Watch the benchmark box: print new milestone lines as they appear, a heartbeat every 15 min, and every
# terminal state (job FAILED/SUCCEEDED/CANCELLED, box gone). No `set -e`: one flaky ssh must not end the watch.
CLUSTER="${1:-bonsai2-run-bench}"; SKY="${SKY:-$HOME/.cairn-sky-venv/bin/sky}"
seen=""; start=$(date +%s); last_hb=$start
while true; do
  out=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$CLUSTER" '
    cat ~/sky_logs/*/setup*.log ~/sky_logs/*/*/setup*.log 2>/dev/null | grep -E ">>>|humaneval |mbpp |gsm8k |mtbench |L4,"
    cat ~/sky_logs/sky-*/run.log ~/sky_logs/*/*/run.log 2>/dev/null | grep -E "GATE|tok/s|Traceback"
    cat ~/sky_workdir/results/bench-*/evalbox.log 2>/dev/null | grep -E "unit done|FAILED|died|queue empty|EVALBOX DONE|start:"
    echo "PROGRESS $(cat ~/sky_workdir/results/bench-*/*/*/*.jsonl 2>/dev/null | wc -l) rows"' 2>&1)
  rc=$?
  if [ $rc -ne 0 ]; then
    st=$("$SKY" status "$CLUSTER" 2>&1 | grep -E "^$CLUSTER" | awk '{print $NF}')
    echo "SSH_FAIL rc=$rc cluster-status=${st:-GONE}"
  fi
  new=$(comm -13 <(echo "$seen" | grep -v PROGRESS | sort -u) <(echo "$out" | grep -v PROGRESS | sort -u))
  [ -n "$new" ] && echo "$new"
  seen="$out"
  job=$("$SKY" queue "$CLUSTER" 2>/dev/null | awk '$1=="1"' | grep -oE "SUCCEEDED|FAILED[A-Z_]*|CANCELLED")
  [ -n "$job" ] && { echo "JOB $job"; exit 0; }
  now=$(date +%s)
  if [ $((now - last_hb)) -ge 900 ]; then
    echo "CHECK-IN $(( (now - start) / 60 ))m: $(echo "$out" | grep PROGRESS)"
    ssh -o BatchMode=yes -o ConnectTimeout=15 "$CLUSTER" 'cd ~/sky_workdir && rm -rf /tmp/interim && mkdir -p /tmp/interim && cp -r results/bench-*/*-* /tmp/interim/ && ~/venv/bin/python scripts/score.py ~/sets /tmp/interim --speed-only' 2>&1 | grep "^|" | cut -d"|" -f2-9,10,11,13
    last_hb=$now
  fi
  sleep 60
done
