# Hostinger VPS Deployment

## Architectuur

```
git push → GitHub Actions
              ├── build Dockerfile.api       → ghcr.io/djspilot/alestest-api:latest
              └── build Dockerfile.viewer    → ghcr.io/djspilot/alestest-viewer:latest
                         ↓
                    SSH naar VPS
                         ↓
              docker compose pull + up -d
```

De VPS bouwt **nooit** zelf een image. Hij downloadt altijd een pre-gebouwd image van ghcr.io.
De productie-image bevat nu ook de volledige FreeCAD-unfold runtime.

---

## Eenmalige VPS setup (Hostinger Ubuntu)

### 1. Setup script draaien

```bash
ssh root@<VPS-IP>
bash <(curl -fsSL https://raw.githubusercontent.com/djspilot/alestest/main/deploy/scripts/vps-setup.sh)
```

### 2. .env invullen

```bash
nano /srv/alestest/.env
```

Minimaal:
```env
API_KEYS=genereer-een-lange-random-sleutel
FREECAD_RUNTIME_ROOT=/srv/alestest/shared/runtime/freecad
```

Genereer een sleutel:
```bash
openssl rand -hex 32
```

### 3. GitHub deploy token aanmaken

Ga naar GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens

Rechten: `read:packages` (alleen lezen van ghcr.io)

Sla op:
```bash
echo "ghp_jouwtoken" > /srv/alestest/.ghcr_token
chmod 600 /srv/alestest/.ghcr_token
```

### 4. Eerste deploy

```bash
/srv/alestest/deploy.sh
```

### 5. nginx configureren

```bash
# API
cp /pad/naar/deploy/nginx/api.example.conf /etc/nginx/sites-available/ales-api
nano /etc/nginx/sites-available/ales-api  # server_name aanpassen

# Viewer
cp /pad/naar/deploy/nginx/viewer.example.conf /etc/nginx/sites-available/ales-viewer
nano /etc/nginx/sites-available/ales-viewer  # server_name aanpassen

ln -s /etc/nginx/sites-available/ales-api /etc/nginx/sites-enabled/
ln -s /etc/nginx/sites-available/ales-viewer /etc/nginx/sites-enabled/

nginx -t && systemctl reload nginx
```

### 6. HTTPS via Let's Encrypt

```bash
certbot --nginx -d api.jouwdomein.nl -d viewer.jouwdomein.nl
```

---

## GitHub Actions instellen (eenmalig)

Ga naar je GitHub repo → Settings → Secrets and variables → Actions

Voeg toe:

| Secret | Waarde |
|--------|--------|
| `VPS_HOST` | IP-adres van je Hostinger VPS |
| `VPS_USER` | `root` (of je gebruikersnaam) |
| `VPS_SSH_KEY` | Inhoud van private SSH key (zie hieronder) |
| `VITE_PIPELINE_API_BASE_URL` | `https://api.jouwdomein.nl` |

### SSH key aanmaken

```bash
# Op je eigen Mac:
ssh-keygen -t ed25519 -C "github-deploy-ales" -f ~/.ssh/ales_deploy

# Public key op VPS zetten:
ssh-copy-id -i ~/.ssh/ales_deploy.pub root@<VPS-IP>

# Private key kopiëren naar GitHub Secret VPS_SSH_KEY:
cat ~/.ssh/ales_deploy
```

---

## Na de setup: updaten is gewoon pushen

```bash
git add .
git commit -m "fix: iets aangepast"
git push
```

GitHub Actions bouwt de nieuwe images (~4 min) en deployt automatisch naar de VPS.

### Handmatig deployen (zonder commit)

Via GitHub UI: Actions → Build & Deploy → Run workflow

Of direct op de VPS:
```bash
/srv/alestest/deploy.sh
```

---

## Hybrid: VPS + lokaal

De VPS draait de **lite** pipeline (geen unfold). Voor volledige analyse met flat dimensions:

```bash
# Lokaal:
python run.py -f part.step

# Of: viewer tijdelijk naar lokaal wijzen
# API URL in viewer instellen op: http://localhost:8000
# Dan: python -m manufacturing_pipeline.api.app (lokaal draaien)
```

---

## Smoketest

```bash
curl -H "X-API-Key: jouwkey" https://api.jouwdomein.nl/api/v1/health
```

## Logs bekijken

```bash
docker compose -f /srv/alestest/docker-compose.prod.yml logs -f api
cat /srv/alestest/deploy.log
```
