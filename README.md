# ALES Manufacturing Pipeline

Geautomatiseerde analyse van STEP CAD-bestanden voor productie. Extraheert geometrie, detecteert features (gaten, zettingen, draad), classificeert onderdelen en genereert productieklare rapporten volgens Nederlandse/ISO-normen.

Gebouwd voor plaatwerk- en metaalbewerkingsbedrijven die snel en nauwkeurig werkvoorbereidingsdata uit 3D-modellen willen halen.

> Voor een uitgebreide technische beschrijving van hoe de engine werkt en hoe deze zich verhoudt tot SpaceClaim, zie **[docs/ENGINE.md](docs/ENGINE.md)**.

> Voor het nieuwe feature-detection traject (v3) en de geplande stappen, zie **[docs/FEATURE_DETECTION_ROADMAP.md](docs/FEATURE_DETECTION_ROADMAP.md)**.

---

## Wat doet het?

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐     ┌──────────────┐
│             │     │            Manufacturing Pipeline                    │     │              │
│  STEP File  │────▶│                                                      │────▶│  Rapporten   │
│  (.step)    │     │  1. Laad & parse 3D-geometrie (CadQuery/OCP)        │     │              │
│             │     │  2. Classificeer onderdeel (plaatwerk/profiel/etc)   │     │  - PDF       │
└─────────────┘     │  3. Detecteer features:                              │     │  - Excel     │
                    │     - Gaten (cilindrisch + vormgaten)                │     │  - XML       │
                    │     - Zettingen (radius, hoek, K-factor)            │     │  - JSON      │
                    │     - Draad (M3–M68, ISO 68-1)                      │     │  - Database   │
                    │  4. Ontvouw plaatwerk (FreeCAD)                      │     │              │
                    │  5. Pas ISO-normen toe                               │     └──────────────┘
                    │  6. Genereer rapporten                               │
                    └──────────────────────────────────────────────────────┘
```

### Belangrijkste features

- **Onderdeelclassificatie** — Herkent automatisch plaatwerk, draaidelen, profielen, samenstellingen
- **Gatdetectie** — Cilindrische vlakken + inner wire methode voor sleuven en vormgaten
- **Zetanalyse** — Telt productierelevante zettingen, sluit profielen en afrondingen uit
- **Plaatwerk ontvouwen** — FreeCAD SheetMetal workbench met multi-poging strategie
- **AAG Feature Recognition** — Attributed Adjacency Graph voor topologie-gebaseerde herkenning
- **ISO-normen** — ISO 2768, ISO 286, ISO 1302, ISO 68-1, ISO 13715, EN 10025/573
- **ERP-integratie** — XML/Excel export in SpaceClaim-formaat, Windows file watcher service
- **Batchverwerking** — Parallelle analyse van hele mappen met caching

---

## Snel aan de slag

### Vereisten

- Python 3.10+
- [FreeCAD](https://www.freecad.org/) (optioneel, voor plaatwerk ontvouwen)

### Installatie

```bash
git clone https://github.com/djspilot/alestest.git
cd alestest
pip install -r requirements.txt
```

### Eerste analyse draaien

```bash
# Interactieve bestandsselectie
python run.py

# Specifiek bestand analyseren
python run.py -f data/input/mijnonderdeel.step

# AAG topologie-analyse met uitgebreide output
python run.py -f mijnonderdeel.step --aag -v
```

Output verschijnt in `data/output/<onderdeelnaam>/` — bevat PDF-rapport, SVG-afbeeldingen en analysedata.

---

## Gebruiksmodi

### 1. Quick Mode (standaard)

Snelle analyse met PDF-rapport. Ideaal voor dagelijkse werkvoorbereiding.

```bash
python run.py -f part.step              # Basisanalyse
python run.py -f part.step --aag        # Met AAG feature recognition
python run.py -f part.step --excel      # Excel export (SpaceClaim-formaat)
python run.py -f part.step --analyze    # Toon gedetailleerde redenering
python run.py -f part.step --debug      # Debug gatdetectie
python run.py -f part.step --no-unfold  # Sla ontvouwen over
python run.py --list                    # Toon beschikbare STEP-bestanden
```

### 2. Batchverwerking

Verwerk hele mappen. Resultaten worden gecacht voor snelle heranalyse.

```bash
python run.py --batch                             # Alle bestanden in data/input/
python run.py -f ./map --batch -p 4               # Parallel (4 workers)
python run.py --batch --json                      # JSON output voor ERP
python run.py --batch --excel --reference ref.xlsx # Met SpaceClaim-vergelijking
python run.py --batch --no-cache                  # Forceer heranalyse
```

### 3. Full ISO Pipeline

Volledige analyse met database-opslag en alle ISO-normcontroles.

```bash
python run.py -f part.step --full                    # Volledige pipeline
python run.py -f part.step --full --production-info  # Met productietabel
python run.py --full --status                        # Toon cache-status
python run.py --full --from threads                  # Hervat vanaf stage
python run.py --full --list-stages                   # Toon alle stages
python run.py --full --clear-cache                   # Wis cache
```

### 4. REST API (Docker)

Deploy als webservice voor analyse op afstand.

```bash
# Start
docker compose up -d

