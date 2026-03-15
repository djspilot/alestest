# FASE 1: COMPLETE INVENTARISATIE - Classificatie Criteria

## Overzicht Detectiefuncties

### A. GEOMETRISCHE METINGEN (Basis)
Deze functies meten fundamentele eigenschappen van een solid:

| Functie | Doel | Return Type | Gebruikt door |
|---------|------|-------------|---------------|
| `get_solid_volume()` | Volume in mm³ | float | Alle ratio berekeningen |
| `get_solid_bounding_box()` | Bbox [L, W, H] in mm | tuple(3) | Dimensie ratios |
| `get_solid_topology_counts()` | Aantal faces, edges | tuple(2) | Bent sheet detect |
| `_get_solid_surface_area()` | Totaal oppervlak mm² | float | SA/V ratio |
| `_solid_bbox_sorted()` | Dims [klein, mid, lang] | tuple(3) | Ratio consistency |
| `_get_solid_bbox_extents()` | xmin,ymin,... xmax,ymax | tuple(6) | Section slicing |

**Wiskundige Basis**:
```python
volume_ratio = volume / (L × W × H)              # 0-1, hoeveel van bbox is gevuld?
thickness_ratio = smallest / middle              # 0-1, hoe dun relatief?
aspect_ratio = longest / middle                  # >1, hoe langwerpig?
length_ratio = longest / smallest                # >1, lang vs dik?
cross_ratio = middle / smallest                  # ~1 = vierkant, anders rechthoekig
sa_v_ratio = surface_area / volume              # cm⁻¹, oppervlak per volume
```

---

### B. OPPERVLAK ANALYSE (Plate Detection)

#### B1. `_get_top2_face_percent(solid) -> float`
**Doel**: Meet % oppervlak in de 2 grootste faces
**Methode**: 
- Sorteer alle faces op oppervlakte
- Neem top 2
- Return: (face1_area + face2_area) / total_area × 100

**Gebruik**: Platen hebben dominant top/bottom faces (>50%)

**Code locatie**: Line 786
**Threshold**: `PLATE_FACE_TOP2_THRESHOLD_PCT = 50.0`

---

#### B2. `_get_top2_parallel_planar_face_percent(solid) -> float`
**Doel**: Zoals B1 maar ALLEEN parallelle vlakke faces
**Methode**:
- Filter alleen vlakke faces (GeomAbs_Plane)
- Check parallelisme via dot product van normalen
- Neem grootste 2 parallelle faces

**Gebruik**: Stricter plate check (negeer cylindrische caps)

**Code locatie**: Line 433
**Threshold**: Gebruikt in face analysis

---

#### B3. `_is_plate_by_face_analysis(solid, threshold=60.0) -> bool`
**Doel**: Bepaal of solid een plaat is obv faces
**Methode**: Return top2_percent >= threshold

**Code locatie**: Line 502
**Threshold**: `PLATE_FACE_TOP2_THRESHOLD_PCT = 50.0` (default 60 in functie)

---

### C. TUBE/PIPE DETECTION (Standard Profile)

#### C1. `_detect_hollow_tube(solid, volume, dims) -> bool`
**Doel**: Detecteer holle buizen (EN 10210, kokers)
**Methode**:
1. Meet % cylindrisch oppervlak
2. Check volume_ratio (moet laag zijn = hol)
3. Check aspect_ratio (niet gecomprimeerd)

**Criteria**:
```python
cylindrical_pct >= 60.0%  AND
volume_ratio < 0.7        AND
aspect_ratio >= 0.5
```

**Code locatie**: Line 527
**Thresholds**:
- `STANDARD_TUBE_CYLINDRICAL_MIN_PCT = 60.0`
- `STANDARD_TUBE_VOLUME_RATIO_MAX = 0.7`
- `STANDARD_TUBE_ASPECT_MIN = 0.5`

**Return**: `True` → classify as "anders" (purchased)

---

#### C2. `_detect_variable_thickness(solid, dims) -> bool`
**Doel**: Detecteer I-balken, UNP, L-profielen (variabele dikte)
**Methode**:
1. Sorteer faces op oppervlak
2. Check top 2 faces: verschil > 20%?
3. Check elongated (length_ratio >= 5.0)

**Criteria**:
```python
|face1_area - face2_area| / max(face1, face2) > 0.20  AND
length_ratio >= 5.0
```

**Code locatie**: Line 642
**Thresholds**:
- `STANDARD_PROFILE_FACE_AREA_TOLERANCE = 0.20`
- `STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN = 5.0`

**Return**: `True` → classify as "anders" (purchased)

---

### D. CLOSED EXTRUSION DETECTION (Hard Profile)

