# Classificatie Step Review - STEP 0 (Definitieve structuur + exit regels)

## Doel
- Dit document legt STEP 0 eenduidig vast:
  - welke criteria per stap gelden,
  - waarom die criteria nodig zijn,
  - welke broncode erbij hoort,
  - wanneer de beslisboom direct stopt en wanneer hij moet doorvallen.

## Bevestiging van jouw 4 regels
- Ja, dit is de bedoelde hoofdstructuur:
  - 0.2 = alleen holle gesloten secties (buis/koker).
  - 0.3 = open profiel (L/U/I/T).
  - 0.4a = vlakke plaat.
  - 0.4b = gezette plaat.
- En ja: als 0.2 matcht, verlaat de boom STEP 0 direct. Dan ga je niet meer naar 0.3 of 0.4.

## Kerntermen
- section: 2D doorsnede van het solid.
- holes: aantal interne lussen (interior rings) in die section.
- reentrant_corners: aantal inwendige (concave) hoeken van de section.
- dikteConstant:
  - gewenste betekenis: lokale wanddikte ongeveer constant,
  - huidige praktische implementatie: proxy via 3D face-area asymmetrie.

## Stap 0 - Volgorde met exitgedrag

### 0.1 Slice-validatie (poort)
Criteria:
- stabiele extrusie-as,
- minimaal 3 geldige sections,
- dominant section cluster >= 0.30.

Waarom:
- voorkomt false positives op instabiele of niet-extrusie-achtige geometrie.

Exit:
- niet gehaald -> ANDERS (stop).
- wel gehaald -> door naar 0.2.

Broncode:
- manufacturing_pipeline/analysis/profile_classifier.py:1234-1286

Gerelateerde code:
```python
axis = find_extrusion_axis(solid_shape)
if axis is None:
    return {"label": "ANDERS", "reason": "geen stabiele extrusie-as gevonden"}

if len(sections) < 3:
    return {"label": "ANDERS", "reason": "te weinig geldige doorsneden"}

cluster = dominant_section_cluster(sections)
if len(cluster) / max(len(sections), 1) < 0.60:
    return {"label": "ANDERS", "reason": "doorsneden zijn niet stabiel genoeg langs de lengte"}
```

---

### 0.2 Gesloten-hol (koker/buis)
Primaire criteria:
- holes == 1,
- outer+inner near-circle -> RONDE_BUIS,
- outer+inner near-rectangle -> RECHTHOEKIGE_KOKER.

Waarom:
- holes==1 is het sterkste slice-signaal voor holle doorsnede.
- exact "4 corners" is minder robuust dan near-rectangle (fillets/afrondingen).

Extra confidence criteria (optioneel, scoreverhogend):
- cylindrical face percentage hoog,
- volume_ratio laag,
- aspect niet te vlak.

Exit:
- match op buis/koker -> direct classificeren en STEP 0 verlaten.
- geen match -> door naar 0.3.

Broncode:
- hoofdregel: manufacturing_pipeline/analysis/profile_classifier.py:1169-1186
- extra confidence bouwsteen: manufacturing_pipeline/analysis/assembly_analysis.py:575-639

Gerelateerde code:
```python
if features.holes == 1:
    outer = Polygon(poly.exterior.coords)
    inner = Polygon(list(poly.interiors[0].coords))
    if _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94):
        return {"label": "RONDE_BUIS", "method": "rule", "features": features}
    if _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner):
        return {"label": "RECHTHOEKIGE_KOKER", "method": "rule", "features": features}
```

---

### 0.3 Open profiel (L/U/I/T)
Primaire criteria:
- holes == 0,
- reentrant_corners > 0,
- dikteConstant == false.

Waarom:
- reentrant_corners onderscheidt open concave secties van vlakke/massieve rechthoeken.
- template-match borgt dat vorm echt in I/U/L/T familie valt.

Extra confidence criteria:
- best.score <= 0.12 (template threshold),
- family in I_FAMILY/U_FAMILY/L_FAMILY/T_FAMILY,
- bent-sheet veto actief om gezette plaat niet als profiel te labelen.

Exit:
- criteria + confidence gehaald -> PROFIEL en stop.
- anders -> door naar 0.4.

Broncode:
- reentrant: manufacturing_pipeline/analysis/profile_classifier.py:958-974
- template accept: manufacturing_pipeline/analysis/profile_classifier.py:1208-1217
- bent-sheet signal: manufacturing_pipeline/analysis/assembly_analysis.py:752-839

