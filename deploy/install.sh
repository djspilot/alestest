#!/bin/bash
set -e

# ============================================================================
# Manufacturing Analysis API - Debian VPS Installer
# ============================================================================
#
# Usage: sudo bash install.sh
#
# This script installs the manufacturing analysis API on a Debian VPS.
# It sets up Docker, nginx with SSL, and starts the API service.
# ============================================================================

INSTALL_DIR="/opt/manufacturing-api"
REPO_URL="https://github.com/djspilot/alestest.git"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "============================================"
echo "  Manufacturing Analysis API Installer"
echo "  Debian VPS Setup"
echo "============================================"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (sudo)${NC}"
    exit 1
fi

# ---- Step 1: Gather configuration ----

echo -e "${YELLOW}Configuration${NC}"
echo ""

# Domain name
read -p "Domain name (e.g., api.example.com) [leave empty for IP-only]: " DOMAIN
echo ""

# API Key
read -p "API key for authentication [leave empty for no auth]: " API_KEY
echo ""

# Repo URL
read -p "Git repository URL [$REPO_URL]: " INPUT_REPO
REPO_URL="${INPUT_REPO:-$REPO_URL}"

echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Domain:      ${DOMAIN:-<IP-only>}"
echo "  API Key:     ${API_KEY:+configured}"
echo "  Repo:        $REPO_URL"
echo "  Install dir: $INSTALL_DIR"
echo ""
read -p "Continue? [Y/n] " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn] ]]; then
    echo "Aborted."
    exit 0
fi

# ---- Step 2: Install system packages ----

echo ""
echo -e "${YELLOW}[1/6] Installing system packages...${NC}"

apt-get update -qq
apt-get install -y -qq \
    docker.io \
    docker-compose-plugin \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    > /dev/null 2>&1

# Enable and start Docker
systemctl enable docker
systemctl start docker

echo -e "${GREEN}  Done.${NC}"

# ---- Step 3: Clone or update repository ----

echo -e "${YELLOW}[2/6] Setting up application...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --ff-only || true
else
    echo "  Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo -e "${GREEN}  Done.${NC}"

# ---- Step 4: Write environment file ----

echo -e "${YELLOW}[3/6] Writing configuration...${NC}"

cat > "$INSTALL_DIR/.env" <<EOF
API_KEYS=${API_KEY}
FREECAD_PATH=/usr/lib/freecad
UPLOAD_DIR=/tmp/manufacturing-uploads
MAX_FILE_SIZE_MB=100
JOB_TTL_SECONDS=3600
EOF

echo -e "${GREEN}  Done.${NC}"

# ---- Step 5: Build and start Docker ----

echo -e "${YELLOW}[4/6] Building and starting Docker containers...${NC}"
echo "  (This may take 5-10 minutes on first run)"

cd "$INSTALL_DIR"
docker compose up -d --build

echo -e "${GREEN}  Done.${NC}"

# ---- Step 6: Configure nginx ----

echo -e "${YELLOW}[5/6] Configuring nginx...${NC}"

NGINX_CONF="/etc/nginx/sites-available/manufacturing-api"

if [ -n "$DOMAIN" ]; then
    SERVER_NAME="$DOMAIN"
else
    SERVER_NAME="_"
fi

cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 600s;
        proxy_connect_timeout 10s;
    }
}
EOF

# Enable site, disable default
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/manufacturing-api
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx

echo -e "${GREEN}  Done.${NC}"

# ---- Step 7: SSL (optional) ----

if [ -n "$DOMAIN" ]; then
    echo -e "${YELLOW}[6/6] Setting up SSL with Let's Encrypt...${NC}"
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || {
        echo -e "${YELLOW}  SSL setup failed. You can retry manually:${NC}"
        echo "  certbot --nginx -d $DOMAIN"
    }
else
    echo -e "${YELLOW}[6/6] Skipping SSL (no domain configured)${NC}"
    echo "  To add SSL later: certbot --nginx -d yourdomain.com"
fi

# ---- Done ----

echo ""
echo "============================================"
echo -e "${GREEN}  Installation complete!${NC}"
echo "============================================"
echo ""

if [ -n "$DOMAIN" ]; then
    echo "  Frontend: https://$DOMAIN"
    echo "  API:      https://$DOMAIN/api/v1/health"
    echo "  Docs:     https://$DOMAIN/docs"
else
    IP=$(hostname -I | awk '{print $1}')
    echo "  Frontend: http://$IP"
    echo "  API:      http://$IP/api/v1/health"
    echo "  Docs:     http://$IP/docs"
fi

echo ""
echo "  Manage:"
echo "    cd $INSTALL_DIR"
echo "    docker compose logs -f     # View logs"
echo "    docker compose restart     # Restart"
echo "    docker compose down        # Stop"
echo "    docker compose up -d --build  # Rebuild"
echo ""
