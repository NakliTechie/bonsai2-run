#!/usr/bin/env bash
# Ternary Bonsai 2 27B + DFlash2 on Google Cloud Run: one NVIDIA L4, OpenAI- and Anthropic-compatible API, $0 when idle.
# Run it in Cloud Shell (already signed in) or anywhere with gcloud:
#   curl -fsSL https://raw.githubusercontent.com/NakliTechie/bonsai2-run/main/cloudrun/bonsai2-cloudrun.sh | bash
# Knobs (env): PROJECT (default: current gcloud project), REGION (default: first region with L4 quota),
#   SERVICE=bonsai2, BUCKET=<project>-bonsai2, IMAGE=ghcr.io/naklitechie/bonsai2-run:latest,
#   PROFILE=code|chat (code: draft 7 + prompt lookup; chat: draft 3), DOWN=1 (delete the service and bucket).
# Needs: a billing account on the project. A Free Trial account must be upgraded to paid first
# (Google keeps the unused credit; GPUs and quota increases are blocked during the trial).
set -euo pipefail

SERVICE="${SERVICE:-bonsai2}"
IMAGE="${IMAGE:-ghcr.io/naklitechie/bonsai2-run:latest}"
PROFILE="${PROFILE:-code}"
REGIONS="${REGIONS:-asia-southeast1 us-east4 europe-west4 europe-west1 us-central1}"   # Cloud Run L4 regions
QUOTA_ID=NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion
TARGET=Ternary-Bonsai-2-27B-PQ2_0.gguf; DRAFT=Qwen3.8-27B-DFlash2-r3-Q4_K_M.gguf

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not found. Open https://shell.cloud.google.com and run this there."
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
[ -n "$PROJECT" ] || die "No project. Run: gcloud config set project <your-project-id>   (or PROJECT=<id> before this script)"
gcloud config set project "$PROJECT" >/dev/null 2>&1
BUCKET="${BUCKET:-$PROJECT-bonsai2}"

if [ "${DOWN:-0}" = 1 ]; then
  say "Deleting service $SERVICE and bucket gs://$BUCKET"
  for r in $REGIONS; do gcloud run services delete "$SERVICE" --region "$r" --quiet >/dev/null 2>&1 && echo "deleted $SERVICE in $r"; done
  gcloud storage rm -r "gs://$BUCKET" --quiet >/dev/null 2>&1 && echo "deleted gs://$BUCKET"
  exit 0
fi

say "Project $PROJECT: billing"
[ "$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null)" = True ] || {
  ACCT=$(gcloud billing accounts list --filter=open=true --format='value(name)' --limit 1)
  [ -n "$ACCT" ] || die "No open billing account. Create one at https://console.cloud.google.com/billing"
  echo "linking billing account $ACCT"; gcloud billing projects link "$PROJECT" --billing-account "$ACCT" >/dev/null
}

say "Enabling APIs (1-2 min the first time)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com storage.googleapis.com compute.googleapis.com \
  cloudquotas.googleapis.com >/dev/null
gcloud components list --filter=id=beta --format='value(state.name)' 2>/dev/null | grep -q Installed \
  || gcloud components install beta --quiet >/dev/null 2>&1 || true   # Cloud Shell already has it

say "Finding a region with Cloud Run L4 quota"
granted() { gcloud beta quotas info describe "$QUOTA_ID" --service=run.googleapis.com --project="$PROJECT" --format=json 2>/dev/null |
  python3 -c "import json,sys; d=json.load(sys.stdin); print(max([int(x['details'].get('value',0)) for x in d.get('dimensionsInfos',[]) if x.get('dimensions',{}).get('region')=='$1'] or [0]))"; }
