# ALES Manufacturing Pipeline

**Laatste update:** 23 maart 2026
**Versie:** 3.7-dev (Step 0 stabilisatie + testfundament)

> Zie [TIMELINE.md](TIMELINE.md) voor de volledige versiegeschiedenis.

### v3.7-dev — Step 0 stabilisatie + testfundament (23 maart 2026)

**Doel van deze update:** classificatiepad robuuster maken, regressiepad stabiliseren en testbasis klaarzetten voor feature-validatie per classificatie.

**Wat is gedaan:**

1. **Step 0/CadQuery wrapper-fix**
   - OCP-shape unwrapping toegevoegd voor CadQuery-solids (`shape.wrapped`) in Step 0 section tooling en assembly-geometry helpers.
   - Effect: geen onterechte `step0=0.x` dependency-fallback meer bij CadQuery-solid input.

2. **Classificatiegedrag gevalideerd op 803041-7028**
   - Step 0: `PLAAT` op `0.4a` met `fallthrough=True`.
   - Volledige pipeline (`classify_solid`): eindresultaat `ANDERS`.
   - Dit bevestigt dat fallback nog steeds functioneel en gewenst is.

3. **Test- en pytest-stabilisatie**
   - `pytest.ini` toegevoegd om reguliere testdiscovery te stabiliseren en legacy script-tests uit standaardrun te houden.
   - `tests/test_xml_export.py` gemoderniseerd naar pytest-compatibele smoke-tests (zonder verouderde `PartAnalyzer`-import).
   - Resultaat: `python -m pytest -q` draait stabiel en groen.

4. **Warning-cleanup**
   - NumPy 2.0 deprecation in `step0_section_tools.py` opgelost (2D cross-product zonder `np.cross` op 2D vectors).
   - Ruisende third-party deprecations gefilterd in pytest-config.

**Status nu:**
- Standaard regressierun: **22 passed**
- Classificatieflow is stabiel genoeg om de volgende fase te starten: **feature-opbouw en feature-validatie per classificatieklasse**.

**Plan voor morgen (start fase feature-tests):**
- Featurevalidatie per klasse opzetten (`plaat`, `profiel`, `anders`) met vaste referentiesets.
- Per solid zowel **Step 0 trace** als **final class** vastleggen.
- Tests zo opzetten dat **fallback-invloed expliciet wordt meegenomen** (dus niet alleen eindlabel testen, maar ook pad/regels).
- Eerste focus: `profiel` (`RONDE_BUIS` + `RECHTHOEKIGE_KOKER`) inclusief XML Tube-velden.

### v3.6-dev — Stappenplan StepFile ontwerp (18 maart 2026)

**Nieuwe ontwikkelstroom naast de bestaande pipeline**

Er wordt een alternatieve StepFile-flow opgezet binnen dezelfde repository. Deze nieuwe route gebruikt bestaande code uit `alestest`, maar wordt bewust als aparte ontwikkelstroom opgezet zodat de huidige productieflow intact blijft.

**Kernkeuzes:**

1. De huidige HTML-ingang voor STEP-bestanden blijft behouden.
2. De classificatie wordt expliciet uitgewerkt in een aparte `classification.py` op basis van `classification_step_review.md`.
3. Pas na classificatie volgt de verdiepende geometrie-analyse per categorie.
4. De UI voor classificatie-overzicht en handmatige wijziging komt later.
5. XML/DXF-opbouw wordt als aparte vervolgstap gemoduleerd.

**Advies voor implementatie:**

- Blijf in dezelfde repository werken.
- Gebruik een aparte branch, bijvoorbeeld `feature/stappenplan-stepfile`.
- Push eerst de ontwerpdocumenten, daarna pas de implementatie.
- Bouw de nieuwe flow parallel aan de bestaande pipeline.

**Documenten voor deze ontwikkelstroom:**

