# ALES Manufacturing Pipeline

**Laatste update:** 2 maart 2026

Geautomatiseerde analyse van STEP CAD-bestanden voor productie. Extraheert geometrie, detecteert features (gaten, zettingen, draad), classificeert onderdelen en genereert productieklare rapporten volgens Nederlandse/ISO-normen.

Gebouwd voor plaatwerk- en metaalbewerkingsbedrijven die snel en nauwkeurig werkvoorbereidingsdata uit 3D-modellen willen halen.

> Voor een uitgebreide technische beschrijving van hoe de engine werkt en hoe deze zich verhoudt tot SpaceClaim, zie **[docs/ENGINE.md](docs/ENGINE.md)**.

> Voor het nieuwe feature-detection traject (v3) en de geplande stappen, zie **[docs/FEATURE_DETECTION_ROADMAP.md](docs/FEATURE_DETECTION_ROADMAP.md)**.

> Voor het classificatie-schema (4 categorieën) en unfold-triggering, zie **[docs/CLASSIFICATION_SCHEMA.md](docs/CLASSIFICATION_SCHEMA.md)** ⭐ **START HIER** voor begrip van how parts flow through the pipeline.

> **Classificatie beslisboom:** Welke criteria worden wanneer toegepast? Zie **[docs/CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md)** voor complete beslisboom met thresholds en rationale. 🌳

> Voor de huidige, gefaseerde XML-uitrol (plaat vlak → plaat gezet/unfold → profiel → gaten plaat → gaten profiel) met validatie via STEP/XML referentieparen, zie **[docs/FEATURE_DETECTION_ROADMAP.md](docs/FEATURE_DETECTION_ROADMAP.md)**.

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

- **Onderdeelclassificatie (4 categorieën)** — 
  1. **Vlakke plaat** (plaair, geen zettingen) → Box geometry export
  2. **Gezette plaat** (bent sheet met >0 bends) → Unfold via FreeCAD SheetMetal
  3. **Profiel** (draaideel, buis, hoekstaal) → Cross-section karakterisering
  4. **Anders** (samenstellingen, ingewikkelde vormen) → Geometrie-dump
- **Gatdetectie** — Cilindrische vlakken + inner wire methode voor sleuven en vormgaten
- **Zetanalyse** — Telt productierelevante zettingen, sluit profielen en afrondingen uit
- **Plaatwerk ontvouwen** — FreeCAD SheetMetal workbench met multi-poging strategie (gezette_plaat only)
- **AAG Feature Recognition** — Attributed Adjacency Graph voor topologie-gebaseerde herkenning
- **ISO-normen** — ISO 2768, ISO 286, ISO 1302, ISO 68-1, ISO 13715, EN 10025/573
- **ERP-integratie** — XML/Excel export in SpaceClaim-formaat, Windows file watcher service
- **Batchverwerking** — Parallelle analyse van hele mappen met caching

---

## ⚙️ Tuning: Alle Classificatie-Parameters (importance!)

**⭐ BELANGRIJK:** Alle machine learning en regelgebaseerde classificatie-parameters zijn gecentraliseerd in **ÉÉN bestand:**

```
manufacturing_pipeline/analysis/classification_variables.py
```

**Waarom dit belangrijk is:**
- Alle thresholds op één plek → makkelijk aanpassen
- Geen code-wijzigingen elders nodig
- Overzicht van wat je kan tunen
- Versiecontrole via Git

**Wat je daar vindt:**
- V3 feature thresholds (planar ratio, aspect ratio, cylindrical ratio)
- Cross-section profile detection (perimeter, L/D verhouding, hollow ratio)
- V2 legacy profile thresholds
- ISO-normen instellingen

👉 **Zie onderaan voor gedetailleerde thresholds en hoe te tunen!**

---

## Snel aan de slag

### Vereisten

