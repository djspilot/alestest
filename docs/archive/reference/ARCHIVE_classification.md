# Classificatie

**Laatste update:** maart 2026
**Bronbestanden:** `classification.py`, `classification_variables.py`, `step0_section_tools.py`, `assembly_analysis.py`

Dit document consolideert de classificatie-documentatie in één referentie.

---

## Overzicht: 4 Categorieën

De pipeline classificeert elk onderdeel in **exact één van 4 categorieën**:

```
┌──────────────────────────────────────────────────────────────────┐
│                   ONDERDEELCLASSIFICATIE                         │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐      │
│  │ VLAKKE PLAAT   │  │ GEZETTE PLAAT  │  │    PROFIEL     │      │
│  │                │  │                │  │                │      │
│  │ • 0 zettingen  │  │ • ≥1 zettingen │  │ • Cylindrisch  │      │
│  │ • Planair      │  │ • Planair base │  │ • L/D >> D     │      │
│  │ • Box dims     │  │ • UNFOLD       │  │ • Cross-sect   │      │
│  │                │  │   applicabel   │  │ • Vol-afhang   │      │
│  │ Bv: stutplaat, │  │ • Solid apart  │  │ • Hoek/buis    │      │
│  │     steunplaat │  │   behandeld    │  │                │      │
│  │                │  │                │  │ Bv: as,        │      │
│  │ XML: Sheet_*   │  │ Bv: deurstuk,  │  │     buis,      │      │
│  │ NrBends = 0    │  │     beugel      │  │     hoekstaal  │      │
│  │                │  │                │  │                │      │
│  │                │  │ XML: Sheet_*   │  │ XML: Tube_*    │      │
│  │                │  │ NrBends > 0    │  │                │      │
│  │                │  │ UnfoldSuccess  │  │                │      │
│  │                │  │ = True         │  │                │      │
│  └────────────────┘  └────────────────┘  └────────────────┘      │
│        ~10-15%              ~40%                ~20%              │
│                                                                  │
│                      ┌────────────────┐                          │
│                      │    ANDERS      │                          │
│                      │                │                          │
│                      │ Alles wat niet │                          │
│                      │ in de 3 groepen│                          │
│                      │ past:          │                          │
│                      │ • Assemblies   │                          │
│                      │ • Complex 3D   │                          │
│                      │ • Niet-metaal  │                          │
│                      │                │                          │
│                      │ XML: Others_*  │                          │
│                      └────────────────┘                          │
│                           ~25%                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Beslisboom: Stappen-overzicht

| # | Stap | Check | Threshold(s) | Als TRUE | Als FALSE |
|---|------|-------|--------------|----------|-----------|
| 0 | STEP 0 | Gesloten constant profiel | zie Step 0 detail | **PROFIEL** | → 0B |
| 0B | STEP 0B | Route profiel (router) | confidence ≥ 0.7 | **PROFIEL/ANDERS** | → 1A |
| 1A | STEP 1 | Plaatdetectie — Face Analysis | `top2_planar% > 50%` | **PLAAT** | → 1B |
| 1B | STEP 1 | Gebogen plaat — Bent Sheet | 7 criteria (zie detail) | **PLAAT** (of PROFIEL als bend_sum ≥ 360°) | → 1C |
| 1C | STEP 1 | Dunne plaat — Plate Thin | `smallest < 25mm` + `thick_ratio < 0.15` + `aspect > 5.0` | **PLAAT** | → 1D |
| 1D | STEP 1 | Gatenrijke plaat — Feature Heavy | 5 criteria (zie detail) | **PLAAT** | → 2B |
| 2B | STEP 2 | Solid rechthoekig profiel | geom → volume → SA/V | **PROFIEL** | → 3A |
| 3A | STEP 3 | Standaard holle buis | `cyl% ≥ 60%` + `vol_ratio < 0.7` + `aspect ≥ 0.5` | **ANDERS** | → 3B |
| 3B | STEP 3 | Variabele dikte profiel | `length_ratio ≥ 5.0` + `top2_faces differ > 20%` + NOT bent_sheet | **ANDERS** | → 4 |
| 4 | STEP 4 | DEFAULT | — | **ANDERS** | — |

Alle thresholds zijn gecentraliseerd in `classification_variables.py` (single source of truth).

---

## Classificatie-pipeline: architectuur

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STEP File Input                                   │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────────┐       ┌──────────────────┐
│  STEP Parser      │       │  CadQuery/OCP    │
│  (Metadata)       │       │  (Geometrie)     │
│                   │       │                  │
│ • Partnamen       │       │ • Solids         │
│ • Assembly struct │       │ • Faces/Edges    │
│ • Counts          │       │ • Volume/BBox    │
└─────────┬─────────┘       └────────┬─────────┘
          │                          │
          └──────────┬───────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  analyze_assembly()   │
         │                       │
         │  1. Group solids      │
         │  2. Match names       │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────────────────────────┐
         │  Classificatie (PER PART)                 │
         │                                           │
         │  IF part_name exists:                     │
         │     IF "DIN/EN/ISO" in name:              │
         │        → class = "anders" (gekocht)       │
         │                                           │
         │  ELSE:                                    │
         │     → classify_solid(solid)               │
         │       → Step 0 → Step 1 → ... → Step 4   │
         └───────────────────────────────────────────┘
```

