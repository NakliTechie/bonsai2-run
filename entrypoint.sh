#!/usr/bin/env bash
# Stage the GGUFs from the GCS FUSE mount into /dev/shm with parallel range reads, warm the CUDA
# libraries into the page cache at the same time, then exec llama-server with the DFlash2 drafter.
# Every knob is an env var so deploy.sh and the smoke test drive the same image.
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/mnt/gcs}"
TARGET="${TARGET:-Ternary-Bonsai-2-27B-PQ2_0.gguf}"                # with DFlash2, PQ2_0 beats PTQ1_0 on all 3 prompts on L4 (results/smoke-2026-09-24)
DRAFT="${DRAFT-Qwen3.8-27B-DFlash2-r3-Q4_K_M.gguf}"   # empty string = plain decode, no speculation
COPY_TO_SHM="${COPY_TO_SHM:-1}"                        # 0 = read straight from MODEL_DIR
COPY_STREAMS="${COPY_STREAMS:-8}"                      # parallel range reads per file
CTX="${CTX:-16384}"
PARALLEL="${PARALLEL:-1}"
DRAFT_N_MAX="${DRAFT_N_MAX:-7}"
PORT="${PORT:-8080}"

us() { echo "${EPOCHREALTIME/./}"; }
t0=$(us)
log() { local d=$(( $(us) - t0 )); printf '[bonsai2-run +%d.%03ds] %s\n' $((d / 1000000)) $((d / 1000 % 1000)) "$*"; }

# Copy one file as COPY_STREAMS concurrent byte ranges; a single FUSE stream does not saturate VPC egress.
stage() {
  local src="$1" dst="$2" size chunk i
  size=$(stat -c %s "$src"); chunk=$(( (size + COPY_STREAMS - 1) / COPY_STREAMS ))
  truncate -s "$size" "$dst"
  for ((i = 0; i < COPY_STREAMS; i++)); do
    dd if="$src" of="$dst" bs=16M iflag=skip_bytes,count_bytes oflag=seek_bytes conv=notrunc,nocreat \
       skip=$(( i * chunk )) seek=$(( i * chunk )) count="$chunk" status=none &
  done
  wait
  [ "$(stat -c %s "$dst")" = "$size" ] || { echo "stage: size mismatch on $dst" >&2; return 1; }
}

files=("$TARGET"); [ -n "$DRAFT" ] && files+=("$DRAFT")
for f in "${files[@]}"; do [ -f "$MODEL_DIR/$f" ] || { echo "missing $MODEL_DIR/$f" >&2; exit 1; }; done

# Page-cache the server binary and CUDA runtime libs while the weights stream (djev-run's rootfs prefetch).
( cat /app/llama-server /usr/local/cuda/lib64/libcublas*.so* /usr/local/cuda/lib64/libcudart*.so* >/dev/null 2>&1 || true ) &

WDIR="$MODEL_DIR"
if [ "$COPY_TO_SHM" = 1 ]; then
  WDIR=/dev/shm/models; mkdir -p "$WDIR"
  log "staging ${files[*]} -> $WDIR ($COPY_STREAMS streams/file)"
  pids=(); for f in "${files[@]}"; do stage "$MODEL_DIR/$f" "$WDIR/$f" & pids+=($!); done
  for p in "${pids[@]}"; do wait "$p"; done
  log "staged $(du -sh "$WDIR" | cut -f1)"
fi
wait

args=(-m "$WDIR/$TARGET" -ngl 999 -fa on -c "$CTX" -np "$PARALLEL" --host 0.0.0.0 --port "$PORT"
      --no-warmup --metrics --jinja)
if [ -n "$DRAFT" ]; then
  args+=(-md "$WDIR/$DRAFT" --spec-type draft-dflash --spec-draft-n-max "$DRAFT_N_MAX" -ngld 999)
fi
# shellcheck disable=SC2206
args+=(${EXTRA_ARGS:-})
log "exec llama-server ${args[*]}"
exec /app/llama-server "${args[@]}"
