#!/usr/bin/env bash
# Quick VPS health check — run from local machine:
#   bash scripts/check-vps.sh                # HTTP status + container state
#   bash scripts/check-vps.sh --logs         # + last 60 log lines
#   bash scripts/check-vps.sh --follow       # live log stream (Ctrl+C to stop)
#   bash scripts/check-vps.sh --fix          # pull latest image and restart
#   bash scripts/check-vps.sh --env          # show active env vars in container
set -euo pipefail

VPS=root@api.aidoel.nl
COMPOSE=/srv/alestest/docker-compose.prod.yml
ENV=/srv/alestest/.env
CONTAINER=ales-api

SHOW_LOGS=0
DO_FOLLOW=0
DO_FIX=0
SHOW_ENV=0
for arg in "$@"; do
  case "$arg" in
    --logs)   SHOW_LOGS=1 ;;
    --follow) DO_FOLLOW=1 ;;
    --fix)    DO_FIX=1 ;;
    --env)    SHOW_ENV=1 ;;
  esac
done

# Skip status block when streaming logs live
if [[ "$DO_FOLLOW" == "0" ]]; then
  echo "── API endpoint ────────────────────────────────"
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 6 https://api.aidoel.nl/api/v1/health 2>/dev/null || echo "TIMEOUT")
  if [[ "$HTTP" == "200" || "$HTTP" == "401" ]]; then
    echo "  ✓ https://api.aidoel.nl/api/v1/health → $HTTP (up)"
  else
    echo "  ✗ https://api.aidoel.nl/api/v1/health → $HTTP"
  fi

  echo "── Container status ────────────────────────────"
  ssh "$VPS" "docker ps -a --filter name=$CONTAINER --format '  {{.Names}}  {{.Status}}  {{.Image}}'"

  echo "── GitHub Actions (last 3) ─────────────────────"
  gh run list --limit 3 2>/dev/null || echo "  (gh CLI not available)"
fi

if [[ "$SHOW_ENV" == "1" ]]; then
  echo "── Active env vars in container ────────────────"
  ssh "$VPS" "docker exec $CONTAINER env 2>/dev/null | grep -E 'API_KEYS|DISABLE|FREECAD|UPLOAD|DB_PATH|PORT' | sed 's/API_KEYS=.*/API_KEYS=***/' | sort" || \
    echo "  (container not running)"
fi

if [[ "$SHOW_LOGS" == "1" ]]; then
  echo "── Container logs (last 60) ────────────────────"
  ssh "$VPS" "docker logs --tail 60 $CONTAINER 2>&1" || true
fi

if [[ "$DO_FOLLOW" == "1" ]]; then
  echo "── Live log stream from $CONTAINER (Ctrl+C to stop) ──"
  ssh -t "$VPS" "docker logs -f --tail 20 $CONTAINER 2>&1" || true
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
