# ALES Manufacturing Pipeline

Analyseert STEP CAD-bestanden: classificeert onderdelen, detecteert features (gaten, zettingen, draad), ontvouwt plaatwerk en genereert rapporten (PDF/Excel/XML) voor ERP-integratie.

**Status:** quick-only modus — `python run.py`
**Versie:** 3.14-dev (maart 2026)

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐     ┌──────────────┐
│             │     │            Manufacturing Pipeline                    │     │              │
│  STEP File  │────▶│                                                      │────▶│  Rapporten   │
│  (.step)    │     │  1. Laad & parse 3D-geometrie (CadQuery/OCP)        │     │              │
│             │     │  2. Classificeer onderdeel (plaatwerk/profiel/etc)   │     │  - PDF       │
└─────────────┘     │  3. Detecteer features (gaten, zettingen, draad)    │     │  - Excel     │
                    │  4. Ontvouw plaatwerk (FreeCAD)                      │     │  - XML       │
                    │  5. Genereer rapporten                               │     │              │
                    └──────────────────────────────────────────────────────┘     └──────────────┘
```

## Snel aan de slag

### Vereisten

- Python 3.10+
- Voor plaatwerk ontvouwen: een headless FreeCAD runtime met SheetMetal broncode

### Installatie

```bash
pip install -r requirements.txt
```

### Host Python dependencies

De pipeline gebruikt `cadquery` in de host Python omgeving. Controleer of installeer die dependencies met:

```bash
python -m manufacturing_pipeline.tools.ensure_python_deps --doctor
python -m manufacturing_pipeline.tools.ensure_python_deps
```

Automatisch installeren tijdens pipeline-runs kan met:

```bash
PIPELINE_AUTO_INSTALL_PY_DEPS=1 python run.py -f data/input/part.step
```

### Headless unfold runtime

Voor ontvouwen is de desktop-app niet meer de aanbevolen route. Gebruik een beheerde headless runtime:

```bash
python -m manufacturing_pipeline.tools.ensure_unfold_runtime
```

Wat dit doet:
- installeert een lokale FreeCAD runtime onder `.runtime/freecad` via `micromamba` of `conda`
- haalt de `SheetMetal` workbench broncode op
- verifieert `FreeCADCmd`, `Part` en `SheetMetalUnfolder`
- slaat runtime-configuratie op zodat de pipeline die automatisch gebruikt

Extra opties:

```bash
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --no-install
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --update-sheetmetal
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --json
```

Op macOS en Windows gebruikt de pipeline standaard de subprocess-route via `FreeCADCmd`.

### Analyse draaien

```bash
python run.py                              # Interactieve bestandsselectie
python run.py -f data/input/part.step      # Specifiek bestand
python run.py -f part.step --aag           # Met AAG feature recognition
python run.py -f part.step --excel         # Excel export (SpaceClaim-formaat)
python run.py -f part.step --analyze       # Toon gedetailleerde redenering
python run.py -f part.step --debug         # Debug gatdetectie
python run.py -f part.step --no-unfold     # Sla ontvouwen over
python run.py --list                       # Beschikbare STEP-bestanden
```

### Batchverwerking

```bash
python run.py --batch                      # Alle bestanden in data/input/
python run.py -f ./folder --batch -p 4     # Parallel (4 workers)
python run.py --batch --excel              # Excel output
python run.py --batch --json               # JSON output voor ERP
```

### Viewer

```bash
python run_viewer.py
```

## Belangrijkste features

- **Classificatie (4 categorieën)** — Vlakke plaat, gezette plaat, profiel, anders
- **Gatdetectie** — Cilindrische gaten + vormgaten (sleuven, rechthoeken), tapgaten (ISO 68-1), verzonken gaten
- **Zetanalyse** — Productierelevante zettingen, profielherkenning, ERP-telling
- **Plaatwerk ontvouwen** — Headless FreeCAD runtime + SheetMetal broncode, multi-poging strategie
- **ERP-integratie** — XML/Excel export in SpaceClaim-formaat

## Architectuur

```
run.py → manufacturing_pipeline/cli.py
              │
    ┌─────────┼─────────────┐
    ▼         ▼             ▼
 core/     analysis/     reporting/
 config    router         PDF
 models    classification  Excel
 utils     step_processing XML
           sheetmetal      CLI output
           part_analyzer
           freecad_unfold
           iso_standards
```

### Classificatie-parameters

Alle thresholds zijn gecentraliseerd in **één bestand:**

```
manufacturing_pipeline/analysis/classification_variables.py
```

Pas hier waarden aan om de classificatie te tunen — geen codewijzigingen elders nodig.

## Projectstructuur

```
├── run.py                              # Startpunt
├── run_viewer.py                       # Viewer launcher
├── requirements.txt                    # Python dependencies
│
├── manufacturing_pipeline/             # Kernpakket
│   ├── cli.py                          # CLI-interface
│   ├── core/                           # Config, modellen, utilities
│   ├── analysis/                       # Classificatie, detectie, ontvouwen
│   │   ├── classification.py           # Step 0 beslisboom
│   │   ├── classification_variables.py # Alle thresholds (single source of truth)
│   │   ├── step_processing.py          # STEP-parsing, gat/zetdetectie
│   │   ├── freecad_unfold.py           # FreeCAD ontvouw-integratie
│   │   ├── sheetmetal/                 # Interne FreeCAD runtime / SheetMetal helpers
│   │   └── ...
│   ├── reporting/                      # PDF, Excel, XML, CLI output
│   ├── scripts/                        # AAG analyzer, ERP vergelijking
│   ├── tools/                          # Runtime installer / utility commands
│   └── tests/                          # Testsuite
│
├── viewer/                             # Web-based 3D viewer
├── docs/                               # Technische documentatie
└── data/                               # Runtime data (gitignored)
    ├── input/                          # STEP-bestanden
    └── output/                         # Analyseresultaten
```

## Ontwikkeling

```bash
python -m pytest                         # Tests draaien
python run.py -f part.step --debug       # Debug gatdetectie
```

### ERP-vergelijkingstool

```bash
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ --aag -v
```

## Documentatie

Zie [`docs/README.md`](docs/README.md) voor een overzicht van alle technische documentatie.
