#!/usr/bin/env bash
# Box-side benchmark: one worker per GPU pulls (config, think) units from a queue, runs its own server container
# on its own GPU, and runs every prompt set through scripts/evalrun.py. Resumable; mirrors results to S3.
#   OUT=results/bench-2026-09-24 bash scripts/evalbox.sh
# Extra pass on the same box: set UNITS / *_LIMITS / *_MAX / TAG, and AFTER_LOG=<main evalbox.log> so worker g
# starts only once the main run's worker g reports "queue empty" (never two servers timing on one GPU).
# Top-up pass: TOPUP_MAX=16384 SERVER_CTX=20480 and units "<quant> <mode> on <set>". Each unit waits until all
# CONFIGS finished <set> (TOPUP_N rows), then re-runs the union of their truncated ids into <set>.topup.jsonl.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
MODELS="${MODELS:-$HOME/models}"; IMAGE="${IMAGE:-bonsai2-run:dev}"; OUT="${OUT:-results/bench-$(date +%F)}"
SETS="${SETS:-$HOME/sets}"; S3="${S3:-s3://skypilot-cairn-artifacts/bonsai2-run/$(basename "$OUT")}"
OFF_LIMITS="${OFF_LIMITS:-humaneval:164 mbpp:100 gsm8k:100 mtbench:80}"; ON_LIMITS="${ON_LIMITS:-humaneval:40 mbpp:40 gsm8k:40 mtbench:40}"
OFF_MAX="${OFF_MAX:-1024}"; ON_MAX="${ON_MAX:-4096}"; TAG="${TAG:-}"; AFTER_LOG="${AFTER_LOG:-}"
SERVER_CTX="${SERVER_CTX:-8192}"; TOPUP_MAX="${TOPUP_MAX:-}"; TOPUP_N="${TOPUP_N:-40}"
CONFIGS="${CONFIGS:-PQ2_0-plain PTQ1_0-plain PQ2_0-dflash}"
UNITS="${UNITS:-PQ2_0 plain on;PTQ1_0 plain on;PQ2_0 dflash on;PQ2_0 plain off;PTQ1_0 plain off;PQ2_0 dflash off}"
mkdir -p "$OUT"; log() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/evalbox$TAG.log"; }

# Longest units first so the 4 GPUs finish together (think-on generates ~3x the tokens).
QUEUE="$OUT/.queue$TAG"; [ -f "$QUEUE" ] || tr ';' '\n' <<< "$UNITS" > "$QUEUE"
pop() { flock "$QUEUE.lock" bash -c "head -1 '$QUEUE'; sed -i 1d '$QUEUE'"; }

topup_ids() {  # set -> file of ids truncated by any config (waits for all configs to finish the set)
  local s=$1 f="$OUT/topup-ids/$1.txt" c files=()
  mkdir -p "$OUT/topup-ids"
  for c in $CONFIGS; do
    until [ "$(wc -l < "$OUT/$c/on/$s.jsonl" 2>/dev/null || echo 0)" -ge "$TOPUP_N" ]; do sleep 60; done
    files+=("$OUT/$c/on/$s.jsonl")
  done
  python3 -c "import json,sys; print('\\n'.join(sorted({r['id'] for p in sys.argv[1:] for r in map(json.loads, open(p)) if r['finish'] == 'length'})))" \
    "${files[@]}" > "$f.tmp.$$" && mv "$f.tmp.$$" "$f"
  echo "$f"
}

unit() {  # gpu quant mode think [set]
  local g=$1 q=$2 m=$3 th=$4 port=$((8090 + $1)) name="b2r$1" dir="$OUT/$2-$3/$4" limits mt flag=""
  mkdir -p "$dir"; [ "$th" = on ] && { limits=$ON_LIMITS; flag="--think"; mt=$ON_MAX; } || { limits=$OFF_LIMITS; mt=$OFF_MAX; }
  local d=()   # mode -> container env; the dir name keeps the mode, so every mode is its own config in score.py
  case "$m" in
    plain)    d=(-e DRAFT=) ;;
    dflash|dflashrep) d=() ;;
    dflashn3) d=(-e DRAFT_N_MAX=3) ;;
    zlab)     d=(-e DRAFT=Qwen3.8-27B-DFlash2-Q4_K_M.gguf) ;;
    ngram)    d=(-e DRAFT= -e "EXTRA_ARGS=--spec-type ngram-mod") ;;
  esac
  docker rm -f "$name" >/dev/null 2>&1
  docker run -d --name "$name" --gpus "device=$g" --shm-size=16g -p "$port:8080" -v "$MODELS":/mnt/gcs:ro \
    -e TARGET="Ternary-Bonsai-2-27B-$q.gguf" -e CTX="$SERVER_CTX" "${d[@]}" "$IMAGE" >/dev/null
  until curl -sf "localhost:$port/health" >/dev/null; do
    docker ps -q -f "name=^$name$" | grep -q . || { log "gpu$g $q-$m-$th: server died"; docker logs "$name" > "$dir/server.log" 2>&1; return 1; }
    sleep 1
  done
  if [ -n "$TOPUP_MAX" ]; then
    local ids; ids=$(topup_ids "$5")
    log "gpu$g $q-$m-$th: top-up $5 ($(grep -c . "$ids") ids, max $TOPUP_MAX)"
    python3 scripts/evalrun.py "http://localhost:$port" "$SETS/$5.jsonl" "$dir/$5.topup.jsonl" --ids "$ids" \
      --limit "$TOPUP_N" --max-tokens "$TOPUP_MAX" --think 2>>"$dir/errors.log" || log "gpu$g $q-$m-$th: top-up $5 FAILED rc=$?"
    limits=""
  fi
  for sl in $limits; do   # set:n[:max_tokens]
    local sn n smt; IFS=: read -r sn n smt <<< "$sl"
    log "gpu$g $q-$m-$th: $sn (n=$n, max ${smt:-$mt})"
    python3 scripts/evalrun.py "http://localhost:$port" "$SETS/$sn.jsonl" "$dir/$sn.jsonl" \
      --limit "$n" --max-tokens "${smt:-$mt}" $flag 2>>"$dir/errors.log" || log "gpu$g $q-$m-$th: $sn FAILED rc=$?"
  done
  docker logs "$name" > "$dir/server.log" 2>&1; docker rm -f "$name" >/dev/null
  log "gpu$g $q-$m-$th: unit done"
}

worker() {
  local g=$1 u
  [ -z "$AFTER_LOG" ] || until grep -q "gpu$g: queue empty" "$AFTER_LOG"; do sleep 30; done
  while u=$(pop) && [ -n "$u" ]; do unit "$g" $u; done; log "gpu$g: queue empty"
}

( while true; do sleep 300; aws s3 sync "$OUT" "$S3" --only-show-errors; done ) & SYNC=$!
n=$(nvidia-smi -L | wc -l); log "start: $n GPUs, image $IMAGE"
pids=(); for ((g = 0; g < n; g++)); do worker "$g" & pids+=($!); done
wait "${pids[@]}"
kill "$SYNC" 2>/dev/null; aws s3 sync "$OUT" "$S3" --only-show-errors
log "EVALBOX DONE"