# Analyseer een bestand
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: jouw-key" \
  -F "file=@mijnonderdeel.step"

# Haal resultaten op
curl http://localhost:8000/api/v1/jobs/{job_id} -H "X-API-Key: jouw-key"

# Verschillende formaten
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=excel"
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=xml"
```

---

## Geautomatiseerd draaien

### Optie A: Windows File Watcher (ERP-integratie)

Monitort automatisch een map op nieuwe STEP-bestanden, analyseert ze en exporteert XML voor ERP-import. Draait als achtergrondservice.

```bash
# 1. Configureer .env
cp .env.example .env
# Zet WATCHED_FOLDER naar je offerte-map, bijv:
# WATCHED_FOLDER=G:\ALES\Offerte-ALES

# 2. Test met een enkel bestand
python deploy/file_watcher_service.py --test --file pad/naar/bestand.step

# 3. Start de watcher
python deploy/file_watcher_service.py
```

Installeer als Windows-service (draait automatisch bij opstarten):
```bash
deploy\install_windows_service.bat
```

Werkwijze:
```
┌──────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│  Offerte-map     │     │  File        │     │  Pipeline    │     │  XML naar   │
│  (netwerk/lokaal)│────▶│  Watcher     │────▶│  Analyse     │────▶│  ERP-map    │
│                  │     │  (watchdog)  │     │              │     │             │
│  Nieuw .step     │     │  Detecteert  │     │  Gaten,      │     │  SpaceClaim │
│  bestand ↓       │     │  wijzigingen │     │  zettingen,  │     │  compatible │
└──────────────────┘     └──────────────┘     │  ontvouwen   │     │  XML output │
                                              └──────────────┘     └─────────────┘
```

### Optie B: Docker API met automatische verwerking

Voor VPS/server deployment. Bestanden uploaden via HTTP, resultaten ophalen als JSON/XML/Excel.

```bash
# 1. Configureer
cp .env.example .env
echo "API_KEYS=mijn-geheime-key" >> .env

# 2. Start
docker compose up -d

# 3. Automatiseer vanuit je eigen systeem
curl -X POST http://jouw-server:8000/api/v1/analyze \
  -H "X-API-Key: mijn-geheime-key" \
  -F "file=@onderdeel.step"
```

### Optie C: Cron/scheduled batch

Draai periodiek een batchanalyse op een inputmap:

```bash
# Elk uur alle nieuwe bestanden analyseren (crontab -e)
0 * * * * cd /opt/ales-pipeline && python run.py --batch --json --no-cache >> /var/log/ales.log 2>&1

# Of op Windows (Taakplanner):
python run.py -f G:\ALES\Input --batch --excel --reference G:\ALES\spaceclaim.xml
```

---

## Architectuur

```
┌──────────────────────────────────────────────────────────────────┐
│                        Ingangspunten                             │
│                                                                  │
│  python run.py ───────┐                                          │
│  python -m mfg_pipe ──┤                                          │
│                       ▼                                          │
│               manufacturing_pipeline/cli.py                      │
│                       │                                          │
│         ┌─────────────┼─────────────┐                            │
│         ▼             ▼             ▼                            │
│    ┌─────────┐  ┌──────────┐  ┌───────────┐                     │
│    │  core/  │  │ analysis/│  │ reporting/│                     │
│    │         │  │          │  │           │                     │
│    │ config  │  │ step_proc│  │ PDF       │                     │
│    │ models  │  │ sheetmtl │  │ Excel     │                     │
│    │ utils   │  │ analyzer │  │ XML       │                     │
│    │         │  │ iso_std  │  │ CLI output│                     │
│    └─────────┘  │ freecad  │  └───────────┘                     │
│                 │ aag      │                                     │
│                 └──────────┘                                     │
│                                                                  │
│  api/app.py ──▶ routes.py ──▶ manufacturing_pipeline (zelfde)   │
│  file_watcher ──▶ map monitoren ──▶ manufacturing_pipeline       │
└──────────────────────────────────────────────────────────────────┘
```

### Analyse-flow

```
              Quick Mode (standaard)                    Full Mode (--full)
              ──────────────────────                    ──────────────────

              ┌──────────────┐                      ┌──────────────────┐
              │  Laad STEP   │                      │    Laad STEP     │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │ Classificeer │                      │  Detecteer gaten │
              │ (type, dikte)│                      │  & zettingen     │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │  Detecteer   │                      │  Geometrie &     │
              │  Features    │                      │  vlakanalyse     │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │  Ontvouw     │                      │  Onderdeel-      │
              │ (als plaat)  │                      │  classificatie   │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │ Genereer PDF │                      │  ISO-normen      │
              └──────────────┘                      │  (2768/286/etc)  │
                                                    └────────┬─────────┘
                                                             │
                                                    ┌────────▼─────────┐
                                                    │  Rapport + DB    │
                                                    └──────────────────┘
