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
- dominant section cluster >= 0.60.

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

Besliscriterium:
- _detect_bent_sheet(solid, volume, dims) == true -> GEZETTE PLAAT,
- _detect_bent_sheet(solid, volume, dims) == false -> PROFIEL.

Waarom:
- scheidt constant-dikte open secties direct in STEP 0.
- voorkomt dat 0.4b eerst nog moet doorvallen naar Step 1 voordat profiel versus gezette plaat beslist is.

Exit:
- _detect_bent_sheet == true -> GEZETTE PLAAT en stop.
- _detect_bent_sheet == false -> PROFIEL en stop.

Broncode:
- bent sheet criteria: manufacturing_pipeline/analysis/assembly_analysis.py:752-839

Gerelateerde code:
```python
if _detect_bent_sheet(solid, volume, dims):
    return "plaat"
return "profiel"
```

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
5. 0.4b constant-dikte open sectie: `_detect_bent_sheet` true -> plaat, false -> profiel, en stop.
6. 0.6 massief profiel fallback, anders ANDERS.

## Kritieke risico's
- R1: constante-dikte L-profielen hangen nu volledig af van `_detect_bent_sheet`; een false positive geeft onterecht gezette plaat.
- R2: dikteConstant blijft een proxy; open-sectie fouten blijven mogelijk.
- R3: echte gezette platen hangen in 0.4b ook volledig af van `_detect_bent_sheet`; een false negative geeft onterecht profiel.
- R4: BENT_SHEET_LARGE_RADIUS_MIN_MM ontbreekt in centrale variables, waardoor _is_bent_sheet fragiel kan zijn.
  - gebruikslocatie: manufacturing_pipeline/analysis/assembly_analysis.py:678

## Slot
- Je 4-regel structuur is correct als basisstructuur.
- De extra confidence-criteria hierboven zijn nodig om classificatienauwkeurigheid hoog te houden.
- Vlakke plaat mag direct stoppen bij high confidence; anders expliciet door naar Step 1 fallback.
- 0.4b routeert nu direct met `_detect_bent_sheet`: false = profiel, true = gezette plaat.
