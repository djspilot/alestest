# Unfold Review (Current Pipeline)

Dit document beschrijft de actuele unfold-logica zoals die nu door de manufacturing pipeline wordt gebruikt.

## 1) Actieve route in run_analysis

De actieve pipeline-route is:
- `runtime_analysis.run_analysis(...)`
- `runtime_unfold.run_unfold_to_step(...)`

Belangrijk:
- De actieve route zit niet in `core/utils.py`.
- De actieve route roept niet `analysis/freecad_unfold.unfold_sheet_metal(...)` aan.
- `run_unfold_to_step` bevat zelf een embedded FreeCAD-script en voert de unfold direct uit via subprocess.

## 2) Criteria en thresholds in run_unfold_to_step (actief)

### Trigger in de pipeline
- Unfold wordt alleen geprobeerd als onderdeel als `GEBOGEN PLAATWERK` is geclassificeerd.
- Unfold wordt overgeslagen bij `--no-unfold` of wanneer de stage `unfold` disabled is.

### Subprocess en timeout
- De actieve route start FreeCAD via:
  - `subprocess.run([FREECAD_PYTHON, "-c", unfold_script], timeout=180)`
- Timeout in de actieve route: **180 seconden**.

### Selectie van solids en base faces
In het embedded script:
- Solids worden op volume gesorteerd (aflopend).
- Maximaal top-3 solids worden geprobeerd.
- Voor elke solid:
  - Planar faces worden op oppervlakte gesorteerd (aflopend).
  - Maximaal top-10 base faces worden geprobeerd.

### K-factor
**Toleranties en criteria** (code-volgorde, runtime_unfold.py/thresholds.py):

| Criterium | Threshold | Gevolg |
|---|---|---|
| `k_factor_baseline` | `k = 0.44` | Huidige effectieve baseline voor unfold-berekening |
| `k_factor_thickness_buckets` | `0.5..20.0 mm` buckets | Bucket-lookup actief, maar huidige mapping geeft nog overal `0.44` |
| `k_factor_future_direction` | per dikte + materiaalsoort | Voorbereid op variabele K-factor met expliciete validatie van unfold-uitkomsten |

### Resultaatselectie (beste unfold)
- Geslaagde pogingen krijgen een score:
  - `score = (num_folds * 1000000) + area`
- De poging met hoogste score wint.
- Dit betekent: eerst maximaliseren op aantal fold lines, daarna op vlakke oppervlakte.

### Dikte-detectie
- Dikte wordt per solid berekend door grootste planar face te nemen en afstand te meten naar tegenliggende parallelle face (dot < -0.9).
- Deze gemeten dikte wordt als `thickness` in het unfold-resultaat gezet.
- In `run_analysis` kan deze waarde `analysis.thickness` overschrijven als:
  - `thickness > 0`
  - `thickness < 25.0`
  - en huidige dikte 0 is of > 0.1 afwijkt.

**Toleranties en criteria** (code-volgorde, runtime_analysis.py/runtime_unfold.py):

| Criterium | Threshold | Gevolg |
|---|---|---|
| `opposite_face_match` | `dot < -0.9` | Face telt als geldige tegenliggende parallelle face voor diktebepaling |
| `thickness_positive` | `thickness > 0` | Alleen positieve unfold-dikte mag gebruikt worden |
| `thickness_upper_bound` | `thickness < 25.0 mm` | Uitsluiten van onrealistische overschrijvingen |
| `thickness_delta_or_empty` | `current == 0` of `abs(new-current) > 0.1 mm` | Override alleen bij ontbrekende of materieel afwijkende huidige dikte |

### Fold-merge thresholds
`run_unfold_to_step` clustert fold-segmenten met:
- `offset_tol = 2.0 mm`
- `angle_tol = 1.0 deg`
- `radius_tol = 0.5 mm`
- `overlap_tol = 5.0 mm`
- `gap_tol = 120.0 mm`

Belangrijk:
- Deze criteria en merge-voorwaarde blijven ongewijzigd geldig.
- De waardes zijn nu centraal beheerbaar via `manufacturing_pipeline/core/thresholds.py` (defaults) en `data/config/thresholds.json` (overrides).

Merge-voorwaarde:
- same axis + offset binnen tol
- hoek en radius compatibel binnen tol
- segmenten zijn extension-compatible (`overlap <= 5.0` en `gap <= 120.0`)

Uitleg criteria:
- Same line: segmenten worden als dezelfde lijn gezien wanneer ze dezelfde hoofdas (X of Y) hebben en het offsetverschil `<= 2.0 mm` is.
- Hoekcompatibiliteit: segmenten zijn hoek-compatibel als het hoekverschil `<= 1.0 deg` blijft.
- Radiuscompatibiliteit: segmenten zijn radius-compatibel als het radiusverschil `<= 0.5 mm` blijft.
- Extension-compatibility: segmenten worden samengevoegd wanneer de aansluiting voldoet aan `overlap <= 5.0 mm` en `gap <= 120.0 mm`.

### Resultaatvelden
Bij succes bevat output onder andere:
- `flat_step_path`
- `flat_length`, `flat_width`
- `fold_lines` (na merge, indien merge gelukt)
- `raw_fold_lines` (ongewijzigd)
- `thickness`
- `fold_details`
- `bend_line_segments`
- `bend_line_groups`
- `bends_logical`
- `attempts`
- `error_details`

## 3) Rol van freecad_unfold.py

`analysis/freecad_unfold.py` bevat een aparte unfold-implementatie met eigen defaults en fallback-logica.
Deze route is waardevol voor losse tooling/legacy en tests, maar is **niet** de primaire route vanuit `run_analysis`.

Wat wel relevant blijft:
- Drempels voor cylindrische bend-detectie in die module:
  - `angle_rad > 0.3`
  - `length > 5`
- Daar bestaat ook een FreeCADCmd-fallbackpad met andere control-flow.

## 4) Error handling

Actieve route gebruikt `UNFOLD_ERROR_MESSAGES` voor vertaling van SheetMetalUnfolder-codes, inclusief o.a.:
- 1, 3, 5, 11, 12, 17, 21, 26

Bij mislukking:
- `error_details` bewaart face/stage/code/message.
- `error` wordt samengevat met prioriteit voor exception-details.

## 5) Praktische debugging-afspraak

Voor pipeline-validatie is leidend:
- `runtime_analysis` -> `runtime_unfold.run_unfold_to_step`

Niet leidend voor pipelinegedrag:
- aannames die uit oude `core/utils.py`-teksten komen
- aannames dat de actieve route direct `unfold_sheet_metal(...)` gebruikt

Viewer/debug-uitvoer moet altijd worden geïnterpreteerd als visualisatie van deze pipeline-uitkomst, niet andersom.
