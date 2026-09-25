#!/usr/bin/env bash
# bonsai2-run: scale-to-zero Cloud Run GPU deploy of Ternary-Bonsai-2-27B + DFlash2 drafter.
#   ./deploy.sh status | build | stage | deploy | bench | sweep | down
# First deploy: ./deploy.sh build && STAGE_VIA=cloudbuild BUCKET=<name> ./deploy.sh stage && BUCKET=<name> ./deploy.sh deploy
# Every verb ends with one `verdict=<CODE> next=<command>` line and the matching exit code (SPEC.md §0).
set -uo pipefail
cd "$(dirname "$0")" || exit 2

BUCKET="${BUCKET:-}"
REGION="${REGION:-asia-southeast1}"                 # L4 quota approved (2026-09-25): asia-southeast1 us-east4 europe-west4 europe-west1
SERVICE="${SERVICE:-bonsai2}"
IMAGE="${IMAGE:-}"                                  # default: $REGION-docker.pkg.dev/$PROJECT/bonsai2/bonsai2-run:latest
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"                   # or nvidia-rtx-pro-6000 (needs CPU=20 MEMORY=80Gi)
CPU="${CPU:-8}"; MEMORY="${MEMORY:-32Gi}"; CONCURRENCY="${CONCURRENCY:-4}"
PREFIX="${PREFIX:-bonsai2}"
TARGET="${TARGET:-Ternary-Bonsai-2-27B-PQ2_0.gguf}"
DRAFT="${DRAFT-Qwen3.8-27B-DFlash2-r3-Q4_K_M.gguf}"
TARGET_REPO=prism-ml/Ternary-Bonsai-2-27B-gguf; DRAFT_REPO=naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2
ENV_EXTRA="${ENV_EXTRA:-}"                          # extra entrypoint knobs, e.g. CTX=32768,DRAFT_N_MAX=5

verdict() { echo "verdict=$1 next=$2"; exit "$3"; }
step() { echo "[$(date +%T)] $*"; }

preflight() {
  command -v gcloud >/dev/null || verdict NO_GCLOUD "brew install --cask google-cloud-sdk && gcloud auth login" 10
  PROJECT="$(gcloud config get-value project 2>/dev/null)"
  [ -n "$PROJECT" ] || verdict NO_PROJECT "gcloud config set project <id>" 11
  IMAGE="${IMAGE:-$REGION-docker.pkg.dev/$PROJECT/bonsai2/bonsai2-run:latest}"
}
need_bucket() { [ -n "$BUCKET" ] || verdict NO_BUCKET "BUCKET=<name> ./deploy.sh stage" 12; }
objects() { gcloud storage ls -l "gs://$BUCKET/$PREFIX/" 2>/dev/null | awk '$1 ~ /^[0-9]+$/ {n=split($3,p,"/"); print p[n], $1}'; }
files() { echo "$TARGET"; [ -z "$DRAFT" ] || echo "$DRAFT"; }

cmd_status() {
  preflight
  local svc objs; svc="$(gcloud run services describe "$SERVICE" --region "$REGION" --format=json 2>/dev/null || true)"
  objs="$( [ -n "$BUCKET" ] && objects || true)"
  python3 - "$svc" "$objs" "$(files)" <<'PY'
import json, sys
svc = json.loads(sys.argv[1]) if sys.argv[1].strip() else None
objs = dict(l.split() for l in sys.argv[2].splitlines() if l.strip())
want = [f for f in sys.argv[3].splitlines() if f]
out = {"deployed": bool(svc), "weights": {f: int(objs[f]) if f in objs else None for f in want}}
if svc:
    tpl = svc["spec"]["template"]; ann = tpl["metadata"].get("annotations", {})
    c = tpl["spec"]["containers"][0]
    out.update(url=svc["status"].get("url"), ready_revision=svc["status"].get("latestReadyRevisionName"),
               image=c["image"], gpu=tpl["spec"].get("nodeSelector", {}).get("run.googleapis.com/accelerator"),
               min=ann.get("autoscaling.knative.dev/minScale", "0"), max=ann.get("autoscaling.knative.dev/maxScale"))
print(json.dumps(out))
PY
  [ -n "$svc" ] || verdict NOT_DEPLOYED "./deploy.sh deploy" 16
  verdict OK "./deploy.sh bench" 0
}

cmd_build() {  # image on Cloud Build (global pool: new accounts can't use E2_HIGHCPU_32 in regional pools)
  preflight
  gcloud artifacts repositories describe bonsai2 --location="$REGION" >/dev/null 2>&1 || {
    step "create Artifact Registry repo bonsai2 in $REGION"
    gcloud artifacts repositories create bonsai2 --repository-format=docker --location="$REGION" >/dev/null || verdict BUILD_FAILED "check Artifact Registry API/permissions" 17
  }
  step "build $IMAGE (Cloud Build, ~16 min)"
  gcloud builds submit --config infra/gcp/cloudbuild-image.yaml --substitutions "_IMAGE=$IMAGE" . 2>&1 | tail -3
  [ "${PIPESTATUS[0]}" = 0 ] || verdict BUILD_FAILED "gcloud builds list --limit 3" 17
  verdict OK "STAGE_VIA=cloudbuild BUCKET=<name> ./deploy.sh stage" 0
}

