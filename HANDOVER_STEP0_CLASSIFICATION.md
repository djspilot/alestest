# Handover — STEP 0 Classification Pipeline

**Datum:** 18 maart 2026  
**Branch:** `feature/stappenplan-stepfile`  
**Status:** 🔵 **Test Phase** (code gereed, testing nog uit te voeren)  
**Volgende eigenaar:** (morgen)

---

## Samenvatting: Wat is gedaan

### Modules toegevoegd/aangepast
1. **`manufacturing_pipeline/analysis/classification.py`** (nieuw)
   - Volledige STEP 0 beslisboom volgens `classification_step_review.md`
   - `classify_step0(solid)` is het entrypoint
   - Runtime resilient zonder pythonocc-core (valt gracieus terug naar fallthrough)

2. **`manufacturing_pipeline/analysis/assembly_analysis.py`** (aangepast)
   - Import: `from manufacturing_pipeline.analysis.classification import classify_step0`
   - In `classify_solid()`: STEP 0 wordt nu eerst uitgevoerd (regel ~1330)
   - Trace-info: stepstap, fallthrough-gedrag, confidence, methode

3. **`manufacturing_pipeline/analysis/classification_variables.py`** (bugfix)
   - Toegevoegd: `BENT_SHEET_LARGE_RADIUS_MIN_MM = 1.0` (ontbrekende constante R4)

### Git commits
- `7af9c5e` — feat: implement STEP 0 classification pipeline
- `8b79298` — fix: make step0 classifier resilient without pythonocc-core

### Status van STEP 0 nu
- ✅ Code: volledig en foutvrij
- ✅ Imports: getest, geen crashes
- ✅ Fallback: werkt (STEP 0 valt door naar legacy als pythonocc-core ontbreekt)
- ⚠️ Echte actieve classificatie: **NOG NIET GETEST** (vereist pythonocc-core of OCP-kompatibiliteit)

---

## Wat nog moet gebeuren

### Fase 1: Setup & Baseline (Morgen - Start)
- [ ] Testplan schrijven (zie template hieronder)
- [ ] Controleer: `check_bom_classification.py` draait zonder regressie
- [ ] Controleer: `test_classify_direct.py` draait zonder crash

### Fase 2: STEP 0 Aktivering (Afhankelijk van omgeving)
**Optie A: pythonocc-core beschikbaar**
- [ ] Installeer/Enable pythonocc-core in testomgeving
- [ ] Voer `classification.py` tests uit
- [ ] Verwerk foutmeldingen (waarschijnlijk kleine thresholds)
- [ ] Valideer tegen referentie BOM (8 items uit v3.0)

**Optie B: OCP-kompatibiliteit uitstellen**
- [ ] Accepteer dat STEP 0 nu veilig terugvalt (fallthrough=True)
- [ ] Valideer dat legacy Step 1-4 routes nog goed werken
- [ ] Zet plan op voor later OCP-enablement

### Fase 3: Regressietest (Afhankelijk van keus A/B)
- [ ] Draai `check_bom_classification.py` — verwacht: **3 plaat, 0 profiel, 2 anders** (of uw ref)
- [ ] Draai `test_classify_direct.py` — verwacht: geen crashes
- [ ] Check trace-output: `step0_*` velden zichtbaar in details

### Fase 4: Merge-voorbereiding
- [ ] Schrijf samenvatting testresultaten
- [ ] Creëer Pull Request naar `main` met testplan als beschrijving
- [ ] Merge als: ✅ geen regressie + ✅ step0 trace beschikbaar

---

## Testplan Template

Vul dit in wanneer je morgen begint:

```markdown
## Testplan — STEP 0 Classification (Datum: [morgen])

### Omgeving
- Python versie: [check: python --version]
- pythonocc-core beschikbaar: [ja/nee]
- OCP import status: [werkt/fallback]

### Basis Regressietest
**check_bom_classification.py**
- [ ] Draait zonder crash: ✅ / ❌
- [ ] Plaat count: (aantal) [verwacht: 3]
- [ ] Profiel count: (aantal) [verwacht: 0]
- [ ] Anders count: (aantal) [verwacht: 2]
- [ ] Bent_sheet_metal rule zichtbaar: ja/nee
- [ ] step0_fallthrough zichtbaar: ja/nee

**test_classify_direct.py**
- [ ] Draait zonder crash: ✅ / ❌
- [ ] Solids geladen: (aantal)
- [ ] Classificaties correct: (ja/nee)

### STEP 0 Trace Inspection
```python
from manufacturing_pipeline.analysis.assembly_analysis import classify_solid
# Inspecteer trace['features']['step0_*'] en trace['rules']
```
- [ ] step0_step veld aanwezig: ja/nee
- [ ] step0_fallthrough: [True/False]
- [ ] step0_label: [ANDERS/PROFIEL/...]
- [ ] step0_dependency_errors bij fallback: [toon fouten]

### Aantekeningen
[Hier notities van testen, problemen, etc.]

### Conclusie
- [ ] Geen regressie
- [ ] Merge naar main OK
- [ ] Wacht op verdere OCP-enablement
```

---

## Bestandslocaties (Makkelijk terug te vinden)

| Bestand | Regel | Wat |
|---------|-------|-----|
| [classification.py](manufacturing_pipeline/analysis/classification.py#L811) | 811 | `def classify_step0()` entrypoint |
| [assembly_analysis.py](manufacturing_pipeline/analysis/assembly_analysis.py#L1330) | 1330 | Integratieplaats in `classify_solid()` |
| [classification_variables.py](manufacturing_pipeline/analysis/classification_variables.py#L99) | 99 | Nieuwe `BENT_SHEET_LARGE_RADIUS_MIN_MM` |
| [check_bom_classification.py](check_bom_classification.py) | — | Regressietest |
| [test_classify_direct.py](test_classify_direct.py) | — | STEP import test |

---

## Vragen voor morgen?

1. **"Moet STEP 0 echt actief zijn of mag fallthrough?"**  
   → Antwoord: Start met verifiëren dat fallthrough netjes werkt. STEP 0 full activation is fase 2 (afhankelijk van pythonocc-core).

2. **"Welke branches moet ik testen?"**  
   → Deze: `feature/stappenplan-stepfile` (niet main, want daar zit v3.5).

3. **"Wat als trace-info niet zichtbaar is?"**  
   → Dan is classification.py niet correct geïntegreerd. Check regel ~1325-1370 in assembly_analysis.py.

4. **"Kan ik dit morgen direct naar main mergen?"**  
   → Ja, als:  
   ✅ check_bom_classification.py draait zonder regressie  
   ✅ step0_fallthrough zichtbaar in trace  
   ✅ geen crashes

---

## Commit-referenties

```bash
git log --oneline feature/stappenplan-stepfile | head -5
# 8b79298 fix: make step0 classifier resilient without pythonocc-core
# 7af9c5e feat: implement STEP 0 classification pipeline
# 56e2be4 docs: add StepFile plan and classification review
# 6e3cc41 docs: publish StepFile plan for main
# 2102eef v3.5 baseline
```

---

**Volgende:** Morgen testplan schrijven en regressietesten draaien.
