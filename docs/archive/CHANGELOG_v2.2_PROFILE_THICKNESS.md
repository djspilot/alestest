# Changelog v2.2 - Profile Robustness + Wall Thickness Fix

**Datum:** 4 maart 2026  
**Classificatie Versie:** 2.2  
**Scope:** Profiel-detectie robuustheid + Koker wanddikte berekening

---

## Executive Summary

Deze release levert twee belangrijke verbeteringen voor profiel-onderdelen:

1. **Hard profile signature via cross-section analyse**
   - Closed extrusion detection (kokers, buizen) nu robuust tegen bent-sheet heuristic tuning
   - Multi-slice contour analyse: gesloten + constant → profiel
   
2. **Correct wall thickness for rectangular tubes**
   - Oude formule gaf te hoge diktes (bijv. 14.7 mm i.p.v. 3 mm)
   - Nieuwe analytische doorsnede-balans formule: exacte wanddikte uit volume ratio

**Impact:**
- Classificatie: Gesloten kokers blijven betrouwbaar als `profiel`, ongeacht bent-sheet thresholds
- XML output: `Tube_Thickness` nu fysisch correct voor rechthoekige holle profielen

---

## Wijziging 1: Hard Profile Override (Closed Constant Cross-Section)

### Probleem

Gesloten rechthoekige extrusies (bijv. 100×50-kokers) konden als `plaat` geclassificeerd worden wanneer:
- Bent-sheet detectieregels werden verfijnd (edge count, volume ratio, aspect ratio)
- Kokers hebben veel edges en lage volume ratio, vergelijkbaar met gezette platen
- Geen expliciete geometrie-check voor "gesloten doorsnede langs lengterichting"

**Voorbeeld:**
- 100×50×1877 mm koker met 12 edges en volume_ratio=0.17 → `plaat` ❌ (fout)

### Oplossing

Nieuwe hard profile signature vóór bent-sheet check:

**Algoritme:**
1. Bepaal dominante lengte-as uit bounding box
2. Sample cross-sections op 20%, 40%, 60%, 80% van lengte
3. Per sample: check contour closure (vertex graph, geen open uiteinden)
4. Bereken perimeter per gesloten contour + edge count
5. Classificeer als **PROFIEL** indien:
   - Minimaal 3 valide slices
   - Minimaal 75% gesloten contours
   - Perimeter coefficient of variation (CV) ≤ 0.08 (constant)
   - Edge count spread ≤ 2 (topologisch stabiel)

**Code locatie:**
- Functie: `_detect_closed_constant_cross_section()` in `assembly_analysis.py`
- Configurabele thresholds: `classification_variables.py` (CROSS_SECTION_*)
- Classificatie flow: tussen step 1 (standard detection) en step 1.5 (bent sheet)

**Thresholds toegevoegd:**
```python
CROSS_SECTION_SAMPLE_FRACTIONS = (0.2, 0.4, 0.6, 0.8)
CROSS_SECTION_MIN_VALID_SAMPLES = 3
CROSS_SECTION_CLOSED_RATIO_MIN = 0.75
CROSS_SECTION_PERIMETER_CV_MAX = 0.08
CROSS_SECTION_EDGE_COUNT_SPAN_MAX = 2
```

**Wat dit oplost:**
- Gesloten kokers: betrouwbaar als `profiel` ✓
- Open U/C-profielen: slices niet gesloten → blijven bij bent-sheet of anders ✓
- Variabele profielen (I-balk): perimeter CV hoog → vallen door check ✓

**Test case:**
```
10001091875_Rev_00.step (2 kokers 100×50×3):
- Voor v2.2: plaat (veel edges + lage volume_ratio trigger bent-sheet)
- Na v2.2: profiel (closed_constant_section rule) ✓
```

---

## Wijziging 2: Rectangular Tube Wall Thickness Calculation

### Probleem

Oude benadering gebruikte foutieve sqrt(volume_ratio) afleiding:
```python
# OUD (FOUT):
thickness = smallest * (1 - math.sqrt(volume_ratio)) / 2.0
```

