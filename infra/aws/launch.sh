#!/usr/bin/env bash
# Guarded, detached launch of the CUDA smoke box under the cairn-skypilot identity (infra/aws Gotchas 9, 10).
#   CONFIRM_GPU_SPEND=1 bash infra/aws/launch.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
[ -n "${CONFIRM_GPU_SPEND:-}" ] || { echo "[launch] ABORT: set CONFIRM_GPU_SPEND=1 to spend." >&2; exit 1; }
PROFILE="${AWS_PROFILE_LAUNCH:-cairn-skypilot}"; EXPECT_ARN="arn:aws:iam::615809814090:user/cairn-skypilot"
CLUSTER="${CLUSTER:-bonsai2-run-smoke}"; IDLE="${IDLE_MIN:-45}"; TASK="${TASK:-infra/aws/smoke.sky.yaml}"; SKY="${SKY:-$HOME/.cairn-sky-venv/bin/sky}"
got="$(aws sts get-caller-identity --profile "$PROFILE" --query Arn --output text)"
[ "$got" = "$EXPECT_ARN" ] || { echo "[launch] ABORT: $PROFILE resolves to $got" >&2; exit 1; }
export AWS_PROFILE="$PROFILE"
"$SKY" api stop >/dev/null 2>&1 || true
"$SKY" status >/dev/null 2>&1 || true
echo "[launch] $(date '+%F %T') cluster=$CLUSTER profile=$PROFILE idle-autodown=${IDLE}m"
exec "$SKY" launch -c "$CLUSTER" "$TASK" -y -d -i "$IDLE" --down "$@"