Gerelateerde code:
```python
reentrant = count_reentrant_corners(poly)
matches = match_templates(poly, registry, top_k=5)
best = matches[0] if matches else None
if best and best.score <= template_accept_threshold:
    return {
        "label": best.family,
        "method": "template",
        "top_matches": matches,
    }
```

---

### 0.4a Vlakke plaat
Primaire criteria:
- holes == 0,
- reentrant_corners == 0,
- dikteConstant == true.

Extra confidence criteria (high confidence direct):
- near-rectangle true,
- bbox_ratio <= 0.30.

Waarom:
- voorkomt dat niet-rechthoekige of twijfelachtige solids te vroeg als plaat stoppen.

Exit:
- high confidence gehaald -> PLAAT en stop.
- niet high confidence -> doorvallen naar Step 1 plaatdetectie (1A/1B/1C/1D).

Broncode:
- vlakke plaat rule: manufacturing_pipeline/analysis/profile_classifier.py:1190-1197
- Step 1 fallback regels: manufacturing_pipeline/analysis/assembly_analysis.py:1364-1392

Gerelateerde code:
```python
if features.holes == 0 and _is_nearly_rectangle(poly):
    if features.bbox_ratio <= 0.30:
        return {
            "label": "PLAT_STAAL",
            "confidence": 0.98,
            "method": "rule",
            "features": features,
        }
```

Step 1 fallback (relevant):
```python
if _is_plate_by_face_analysis(solid, threshold=PLATE_FACE_TOP2_THRESHOLD_PCT):
    return "plaat"
if _detect_bent_sheet(solid, volume, dims):
    return "plaat"
if smallest < PLATE_THICK_MAX_MM and thickness_ratio < PLATE_THICKNESS_RATIO_MAX and aspect_ratio > PLATE_ASPECT_RATIO_MIN:
    return "plaat"
if _is_feature_heavy_plate_candidate(...):
    return "plaat"
```

---

### 0.4b Gezette plaat
Primaire criteria:
- holes == 0,
- reentrant_corners > 0,
- dikteConstant == true.

Uitkomst:
- als alle primaire criteria waar zijn -> GEZETTE_PLAAT (stop).

#### Criterion 1: holes == 0 (Geen gaten in doorsnede)
**Betekenis**: De 2D-doorsnede (slice door het solid langs de extrusieas) bevat GEEN interne lussen.

**Interpretatie**:
- `holes == 0` = vlakke doorsnede, geen gaten
- `holes >= 1` = holle doorsnede (koker/buis), moet reeds in 0.2 afgehandeld zijn

**Detectie** (profile_classifier.py):
```python
from shapely.geometry import Polygon as ShapelyPolygon
poly = core_section_polygon  # 2D contour van slice
num_holes = len(poly.interiors)  # Aantal interior rings
# holes == 0 betekent: len(poly.interiors) == 0
```

**Voorbeeld**:
- Rechthoekige plaat: holes=0 ✓
- L-profiel: holes=0 ✓ (open vorm, geen gat)
- U-kanaal: holes=0 ✓ (open vorm, geen gat)
- Rechthoekige koker: holes=1 ✗ (zou in 0.2 stoppen)

---

#### Criterion 2: reentrant_corners > 0 (Concave hoeken = open vorm)
**Betekenis**: De 2D-doorsnede heeft INWENDIGE (concave) hoeken, wat aangeeft dat de vorm OPEN is.

**Interpretatie**:
- `reentrant_corners == 0` = gesloten convex vorm (rechthoek, cirkel, etc.) of volledige vlakke plaat
- `reentrant_corners > 0` = open profiel met inwendige hoeken (L, U, I, T, kanaal, tray, etc.)

**Detectie** (profile_classifier.py:958–974, `count_reentrant_corners`):
```python
def count_reentrant_corners(polygon):
    """Tel inwendige (concave) hoeken in 2D-contour.
    
    Werkwijze:
    - Loop door alle vertexen van de buitencontour
    - Bereken cross-product van twee opeenvolgende edges
    - cross_product < 0 → concave hoek (inwendig)
    - cross_product > 0 → convex hoek (uitwendig)
    """
    reentrant_count = 0
    coords = list(polygon.exterior.coords)
    for i in range(len(coords) - 1):
        v1 = np.array(coords[i+1]) - np.array(coords[i])
        v2 = np.array(coords[i+2]) - np.array(coords[i+1])
        cross = np.cross(v1, v2)
        if cross < 0:  # Concave
            reentrant_count += 1
    return reentrant_count
```