cmd_stage() {
  preflight; need_bucket
  gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || {
    step "create gs://$BUCKET in $REGION"
    gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access >/dev/null || verdict NO_BUCKET "check bucket name/permissions" 12
  }
  if [ "${STAGE_VIA:-local}" = cloudbuild ]; then   # download from HF inside GCP: no local upload
    step "stage via Cloud Build (infra/gcp/cloudbuild-stage.yaml)"
    gcloud builds submit --region="$REGION" --no-source --config infra/gcp/cloudbuild-stage.yaml \
      --substitutions "_BUCKET=$BUCKET,_PREFIX=$PREFIX" >/dev/null || verdict WEIGHTS_MISSING "gcloud builds list --region $REGION" 13
    verdict OK "./deploy.sh deploy" 0
  fi
  local have tmp; have="$(objects)"; tmp="${TMPDIR:-/tmp}/bonsai2-stage"; mkdir -p "$tmp"
  for f in $(files); do
    if echo "$have" | grep -q "^$f "; then step "skip $f (present, $(echo "$have" | awk -v f="$f" '$1==f{print $2}') bytes)"; continue; fi
    repo=$TARGET_REPO; [ "$f" = "$DRAFT" ] && repo=$DRAFT_REPO
    step "download $repo/$f"; hf download "$repo" "$f" --local-dir "$tmp" >/dev/null || verdict WEIGHTS_MISSING "pip install -U huggingface_hub, then re-run ./deploy.sh stage" 13
    step "upload gs://$BUCKET/$PREFIX/$f"; gcloud storage cp "$tmp/$f" "gs://$BUCKET/$PREFIX/$f" || verdict WEIGHTS_MISSING "re-run ./deploy.sh stage" 13
  done
  verdict OK "./deploy.sh deploy" 0
}

cmd_deploy() {
  preflight; need_bucket
  local have; have="$(objects)"
  for f in $(files); do echo "$have" | grep -q "^$f " || verdict WEIGHTS_MISSING "./deploy.sh stage" 13; done
  step "deploy $SERVICE ($GPU_TYPE, $CPU vCPU, $MEMORY, min 0 / max 1) image $IMAGE"
  gcloud beta run deploy "$SERVICE" \
    --region="$REGION" --image="$IMAGE" \
    --gpu=1 --gpu-type="$GPU_TYPE" --no-gpu-zonal-redundancy \
    --cpu="$CPU" --memory="$MEMORY" --no-cpu-throttling \
    --concurrency="$CONCURRENCY" --min-instances=0 --max-instances=1 --port=8080 --timeout=900 \
    --network=default --subnet=default --vpc-egress=all-traffic \
    --add-volume="name=weights,type=cloud-storage,bucket=$BUCKET,readonly=true,mount-options=enable-buffered-read=true" \
    --add-volume-mount=volume=weights,mount-path=/mnt/gcs \
    --startup-probe=httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=1,periodSeconds=1,timeoutSeconds=1,failureThreshold=240 \
    --set-env-vars="MODEL_DIR=/mnt/gcs/$PREFIX,TARGET=$TARGET,DRAFT=$DRAFT${ENV_EXTRA:+,$ENV_EXTRA}" \
    --no-allow-unauthenticated --quiet 2>&1 | tail -20
  [ "${PIPESTATUS[0]}" = 0 ] || verdict DEPLOY_FAILED "gcloud run services logs read $SERVICE --region $REGION --limit 50" 14
  verdict OK "./deploy.sh bench" 0
}

cmd_bench() {
  preflight
  local url; url="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null)"
  [ -n "$url" ] || verdict NOT_DEPLOYED "./deploy.sh deploy" 16
  local out tok; out="results/cloudrun-$GPU_TYPE-$(date +%F-%H%M)"; mkdir -p "$out"; tok="$(gcloud auth print-identity-token)"
  step "health (cold start if scaled to zero)"
  local t0=$SECONDS; curl -sf -m 600 -H "Authorization: Bearer $tok" "$url/health" >/dev/null || verdict UNHEALTHY "gcloud run services logs read $SERVICE --region $REGION --limit 50" 15
  step "first /health 200 after $((SECONDS - t0))s" | tee "$out/cold.txt"
  python3 scripts/bench.py run "$url" "$out/bench.jsonl" --token "$tok" || verdict UNHEALTHY "gcloud run services logs read $SERVICE --region $REGION --limit 50" 15
  verdict OK "cat $out/bench.jsonl" 0
}

cmd_sweep() {  # DFlash2 draft length x confidence floor on one warm instance; per-request, no redeploy
  preflight
  local url out tok n p; url="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null)"
  [ -n "$url" ] || verdict NOT_DEPLOYED "./deploy.sh deploy" 16
  out="results/sweep-$GPU_TYPE-$(date +%F-%H%M)"; mkdir -p "$out"; tok="$(gcloud auth print-identity-token)"
  for n in ${SWEEP_N_MAX:-1 2 3 5 7}; do for p in ${SWEEP_P_MIN:-0.0 0.5}; do
    step "n_max=$n p_min=$p"
    python3 scripts/bench.py run "$url" "$out/n$n-p$p.jsonl" --token "$tok" --n-max "$n" --p-min "$p" \
      || verdict UNHEALTHY "gcloud run services logs read $SERVICE --region $REGION --limit 50" 15
  done; done
  verdict OK "ls $out" 0
}

cmd_down() {
  preflight
  gcloud run services delete "$SERVICE" --region "$REGION" --quiet >/dev/null 2>&1 || verdict NOT_DEPLOYED "nothing to delete" 16
  verdict OK "./deploy.sh deploy   # bucket gs://$BUCKET kept; delete it with gcloud storage rm -r" 0
}

case "${1:-status}" in
  status|build|stage|deploy|bench|sweep|down) "cmd_$1" ;;
  *) echo "usage: ./deploy.sh status|build|stage|deploy|bench|sweep|down"; exit 2 ;;
esac
