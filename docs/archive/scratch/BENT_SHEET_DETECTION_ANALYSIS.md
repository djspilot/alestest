# Gezette Plaat Detectie Criteria - Analyse voor 10001075562_Rev_00

## ❌ Huidige Probleem
Item `10001075562_Rev_00` is een **gezette U-profiel** (gebogen plaatwerk) met:
- **Afmetingen:** 40mm × 60mm × 201,5mm  
- **Dikte:** 3mm  
- **Type:** U-vormig gebogen plaatwerk (formed sheet metal)
- **Huide classificatie:** `anders` (FOUT)
- **Gewenste classificatie:** `plaat` (correct)

---

## ✅ Detectie Criteria uit Code (`classification_variables.py`)

### 1. PLAATWERK DETECTIE (Plate Detection)
**Bron:** `classification_variables.py` lines 27-30

```python
# Top2 faces analysis (primary plate detection method)
PLATE_FACE_TOP2_THRESHOLD_PCT = 50.0  # >=50% surface area in top 2 faces → plate

# Thin plate bbox fallback (when face analysis inconclusive)
PLATE_THICK_MAX_MM = 25.0              # <25mm thickness
PLATE_THICKNESS_RATIO_MAX = 0.15       # smallest/middle < 0.15 (thin)
PLATE_ASPECT_RATIO_MIN = 5.0           # longest/middle > 5.0 (elongated)
```

**Criteria voor classificatie als PLAAT:**
- **Optie A (Primary):** Top 2 gezichten ≥50% van oppervlakte → PLAAT
- **Optie B (Fallback):** 
  - Dikte < 25mm EN
  - Dikterratio < 0.15 EN  
  - Aspectratio > 5.0

---

## ❌ Waarom 10001075562_Rev_00 NIET geclassificeerd wordt als PLAAT

### Probleem 1: Top 2 Gezichten < 50%
**Huidige waarde (geschat):** ~30-35% (omdat de U-vorm veel zijvlakken heeft)  
**Vereist voor PLAAT:** ≥50%  
**⚠️ MISMATCH:** Gezette (gebogen) platen hebben meer zijvlakken dan vlakke platen → lagere top 2%

### Probleem 2: Diktedetectie Faalt
De huidge code checkt alleen `smallest` (dikte = 3mm):
- `smallest = 3mm` ✓ (< 25mm) 
- Maar de **dikterratio** = `smallest / middle` = `3 / 40` = **0.075** ✓ (< 0.15)
- **Aspectratio** = `longest / middle` = ?

**⚠️ ISSUE:** De bounding box dimensies voor een U-profiel zijn:
- Sorted: [3mm, 40mm, 201.5mm] (smallest, middle, longest)
- Maar een **gebogen** plaat heeft **geen rechthoekige vochtvolume** meer!
- Volume_ratio zal veel lager zijn dan voor vlakke platen

---

## 🔍 Geometrische Analyse van U-Profiel

### BBox Dimensies
```
Smallest (thickness):  3.0 mm    ← Plaatdikte
Middle (width):        40.0 mm   ← U openingsbreedte  
Longest (length):      201.5 mm  ← Lengte van profiel
```

### Ratios
- **Thickness ratio:** 3.0 / 40 = **0.075** ✓ (< 0.15 voor plaat)
- **Aspect ratio:** 201.5 / 40 = **5.04** ✓ (> 5.0 voor plaat)
- **Volume ratio:** LAAG (~0.3-0.4) omdat U-vorm veel minder volume dan rechthoek
  - Rechthoekige bbox volume: 3 × 40 × 201.5 = 24,180 mm³
  - Werkelijk volume U-profiel: ~7,000-8,000 mm³ = ~0.33

### Top 2 Gezichten
- Voor **gebogen** U-profiel: ~2 lange flens gezichten + 2 korte U-zijvlakken
- Schatting: ~30-40% van oppervlakte (veel minder dan vlakke plaat >60%)

---

## 🎯 Root Cause

De huige detectie criteria **slagen niet voor gezette (gebogen) platen** omdat:

1. **Face analysis (top2%):** Gebogen geometrie verdeelt oppervlakte over meer gezichten
   - Vlakke plaat: 2 grote gezichten (90%+ van oppervlakte)
   - U-profiel: 4-5 gezichten van ongelijke grootte

2. **Thickness ratio check werkt wel:** Maar wordt **NIET BEREIKT** omdat face analysis faalt eerst
   
3. **Geen huige "bent sheet detection":** De code heeft geen speciale logica voor gefrmde plaatwerk

---

## ✅ OPLOSSING: Gezette Plaat Detectie Toevoegen

**Criteria voor Gezette/Gebogen Plaatwerk:**
```python
# Bent sheet detection - formed plate with small radius bends
BENT_SHEET_LARGE_RADIUS_MIN_MM = 1.0      # Bends have radius >= 1mm
BENT_SHEET_MIN_EDGE_COUNT = 8             # Formed sheets have many edges
```

**Logica:**
1. **Check bent shape:** 
   - Aantal edges ≥ 8 (U-profiel heeft typically 12-16 edges)
   - Thickness < 5mm
   - Volume_ratio 0.25-0.5 (less than solid profile)

2. **Fallback naam check:**
   - Deel van naam bevat: "u-profiel", "gezette", "gebogen", "channel", "channel section"

3**Precedence in code:**
   ```
   if (dikte < 5mm AND aantal_edges >= 8 AND volume_ratio 0.25-0.5):
       → PLAAT (gezette/gebogen)
   ```

---

## 📋 Samenvating

| Criterium | Waarde voor U-Profiel | Grens voor "plaat" | Status |
|-----------|----------------------|-------------------|--------|
| Dikte (smallest) | 3.0 mm | < 25mm | ✅ PASS |
| Dikterratio | 0.075 | < 0.15 | ✅ PASS |
| Aspectratio | 5.04 | > 5.0 | ✅ PASS |
| Top 2% gezichten | ~35% | ≥ 50% | ❌ **FAIL** |
| Volume_ratio | ~0.33 | varies | ⚠️ Ambiguous |
| Aantal edges | ~12-16 | (no check) | ⚠️ Missing |

**Conclusie:** Het item voldoet aan 3 van 4 criteria, maar **faalt op top2% gezicht ratio** omdat gebogen geometrie niet in deze criteria voorzien is.

---

## Git Vastlegging Nodig
Deze analyse moet vastgelegd worden:
1. Update `classification_variables.py` met bent sheet detectie thresholds
2. Update `classify_solid()` functie in `assembly_analysis.py` met bent sheet detection
3. Add detection method `_detect_bent_sheet()` met edge counting logic
4. Test met 10001075562_Rev_00 → moet nu `plaat` opleveren