### Naam-first strategie

De huidige implementatie controleert namen vóór geometrie:

```python
# In analyze_assembly()
if part_name:
    name_upper = part_name.upper()
    is_standard = any(std in name_upper for std in ['DIN ', 'DIN-', 'EN ', 'EN-', 'ISO ', 'ISO-'])
    if is_standard:
        part_class = "anders"  # Gekocht profiel, geen geometrie-check

if part_class is None:
    part_class, class_trace = classify_solid(solid, return_trace=True)
```

### STEP Parser

`parse_step_assembly_structure()` in `assembly_analysis.py` extraheert partnamen uit STEP-metadata (NEXT_ASSEMBLY_USAGE_OCCURRENCE, PRODUCT_DEFINITION). Deze metadata bevat semantische info die niet uit geometrie af te leiden is (bijv. "DIN 1026 - U 160 - 600").

---

## Step 0 Criteria (detail)

Bestanden: `classification.py`, `step0_section_tools.py`

### Begrippen

- **section**: 2D doorsnede van een solid
- **core section**: representatieve sectie uit het dominante sectiecluster
- **holes**: aantal interne lussen in de sectie
- **reentrant_corners**: aantal concave hoeken in de sectie
- **dikteConstant**: constante dikte-indicatie op basis van face-analyse

### Stopregel

Eerste match met `fallthrough=False` stopt de Step 0 classificatie.

### Stap 0.1 — Slice-validatie

Poortcriteria:
- stabiele extrusie-as gevonden
- minimaal 3 geldige dwarsdoorsneden
- dominant cluster ratio >= `STEP0_CLUSTER_RATIO_MIN` (0.30)

As-selectie (2 fasen):
- fase A: kandidaten met `axis_extent >= 0.60 * max_extent`
- fase B: als fase A geen geldige kandidaat oplevert, fallback naar overige assen

Kwaliteitsgates op kandidaat-as:
- `success >= 3`
- `cluster_ratio >= 0.30`
- `mean_section_distance <= 0.50`
- `area_cv <= 0.25`

Subcheck massieve ronde as (alleen bij ronde massieve kernsectie):
- vereist: `holes == 0`, `reentrant_corners == 0`
- ratio: A_axial / (D_max × L)
- als ratio < `ROUND_SHAFT_AXIAL_AREA_RATIO_MIN` (0.99) → `ANDERS`

### Stap 0.2 — Gesloten-hol (buis/koker)

Primaire herkenning:
- `holes == 1`
- outer+inner near-circle → ronde buis pad
- outer+inner near-rectangle → rechthoekige koker pad

Ronde holle buis extra consistentiecheck:

| Check | Maat | Drempel | Uitkomst |
|-------|------|---------|----------|
| Buitendiameter-variatie (OD) | `(max_OD - min_OD) / max_OD` | > 0.15 | → ANDERS |
| Wanddikte-variatie | `(max_t - min_t) / max_t` | > 0.25 | → ANDERS |
| Minimale lengte | `length_ratio` | < 1.5 | skip check |

Secties zonder inner ring worden overgeslagen in wanddikte-check (kan komen door radiale gaten).

Uitkomst:
- ronde buis + checks geslaagd → `RONDE_BUIS`
- ronde buis + check faalt → `ANDERS`
- rechthoekig + criteria geslaagd → `RECHTHOEKIGE_KOKER`
- anders → door naar 0.3

### Stap 0.3 — Open profiel

Criteria:
- `holes == 0`
- `reentrant_corners > 0`
- geen bent-sheet veto
- template match binnen open profielen

Match → `PROFIEL`, anders → door naar 0.4a

### Stap 0.4a — Vlakke plaat

Harde criteria:
- `holes == 0`
- `reentrant_corners == 0`
- `dikteConstant == True`

Confidence-tier:
- high confidence: stop als `near-rectangle` en `bbox_ratio <= 0.30`
- low confidence: `PLAAT` met `fallthrough=True`

### Stap 0.4b — Gezette plaat

Criteria:
- `holes == 0`
- `reentrant_corners > 0`
- `dikteConstant == True`

Bij twijfel op primaire as worden alternatieve assen geëvalueerd.

Match → `GEZETTE_PLAAT`, anders → door naar 0.5