#### D1. `_detect_closed_constant_cross_section(solid, dims) -> (bool, dict)`
**Doel**: Detecteer closed/open profiles met constante doorsnede
**Methode**: (GEEN echte cross-section slice!)
1. Sample 4 planes langs lengterichting (20%, 40%, 60%, 80%)
2. Per plane: tel edges, check closed loops
3. Check consistency:
   - ≥75% closed contours
   - Perimeter variatie < 8%
   - Edge count spread ≤ 2

**Pseudo-slicing**: Gebruikt BRepAlgoAPI_Section maar geen echte mesh slicing

**Code locatie**: Line 995
**Thresholds**:
- `CROSS_SECTION_SAMPLE_FRACTIONS = (0.2, 0.4, 0.6, 0.8)`
- `CROSS_SECTION_CLOSED_RATIO_MIN = 0.75`
- `CROSS_SECTION_PERIMETER_CV_MAX = 0.08`
- `CROSS_SECTION_EDGE_COUNT_SPAN_MAX = 2`

**Return**: `(True, metrics)` → classify as "profiel"

---

### E. BENT SHEET DETECTION

#### E1. `_detect_bent_sheet(solid, volume, dims) -> bool`
**Doel**: Detecteer gevouwen/gezette plaat (U-profiel, bakjes)
**Methode**: Check combinatie van:
1. Veel edges (≥8) door buigingen
2. Laag volume_ratio (0.10 - 0.50)
3. Niet te hoge top2_faces (<60%)
4. Thin-ish (smallest < 100mm, ruim)
5. Elongated (aspect >= 2.0)

**Criteria** (ALLE moeten waar zijn):
```python
edge_count >= 8               AND
0.10 <= volume_ratio < 0.50   AND
top2_percent < 60.0           AND
smallest < 100.0              AND
aspect_ratio >= 2.0
```

**Code locatie**: Line 704
**Thresholds**:
- `BENT_SHEET_MIN_EDGE_COUNT = 8`
- `BENT_SHEET_VOLUME_RATIO_MIN = 0.10`
- `BENT_SHEET_VOLUME_RATIO_MAX = 0.50`
- `BENT_SHEET_TOP2_FACES_MAX_PCT = 60.0`
- `BENT_SHEET_THICKNESS_MAX_MM = 100.0`
- `BENT_SHEET_ASPECT_RATIO_MIN = 2.0`

**Return**: `True` → classify as "plaat" (unless closed loop ≥360°)

---

#### E2. `_estimate_bend_angle_sum(solid) -> float`
**Doel**: Schat totale buighoek (som van alle bends)
**Methode**:
1. Find cylindrische faces (bends)
2. Per cilinder: meet hoek via arc length
3. Filter: min angle 20°, min length 5mm
4. Return sum

**Gebruik**: Als sum ≥ 360° → closed profile (niet bent sheet)

**Code locatie**: Line 814
**Thresholds**: min_angle=20°, min_length=5mm

---

### F. LEGACY/HULP FUNCTIES

#### F1. `_is_bent_sheet(solid) -> bool`
**DEPRECATED** - Oude versie, line 596
Gebruik `_detect_bent_sheet()` in plaats daarvan

---

## SAMENVATTING: ALLE THRESHOLDS