- [STAPPENPLAN_STEPFILE.md](STAPPENPLAN_STEPFILE.md) — nieuw architectuur- en branchplan.
- [classification_step_review.md](classification_step_review.md) — specificatie voor de nieuwe classificatielaag.
- [CLASSIFICATION_THRESHOLDS_MATRIX.md](CLASSIFICATION_THRESHOLDS_MATRIX.md) — overzicht van de huidige thresholds en beslismomenten.

### v3.5 — XCAF Segfault Fix + AAG als Fallback (16 maart 2026)

**Twee architectuurwijzigingen die de stabiliteit en snelheid sterk verbeteren**

#### Probleem 1: Segfault op complexe assemblies

Bij het laden van complexe STEP-bestanden (bijv. 803139-0010.step, een bordes met 71 solids) crashte de XCAF reader in de OCP/OpenCascade C++ kernel met een segmentation fault (exit code 139). Dit is een onherstelbare crash — het hele Python-proces sterft.

**Oplossing: XCAF subprocess probe**

De XCAF reader wordt nu eerst in een apart subprocess getest. Als dat subprocess crasht (segfault), valt de pipeline automatisch terug op de CadQuery importer — zonder dat het hoofdproces ooit crasht.

```
XCAF probe (subprocess)
├── OK → laad in-process via XCAF (sneller, namen behouden)
├── CRASH (segfault) → automatisch CadQuery fallback
└── TIMEOUT (>60s) → automatisch CadQuery fallback
```

**Waarom een subprocess?** Een segfault in C++ code (OCP/OpenCascade) kan niet worden gevangen met Python try/except. Het enige veilige mechanisme is het isoleren van de risicovolle code in een apart proces.

| Bestand | Voor | Na |
|---------|------|-----|
| 803139-0010.step (4.5MB, 71 solids) | SEGFAULT (crash) | 57s OK |

#### Probleem 2: AAG als bottleneck

AAG (Attributed Adjacency Graph) analyse draaide altijd als stap 3, via een FreeCAD subprocess met 300s timeout. Voor de meeste bestanden was dit onnodig — de standaard geometrie-analyse (dikte-detectie, bend counting, profiel classificatie) levert al voldoende data.

**Oplossing: AAG als fallback**

AAG draait nu alleen wanneer:
1. `--aag` flag is meegegeven (handmatig forceren), OF
2. Standaard analyse heeft **geen dikte** EN **geen classificatie** gevonden (auto-fallback)

**Waarom?** De standaard analyse (stap 3) detecteert dikte via parallel-face pairing en classificeert via surface ratio's, bend counting en profiel cross-secties. Voor >95% van de onderdelen is dit voldoende. AAG voegt alleen waarde toe bij zeer ongebruikelijke geometrie waar geen van deze methoden werkt.

| Bestand | Voor (AAG primair) | Na (AAG fallback) | Verschil |
|---------|-------------------|-------------------|----------|
| 10001071891_Rev_00.step | 8m 10s | 3m 13s | **-60%** |
| 803139-0010.step | SEGFAULT | 57s | **Werkt nu** |

**Analyse flow (nieuw):**
```
[1/7] Load STEP                → XCAF probe + fallback
[2/7] Profile Router           → PLAAT / PROFIEL / ROND / OVERIG
[3/7] Classify geometry        → Dikte, bends, profiel, sheet metal
      AAG Fallback             → Alleen als stap 3 onvoldoende data geeft
[5/7] Unfold                   → FreeCAD SheetMetal (indien plaatwerk)
[6/7] Detect holes             → Cilindrisch + vormgaten
[7/7] Save results             → PDF, timing JSON
```

