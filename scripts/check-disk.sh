#!/usr/bin/env bash
# Check free space before pulling images or running large imports.
# Thresholds: warn below 10 GB, stop new imports/images below 5 GB.
# Both the project disk and the Docker data disk matter: images and volumes
# live on the Docker data disk (F: on this machine), not on the project disk.
set -euo pipefail

cd "$(dirname "$0")/.."

WARN_GB=10
STOP_GB=5
DATA_DISK="${DATA_DISK_PATH:-/f}"

free_gb() {
  df -Pk "$1" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}'
}

echo "== project disk =="
df -h . | tail -1
PROJECT_FREE=$(free_gb .)
echo "free: ${PROJECT_FREE} GB"

echo
echo "== docker data disk (${DATA_DISK}) =="
if [ -d "$DATA_DISK" ]; then
  df -h "$DATA_DISK" | tail -1
  DATA_FREE=$(free_gb "$DATA_DISK")
  echo "free: ${DATA_FREE} GB"
else
  DATA_FREE=$PROJECT_FREE
  echo "not mounted, falling back to project disk"
fi

echo
echo "== docker usage =="
docker system df | sed -n '1,6p'

if [ "$DATA_FREE" -lt "$PROJECT_FREE" ]; then
  MIN_FREE=$DATA_FREE
  BINDING="docker data disk"
else
  MIN_FREE=$PROJECT_FREE
  BINDING="project disk"
fi

echo
echo "binding constraint: ${BINDING} (${MIN_FREE} GB free)"
if [ "$MIN_FREE" -lt "$STOP_GB" ]; then
  echo "RESULT: STOP - below ${STOP_GB} GB. Do not pull images or run bulk imports."
  exit 2
elif [ "$MIN_FREE" -lt "$WARN_GB" ]; then
  echo "RESULT: WARN - below ${WARN_GB} GB. Clean up before next deployment."
  exit 1
else
  echo "RESULT: OK"
fi
