#!/bin/bash
set -e

# ============================================================================
# Deploy to VPS - Push local code to api.aidoel.nl and rebuild
#
# Usage:
#   ./deploy.sh              # Full deploy (sync + build + restart)
#   ./deploy.sh --quick      # Sync + restart only (skip Docker rebuild)
#   ./deploy.sh --logs       # Deploy then tail logs
#   ./deploy.sh --status     # Just check VPS status
#
# Tip: Run 'ssh-add' first to avoid repeated passphrase prompts.
# ============================================================================

# --- Configuration (override via environment or edit here) ---
VPS_HOST="${VPS_HOST:-api.aidoel.nl}"
VPS_USER="${VPS_USER:-root}"
VPS_DIR="${VPS_DIR:-/opt/manufacturing-api}"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -o PreferredAuthentications=publickey"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- Helper functions ---
ssh_cmd() {
    ssh $SSH_OPTS "${VPS_USER}@${VPS_HOST}" "$@"
}

info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*"; exit 1; }

# --- Parse arguments ---
QUICK=false
LOGS=false
STATUS_ONLY=false

for arg in "$@"; do
    case $arg in
        --quick)  QUICK=true ;;
        --logs)   LOGS=true ;;
        --status) STATUS_ONLY=true ;;
        --help|-h)
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick    Skip Docker rebuild, just sync and restart"
            echo "  --logs     Show container logs after deploy"
            echo "  --status   Only check VPS status (no deploy)"
            echo ""
            echo "Environment:"
            echo "  VPS_HOST   Target host (default: api.aidoel.nl)"
            echo "  VPS_USER   SSH user (default: root)"
            echo "  VPS_DIR    Install directory (default: /opt/manufacturing-api)"
            echo ""
            echo "Tip: Run 'ssh-add' first to cache your key passphrase."
            exit 0
            ;;
    esac
done

# --- Ensure ssh-agent has keys loaded ---
if ! ssh-add -l &>/dev/null; then
    warn "No SSH keys loaded in agent. Adding all keys..."
    for key in ~/.ssh/id_rsa ~/.ssh/id_ed25519; do
        [ -f "$key" ] && ssh-add "$key" 2>/dev/null && info "  Added $(basename $key)"
    done
else
    info "SSH agent has $(ssh-add -l 2>/dev/null | wc -l | tr -d ' ') key(s) loaded"
fi

# Verify at least one key is in the agent
if ! ssh-add -l &>/dev/null; then
    error "No SSH keys loaded. Run 'ssh-add ~/.ssh/id_rsa' or 'ssh-add ~/.ssh/id_ed25519' manually."
fi

# --- Status check ---
if $STATUS_ONLY; then
    info "Checking VPS status at ${VPS_HOST}..."
    ssh_cmd "cd ${VPS_DIR} && docker compose -f deploy/docker-compose.yml ps && echo '' && echo '--- Recent logs ---' && docker compose -f deploy/docker-compose.yml logs --tail=20"
    exit 0
fi

# --- Pre-flight checks ---
info "Deploying to ${VPS_USER}@${VPS_HOST}:${VPS_DIR}"

# Test SSH connection
ssh_cmd "true" 2>/dev/null || {
    echo ""
    error "Cannot connect to ${VPS_HOST}. Your SSH key may not be authorized on the VPS.

  To fix, copy your public key to the VPS:
    ssh-copy-id -i ~/.ssh/id_rsa ${VPS_USER}@${VPS_HOST}
  or:
    ssh-copy-id -i ~/.ssh/id_ed25519 ${VPS_USER}@${VPS_HOST}

  (You'll need the VPS root password once for this.)"
}
info "SSH connection OK"

# --- Step 1: Create tarball of source code ---
info "Packaging source code..."

TAR_FILE=$(mktemp /tmp/deploy-XXXXXX.tar.gz)
tar czf "$TAR_FILE" \
    --exclude='.git' \
    --exclude='.DS_Store' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='data' \
    --exclude='.pipeline_cache' \
    --exclude='.env' \
    --exclude='.claude' \
    --exclude='tests' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='deploy.sh' \
    .

TARSIZE=$(du -h "$TAR_FILE" | cut -f1)
info "Package ready (${TARSIZE})"

# --- Step 2: Upload and extract ---
info "Uploading to VPS..."

ssh_cmd "mkdir -p ${VPS_DIR}"
scp $SSH_OPTS "$TAR_FILE" "${VPS_USER}@${VPS_HOST}:/tmp/deploy-upload.tar.gz"
ssh_cmd "cd ${VPS_DIR} && tar xzf /tmp/deploy-upload.tar.gz && rm /tmp/deploy-upload.tar.gz"
rm -f "$TAR_FILE"

info "Files synced"

# --- Step 3: Build and restart ---
if $QUICK; then
    info "Quick restart (no rebuild)..."
    ssh_cmd "cd ${VPS_DIR} && docker compose -f deploy/docker-compose.yml restart"
else
    info "Building Docker image and restarting (this may take a few minutes)..."
    ssh_cmd "cd ${VPS_DIR} && docker compose -f deploy/docker-compose.yml up -d --build"
fi

# --- Step 4: Verify ---
info "Waiting for container to start..."
sleep 5

# Health check
HTTP_STATUS=$(ssh_cmd "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/health" 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    info "Health check OK (HTTP 200)"
    echo ""
    echo -e "${GREEN}Deployed successfully to https://${VPS_HOST}${NC}"
    echo "  API:      https://${VPS_HOST}/api/v1/health"
    echo "  Frontend: https://${VPS_HOST}"
    echo ""
else
    warn "Health check returned HTTP ${HTTP_STATUS}"
    warn "Container may still be starting. Check logs:"
    echo "  ./deploy.sh --status"
    echo "  ssh ${VPS_USER}@${VPS_HOST} 'cd ${VPS_DIR} && docker compose -f deploy/docker-compose.yml logs -f'"
fi

# --- Optional: Tail logs ---
if $LOGS; then
    echo ""
    info "Tailing logs (Ctrl+C to stop)..."
    ssh_cmd "cd ${VPS_DIR} && docker compose -f deploy/docker-compose.yml logs -f --tail=50"
fi
