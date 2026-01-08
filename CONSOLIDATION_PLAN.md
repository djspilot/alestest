# Plan: Consolidatie Manufacturing Pipeline

## Doel
Vereenvoudig de projectstructuur door alle code te consolideren in één `src/` folder, met simpele `input/` en `output/` folders.

---

## Nieuwe Structuur

```
/
├── src/                              # ALLE Python modules
│   ├── __init__.py
│   ├── step_processing.py            # Core geometrie analyse
│   ├── iso_standards.py              # ISO tolerantie tabellen
│   ├── sheetmetal_analysis.py        # Plaatwerk analyse
│   ├── part_analyzer.py              # Part classificatie
│   ├── freecad_unfold.py             # FreeCAD integratie
│   ├── assembly_analysis.py          # Multi-solid handling
│   ├── werkvoorbereiding.py          # Kostenschatting
│   ├── report_generator.py           # PDF generatie
│   ├── aag_analyzer.py               # AAG feature recognition (van scripts/)
│   ├── cache_manager.py              # Caching systeem
│   ├── database.py                   # SQLite operaties
│   ├── config.py                     # Configuratie
│   ├── models.py                     # Data models
│   ├── correlation.py                # Dimensie correlatie
│   ├── pdf_processing.py             # PDF parsing
│   └── pmi_processing.py             # PMI extractie
│
├── run.py                            # Hoofd entry point (herschreven)
├── compare_erp.py                    # ERP validatie tool (van scripts/)
│
├── input/                            # STEP bestanden hier plaatsen
│   └── (*.step files)
│
├── output/                           # Analyse resultaten
│   └── <part_name>/
│       ├── images/
│       ├── *_report.pdf
│       └── *_results.json
│
├── data/                             # Database en referentie bestanden
│   └── manufacturing_data.db
│
├── .cache/                           # Pipeline cache (hernoemd)
│
├── requirements.txt
├── CLAUDE.md
└── .gitignore
```

---

## Te Verwijderen

### Folders
| Folder | Actie |
|--------|-------|
| `manufacturing_pipeline/` | modules naar `src/` |
| `scripts/` | essentiële code naar `src/`, rest verwijderen |
| `resources/` | vervangen door `input/`, `output/`, `data/` |
| `examples/` | example STEP naar `input/`, rest verwijderen |

### Debug/Test Scripts (verwijderen)
- `scripts/test_accuracy.py`
- `scripts/test_freecad.py`
- `scripts/test_unfold_holes.py`
- `scripts/debug_bends.py`
- `scripts/debug_excel.py`
- `scripts/inspect_assembly.py`
- `scripts/inspect_solids.py`
- `scripts/inspect_unfold_tree.py`
- `scripts/probe_step_pmi.py`
- `scripts/batch_process.py`

### Dubbele Code (elimineren)
- `scripts/pipeline_functions.py` (1602 regels) → functionaliteit zit al in `src/` modules

### Andere Bestanden
- `manufacturing_pipeline/pipeline_config.json` → config in `src/config.py`
- `manufacturing_pipeline/README.md`
- `manufacturing_pipeline/sql/` folder
- `RESEARCH_QUESTIONS.md`
- `todo.md`

---

## Implementatie Stappen

### Stap 1: Nieuwe folders aanmaken
```bash
mkdir -p src input output data .cache
```

### Stap 2: Modules kopiëren naar src/

**Van `manufacturing_pipeline/src/` (16 bestanden):**
- `step_processing.py`
- `iso_standards.py`
- `sheetmetal_analysis.py`
- `part_analyzer.py`
- `freecad_unfold.py`
- `assembly_analysis.py`
- `werkvoorbereiding.py`
- `report_generator.py`
- `cache_manager.py`
- `database.py`
- `config.py`
- `models.py`
- `correlation.py`
- `pdf_processing.py`
- `pmi_processing.py`
- `__init__.py`