**Timing output (voorbeeld met AAG skip):**
```
╔════════════════════════════════════════════════════════════╗
║ 10001071891_Rev_00.step (6.1 MB)                          ║
╠════════════════════════════════════════════════════════════╣
║ [1/7] Load STEP                  4.84s   OK               ║
║ [2/7] Profile Router             0.73s   OK               ║
║ [3/7] Classify geometry          0.35s   OK               ║
║       AAG Fallback               SKIP                     ║
║ [5/7] Unfold                  3m 00s     OK               ║
║ [6/7] Detect holes               7.33s   OK               ║
║       ├─ Cylindrical             0.25s  (8 found)         ║
║       ├─ Shaped                  7.09s  (255 found)       ║
║       └─ Dedup                   0.00s                    ║
║ [7/7] Save results               0.00s   OK               ║
╠════════════════════════════════════════════════════════════╣
║ TOTAL                          3m 13s                     ║
║ Faces: 2,441  Holes: 262  Solids: 7                       ║
╚════════════════════════════════════════════════════════════╝
```

Timing JSON wordt opgeslagen in `data/output/<part>/<part>_timing.json` voor vergelijking tussen bestanden.

### v3.4 — Performance Profiling + Optimalisaties (16 maart 2026)

**Profiling infrastructuur + algoritmische optimalisaties voor grote STEP-bestanden**

| Wijziging | Impact |
|-----------|--------|
| **AnalysisProfiler** (`core/profiler.py`) | Terminal timing-tabel + `_timing.json` per analyse-run |
| **`precompute_face_properties()`** | Eenmalige OCP face-extractie, voorkomt herhaalde `BRepAdaptor` calls |
| **Diameter bucketing** in `detect_holes()` | O(n²) → O(n × bucket) voor hole grouping |
| **Type/dim bucketing** in `detect_shaped_holes()` | O(n²) → O(n × bucket) voor deduplicatie |
| **Squared distance** in inner loops | `math.sqrt()` vermeden waar niet nodig |
| **Normal-direction grouping** in `part_analyzer.py` | Snellere dikte-detectie via anti-parallel lookup |

### v3.3 — Hybride Dwarsdoorsnede + FreeCAD Lip-detectie (16 maart 2026)

**Gezette platen: twee complementaire methodes gecombineerd**

| Methode | Sterk in | Zwakke plek |
|---------|----------|-------------|
| **Dwarsdoorsnede (PCA)** | Lang uniform geperst profiel (U/C/Z) — exact 2 bends @ 90°, t=5mm | Lip < 20% van lengte → valt buiten sample-zone |
| **FreeCAD SheetMetal** | Korte lip met extra zetting bij uiteinde | Complex oppervlak (error 13/17) → faalt |

**Nieuwe beslisboom (hybride):**

```
Dwarsdoorsnede succesvol?
├── JA → gebruik dwarsdoorsnede resultaten
│   └── End-complexity vlag? (meer edges aan uiteinden dan midden)
│       ├── JA → FreeCAD unfold als lip-check
│       │         FreeCAD meer bends? → upgrade naar FreeCAD data
│       │         FreeCAD faalt?      → dwarsdoorsnede + log "possible lip"
│       └── NEE → dwarsdoorsnede volledig, stop
└── NEE → FreeCAD unfold
          Succesvol? → gebruik FreeCAD resultaten
          Faalt ook? → bbox-methode
```

**Technische details:**
- `profile_features.py`: `extract_bent_plate_cross_section()` retourneert nu `has_end_complexity` (bool)
  - Vergelijkt edge-count van end-secties (frac 0.2/0.8) met mediaan van middle-secties (frac 0.4/0.5/0.6)
  - `True` wanneer een uiteinde meer edges heeft → potentiële lip aanwezig
- `xml_exporter.py`: Nieuw HYBRID LIP CHECK blok na de cross-sectie stap
  - Triggert FreeCAD unfold alleen wanneer `has_end_complexity=True`
  - FreeCAD unfold vindt meer bends → upgrade; zelfde bends → cross-sectie behoudt
  - Proactieve unfold overgeslagen als lip-check al gelopen heeft (geen dubbel werk)
- FreeCAD unfold faalt op 10001073529 met codes 13 (plaatdikte ongeldig) + 17 (oppervlak niet ondersteund)
  → dwarsdoorsnede is daar de primaire methode