```

---

## API-referentie

| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| `POST` | `/api/v1/analyze` | Upload STEP-bestand, retourneert `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Resultaten ophalen (standaard JSON) |
| `GET` | `/api/v1/jobs/{job_id}?format=csv` | Resultaten als CSV |
| `GET` | `/api/v1/jobs/{job_id}?format=xml` | Resultaten als SpaceClaim XML |
| `GET` | `/api/v1/jobs/{job_id}?format=excel` | Resultaten als Excel (.xlsx) |
| `GET` | `/api/v1/health` | Health check |

**Authenticatie:** Zet `API_KEYS` in `.env` (komma-gescheiden voor meerdere keys). Stuur mee als `X-API-Key` header. Leeg = geen auth (alleen dev).

---

## Deployment

### Docker (aanbevolen)

```bash
cp .env.example .env
# Bewerk .env — zet minimaal API_KEYS

docker compose up -d
curl http://localhost:8000/api/v1/health
```

### VPS Setup (Ubuntu)

```bash
apt update && apt install docker.io docker-compose-v2 nginx certbot python3-certbot-nginx

git clone https://github.com/djspilot/alestest.git /opt/manufacturing-api
cd /opt/manufacturing-api
echo "API_KEYS=jouw-geheime-key" > .env
docker compose up -d

# Nginx reverse proxy
cp deploy/nginx.conf /etc/nginx/sites-available/manufacturing-api
ln -s /etc/nginx/sites-available/manufacturing-api /etc/nginx/sites-enabled/
certbot --nginx -d api.jouwdomein.nl
```

### Omgevingsvariabelen

| Variabele | Standaard | Beschrijving |
|-----------|-----------|-------------|
| `API_KEYS` | _(leeg)_ | Komma-gescheiden API-keys |
| `FREECAD_PATH` | `/usr/lib/freecad` | FreeCAD-installatiepad |
| `UPLOAD_DIR` | `/tmp/manufacturing-uploads` | Uploadmap |
| `MAX_FILE_SIZE_MB` | `100` | Max uploadgrootte |
| `JOB_TTL_SECONDS` | `3600` | Hoe lang resultaten bewaard blijven |
| `WATCHED_FOLDER` | — | Map voor file watcher |
| `ENABLE_UNFOLD` | `True` | FreeCAD ontvouwen aan/uit |

---

## Projectstructuur

```
├── run.py                              # Startpunt
├── Dockerfile                          # Docker-image
├── docker-compose.yml                  # Docker-orchestratie
├── requirements.txt                    # Python-dependencies
│
├── manufacturing_pipeline/             # Kernpakket
│   ├── cli.py                          # CLI-interface
│   ├── core/                           # Config, modellen, utilities
│   ├── analysis/                       # Businesslogica
│   │   ├── step_processing.py          #   STEP-parsing, gat/zetdetectie
│   │   ├── sheetmetal_analysis.py      #   Plaatwerk classificatie
│   │   ├── part_analyzer.py            #   Onderdeeltype classificatie
│   │   ├── iso_standards.py            #   ISO/NEN-normen
│   │   ├── freecad_unfold.py           #   FreeCAD ontvouw-integratie
│   │   └── ...
│   ├── data/                           # Caching, database
│   ├── reporting/                      # PDF, Excel, XML, CLI output
│   └── scripts/                        # AAG analyzer, ERP vergelijking
│
├── api/                                # REST API (FastAPI)
├── deploy/                             # Deployment (file watcher, nginx, etc.)
├── tests/                              # Testsuite
├── docs/                               # Documentatie
│   └── ENGINE.md                       # Technische engine-beschrijving
└── data/                               # Runtime data (gitignored)
    ├── input/                          # STEP-bestanden voor analyse
    ├── output/                         # Analyseresultaten
    └── db/                             # SQLite database
```

---

## Ontwikkeling

### Tests draaien

```bash
python -m pytest tests/
```

### ERP-vergelijkingstool

Valideer pipeline-output tegen SpaceClaim-referentiedata:

```bash
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ --aag -v
```

### Dependencies

| Package | Doel |
|---------|------|
| `cadquery` / `cadquery-ocp` | CAD-kernel — STEP-parsing en geometrie |
| `FreeCAD` + SheetMetal workbench | Plaatwerk ontvouwen |
| `fastapi` + `uvicorn` | REST API |
| `openpyxl` | Excel-export |
| `numpy` | Numerieke berekeningen |

---

## Meer informatie

- **[docs/ENGINE.md](docs/ENGINE.md)** — Uitgebreide technische beschrijving van de analyse-engine en vergelijking met SpaceClaim
- **CLAUDE.md** — Instructies voor AI-assistenten die met deze codebase werken