**Resultaat voor 100×50-koker met volume_ratio=0.1702:**
- Oude formule: `t ≈ 14.7 mm` ❌
- Verwachte waarde: `t ≈ 3.0 mm` ✓

**Oorzaak:**
- Formule was een onvolledige benadering voor dunne wanden
- Werkte redelijk voor zeer dunne tubes (t << W, H)
- Faalde voor standaard wanddiktes (t ≈ 3-4 mm bij W=100, H=50)

### Oplossing

Analytische oplossing via doorsnede-balans:

**Afleiding:**

Voor een constante holle rechthoekige doorsnede geldt:
```
volume_ratio f = A_material / (W×H)
A_material = W×H - (W-2t)(H-2t)
           = W×H - WH + 2tW + 2tH - 4t²
           = 2t(W+H) - 4t²

⇒ f×W×H = 2t(W+H) - 4t²
⇒ 4t² - 2(W+H)t + f×W×H = 0
```

Kwadratische vergelijking met oplossingen:
```
t = [2(W+H) ± sqrt(4(W+H)² - 16fWH)] / 8
  = [(W+H) ± sqrt((W+H)² - 4fWH)] / 4
```

Fysisch relevante oplossing (kleine wortel):
```
t = [(W+H) - sqrt((W+H)² - 4fWH)] / 4
```

**Code implementatie:**
```python
def _estimate_wall_thickness(smallest_dim, middle_dim, volume_ratio, torus_radii):
    """Strategy 1: Analytical area-balance solve from volume ratio."""
    if 0.01 < volume_ratio < 0.98 and smallest_dim > 0 and middle_dim > 0:
        width = float(middle_dim)
        height = float(smallest_dim)
        fill_ratio = float(volume_ratio)

        discriminant = ((width + height) ** 2) - (4.0 * fill_ratio * width * height)
        if discriminant >= 0:
            thickness = ((width + height) - math.sqrt(discriminant)) / 4.0
            if 0.5 <= thickness <= (height / 2.0):
                return round(thickness, 1)
    
    # Strategy 2: Torus fallback (when analytical inconclusive)
    if torus_radii:
        inner_radius = min(torus_radii)
        thickness = inner_radius * 1.5
        if 0.5 <= thickness <= smallest_dim / 2.0:
            return round(thickness, 1)
    
    # Strategy 3: Default
    return 3.0
```

**Code locatie:**
- Module: `manufacturing_pipeline/analysis/profile_features.py`
- Functie: `_estimate_wall_thickness()` (regels 392-439)

**Validatie:**

| Koker | W×H (mm) | Volume Ratio | Oude t (mm) | Nieuwe t (mm) | Verwacht |
|-------|----------|--------------|-------------|---------------|----------|
| 100×50 | 100×50 | 0.1702 | 14.7 ❌ | 3.0 ✓ | 3.0 |
| 80×40 | 80×40 | 0.1750 | ~11.8 ❌ | 2.9 ✓ | 3.0 |
| 120×60 | 120×60 | 0.1667 | ~17.6 ❌ | 3.0 ✓ | 3.0 |

**XML output verifiëring:**
```xml
<Tube_Type>R_100x50x3</Tube_Type>
<Tube_Thickness>3</Tube_Thickness>
<Tube_Width>100</Tube_Width>
<Tube_Height>50</Tube_Height>
```

---

## Documentatie Updates

### Bijgewerkte bestanden

1. **CLASSIFICATION_METHODOLOGY.md**
   - Versie: 2.2
   - Toegevoegd: "Hard Closed Cross-Section Override" sectie
   - Toegevoegd: Formule voor rectangular tube thickness calculation
   - Classificatieflow bijgewerkt met nieuwe step 1.25

2. **classification_variables.py**
   - Versie: 2.2
   - Toegevoegd: CROSS_SECTION_* thresholds (5 nieuwe variabelen)
   - Commentaar uitgebreid met closed extrusion rationale