**Resultaat voor 10001073529_Rev_00:**
- Dwarsdoorsnede: 2 bends @ 90°, t=5 mm, L=1903 mm ✅
- FreeCAD: faalt (codes 13 + 17) → cross-sectie behouden ✅

### v3.2 — Robuustere Gatendetectie (15 maart 2026)

**Fase 2b: Drie structurele verbeteringen in gatendetectie**

| Fix | Probleem | Oplossing |
|-----|----------|-----------|
| **Bore-filter** | Ronde buizen als draaideel geclassificeerd → echte gaten konden wegvallen | `filter_bores=False` + post-filter op depth ratio (>30% langste dimensie = boring) |
| **Dedup vlak-check** | Cilindrisch gat op bovenkant koker kon als duplicaat van shaped opening op kopse kant verwijderd worden | As-paralleliteitscheck (`dot < 0.7` = ander vlak → nooit duplicaat) |
| **Thread disambiguatie** | Ø4.00mm matcht op M4 major EN M5 tapped → onterecht als tapgat geclassificeerd | Als diameter matcht op zowel major als tapped → default naar `round` (clearance gat) |

**Resultaat:** Ø3.24mm → thread (alleen M4 tapped match), Ø4.00mm → round (M4 major + M5 tapped → ambigue).

### v3.1 — Profile Hole Detection (15 maart 2026)

**Nieuw: Gatendetectie voor profielen (Fase 2)**

De pipeline detecteert nu ook gaten in profielen (koker, buis, hoekstaal):

| Feature | Beschrijving |
|---------|-------------|
| **Ronde gaten** | Cylindrische gaten via `detect_holes()` met depth-ratio bore-filter |
| **Vormgaten** | Sleuven/rectangles op planaire vlakken (koker-wanden, flenzen) |
| **Tapgaten** | ISO 68-1 threadherkenning (M3–M68) met major/tapped disambiguatie |
| **Verzonken gaten** | Countersink detectie met hoek |
| **XML export** | Nieuwe `Tube_NrHoles`, `Tube_HoleTypes`, `Tube_ThreadedHoles` etc. velden |

Binnenboring van buizen en koker-wanden worden correct uitgefilterd (geen false positives).

### v3.0 — Profile Router Integration (15 maart 2026)

**Pre-routing classificatie via cross-sectie analyse**

De pipeline bepaalt nu vóór alle analyse welk type onderdeel het is:

| Route | Beschrijving | Profiellabels |
|-------|-------------|---------------|
| **PLAAT** | Vlakke plaat / plaatwerk | `PLAT_STAAL` |
| **PROFIEL** | Stalen profiel (ingekocht) | `I/U/L/T_FAMILY`, `RECHTHOEKIGE_KOKER` |
| **ROND** | Rond staal / buis / draaistuk | `ROND_STAAL`, `RONDE_BUIS` |
| **OVERIG** | Niet-geclassificeerd | `ANDERS` |

**Nieuwe modules:**
- `manufacturing_pipeline/analysis/profile_classifier.py` — Cross-sectie profiel classifier
- `manufacturing_pipeline/analysis/router.py` — Router: `route_step_file()`, `route_solid()`, `map_profile_label()`
- `manufacturing_pipeline/core/models.py` — `RouteCategory` enum

**Analyse flow (quick mode):**
```
[1/7] STEP laden (XCAF probe + CadQuery fallback)
[2/7] Profile Router → PLAAT / PROFIEL / ROND / OVERIG
[3/7] Geometrie analyse (dikte, bends, classificatie)
      AAG Fallback (alleen als stap 3 onvoldoende data geeft)
[5/7] Unfold (indien plaatwerk)
[6/7] Gaten detectie
[7/7] Resultaten opslaan
```

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

- **Profile Router (pre-classificatie)** — Bepaalt vóór analyse het type onderdeel via cross-sectie analyse:
  1. **PLAAT** — Vlakke plaat / plaatwerk
  2. **PROFIEL** — Stalen profiel (I/U/L/T/koker, ingekocht)
  3. **ROND** — Rond staal / buis / draaistuk
  4. **OVERIG** — Niet-geclassificeerd