| Variabele | Waarde | Gebruikt in | Betekenis |
|-----------|--------|-------------|-----------|
| **PLATE** ||||
| PLATE_FACE_TOP2_THRESHOLD_PCT | 50.0% | Face analysis | Top2 faces > 50% = plaat |
| PLATE_THICK_MAX_MM | 25.0 mm | Thin plate fallback | Dikte < 25mm = dun |
| PLATE_THICKNESS_RATIO_MAX | 0.15 | Thin plate fallback | smallest/middle < 0.15 |
| PLATE_ASPECT_RATIO_MIN | 5.0 | Thin plate fallback | longest/middle > 5 |
| **PROFILE** ||||
| PROFILE_SMALLEST_MIN_MM | 5.0 mm | Profile detect | Niet te dun |
| PROFILE_LENGTH_RATIO_MIN | 5.0 | Profile detect | Langwerpig |
| PROFILE_CROSS_RATIO_MIN | 0.5 | Profile detect | Rechthoekig cross |
| PROFILE_CROSS_RATIO_MAX | 2.0 | Profile detect | section |
| PROFILE_VOLUME_RATIO_STRONG_MIN | 0.5 | Profile detect | Sterk bewijs (solid) |
| PROFILE_VOLUME_RATIO_WEAK_MIN | 0.15 | Profile detect | Zwak (tiebreaker) |
| PROFILE_SA_V_RATIO_MAX | 1.2 cm⁻¹ | Profile tiebreaker | Tiebreaker voor weak |
| **STANDARD TUBE** ||||
| STANDARD_TUBE_CYLINDRICAL_MIN_PCT | 60.0% | Hollow tube | Cylindrisch oppervlak |
| STANDARD_TUBE_VOLUME_RATIO_MAX | 0.7 | Hollow tube | Hol (niet solid) |
| STANDARD_TUBE_ASPECT_MIN | 0.5 | Hollow tube | Niet samengedrukt |
| **STANDARD PROFILE** ||||
| STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN | 5.0 | Variable thickness | Langwerpig |
| STANDARD_PROFILE_FACE_AREA_TOLERANCE | 0.20 | Variable thickness | Top2 verschil >20% |
| **BENT SHEET** ||||
| BENT_SHEET_THICKNESS_MAX_MM | 100.0 mm | Bent sheet | Max dikte |
| BENT_SHEET_MIN_EDGE_COUNT | 8 | Bent sheet | Min edges (bends) |
| BENT_SHEET_VOLUME_RATIO_MIN | 0.10 | Bent sheet | Min volume fill |
| BENT_SHEET_VOLUME_RATIO_MAX | 0.50 | Bent sheet | Max volume fill |
| BENT_SHEET_TOP2_FACES_MAX_PCT | 60.0% | Bent sheet | Max top2 faces |
| BENT_SHEET_ASPECT_RATIO_MIN | 2.0 | Bent sheet | Min langwerpig |
| **CROSS SECTION** ||||
| CROSS_SECTION_SAMPLE_FRACTIONS | (0.2, 0.4, 0.6, 0.8) | Closed profile | Sample posities |
| CROSS_SECTION_MIN_VALID_SAMPLES | 3 | Closed profile | Min succesvolle slices |
| CROSS_SECTION_CLOSED_RATIO_MIN | 0.75 | Closed profile | 75% closed contours |
| CROSS_SECTION_PERIMETER_CV_MAX | 0.08 | Closed profile | Max variatie (8%) |
| CROSS_SECTION_EDGE_COUNT_SPAN_MAX | 2 | Closed profile | Max edge verschil |

---

## DECISION TREE (Huidige Implementatie)

```
classify_solid(solid)
│
├─ STEP 1A: _detect_hollow_tube()
│  └─ cylindrical≥60% AND vol_ratio<0.7 AND aspect≥0.5
│     ├─ TRUE → "anders" (purchased tube)
│     └─ FALSE → continue
│
├─ STEP 1B: _detect_variable_thickness()
│  └─ face_diff>20% AND length_ratio≥5
│     ├─ TRUE → "anders" (purchased I-beam/UNP)
│     └─ FALSE → continue
│
├─ STEP 1C: _detect_closed_constant_cross_section()
│  └─ closed_ratio≥0.75 AND perim_cv<0.08 AND edge_span≤2
│     ├─ TRUE → "profiel" (closed extrusion)
│     └─ FALSE → continue
│
├─ STEP 1.5: _detect_bent_sheet()
│  └─ edges≥8 AND 0.1<vol<0.5 AND top2<60% AND smallest<100 AND aspect≥2
│     ├─ TRUE → Check bend_angle_sum
│     │   ├─ sum ≥ 360° → "profiel" (closed loop)
│     │   └─ sum < 360° → "plaat" (bent sheet)
│     └─ FALSE → continue
│
├─ STEP 2A: _is_plate_by_face_analysis()
│  └─ top2_percent ≥ 50%
│     ├─ TRUE → "plaat"
│     └─ FALSE → continue
│
├─ STEP 2B: Traditional thin plate check
│  └─ smallest<25 AND thickness_ratio<0.15 AND aspect>5
│     ├─ TRUE → "plaat"
│     └─ FALSE → continue
│
├─ STEP 3: Profile detection
│  └─ smallest≥5 AND length_ratio≥5 AND 0.5≤cross_ratio≤2.0
│     ├─ volume_ratio > 0.5 → "profiel" (strong)
│     ├─ 0.15 ≤ volume_ratio ≤ 0.5 → Check SA/V tiebreaker
│     │   ├─ sa_v_ratio < 1.2 → "profiel" (weak)
│     │   └─ sa_v_ratio ≥ 1.2 → continue
│     └─ volume_ratio < 0.15 → continue
│
└─ STEP 4: Default
   └─ → "anders" (machined part)
```

---

## NEXT STEP: Test alle functies met onze 8 parts

We moeten nu per part zien wat elke functie teruggeeft:

| Part | Classificatie | Hollow Tube? | Variable Thick? | Closed Section? | Bent Sheet? | Top2% | Vol Ratio | ... |
|------|---------------|--------------|-----------------|-----------------|-------------|-------|-----------|-----|
| 10000255318 | plaat | ? | ? | ? | ? | ? | ? | ... |
| 10000503252 | anders | ? | ? | ? | ? | ? | ? | ... |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Klaar voor FASE 2?** Willen we nu een debug script maken dat ALLE deze metingen voor onze 8 parts uitvoert?
