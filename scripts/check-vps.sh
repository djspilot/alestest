#!/usr/bin/env bash
# Quick VPS health check — run from local machine:
#   bash scripts/check-vps.sh
#   bash scripts/check-vps.sh --logs      # show last 40 container log lines
#   bash scripts/check-vps.sh --fix       # pull latest image and restart
set -euo pipefail

VPS=root@api.aidoel.nl
COMPOSE=/srv/alestest/docker-compose.prod.yml
ENV=/srv/alestest/.env
CONTAINER=ales-api

SHOW_LOGS=0
DO_FIX=0
for arg in "$@"; do
  case "$arg" in
    --logs) SHOW_LOGS=1 ;;
    --fix)  DO_FIX=1 ;;
  esac
done

echo "── API endpoint ────────────────────────────────"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 6 https://api.aidoel.nl/api/v1/health 2>/dev/null || echo "TIMEOUT")
if [[ "$HTTP" == "200" ]]; then
  echo "  ✓ https://api.aidoel.nl/api/v1/health → $HTTP"
else
  echo "  ✗ https://api.aidoel.nl/api/v1/health → $HTTP"
fi

echo "── Container status ────────────────────────────"
ssh "$VPS" "docker ps -a --filter name=$CONTAINER --format '  {{.Names}}  {{.Status}}  {{.Image}}'"

echo "── GitHub Actions (last 3) ─────────────────────"
gh run list --limit 3 2>/dev/null || echo "  (gh CLI not available)"

if [[ "$SHOW_LOGS" == "1" ]]; then
  echo "── Container logs (last 40) ────────────────────"
  ssh "$VPS" "docker logs --tail 40 $CONTAINER 2>&1" || true
fi

if [[ "$DO_FIX" == "1" ]]; then
  echo "── Pulling latest image and restarting ─────────"
  ssh "$VPS" "
    docker pull ghcr.io/aidoel/alestest-api:latest
    docker compose -f $COMPOSE --env-file $ENV up -d --force-recreate
    sleep 4
    docker ps --filter name=$CONTAINER --format '  {{.Names}}  {{.Status}}'
  "
fi
