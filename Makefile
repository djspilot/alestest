# =============================================================================
# ALES Manufacturing Pipeline — VPS beheer
# =============================================================================
# Gebruik:
#   make help          overzicht van alle commando's
#   make setup         eenmalige setup (SSH key + VPS inrichten + GitHub Secrets)
#   make ssh           inloggen op VPS
#   make logs          live logs bekijken
#   make deploy        handmatig deployen (zonder commit)
#   make status        container status op VPS
#   make health        API health check
#
# Vereisten: .vps.env aangemaakt (zie .vps.env.example)
# =============================================================================

-include .vps.env
export

SSH_KEY     := $(HOME)/.ssh/ales_deploy
SSH_OPTS    := -i $(SSH_KEY) -o StrictHostKeyChecking=accept-new
SSH         := ssh $(SSH_OPTS) $(VPS_USER)@$(VPS_IP)
SCP         := scp $(SSH_OPTS)
COMPOSE     := docker compose -f /srv/alestest/docker-compose.prod.yml --env-file /srv/alestest/.env

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================
.PHONY: help
help:
	@echo ""
	@echo "  ALES VPS beheer"
	@echo "  ──────────────────────────────────────────"
	@echo "  make setup          Eenmalige setup (SSH + VPS + GitHub)"
	@echo "  make ssh            Inloggen op VPS"
	@echo "  make deploy         Handmatig deployen (pull + restart)"
	@echo "  make logs           Live API logs"
	@echo "  make logs-viewer    Live viewer logs"
	@echo "  make status         Container status"
	@echo "  make health         API health check"
	@echo "  make restart        Containers herstarten"
	@echo "  make update-config  Alleen .env op VPS bijwerken"
	@echo "  make github-secrets GitHub Secrets instellen via gh CLI"
	@echo "  make nginx          nginx configureren op VPS"
	@echo "  make ssl            HTTPS instellen via certbot"
	@echo "  make clean          Oude Docker images opruimen op VPS"
	@echo ""

# =============================================================================
# Validatie
# =============================================================================
.PHONY: _check-env
_check-env:
	@test -f .vps.env || (echo "❌  .vps.env niet gevonden. Kopieer .vps.env.example en vul in." && exit 1)
	@test -n "$(VPS_IP)"     || (echo "❌  VPS_IP niet ingesteld in .vps.env" && exit 1)
	@test -n "$(VPS_USER)"   || (echo "❌  VPS_USER niet ingesteld in .vps.env" && exit 1)
	@test -n "$(VPS_DOMAIN_API)" || (echo "❌  VPS_DOMAIN_API niet ingesteld in .vps.env" && exit 1)

# =============================================================================
# Eenmalige setup
# =============================================================================

## Volledige eenmalige setup: SSH key → VPS inrichten → GitHub Secrets
.PHONY: setup
setup: _check-env setup-ssh-key setup-vps github-secrets
	@echo ""
	@echo "✅  Setup klaar! Push naar main om de eerste deploy te starten:"
	@echo "    git push"

## Stap 1: SSH key aanmaken en op VPS zetten
.PHONY: setup-ssh-key
setup-ssh-key: _check-env
	@echo "→ SSH key aanmaken ($(SSH_KEY))..."
	@test -f $(SSH_KEY) && echo "  Al aanwezig, overgeslagen." || \
		ssh-keygen -t ed25519 -C "ales-deploy" -f $(SSH_KEY) -N ""
	@echo "→ Public key op VPS zetten ($(VPS_USER)@$(VPS_IP))..."
	@echo "  (Voer je VPS wachtwoord in als gevraagd)"
	ssh-copy-id -i $(SSH_KEY).pub $(VPS_USER)@$(VPS_IP)
	@echo "→ SSH alias toevoegen aan ~/.ssh/config..."
	@grep -q "Host ales-vps" ~/.ssh/config 2>/dev/null || \
		printf "\nHost ales-vps\n  HostName $(VPS_IP)\n  User $(VPS_USER)\n  IdentityFile $(SSH_KEY)\n" >> ~/.ssh/config
	@echo "✓ SSH klaar — je kunt nu: ssh ales-vps"

