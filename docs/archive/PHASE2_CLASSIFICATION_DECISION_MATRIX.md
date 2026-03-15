# FASE 2: Classification Decision Matrix

**Document**: PHASE2_CLASSIFICATION_DECISION_MATRIX.md  
**Datum**: 5 maart 2026  
**Versie**: 2.2 (Closed & Constant Cross-Section Override)  
**Doel**: Volledige beslisboom voor classificatie met thresholds en code-verwijzingen

---

## Overzicht: Klassieke Beslisboom

De classificatie-algoritme volgt een **waterfall** van 4 stappen (+ substappen):

```
STEP 1: Standard Profile Check (Purchase items)
├─ 1A: Hollow tube detection
├─ 1B: Variable thickness detection  
└─ 1C: Closed constant section detection

STEP 1.5: Bent Sheet Detection
└─ Bend angle sum check (open vs gesloten)

STEP 2: Plate Detection
├─ 2A: Face-based plate detection
└─ 2B: Thin-plate fallback

STEP 3: Profile Detection
└─ Solid beam/profile criteria

STEP 4: Default
└─ → "anders"
```

---

## Matrix 1: Main Decision Tree (Volgorde waarin checks plaatsvinden)

| Stap | Naam Check | Regel/Criteria | Threshold | JA → | NEE → |
|------|-----------|---|---|---|---|
| **1A** | **Hollow tube** | `mid/max >= 0.5` AND `vol_ratio <= 0.7` AND `cyl_pct >= 60%` | `STANDARD_TUBE_CYLINDRICAL_MIN_PCT=60`, `STANDARD_TUBE_VOLUME_RATIO_MAX=0.7` | **`anders`** | 1B |
| **1B** | **Variable thickness** | `length_ratio >= 5` AND `top2_area_diff > 20%` AND ¬bent_sheet | `STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN=5.0`, `STANDARD_PROFILE_FACE_AREA_TOLERANCE=0.20` | **`anders`** | 1C |
| **1C** | **Closed section** | Gate: `smallest>=5`, `longest/mid>=5`, `0.5<=mid/smallest<=2`; Test: `closed_ratio>=0.75`, `perim_cv<=0.08`, `edge_span<=2`, `samples>=3` | `CROSS_SECTION_CLOSED_RATIO_MIN=0.75`, `CROSS_SECTION_PERIMETER_CV_MAX=0.08`, `CROSS_SECTION_EDGE_COUNT_SPAN_MAX=2` | **`profiel`** | 1.5 |
| **1.5a** | **Bent sheet?** | 7 criteria (zie Matrix 2) | (zie Matrix 2) | → 1.5b | 2A |
| **1.5b** | **Bend angle sum** | `bend_angle_sum >= 360°` | (metriek, geen fixed threshold) | **`profiel`** | **`plaat`** |
| **2A** | **Plate (face-based)** | `top2_planar_percent > threshold` | `PLATE_FACE_TOP2_THRESHOLD_PCT=50` (strikt `>`) | **`plaat`** | 2B |
| **2B** | **Thin plate** | `smallest<25` AND `smallest/mid<0.15` AND `longest/smallest>5` | `PLATE_THICK_MAX_MM=25.0`, `PLATE_THICKNESS_RATIO_MAX=0.15`, `PLATE_ASPECT_RATIO_MIN=5.0` | **`plaat`** | 3 |
| **3** | **Solid profile** | `smallest>=5` AND `longest/mid>=5` AND `0.5<=mid/smallest<=2` PLUS `vol_ratio>0.5` OF (`vol_ratio>=0.15` AND `SA/V<1.2`) | `PROFILE_SMALLEST_MIN_MM=5.0`, `PROFILE_LENGTH_RATIO_MIN=5.0`, `PROFILE_CROSS_RATIO_MIN/MAX=0.5/2.0`, `PROFILE_VOLUME_RATIO_STRONG_MIN=0.5`, `PROFILE_SA_V_RATIO_MAX=1.2` | **`profiel`** | 4 |
| **4** | **Default** | (geen check - alles wat overblijft) | - | **`anders`** | einde |

---

## Matrix 2: Bent-Sheet Detection (7 Criteria - Stap 1.5a)

Alle 7 criteria moeten `TRUE` zijn om bent-sheet te zijn.

| Criterium | Beschrijving | Regel | Threshold |
|-----------|---|---|---|
| **1️⃣ Thickness** | Material moet dun zijn (sheet-metal eigenschap) | `smallest <= 100` | `BENT_SHEET_THICKNESS_MAX_MM=100.0` |
| **2️⃣ Edge count** | Buigingen creëren veel edges | `edge_count >= 8` | `BENT_SHEET_MIN_EDGE_COUNT=8` |
| **3️⃣ Volume ratio** | Moet hol/dun, niet solid | `0.10 <= volume_ratio <= 0.50` | `BENT_SHEET_VOLUME_RATIO_MIN=0.10`, `BENT_SHEET_VOLUME_RATIO_MAX=0.50` |
| **4️⃣ Top2% limiet** | Niet te veel oppervlak in 2 faces (flat plaat-achtig) | `top2_pct <= 60` | `BENT_SHEET_TOP2_FACES_MAX_PCT=60.0` |
| **5️⃣ Aspect ratio** | Moet langwerpig zijn | `longest/smallest >= 2.0` | `BENT_SHEET_ASPECT_RATIO_MIN=2.0` |
| **6️⃣ Exclusion: profiel-achtig** | LANGDURIGE profile mag niet als bent-sheet | Als `smallest>=25` AND `longest/mid>=5` AND `0.5<=mid/smallest<=2` AND `vol_ratio<=0.7`: **afkeuren** | (zie 1C gate values) |
| **7️⃣ Exclusion: perfect square/round** | Perfect geometrie = profiel, niet bent | Als `abs((smallest/mid)-1.0)<0.05`: **afkeuren** | (tolerance hardcoded: 0.05) |