- Python 3.10+
- [FreeCAD](https://www.freecad.org/) (optioneel, voor plaatwerk ontvouwen)

### Installatie

```

### Eerste analyse draaien

```bash
# Interactieve bestandsselectie

# Specifiek bestand analyseren
python run.py -f data/input/mijnonderdeel.step

# AAG topologie-analyse met uitgebreide output
Output verschijnt in `data/output/<onderdeelnaam>/` — bevat PDF-rapport, SVG-afbeeldingen en analysedata.

---

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

## Classification Variables (Centralized Tuning)

**Alle classificatie-parameters zijn gecentraliseerd in:** `manufacturing_pipeline/analysis/classification_variables.py`

Dit bestand bevat alle thresholds en instellingen voor de machine learning en regelgebaseerde classificatie. **Pas hier waarden aan om de nauwkeurigheid te tunen** — geen wijzigingen elders in de codebase nodig!

### V3 Classification Thresholds (Feature-based)

```python
# manufacturing_pipeline/analysis/classification_variables.py

# Planar surface detection (highest priority)
v3_planar_ratio_min = 0.74                # Minimaal 74% planaire oppervlakte

# Top-2 faces + aspect ratio
v3_top2_ratio_min = 0.70                  # Top 2 vlakken >= 70% totaal oppervlak
v3_aspect_ratio_min_top2 = 2.8            # L/D voor plaatwerk

v3_aspect_ratio_min_features = 5.0        # L/D voor onderdelen met features

# Extreme aspect ratio detection
v3_aspect_ratio_min_extreme = 8.0         # Zeer elongated

# Cylindrical ratio threshold
v3_cyl_ratio_profile_threshold = 0.40     # >=40% cylindrisch → profiel
```

### Cross-Section Profile Detection (Hollow Profiles)

```python
# Perimeter & length/diameter for holle profielen (koker, buis)
cross_section_perimeter_min_mm = 40       # Minimale perimeter
cross_section_perimeter_max_mm = 1000     # Maximale perimeter
cross_section_length_ratio_min = 1.0      # L/D >= 1.0 (L >= smallest dimension)
cross_section_perim_area_ratio_min = 9.0  # Perimeter/sqrt(area) voor holle detectie
```

### V2 Profile Thresholds (Legacy)

```python
v2_profile_min_thickness_mm = 5.0
v2_profile_length_ratio_min = 5.0
v2_profile_cross_ratio_min = 0.5
v2_profile_cross_ratio_max = 2.0
v2_profile_volume_ratio_min = 0.5
v2_profile_volume_ratio_ambiguous_min = 0.15
v2_profile_sa_v_ratio_max = 1.2
```

### Hoe te tunen?

1. **Openen:** `manufacturing_pipeline/analysis/classification_variables.py`
2. **Pas waarden aan** voor je industrie/producttype
3. **Test:** `python export_classification_excel_v3.py mijnbestand.stp`
4. **Check:** Excel output en `debug_*.py` scripts
5. **Commit:** `git add -A && git commit -m "Tuning: aangepaste thresholds"`

**Voorbeeld:** Wil je meer plaatwerk detecteren? Verhoog `v3_planar_ratio_min` van 0.74 naar 0.72.

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
│   ├── analysis/
│   │   ├── classification_variables.py  # ⭐ CENTRALIZE TUNING (zie boven)
│   │   ├── cross_section_profile.py     # Holle profiel detectie
│   │   ├── step_processing.py           # STEP-parsing, gat/zetdetectie
│   │   ├── sheetmetal_analysis.py       # Plaatwerk classificatie
│   │   ├── part_analyzer.py             # Onderdeeltype classificatie
│   │   ├── iso_standards.py             # ISO/NEN-normen
│   │   ├── freecad_unfold.py            # FreeCAD ontvouw-integratie
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

### Documentatie Overzicht

| Document | Onderwerp | Gebruik Voor |
|----------|-----------|-------------|
| **[docs/ENGINE.md](docs/ENGINE.md)** | Technische engine beschrijving | Engine architectuur, vergelijking met SpaceClaim |
| **[docs/CLASSIFICATION_SCHEMA.md](docs/CLASSIFICATION_SCHEMA.md)** | 4 classificatie categorieën | ⭐ START HIER: Plaat/Profiel/Anders overzicht |
| **[docs/CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md)** | Complete beslisboom met thresholds | 🌳 Welke criteria worden WANNEER toegepast? |
| **[docs/CLASSIFICATION_ARCHITECTURE.md](docs/CLASSIFICATION_ARCHITECTURE.md)** | Classificatie architectuur | Naam vs geometrie, generieke oplossing |
| **[docs/FEATURE_DETECTION_ROADMAP.md](docs/FEATURE_DETECTION_ROADMAP.md)** | Gefaseerde XML-uitrol | Feature detection planning, validatie |
| **[classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py)** | Alle thresholds | ⚙️ Tuning: wijzig waarden hier (single source of truth) |
| **[CLAUDE.md](CLAUDE.md)** | AI-assistent instructies | Voor AI-tools die met deze codebase werken |

### Snelle Links

**Classificatie begrijpen:**
1. Start met [CLASSIFICATION_SCHEMA.md](docs/CLASSIFICATION_SCHEMA.md) — 4 categorieën uitgelegd
2. Bekijk [CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md) — volledige beslisboom
3. Tune thresholds in [classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py)

**Probleem debuggen:**
- Verkeerde classificatie? → Check [CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md) beslisboom
- Threshold aanpassen? → Edit [classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py)
- Architectuur begrijpen? → Lees [CLASSIFICATION_ARCHITECTURE.md](docs/CLASSIFICATION_ARCHITECTURE.md)

---

**Laatste update:** 2 maart 2026  
**Versie:** 2.1 ✓ COMMITTED (Standard Profile Detection met geometry fallback)

### v2.1 Changelog (2 maart 2026)

**Nieuwe features:**
- ✓ Hollow tube detection (EN 10210-2, etc.): cylindrical ≥60% + volume_ratio <0.7
- ✓ Variable thickness profile detection (DIN 1026 UNP, I-beams): face area diff >20%
- ✓ Bent sheet exclusion: voorkomt false positives op gezette platen
- ✓ Generic geometry-based fallback: werkt ook als STEP parser names mist

**Gebruik voor validatie:**
```bash
python validate_classification_only.py  # Test alle 5 referentie files
python analyze_two_parts.py             # Debug EN 10210-2 + DIN 1026 detection
```

**Documentatie:**
- [CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md) - Complete 3-step beslisboom
- [CLASSIFICATION_ARCHITECTURE.md](docs/CLASSIFICATION_ARCHITECTURE.md) - Naam vs geometrie strategie
- [classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py) - Alle v2.1 thresholds
