#!/usr/bin/env bash
# Box-side benchmark: one worker per GPU pulls (config, think) units from a queue, runs its own server container
# on its own GPU, and runs every prompt set through scripts/evalrun.py. Resumable; mirrors results to S3.
#   OUT=results/bench-2026-09-24 bash scripts/evalbox.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
MODELS="${MODELS:-$HOME/models}"; IMAGE="${IMAGE:-bonsai2-run:dev}"; OUT="${OUT:-results/bench-$(date +%F)}"
SETS="${SETS:-$HOME/sets}"; S3="${S3:-s3://skypilot-cairn-artifacts/bonsai2-run/$(basename "$OUT")}"
OFF_LIMITS="humaneval:164 mbpp:100 gsm8k:100 mtbench:80"; ON_LIMITS="humaneval:40 mbpp:40 gsm8k:40 mtbench:40"
mkdir -p "$OUT"; log() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/evalbox.log"; }

# Longest units first so the 4 GPUs finish together (think-on generates ~3x the tokens).
QUEUE="$OUT/.queue"; [ -f "$QUEUE" ] || printf '%s\n' \
  "PQ2_0 plain on" "PTQ1_0 plain on" "PQ2_0 dflash on" "PQ2_0 plain off" "PTQ1_0 plain off" "PQ2_0 dflash off" > "$QUEUE"
pop() { flock "$QUEUE.lock" bash -c "head -1 '$QUEUE'; sed -i 1d '$QUEUE'"; }

unit() {  # gpu quant mode think
  local g=$1 q=$2 m=$3 th=$4 port=$((8090 + $1)) name="b2r$1" dir="$OUT/$2-$3/$4" limits mt flag=""
  mkdir -p "$dir"; [ "$th" = on ] && { limits=$ON_LIMITS; flag="--think"; mt=4096; } || { limits=$OFF_LIMITS; mt=1024; }
  local d=(); [ "$m" = plain ] && d=(-e DRAFT=)
  docker rm -f "$name" >/dev/null 2>&1
  docker run -d --name "$name" --gpus "device=$g" --shm-size=16g -p "$port:8080" -v "$MODELS":/mnt/gcs:ro \
    -e TARGET="Ternary-Bonsai-2-27B-$q.gguf" -e CTX=8192 "${d[@]}" "$IMAGE" >/dev/null
  until curl -sf "localhost:$port/health" >/dev/null; do
    docker ps -q -f "name=^$name$" | grep -q . || { log "gpu$g $q-$m-$th: server died"; docker logs "$name" > "$dir/server.log" 2>&1; return 1; }
    sleep 1
  done
  for sl in $limits; do
    log "gpu$g $q-$m-$th: ${sl%%:*} (n=${sl##*:})"
    python3 scripts/evalrun.py "http://localhost:$port" "$SETS/${sl%%:*}.jsonl" "$dir/${sl%%:*}.jsonl" \
      --limit "${sl##*:}" --max-tokens "$mt" $flag 2>>"$dir/errors.log" || log "gpu$g $q-$m-$th: ${sl%%:*} FAILED rc=$?"
  done
  docker logs "$name" > "$dir/server.log" 2>&1; docker rm -f "$name" >/dev/null
  log "gpu$g $q-$m-$th: unit done"
}

worker() { local g=$1 u; while u=$(pop) && [ -n "$u" ]; do unit "$g" $u; done; log "gpu$g: queue empty"; }

( while true; do sleep 300; aws s3 sync "$OUT" "$S3" --only-show-errors; done ) & SYNC=$!
n=$(nvidia-smi -L | wc -l); log "start: $n GPUs, image $IMAGE"
pids=(); for ((g = 0; g < n; g++)); do worker "$g" & pids+=($!); done
wait "${pids[@]}"
kill "$SYNC" 2>/dev/null; aws s3 sync "$OUT" "$S3" --only-show-errors
log "EVALBOX DONE"