**Van `scripts/`:**
- `aag_analyzer.py` → `src/`
- `compare_erp.py` → root level

### Stap 3: Imports updaten in alle modules

Verander:
```python
# OUD
from manufacturing_pipeline.src.step_processing import ...
from src.step_processing import ...

# NIEUW
from .step_processing import ...
# of
from src.step_processing import ...
```

### Stap 4: Config.py aanpassen

Update paths:
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CACHE_DIR = os.path.join(PROJECT_ROOT, ".cache")
```

### Stap 5: Cache manager aanpassen
- Verander `.pipeline_cache` naar `.cache`
- Update pad referenties

### Stap 6: Database.py aanpassen
- Database pad naar `data/manufacturing_data.db`

### Stap 7: Nieuwe run.py schrijven
- Combineer beste delen van huidige `run.py` en `manufacturing_pipeline/main.py`
- Gebruik `src/` modules direct
- Ondersteun alle huidige CLI opties

### Stap 8: compare_erp.py aanpassen
- Update imports naar `src/`
- Update input/output paden

### Stap 9: Data migreren
```bash
# Database
mv resources/data/manufacturing_data.db data/
# of
mv manufacturing_pipeline/manufacturing_data.db data/

# Example STEP file (optioneel)
mv examples/core_one_assembly.step input/
```

### Stap 10: Oude folders verwijderen
```bash
rm -rf manufacturing_pipeline/
rm -rf scripts/
rm -rf resources/
rm -rf examples/
rm -rf __pycache__/
```

### Stap 11: Bestanden opruimen
```bash
rm -f RESEARCH_QUESTIONS.md
rm -f todo.md
```

### Stap 12: .gitignore updaten
```gitignore
# Input/Output
input/*.step
input/*.stp
output/
.cache/

# Python
__pycache__/
*.pyc

# Database (optioneel tracken)
# data/manufacturing_data.db
```

### Stap 13: CLAUDE.md updaten
Documentatie aanpassen aan nieuwe structuur.

### Stap 14: requirements.txt maken
```
cadquery>=2.4.0
cadquery-ocp
numpy
reportlab
svglib
pandas
openpyxl
pymupdf
edocr
```

---

## Kritieke Bestanden

### Te Modificeren
| Bestand | Wijziging |
|---------|-----------|
| `config.py` | Paden updaten naar input/output/data |
| `cache_manager.py` | Cache pad naar `.cache/` |
| `database.py` | DB pad naar `data/` |
| `run.py` | Herschrijven met nieuwe imports |
| `compare_erp.py` | Imports updaten |

### Te Kopiëren (17 modules)
- Alle modules uit `manufacturing_pipeline/src/` (16)
- `scripts/aag_analyzer.py` (1)

### Te Verwijderen
- 10 debug/test scripts
- `scripts/pipeline_functions.py` (dubbele code)
- Oude folder structuur

---

## Verwacht Resultaat

| Aspect | Voor | Na |
|--------|------|-----|
| Grootte | ~226 MB | ~70 MB |
| Code folders | 4 | 1 (`src/`) |
| Entry points | 2+ | 1 (`run.py`) |
| Structuur | Verwarrend | Duidelijk |

---

## CLI Commando's (na consolidatie)

```bash
# Basis analyse
python run.py -f input/mypart.step

# Met opties
python run.py -f input/mypart.step --no-cache    # Zonder cache
python run.py -f input/mypart.step --aag         # AAG analyse
python run.py -f input/mypart.step --production-info  # Productie info

# Batch verwerking
python run.py --batch

# ERP vergelijking
python compare_erp.py input/AI-voorbeelden/
```

---

## Notities

- **Caching**: Behouden in `.cache/` folder
- **Database**: Behouden in `data/manufacturing_data.db`
- **Werkvoorbereiding**: Behouden voor kostenschattingen
- **ERP tool**: Behouden als `compare_erp.py` in root