**Logica**: 
- Criteria 1-5 moeten ALLEMAAL waar zijn
- IF waar: check criteria 6-7 (exclusions)
- IF beide exclusions ook FALSE: → bent_sheet = TRUE

---

## Matrix 3: "Anders" Klassificatie Routes

Wanneer wordt een solid `"anders"` classify?

| Route | Voorwaarde | Code-line |
|---|---|---|
| **Direct 1A** | Hollow tube detected = TRUE | `alestest/.../assembly_analysis.py:1267` |
| **Direct 1B** | Variable thickness detected = TRUE | `alestest/.../assembly_analysis.py:1274` |
| **Fallback 4** | Geen van alle vorige checks = TRUE | `alestest/.../assembly_analysis.py:1357` |

Dit is jouw "step 1.6": er is geen expliciete extra stap, het is gewoon de default eindbestemming.

---

## Code-referenties (Exact)

**Classificatie-functie**:  
`c:\Data\DS\Python\Spaceclaim_verv\alestest\manufacturing_pipeline\analysis\assembly_analysis.py:1192`

**Helper-functies**:
- `_detect_hollow_tube()`: Line 527
- `_detect_variable_thickness()`: Line 642
- `_detect_closed_constant_cross_section()`: Line 995
- `_detect_bent_sheet()`: Line 704
- `_estimate_bend_angle_sum()`: Line 814
- `_is_plate_by_face_analysis()`: Line 502
- `_get_top2_face_percent()`: Line 786
- `_get_top2_parallel_planar_face_percent()`: Line 433

**Thresholds**:  
`c:\Data\DS\Python\Spaceclaim_verv\alestest\manufacturing_pipeline\analysis\classification_variables.py:1`

---

## Beslispunten per Dimensie

### Volume Ratio (= Volume / Bbox Volume)

| Waarde | Type | Klassificatie |
|--------|------|---|
| 0.95-1.0 | Solid | Potentieel profiel (STEP 3) |
| 0.5-0.95 | Filled | Profiel (STEP 1C of 3) |
| 0.15-0.50 | Hollow/Formed | Bent-sheet (STEP 1.5) OF massief profiel (STEP 3 weak) |
| 0.10-0.15 | Thin | Bent-sheet of profiel met feature |
| <0.10 | Zeer dun | Faalt bent-sheet, mogelijk default |

### Top2% (twee grootste faces)

| Waarde | Type | Klassificatie |
|--------|------|---|
| >60% | Dominant | Vlakke plaat (STEP 2A) OF buizes/profielen |
| 50-60% | Hoog | Vlakke plaat (STEP 2A, als>50) |
| 30-50% | Matig | Bent-sheet (STEP 1.5) OF I-balk (1B) |
| <30% | Laag | Bent-sheet of profiel |
| ~0% | Zeer laag | Massieve balk / profiel |

### Aspect Ratio (Longest / Smallest)

| Waarde | Type | Klassificatie |
|--------|------|---|
| >10 | Zeer langwerpig | Profiel (STEP 3) OF dunne strip |
| 5-10 | Langwerpig | Profiel (STEP 3) OF bent-sheet (STEP 1.5) |
| 2-5 | Matig | Bent-sheet (1.5) of dikke plaat |
| 1-2 | Compact | Niet langwerpig → "anders" |
| ~1 | Vierkant/rond | Massieve block → "anders" |

---

## Test Checklist (FASE 2 Voorbereiding)

Voor elk van de 8 BOM parts moeten we testen:

- [ ] Hollow tube: cylindrical_pct, volume_ratio, aspect
- [ ] Variable thick: face_area_diff, length_ratio, is_bent_sheet
- [ ] Closed section: section_samples, closed_ratio, perimeter_cv, edge_span
- [ ] Bent sheet: edge_count, volume_ratio, top2%, thickness, aspect, exclusions
- [ ] Bend sum: angle_sum, is_360_or_more
- [ ] Plate detection: top2_planar_percent vs 50%
- [ ] Profile detection: volume_ratio, SA/V ratio
- [ ] Final class: expected vs actual

---

## Versie-aantekening

**v2.2 (5 maart 2026)**:
- Closed & Constant Cross-Section override toegevoegd (STEP 1C)
- Bent-sheet exclusion criteria uitgebreid (criteria 6-7)
- Plate threshold = 50% (was eerder verschillend)

---

Dit document vormt de **officiële referentie** voor alle classificatie-logic.  
Alle changes aan thresholds moeten hier gedocumenteerd worden.