### Stap 0.5 — Massief profiel fallback

Dimensionele/ratio fallback voor `PROFIEL` versus `ANDERS`.

### Kernparameters

| Parameter | Waarde |
|-----------|--------|
| `STEP0_CLUSTER_RATIO_MIN` | 0.30 |
| `ROUND_SHAFT_MIN_LENGTH_RATIO` | 3.0 |
| `ROUND_SHAFT_AXIAL_AREA_RATIO_MIN` | 0.99 |
| Step 0.2 `OD_VAR_MAX` | 0.15 |
| Step 0.2 `WALL_VAR_MAX` | 0.25 |
| Step 0.2 `HOLLOW_TUBE_MIN_LENGTH_RATIO` | 1.5 |

---

## Threshold Matrix (detail per stap)

### Step 0 — Gesloten constant cross-section

Functie: `_detect_closed_constant_cross_section()`

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Geometrie pre-filter | `smallest ≥ 5mm` + `length_ratio ≥ 3.0` + `0.5 ≤ cross_ratio ≤ 3.5` | Alleen extrusion-profielen |
| Uitsluiting gatenrijke plaat | via `_is_feature_heavy_plate_candidate()` | Complexe platen niet als profiel |
| Snijvlakken | 4 samples @ 20%, 40%, 60%, 80% van lengte | Stabiele doorsnede over hele lengte |
| Min geldige samples | ≥ 3 (uit 4) | Laat 1 mislukking toe |
| Gesloten contour ratio | `gesloten_count / samples ≥ 0.75` | Topologisch gesloten |
| Omtrek CV | ≤ 0.08 | Max 8% variatie = constant |
| Edge count spreiding | `max_edges - min_edges ≤ 2` | Max 2 verschil |

### Step 1B — Gebogen plaat (bent sheet)

Functie: `_detect_bent_sheet()`

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Thickness | `smallest ≤ 100mm` | Plaatwerk, niet massief |
| Edge count | ≥ 8 | Vouwspleten = veel randen |
| Volume ratio | `0.10 ≤ vol_ratio ≤ 0.50` | Gevouwen/open, niet hol of massief |
| Top2 faces % | < 60% | Verdeelde faces door vouwen |
| Aspect ratio | ≥ 2.0 | Uitgestrekt |
| Exclusie: rechthoekig profiel | `smallest ≥ 25mm` + `length_ratio ≥ 3.0` + `0.5 ≤ cross ≤ 3.5` + `vol ≤ 0.7` | Kokers uitsluiten |
| Exclusie: perfect rond/vierkant | `abs(cross - 1.0) < 0.05` | Buizen/staven uitsluiten |

Output:
```python
if bend_angle_sum >= 360.0:
    return ("profiel", trace)  # Gesloten bent = profiel
return ("plaat", trace)         # Open bent = plaat
```

### Step 1D — Gatenrijke plaat (feature heavy)

Functie: `_is_feature_heavy_plate_candidate()`

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Top2-planar % bereik | `30% ≤ top2_planar < 50%` | Vangt 30-50% bereik (perforaties) |
| Face count | ≥ 40 | Perforaties = veel kleine faces |
| Edge/face ratio | ≥ 3.0 | Gaten = veel edges per face |
| Volume ratio | < 0.25 | Geperforeerd = hol |
| Aspect ratio | ≥ 2.0 | Plaat is uitgestrekt |

### Step 2B — Solid rechthoekig profiel

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Pre-filter | `smallest ≥ 5mm` + `length_ratio ≥ 3.0` + `0.5 ≤ cross_ratio ≤ 3.5` | Plausibele profielen |
| Volume ratio STRONG | > 0.5 | → PROFIEL (massief) |
| Volume ratio WEAK | 0.15–0.5 | Ambiguïteit |
| SA/V tiebreaker | < 1.2 cm⁻¹ | Lage SA/V = solid → PROFIEL |

### Step 3A — Standaard holle buis

Functie: `_detect_hollow_tube()`

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Aspect ratio | ≥ 0.5 | Niet extreem plat |
| Cylindrische faces % | ≥ 60% | Holle buis = veel cylindrisch |
| Volume ratio | < 0.7 | Hol (veel lucht) |

### Step 3B — Variabele dikte profiel

Functie: `_detect_variable_thickness()`

| Criterium | Threshold | Doel |
|-----------|-----------|------|
| Pre-exclusie | `_is_bent_sheet() == TRUE` | Gebogen platen uitsluiten |
| Length ratio | ≥ 5.0 | DIN profielen zijn langwerpig |
| Top2 face area verschil | > 20% | UNP/I-beam: ongelijke zijden |

---

## Geteste paden

### Pad 1: Plaat (standaard, ~70%)
```
STEP 0 → FALSE → STEP 0B → FALSE → STEP 1A (top2>50%) → TRUE → PLAAT
```