- **Onderdeelclassificatie (4 categorieën)** —
  1. **Vlakke plaat** (vlakke plaat, geen zettingen) → Box geometry export
  2. **Gezette plaat** (bent sheet met >0 bends) → Unfold via FreeCAD SheetMetal
  3. **Profiel** (draaideel, buis, hoekstaal) → Cross-section karakterisering
  4. **Anders** (samenstellingen, ingewikkelde vormen) → Geometrie-dump
- **⭐ Gatdetectie + Snijdata** —
  - **Fase 1 (plaat/gezette plaat):** Cylindrische gaten + vormgaten, contours, buitencontour, totale snijlengte, flat pattern of 3D
  - **Fase 2 (profielen):** Gaten in koker/buis/hoekstaal, tapgaten, verzonken gaten, XML export (`Tube_NrHoles` etc.)
- **Zetanalyse** — Telt productierelevante zettingen, sluit profielen en afrondingen uit
- **Plaatwerk ontvouwen** — FreeCAD SheetMetal workbench met multi-poging strategie (gezette_plaat only)
- **AAG Feature Recognition (fallback)** — Attributed Adjacency Graph, draait alleen als standaard analyse onvoldoende data oplevert of met `--aag` flag
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
│    │ config  │  │ router   │  │ PDF       │                     │
│    │ models  │  │ prof_cls │  │ Excel     │                     │
│    │ utils   │  │ step_proc│  │ XML       │                     │
│    │         │  │ sheetmtl │  │ CLI output│                     │
│    └─────────┘  │ analyzer │  └───────────┘                     │
│                 │ iso_std  │                                     │
│                 │ freecad  │                                     │
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
              │Profile Router│                      │  Profile Router  │
              │PLAAT/PROFIEL/│                      │  Pre-classificat.│
              │ROND/OVERIG   │                      └────────┬─────────┘
              └──────┬───────┘                               │
                     │                              ┌────────▼─────────┐
              ┌──────▼───────┐                      │  Detecteer gaten │
              │ Classificeer │                      │  & zettingen     │
              │ (type, dikte)│                      └────────┬─────────┘
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
3. **Test:** `python docs/scripts/export_classification_excel.py mijnbestand.stp`
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
│   ├── core/                           # Config, modellen, utilities, profiler
│   ├── analysis/
│   │   ├── router.py                    # Pre-routing: PLAAT/PROFIEL/ROND/OVERIG
│   │   ├── profile_classifier.py        # Cross-sectie profiel classifier
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
├── deploy/                             # Deployment (file watcher, nginx, deploy.sh)
├── tests/                              # Testsuite
├── docs/                               # Documentatie, scripts & archief
│   ├── scripts/                       # Standalone analyse/validatie scripts
│   ├── archive/                       # Historische changelogs, profile_pipeline, etc.
│   └── ENGINE.md                      # Technische engine-beschrijving
└── data/                               # Runtime data (gitignored)
    ├── input/                          # STEP-bestanden voor analyse
    ├── output/                         # Analyseresultaten
    ├── snapshots/                      # XML status snapshots (git-tracked)
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
| **[STAPPENPLAN_STEPFILE.md](STAPPENPLAN_STEPFILE.md)** | Alternatieve StepFile-flow | Nieuwe ontwikkelstroom, branch-aanpak, modulaire opbouw |
| **[classification_step_review.md](classification_step_review.md)** | STEP 0 classificatiespecificatie | Basis voor nieuwe `classification.py` |
| **[CLASSIFICATION_THRESHOLDS_MATRIX.md](CLASSIFICATION_THRESHOLDS_MATRIX.md)** | Huidige thresholds-matrix | Referentie voor bestaande beslisboom |
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

**Laatste update:** 18 maart 2026
**Versie:** 3.6-dev (Stappenplan StepFile ontwerp)

> Zie [TIMELINE.md](TIMELINE.md) voor de volledige versiegeschiedenis t/m v3.5.
