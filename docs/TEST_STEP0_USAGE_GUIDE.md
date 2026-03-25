# STEP 0 Classification Detailed Report — Gebruikshandleiding

## Wat doet het script?

Het script `test_step0_detailed_report.py` analyseert STEP-geometrie en geeft per stap (0.1-0.5) een **gedetailleerd diagnostisch report** met:
- ✓ / ✗ Status van elk criterium
- Actuele waarde vs vereiste waarde
- Reden waarom wel/niet verder gegaan wordt

## Gebruik

### Basic: Een STEP-file analyseren
```bash
cd c:\Data\DS\Python\Spaceclaim_verv\alestest
python test_step0_detailed_report.py "data\stepfile\Zetwerk\10000362951_Rev_01.step"
```

### Output lezen

Voorbeeld output voor deel 10000362951_Rev_01:

```
Bounding Box Dimensions: 53.0 × 81.0 × 123.0 mm
Volume: 47555.2 mm³
BBox Volume: 528042.1 mm³
Volume Ratio: 0.0901

STAP 0.1: Slice-validatie (Stabiele extrusie-as)
  ✗ import_available: False
  ➜ No match, continue to next step
     (profile_classifier import error: No module named 'scipy._lib')

STAP 0.4a: Vlakke plaat (High confidence)
  ✗ top2_face_percent > 50%: 31.0% (required: 50.0%)
  ➜ No match, continue to next step

STAP 0.5: Massief profiel fallback
  ✓ smallest >= PROFILE_SMALLEST_MIN_MM: 53.0mm (required: 5.0)
  ✗ length_ratio >= PROFILE_LENGTH_RATIO_MIN: 1.52 (required: 3.0)
  ✓ PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX: 1.53 ([0.5, 3.5])
  ➜ MATCHED: ANDERS
     Reason: geen classificatie in STEP 0 → fallback
     → STAP 0.5 EXIT

ACTUAL RESULT from classify_step0():
  Label:      ANDERS
  Step:       0.5
  Method:     fallback
  Confidence: 0.55
```

## Stappen uitgelegd

### Stap 0.1: Slice-validatie (Poort)
- **Doel**: Controleer dat het solid een **stabiele extrusie-as** heeft
- **Criteria**:
  - Stabiele extrusie-as gevonden
  - Min 3 geldige doorsneden
  - Dominant section cluster >= 60%
- **Uitgang**: 
  - ✓ Passed → doorloopt
  - ✗ Failed → ANDERS (fallthrough=False)

**Status**: ⚠️ Vereist `profile_classifier` module (scipy dependency)

### Stap 0.2: Gesloten-hol → BUIS/KOKER
- **Doel**: Detecteer ronde buizen en rechthoekige kokers
- **Criteria**:
  - Extrusie-as gevonden
  - Doorsneden hebben exact 1 hole (gsloten contour)
  - Outer + inner beide cirkelrond → RONDE_BUIS
  - Outer + inner beide rechthoekig → RECHTHOEKIGE_KOKER
- **Uitgang**: Direct stop bij match

**Status**: ⚠️ Vereist `profile_classifier` module

### Stap 0.3: Open profiel (L/U/I/T)
- **Doel**: Detecteer L-profielen, U-profielen, I-balken, T-profielen
- **Criteria**: (Nog niet in evaluator geïmplementeerd)

**Status**: ⚠️ Vereist `profile_classifier` module

### Stap 0.4a: Vlakke plaat (Hoge betrouwbaarheid)
- **Doel**: Detecteer dunne, vlakke platen via **face analysis**
- **Criteria**:
  - Top2 face percentage > 50% (twee grootste vlakken domineren)
  - Dikte < 25mm
  - Aspect ratio > 1.5
  - Volume ratio 0.15-0.95

**Voorbeeld**:
```
✓ top2_face_percent > 50%: 75.0% (required: 50.0%)
✓ thickness: 3.0mm (required: <25.0)
✓ aspect_ratio > 1.5: 15.2 (required: 1.5)
→ MATCHED: PLAAT
```

### Stap 0.4b: Constant-dikte open sectie
- **Doel**: Detecteer gebogen platen (gezette plaaten) en open profielen
- **Criteria**:
  - Constant wanddikte (geen I-beam achtige variatie)
  - Dunne materiaal (< 25mm)
  - Gebogen geometrie detectie
- **Uitgang**: 
  - Gebogen → GEZETTE_PLAAT
  - Open profiel → PROFIEL
  - Anders → doorval naar 0.5

### Stap 0.5: Massief profiel fallback
- **Doel**: Laatste poging - massieve rechthoekige profielen via dimensies
- **Criteria**:
  - `smallest >= PROFILE_SMALLEST_MIN_MM` (5mm)
  - `length_ratio >= PROFILE_LENGTH_RATIO_MIN` (3.0)
  - `PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX` (0.5 - 3.5)
- **Uitgang**:
  - ✓ Strong volume ratio (> 0.5) → PROFIEL
  - ✓ Weak volume ratio + SA/V check → PROFIEL
  - ✗ Niets OK → ANDERS

## Testscenario's

### 1. Een vlakke plaat testen
```bash
# Zoek een plaat in data/
find data -name "*.step" # en test met een dunne plaat
python test_step0_detailed_report.py "data/path/to/plate.step"
```

Verwachte output:
```
STAP 0.4a: Vlakke plaat (High confidence)
  ✓ top2_face_percent > 50%: 85.0%
  ✓ thickness_check: 2.5mm < 25.0mm
  ✓ aspect_ratio > 1.5: 12.0
  → MATCHED: PLAAT
```

### 2. Een profiel (koker/buis) testen
```bash
python test_step0_detailed_report.py "data/path/to/tube.step"
```

Verwachte output (als profile_classifier werkzaam is):
```
STAP 0.2: Gesloten-hol (BUIS/KOKER)
  ✓ holes == 1: 1
  ✓ outer_nearly_circle: True
  ✓ inner_nearly_circle: True
  → MATCHED: RONDE_BUIS
```

## Dependency Issues

### scipy._lib missing
Enkele stappen (0.1, 0.2, 0.3) vereisen `profile_classifier` module, die scipy nodig heeft.

**Workaround**: Install scipy (als nog niet gedaan)
```bash
pip install scipy
```

Als scipy niet beschikbaar is:
- 0.1-0.3 overslaan
- 0.4a-0.5 werken (basic geometry analysis)

## Uitbreidingen

Voor volledige STEP 0 testing:
1. **Install scipy**: `pip install scipy` (voor 0.1-0.3)
2. **Test profielen**: Test `10040852_1.step` (moet RONDE_BUIS zijn)
3. **Test platen**: Test Zetwerk parts (moet PLAAT zijn)
4. **Threshold tuning**: Pas thresholds in `classification_variables.py` aan

## Bestandslocaties

| Bestand | Beschrijving |
|---------|-------------|
| `test_step0_detailed_report.py` | Dit test script |
| `manufacturing_pipeline/analysis/classification.py` | STEP 0 classifier (entrypoint: `classify_step0()`) |
| `manufacturing_pipeline/analysis/classification_variables.py` | Alle thresholds (PROFILE_LENGTH_RATIO_MIN, etc.) |
| `data/stepfile/Zetwerk/` | Test platen |
| `../stepfiles/` | Meer test STEP-files |

---

**Tip**: Start met deze zetwerk plaat, daarna test je andere parts om de stappen step-by-step te zien.
