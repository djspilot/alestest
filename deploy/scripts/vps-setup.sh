#!/bin/bash
# vps-setup.sh — eenmalige VPS installatie
# Wordt aangeroepen via: make setup-vps
# Of handmatig: bash deploy/scripts/vps-setup.sh
set -euo pipefail

echo "=== ALES VPS Setup ==="

# Docker installeren
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 nginx certbot python3-certbot-nginx curl

systemctl enable --now docker

# Directories aanmaken
mkdir -p /srv/alestest
chmod 755 /srv/alestest

# deploy.sh rechten instellen (wordt apart geüpload via make)
touch /srv/alestest/deploy.sh
chmod +x /srv/alestest/deploy.sh

# deploy.log aanmaken
touch /srv/alestest/deploy.log

# Controleer of docker werkt
docker --version
docker compose version

echo "=== VPS Setup klaar ==="