### Pad 2: Plaat (gebogen, U-profiel)
```
STEP 0 → FALSE → STEP 0B → FALSE → STEP 1A → FALSE → STEP 1B (bent sheet) → TRUE
→ bend_sum < 360° → PLAAT
```

### Pad 3: Profiel (gesloten koker, snel)
```
STEP 0 (gesloten constant?) → TRUE → PROFIEL (early exit)
```

### Pad 4: Profiel (massieve balk)
```
STEP 0-1D → alle FALSE → STEP 2B (vol>0.5) → TRUE → PROFIEL
```

### Pad 5: Anders (holle buis)
```
STEP 0-2B → alle FALSE → STEP 3A (cyl>60%, vol<0.7) → TRUE → ANDERS
```

### Pad 6: Anders (UNP/I-beam)
```
STEP 0-3A → alle FALSE → STEP 3B (length>5, face_diff>20%) → TRUE → ANDERS
```

### Pad 7: Anders (default)
```
STEP 0-3B → alle FALSE → STEP 4 DEFAULT → ANDERS
```

---

## Categorie-details

### Vlakke plaat

- Minimaal 1 groot vlak (>70% van oppervlakte)
- `NrBends == 0`
- Direct fabricable (CNC/laser), geen K-factor

```xml
<CalculationResult>
  <Sheet_PartName>MD-20-11832_1</Sheet_PartName>
  <Sheet_Thickness>5</Sheet_Thickness>
  <Sheet_BoxX>221.61</Sheet_BoxX>
  <Sheet_BoxY>160.59</Sheet_BoxY>
  <Sheet_NrBends>0</Sheet_NrBends>
  <Sheet_UnfoldSuccess>False</Sheet_UnfoldSuccess>
</CalculationResult>
```

### Gezette plaat (bent sheet)

- Planaire base + ≥1 zettingen → unfold required
- Unfold via FreeCAD SheetMetal op individuele solid (niet hele assembly)
- K-factor van toepassing

```xml
<CalculationResult>
  <Sheet_PartName>10040853_1</Sheet_PartName>
  <Sheet_Thickness>3</Sheet_Thickness>
  <Sheet_BoxX>63.93</Sheet_BoxX>
  <Sheet_BoxY>3</Sheet_BoxY>
  <Sheet_NrBends>3</Sheet_NrBends>
  <Sheet_BendAngles>30_30_30</Sheet_BendAngles>
  <Sheet_BendInnerRadii>3_3_3</Sheet_BendInnerRadii>
  <Sheet_BendLength>1.92_1.92_1.92</Sheet_BendLength>
  <Sheet_UnfoldSuccess>True</Sheet_UnfoldSuccess>
</CalculationResult>
```

### Profiel

- Cylindrisch oppervlakteaandeel ≥40%, L/D >> 1
- Draaien, frezen, of standaard-profiel
- Geen unfold van toepassing

```xml
<CalculationResult>
  <Tube_PartName>MD-20-11302_2</Tube_PartName>
  <Tube_Type>Profile</Tube_Type>
  <Tube_Count>2</Tube_Count>
  <Tube_CrossSection>hoekstaal_60x60x8</Tube_CrossSection>
</CalculationResult>
```

### Anders

- Alles wat niet in de 3 groepen past (assemblies, gegoten, complex 3D, niet-metaal)
- Manual engineering required

```xml
<CalculationResult>
  <Others_PartName>Samenstelling_XYZ</Others_PartName>
  <Others_Type>Other</Others_Type>
  <Others_Count>1</Others_Count>
</CalculationResult>
```

---

## Bekende beperkingen

- **Step 2A redundantie**: Step 0 controleert al `_detect_closed_constant_cross_section()` met early exit. Step 2A is onbereikbaar en kan verwijderd worden.
- **Naam-based classificatie**: Als STEP parser faalt (returns None), worden alle delen geometrie-geclassificeerd. DIN/EN profielen kunnen dan als plaat eindigen als top2_faces > 50%.
- **Gespiegelde onderdelen**: Kunnen wisselende assen kiezen. Fix aanwezig (alternate-axis fallback in 0.4b) maar beperkt getest.

---

## Bronbestanden

| Bestand | Rol |
|---------|-----|
| `manufacturing_pipeline/analysis/classification.py` | Step 0 beslisboom (`classify_step0()`) |
| `manufacturing_pipeline/analysis/classification_variables.py` | Alle thresholds (single source of truth) |
| `manufacturing_pipeline/analysis/step0_section_tools.py` | Doorsnede-analyse hulpfuncties |
| `manufacturing_pipeline/analysis/assembly_analysis.py` | `classify_solid()`, `analyze_assembly()` |
| `manufacturing_pipeline/analysis/router.py` | Profile router (Step 0B) |