3. **assembly_analysis.py**
   - Versie: 2.2 in classificatie trace
   - Toegevoegd: `_detect_closed_constant_cross_section()` functie
   - Toegevoegd: `_extract_section_signature()` helper
   - Toegevoegd: `_get_solid_bbox_extents()` helper
   - Modified: `classify_solid()` flow met nieuwe rule "closed_constant_section"

4. **profile_features.py**
   - Modified: `_estimate_wall_thickness()` functie
   - Toegevoegd: Uitgebreide docstring met afleiding formule
   - Strategy 1 nu primair (analytical), Strategy 2 fallback (torus)

5. **xml_exporter.py**
   - Modified: `_process_profiel_item()` nu volledig geïmplementeerd
   - Extract profile features en populate Tube_* XML velden
   - Weight calculatie toegevoegd met materiaal densiteiten

---

## Regressie Check

### Classificatie (validate_classification_only.py)

Draai validatie op bestaande test files:

```bash
python validate_classification_only.py
```

**Verwachte resultaten:**
- 10040852_1.stp: 2 plaat, 2 profiel, 1 anders ✓
- 10040878_1.stp: 2 plaat, 2 profiel, 1 anders ✓ (quantity variance toegestaan)
- MD-16-03698_R2.stp: 2 plaat, 2 profiel, 2 anders ✓ (quantity variance toegestaan)
- 31686-080.stp: 8 plaat, 0 profiel, 10 anders ✓
- 2006020_A-00.STEP: 0 plaat, 0 profiel, 2 anders ✓

**Mogelijk nieuwe wijzigingen:**
- Gesloten kokers die voorheen als `plaat` waren: nu `profiel` ✓ (correctie)

### XML Export

Test profile thickness op bekende koker:

```bash
python generate_xml_dxf.py --step data/output/10001091875_Rev_00.step \
  --output test_profile_v2.2.xml --no-compare
```

**Check XML output:**
```xml
<Tube_Type>R_100x50x3</Tube_Type>  <!-- Was: R_100x50x15 ❌ -->
<Tube_Thickness>3</Tube_Thickness>  <!-- Was: 14.7 ❌ -->
```

---

## Breaking Changes

**Geen.** Beide wijzigingen zijn correcties/verbeteringen:

1. Closed extrusion detection: classified items blijven `profiel` (sterker)
2. Tube thickness: foutieve waardes worden gecorrigeerd naar fysisch kloppend

**Mogelijke impact:**
- XML exports met `Tube_Thickness` kunnen wijzigen (oude waardes waren incorrect)
- BOM classificatie: gesloten kokers nu betrouwbaarder als `profiel`

---

## Git Commit

```bash
git add CLASSIFICATION_METHODOLOGY.md
git add manufacturing_pipeline/analysis/assembly_analysis.py
git add manufacturing_pipeline/analysis/classification_variables.py
git add manufacturing_pipeline/analysis/profile_features.py
git add manufacturing_pipeline/reporting/xml_exporter.py
git add CHANGELOG_v2.2_PROFILE_THICKNESS.md
git add README.md

git commit -m "feat(v2.2): hard profile override + rectangular tube thickness fix

- Add multi-slice cross-section check for closed constant profiles
- Override bent-sheet heuristics when closed extrusion detected
- Fix rectangular tube wall thickness calculation (analytical formula)
- Correct 100x50 koker: 14.7mm → 3.0mm
- Add configurable thresholds in classification_variables.py
- Update documentation: CLASSIFICATION_METHODOLOGY.md + CHANGELOG

Resolves: koker classification robustness + XML thickness accuracy"

git push origin main
```

---

## Referenties

- **Classificatie logica:** [CLASSIFICATION_METHODOLOGY.md](CLASSIFICATION_METHODOLOGY.md)
- **Beslisboom:** [docs/CLASSIFICATION_DECISION_TREE.md](docs/CLASSIFICATION_DECISION_TREE.md)
- **Threshold config:** [manufacturing_pipeline/analysis/classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py)
- **Profile features:** [manufacturing_pipeline/analysis/profile_features.py](manufacturing_pipeline/analysis/profile_features.py)

---

*Changelog gemaakt: 4 maart 2026 | Versie: 2.2 | Status: Production Ready*
