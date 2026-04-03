#!/bin/bash
# deploy.sh — VPS update script
# Locatie op VPS: /srv/alestest/deploy.sh
# Aanroepen: /srv/alestest/deploy.sh
# Wordt automatisch aangeroepen door GitHub Actions na elke push naar main.
set -euo pipefail

COMPOSE_FILE="/srv/alestest/docker-compose.prod.yml"
ENV_FILE="/srv/alestest/.env"
LOG="/srv/alestest/deploy.log"
GHCR_TOKEN="/srv/alestest/.ghcr_token"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "Deploy gestart"

# Login bij ghcr.io
if [ -f "$GHCR_TOKEN" ]; then
    cat "$GHCR_TOKEN" | docker login ghcr.io -u djspilot --password-stdin 2>/dev/null \
        && log "ghcr.io login OK" \
        || log "Waarschuwing: ghcr.io login gefaald (images mogelijk al lokaal)"
fi

# Nieuwe images ophalen
log "Images ophalen van ghcr.io..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull

# Containers herstarten met nieuwe images
log "Containers herstarten..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

# Oude images opruimen
docker image prune -f > /dev/null

log "Deploy klaar ✓"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