## Stap 2: VPS inrichten (Docker, directories, scripts)
.PHONY: setup-vps
setup-vps: _check-env
	@echo "→ VPS inrichten..."
	$(SSH) "bash -s" < deploy/scripts/vps-setup.sh
	@echo "→ .env uploaden naar VPS..."
	@printf "API_KEYS=$(API_KEY)\nMAX_FILE_SIZE_MB=100\nJOB_TTL_SECONDS=31536000\nDISABLE_STAGES=unfold\n" | \
		$(SSH) "cat > /srv/alestest/.env"
	@echo "→ docker-compose.prod.yml uploaden..."
	$(SCP) docker-compose.prod.yml $(VPS_USER)@$(VPS_IP):/srv/alestest/docker-compose.prod.yml
	$(SCP) deploy/scripts/deploy.sh $(VPS_USER)@$(VPS_IP):/srv/alestest/deploy.sh
	$(SSH) "chmod +x /srv/alestest/deploy.sh"
	@echo "→ nginx configureren..."
	$(MAKE) nginx
	@echo "✓ VPS klaar"

## Stap 3: GitHub Secrets instellen via gh CLI
.PHONY: github-secrets
github-secrets: _check-env
	@which gh > /dev/null || (echo "❌  Installeer gh CLI: brew install gh" && exit 1)
	@echo "→ GitHub Secrets instellen..."
	gh secret set VPS_HOST                   --body "$(VPS_IP)"
	gh secret set VPS_USER                   --body "$(VPS_USER)"
	gh secret set VPS_SSH_KEY                < $(SSH_KEY)
	gh secret set VITE_PIPELINE_API_BASE_URL --body "https://$(VPS_DOMAIN_API)"
	@echo "✓ GitHub Secrets ingesteld"

# =============================================================================
# Dagelijks gebruik
# =============================================================================

## Inloggen op VPS
.PHONY: ssh
ssh: _check-env
	ssh ales-vps

## Handmatig deployen (pull nieuwe images + restart)
.PHONY: deploy
deploy: _check-env
	@echo "→ Deployen naar VPS..."
	$(SSH) "/srv/alestest/deploy.sh"
	@echo "✓ Deploy klaar"

## Live API logs
.PHONY: logs
logs: _check-env
	$(SSH) "$(COMPOSE) logs -f api"

## Live viewer logs
.PHONY: logs-viewer
logs-viewer: _check-env
	$(SSH) "$(COMPOSE) logs -f viewer"

## Container status
.PHONY: status
status: _check-env
	$(SSH) "$(COMPOSE) ps && echo '' && docker stats --no-stream"

## API health check
.PHONY: health
health: _check-env
	@curl -sf -H "X-API-Key: $(API_KEY)" https://$(VPS_DOMAIN_API)/api/v1/health | python3 -m json.tool \
		|| echo "❌  API niet bereikbaar op https://$(VPS_DOMAIN_API)"

## Containers herstarten
.PHONY: restart
restart: _check-env
	$(SSH) "$(COMPOSE) restart"
	@echo "✓ Herstart klaar"

## Alleen .env op VPS bijwerken
.PHONY: update-config
update-config: _check-env
	@echo "→ .env uploaden..."
	@printf "API_KEYS=$(API_KEY)\nMAX_FILE_SIZE_MB=100\nJOB_TTL_SECONDS=31536000\nDISABLE_STAGES=unfold\n" | \
		$(SSH) "cat > /srv/alestest/.env"
	$(SSH) "$(COMPOSE) restart"
	@echo "✓ Config bijgewerkt"

## Oude Docker images opruimen
.PHONY: clean
clean: _check-env
	$(SSH) "docker image prune -f"
	@echo "✓ Opgeruimd"

# =============================================================================
# nginx & SSL
# =============================================================================

## nginx configureren op VPS (met jouw domeinnamen)
.PHONY: nginx
nginx: _check-env
	@echo "→ nginx configureren voor $(VPS_DOMAIN_API) en $(VPS_DOMAIN_VIEWER)..."
	@sed 's/api\.example\.com/$(VPS_DOMAIN_API)/g' deploy/nginx/api.example.conf | \
		$(SSH) "cat > /etc/nginx/sites-available/ales-api"
	@sed 's/viewer\.example\.com/$(VPS_DOMAIN_VIEWER)/g' deploy/nginx/viewer.example.conf | \
		$(SSH) "cat > /etc/nginx/sites-available/ales-viewer"
	$(SSH) "\
		ln -sf /etc/nginx/sites-available/ales-api /etc/nginx/sites-enabled/ 2>/dev/null; \
		ln -sf /etc/nginx/sites-available/ales-viewer /etc/nginx/sites-enabled/ 2>/dev/null; \
		nginx -t && systemctl reload nginx"
	@echo "✓ nginx klaar"

## HTTPS instellen via Let's Encrypt
.PHONY: ssl
ssl: _check-env
	$(SSH) "certbot --nginx -d $(VPS_DOMAIN_API) -d $(VPS_DOMAIN_VIEWER) --non-interactive --agree-tos -m admin@$(VPS_DOMAIN_API)"
	@echo "✓ SSL klaar"