request() {  # file a 1-GPU request for region $1; retries while a new project's IAM is still propagating
  local out
  for _ in 1 2 3 4 5 6 7 8 9; do
    out=$(gcloud beta quotas preferences create --service=run.googleapis.com --project="$PROJECT" --quota-id="$QUOTA_ID" \
      --preferred-value=1 --dimensions=region="$1" --preference-id="l4-$1" --email="$(gcloud config get-value account 2>/dev/null)" \
      --justification="Scale-to-zero Cloud Run service with one L4 GPU for an open-weight LLM (min 0, max 1)." 2>&1) && return 0
    case "$out" in *"already exist"*) return 0 ;; *PERMISSION_DENIED*) sleep 10 ;; *) echo "  $1: request failed: ${out##*ERROR: }" | head -c 300; echo; return 1 ;; esac
  done
  echo "  $1: still PERMISSION_DENIED after 90 s (new project IAM)"; return 1
}
state() { gcloud beta quotas preferences describe "l4-$1" --project="$PROJECT" --format='value(quotaConfig.stateDetail)' 2>/dev/null; }
if [ -z "${REGION:-}" ]; then
  for r in $REGIONS; do
    q=$(granted "$r" || echo 0)
    if [ "${q:-0}" -lt 1 ] && request "$r"; then
      for _ in $(seq 1 12); do   # decisions usually arrive in seconds
        q=$(granted "$r" || echo 0); [ "${q:-0}" -ge 1 ] && break
        case "$(state "$r")" in *denied*|*Denied*) break ;; esac
        sleep 5
      done
    fi
    echo "  $r: L4 quota ${q:-0}${q:+ }$( [ "${q:-0}" -lt 1 ] && state "$r" )"
    if [ "${q:-0}" -ge 1 ]; then REGION=$r; break; fi
  done
fi
[ -n "${REGION:-}" ] || die "No L4 quota granted in: $REGIONS. New billing accounts are sometimes refused; retry in a day, or ask at https://console.cloud.google.com/iam-admin/quotas"
echo "region: $REGION"

say "Network: Private Google Access on the default subnet (fast GCS reads from Cloud Run)"
gcloud compute networks describe default >/dev/null 2>&1 || gcloud compute networks create default --subnet-mode=auto >/dev/null
gcloud compute networks subnets update default --region "$REGION" --enable-private-ip-google-access >/dev/null

say "Model files -> gs://$BUCKET (downloaded inside Google Cloud, ~4 min)"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access >/dev/null
if gcloud storage ls "gs://$BUCKET/bonsai2/$TARGET" "gs://$BUCKET/bonsai2/$DRAFT" >/dev/null 2>&1; then
  echo "already staged"
else
  cfg=$(mktemp); cat > "$cfg" <<EOF
steps:
- name: python:3.12-slim
  entrypoint: bash
  args: ["-c", "pip install -q 'huggingface_hub[cli]' && hf download prism-ml/Ternary-Bonsai-2-27B-gguf $TARGET --local-dir /workspace/m && hf download naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2 $DRAFT --local-dir /workspace/m"]
- name: gcr.io/google.com/cloudsdktool/cloud-sdk:slim
  entrypoint: bash
  args: ["-c", "gcloud storage cp /workspace/m/*.gguf gs://$BUCKET/bonsai2/"]
options: {machineType: E2_HIGHCPU_8, diskSizeGb: 50}
timeout: 3600s
EOF
  gcloud builds submit --no-source --region "$REGION" --config "$cfg" >/dev/null
  rm -f "$cfg"
fi

say "Deploying $SERVICE (L4, 8 vCPU, 32 GiB, min 0 / max 1) from $IMAGE"
[ "$PROFILE" = chat ] && ENVS="DRAFT_N_MAX=3,NGRAM=0" || ENVS="DRAFT_N_MAX=7,NGRAM=1"
gcloud beta run deploy "$SERVICE" --region "$REGION" --image "$IMAGE" \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy --cpu 8 --memory 32Gi --no-cpu-throttling \
  --concurrency 4 --min-instances 0 --max-instances 1 --port 8080 --timeout 900 \
  --network default --subnet default --vpc-egress all-traffic \
  --add-volume "name=weights,type=cloud-storage,bucket=$BUCKET,readonly=true,mount-options=enable-buffered-read=true" \
  --add-volume-mount volume=weights,mount-path=/mnt/gcs \
  --startup-probe httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=1,periodSeconds=1,timeoutSeconds=1,failureThreshold=240 \
  --set-env-vars "MODEL_DIR=/mnt/gcs/bonsai2,TARGET=$TARGET,DRAFT=$DRAFT,$ENVS" \
  --no-allow-unauthenticated --quiet >/dev/null

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
say "Your endpoint is live"
cat <<EOF
Step 4. Save your URL (paste this line):

  export URL=$URL

Step 5. Call it:

  curl -s \$URL/v1/chat/completions \\
    -H "Authorization: Bearer \$(gcloud auth print-identity-token)" -H "Content-Type: application/json" \\
    -d '{"messages":[{"role":"user","content":"Write a Python function that checks if a string is a palindrome."}],"max_tokens":1024}'

The first call after an idle spell starts a GPU instance (about 25 s). Idle: \$0. Active: about \$1.4/hour.
Options (thinking off, Anthropic API, SDKs, remove everything): https://github.com/NakliTechie/bonsai2-run#options
EOF
