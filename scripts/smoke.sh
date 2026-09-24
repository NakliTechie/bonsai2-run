#!/usr/bin/env bash
# Box-side smoke of the built image on one CUDA GPU: for each target GGUF, start the container plain and with
# DFlash2, time start -> /health 200, run the greedy bench, and diff plain vs DFlash2 outputs.
#   MODELS=~/models IMAGE=bonsai2-run:dev bash scripts/smoke.sh [PTQ1_0 PQ2_0]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
MODELS="${MODELS:-$HOME/models}"; IMAGE="${IMAGE:-bonsai2-run:dev}"; OUT="${OUT:-results/smoke-$(date +%F)}"
mkdir -p "$OUT"; quants=("${@:-PTQ1_0}")
log() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/smoke.log"; }
log "GPU: $(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader)"

serve() {  # name, extra docker env...; prints seconds to /health 200
  local name=$1; shift
  docker rm -f b2r >/dev/null 2>&1
  local t0; t0=$(date +%s.%N)
  docker run -d --name b2r --gpus all --shm-size=16g -p 8080:8080 -v "$MODELS":/mnt/gcs:ro "$@" "$IMAGE" >/dev/null
  for _ in $(seq 1 600); do
    curl -sf localhost:8080/health >/dev/null 2>&1 && { echo "$(date +%s.%N) - $t0" | bc; docker logs b2r > "$OUT/$name.server.log" 2>&1; return 0; }
    docker ps -q -f name=b2r | grep -q . || break
    sleep 0.25
  done
  docker logs b2r > "$OUT/$name.server.log" 2>&1; echo FAIL; return 1
}

for q in "${quants[@]}"; do
  T="Ternary-Bonsai-2-27B-$q.gguf"
  for mode in plain dflash; do
    name="$q-$mode"; [ $mode = plain ] && d=(-e DRAFT=) || d=()
    s=$(serve "$name" -e TARGET="$T" "${d[@]}") || { log "$name: server did not reach /health (see $OUT/$name.server.log)"; continue; }
    log "$name: ready in ${s}s (local disk -> /dev/shm -> GPU)"
    python3 scripts/bench.py run http://localhost:8080 "$OUT/$name.jsonl" | tee -a "$OUT/smoke.log"
    nvidia-smi --query-gpu=memory.used --format=csv,noheader | sed "s/^/[$name] vram used: /" | tee -a "$OUT/smoke.log"
    docker logs b2r > "$OUT/$name.server.log" 2>&1
  done
  python3 scripts/bench.py diff "$OUT/$q-plain.jsonl" "$OUT/$q-dflash.jsonl" | tee -a "$OUT/smoke.log"
done
docker rm -f b2r >/dev/null 2>&1
log "SMOKE DONE"