**Voorbeelden van hoeken per profiel**:
- Rechthoek **▭**: reentrant=0 (alle hoeken 90° convex)
- L-profiel **⅃**: reentrant=2 (twee concave binnenhoeken)
- U-kanaal **⊓**: reentrant=2 (twee concave binnenhoeken)
- I-profiel **Ⅰ**: reentrant=4 (vier concave hoeken)
- T-profiel **T**: reentrant=2 of meer (concave hoeken in de T-vorm)

---

#### Criterion 3: dikteConstant == true (Constante wanddikte)
**Betekenis**: De wanddikte van het onderdeel is ONGEVEER CONSTANT langs zijn lengte.

**Interpretatie**:
- `dikteConstant == true` = geen variabele profielen (geen I-beam, UNP, etc.)
- `dikteConstant == false` = profielen met variable oppervlakte (twee grootste vlakken verschillen >20%)

**Detectie** (classification.py:228–252, `_is_constant_thickness`):
```python
def _is_constant_thickness(solid) -> bool:
    """Proxy voor dikteConstant.
    
    Werkwijze:
    - Extraheer alle vlakken uit het solid
    - Sorteer op oppervlak (grootste eerst)
    - Bereken verschil tussen top 2 vlakken
    - Constant = NIET variabele dikte (verschil < threshold)
    """
    areas = sorted(_get_face_areas(solid), reverse=True)
    if len(areas) < 2:
        return True
    
    top_area = areas[0]
    second_area = areas[1]
    
    # Verschil in % van grootste vlak
    area_diff = abs(top_area - second_area) / top_area
    
    # Threshold van variables.py (default: 0.20 = 20%)
    return area_diff <= STANDARD_PROFILE_FACE_AREA_TOLERANCE
```

**Voorbeelden**:
- Flat steel plate **▭**: top2_area_diff ≈ 10% → dikteConstant=true ✓
- L-beam steel **⅃**: top2_area_diff ≈ 15% → dikteConstant=true ✓
- Bent U-channel **⊓**: top2_area_diff ≈ 18% → dikteConstant=true ✓
- DIN I-beam (variable): top2_area_diff ≈ 45% → dikteConstant=false ✗ (zou in 0.5 opnieuw beoordeling krijgen)

---

#### Uitkomstregel

Gegeven dat `holes==0`, `reentrant_corners>0`, en `dikteConstant==true`:
- Label direct als **GEZETTE_PLAAT**.
- Er is binnen 0.4b geen extra bent-sheet discriminatie meer.

---

#### Exit-gedrag

| Uitkomst | Resultaat | Volgende |
|----------|-----------|----------|
| `holes != 0` | ✗ Fallthrough → volgende stap | 0.5 |
| `reentrant_corners == 0` | ✗ Fallthrough → volgende stap | 0.5 |
| `dikteConstant == false` | ✗ Fallthrough → volgende stap | 0.5 |
| `holes==0 && reentrant_corners>0 && dikteConstant==true` | ✓ **GEZETTE_PLAAT** (88%) | STOP |

---

#### Broncode

- Primaire criteria + directe 0.4b-uitkomst: manufacturing_pipeline/analysis/classification.py:613–700
- _is_constant_thickness: manufacturing_pipeline/analysis/classification.py:228–252
- count_reentrant_corners: manufacturing_pipeline/analysis/profile_classifier.py:958–974

---

### 0.5 DikteConstant - huidige implementatie
Huidige proxy:
- dikteConstant = not _detect_variable_thickness(...)

Waarom proxy:
- open contouren hebben geen generieke, robuuste lokale 2D-thickness solver in de huidige code.

Broncode:
- manufacturing_pipeline/analysis/assembly_analysis.py:690-748

Gerelateerde code:
```python
if _is_bent_sheet(solid):
    return False

length_ratio = max_dim / min_dim if min_dim > 0 else 0
if length_ratio < PROFILE_LENGTH_RATIO_MIN:
    return False

area_diff = abs(top_area - second_area) / top_area
return area_diff > STANDARD_PROFILE_FACE_AREA_TOLERANCE
```

---

### 0.6 Massief profiel fallback (behouden)
Criteria:
- profiel gate op dimensions,
- volume_ratio en SA/V bevestiging.

Waarom:
- voorkomt dat niet-platte, massieve rechthoekige bars tussen classificaties vallen.

Exit:
- match -> PROFIEL.
- geen match -> ANDERS.

Broncode:
- manufacturing_pipeline/analysis/assembly_analysis.py:1398-1408

Gerelateerde code:
```python
if smallest >= PROFILE_SMALLEST_MIN_MM and length_ratio >= PROFILE_LENGTH_RATIO_MIN and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX:
    if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
        return "profiel"
    elif volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
        if sa_v_ratio < PROFILE_SA_V_RATIO_MAX:
            return "profiel"
```

## Compacte beslisboom
1. 0.1 slice-validatie, anders ANDERS.
2. 0.2 holle gesloten sectie, match -> buis/koker en stop.
3. 0.3 open profielpad, match -> profiel en stop.
4. 0.4a vlakke plaat high confidence, match -> plaat en stop, anders Step 1 fallback.
5. 0.4b constant-dikte open sectie: holes==0 + reentrant>0 + dikteConstant=true -> gezette plaat, en stop.
6. 0.6 massief profiel fallback, anders ANDERS.

## Kritieke risico's
- R1: constante-dikte open profielen met concave sectie gaan nu altijd naar gezette plaat in 0.4b.
- R2: dikteConstant blijft een proxy; open-sectie fouten blijven mogelijk.
- R3: kwaliteitsgrens van 0.4b hangt nu volledig op de drie primaire criteria; fout in holes/reentrant/dikteConstant werkt direct door op label.
- R4: BENT_SHEET_LARGE_RADIUS_MIN_MM ontbreekt in centrale variables, waardoor _is_bent_sheet fragiel kan zijn.
  - gebruikslocatie: manufacturing_pipeline/analysis/assembly_analysis.py:678

## Slot
- Je 4-regel structuur is correct als basisstructuur.
- De extra confidence-criteria hierboven zijn nodig om classificatienauwkeurigheid hoog te houden.
- Vlakke plaat mag direct stoppen bij high confidence; anders expliciet door naar Step 1 fallback.

---

## Pipeline Entry Point (definitief)

### Correct pipeline voor classificatie

```
STEP file
  → assembly_analysis.py::analyze_assembly()   [BOM-extractie → losse solids]
      ↳ xcaf_reader.py::xcaf_match_solids_to_names()          [XCAF primary]
      ↳ TopExp_Explorer + parse_step_shape_rep_name_counts()   [fallback]
  → classify_solid(solid, return_trace=True)    [per solid]
      ↳ classify_step0(solid)                   [Step 0 entry point]
  → BOMItem.part_class + BOMItem.classification_trace
```

### NIET via:
- `router.py::route_step_file()` → `profile_classifier.py`  
  (gebruikt `OCC.Core.*` — niet beschikbaar; OCP via `from OCP.X import Y` wel)
- `cli.py::run_full_pipeline()` Stage 1–14  
  (geometry stages, ISO standards, werkvoorbereiding — niet nodig voor classificatie)

### Reden
`pre-routing` via `router.py` koppelt aan `profile_classifier.py`, dat intern `from OCC.Core.X import Y`
gebruikt. OCC.Core is niet beschikbaar in deze omgeving. OCP is wel beschikbaar en wordt al
gebruikt door `assembly_analysis.py` direct.

### Quick-start: directe classificatie

```bash
python run.py --step0 <step_file.step>
```

Dit slaat Stage 1–14 van de volledige pipeline over en gaat direct via assembly BOM-extractie
naar classificatie per solid.

### Code-pad voor Step 0

```python
import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly

assembly = cq.importers.importStep("mijn_onderdeel.step")
result = analyze_assembly(
    assembly,
    assembly_name="mijn_onderdeel",
    step_file_path="mijn_onderdeel.step",
)

for item in result.flat_bom:
    features = item.classification_trace.get("features", {})
    step0_step  = features.get("step0_step", "?")
    step0_label = features.get("step0_label", "?")
    print(f"{item.part_name}: {item.part_class}  (step0={step0_step}, label={step0_label})")
```

### Aanroepketen

| Laag | Bestand | Functie | Rol |
|------|---------|---------|-----|
| entry | `run.py` | `--step0` mode | start + output |
| BOM extractie | `assembly_analysis.py` | `analyze_assembly()` | solids extraheren + namen mappen |
| classificatie wrapper | `assembly_analysis.py` | `classify_solid()` | Step 0 aanroepen + fallback |
| Step 0 | `classification.py` | `classify_step0()` | stap 0.1 → 0.5 beslisboom |
| (optioneel) | `profile_classifier.py` | stap 0.1–0.4a | vereist OCC.Core — kan falen |
- 0.4b routeert nu direct op primaire criteria: holes==0 + reentrant>0 + dikteConstant=true -> gezette plaat.
