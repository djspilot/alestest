# Handover: Step 0 Assembly Testing & Classificatie Verbetering
**Datum:** 20 maart 2026  
**Status:** ✅ Gepusht naar GitHub  
**Branch:** `feature/step0-cadquery-slicing`  
**Laatste commit:** `4882152` — fix(step0): alternate-axis fallback for 0.4b

---

## 🎯 Wat is AFGEROND (vandaag)

### Alternate-axis fallback voor Step 0.4b (`GEZETTE_PLAAT`)
**Probleem:** Twee gespiegelde onderdelen (`10000362951_Rev_01` en `10000362952_Rev_01`) in assembly `10000541402_Rev_01` kregen inconsistente classificatie:
- `10000362951_Rev_01` → ✅ `GEZETTE_PLAAT (0.4b)` — primary axis was `planar-face-normal`
- `10000362952_Rev_01` → ❌ `ANDERS` — primary axis was `vertex-pca`, gaf `reentrant_corners=0`

**Root cause:** `reentrant_corners` wordt gemeten op de 2D doorsnede van de gekozen as. Gespiegelde onderdelen kiezen soms een andere primaire as (heuristisch), waardoor het profiel er convex uitziet in die richting.

**Oplossing:** Nieuwe helper `_select_step_0_4b_features()` in `classification.py`:
- Als primaire as `holes==0 AND reentrant_corners==0` geeft → probeer alle alternatieve assen
- Kies de beste alternatief met `holes==0` en hoogste `reentrant_corners`
- Bij gebruik van alternatieve as: resultaat bevat `used_alternate_axis=True` en `note` in trace

**Testresultaat:**
```
✅ 10000362951_Rev_01 → GEZETTE_PLAAT (0.4b)  [primary: planar-face-normal, reentrant=2]
✅ 10000362952_Rev_01 → GEZETTE_PLAAT (0.4b)  [alternate: planar-face-normal, reentrant=2]
Regressie: 9 OK, 0 FAIL, 0 SKIP
```

---

## ⚠️ Wat NOG GEDAAN MOET WORDEN

### 1. Meer samenstellingen testen
Tot nu toe zijn slechts **2 assembly-samenstellingen** gevalideerd:
- `10000541402_Rev_01.step` (21 solids, 12 BOM lines)
- `10000869069_Rev_00.step` (los onderdeel, grotere file)

Het classificatiesysteem heeft nog steeds **kleine verbeteringen nodig** voor edge cases die pas zichtbaar worden bij meer assemblies. Prioriteit:
- Samenstellingen met gemixte onderdelen (platen + profielen + normaalonderdelen)
- Samenstellingen met dunne wandige profielen
- Samenstellingen waar meerdere onderdelen identieke volumes hebben

### 2. Bekende beperkingen die verder onderzoek vragen

| Beperking | Stap | Impact |
|-----------|------|--------|
| Gespiegelde onderdelen kiezen wisselende assen | 0.4b | Fix aanwezig (alternate-axis), maar nog weinig getest |
| `vertex-pca` as als fallback is fragiel | 0.3/0.4b | Kan nog edge cases missen |
| Assembly solid-volgorde vs naam-volgorde mismatch | Alle | Zie `solid_to_name_matching_analysis.md` in user memory |
| Profielen met `closed_constant_section` maar geen vast volume | 0.3 | Sporadisch gezien |

---

## 🛠️ Testmethode (voor volgende chat)

### Stap 1: Environment activeren
```powershell
cd C:\Data\DS\Python\Spaceclaim_verv
.\.venv\Scripts\Activate.ps1
cd alestest
```

### Stap 2: Branch verifiëren
```powershell
git branch -vv
# Zould tonen: * feature/step0-cadquery-slicing [origin/feature/step0-cadquery-slicing]
git log --oneline -5
```

### Stap 3: Regressietest (altijd eerst uitvoeren)
```powershell
python test_regression_step0.py
# Verwacht: 9 OK, 0 FAIL, 0 SKIP
```

### Stap 4: Nieuwe assembly testen
```powershell
# Methode A: BOM output voor één assembly
python run.py --bom "data/stepfile/<assembly>.step" 2>&1 | Select-String "FINAAL|Error|Stap"

# Methode B: Gedetailleerde trace voor één onderdeel in assembly
python -c "
from manufacturing_pipeline.analysis.classification import classify_step0_detailed_trace
import cadquery as cq
# laad solid, run trace, bekijk output
"

# Methode C: Check BOM classificatie (vergelijkt met verwacht)
python check_bom_classification.py
```

### Stap 5: Nieuw onderdeel toevoegen aan regressietest
Bewerk `test_regression_step0.py` — voeg een `TestCase` toe:
```python
TestCase(
    file="data/stepfile/<naam>.step",
    expected_step="0.4b",           # of 0.1, 0.2, 0.3, 0.5, etc.
    expected_label="GEZETTE_PLAAT", # of RONDE_BUIS, PROFIEL, ANDERS, etc.
    comment="beschrijving van het onderdeel",
),
```

---

## 📁 Sleutelbestanden

| Bestand | Doel |
|---------|------|
| `manufacturing_pipeline/analysis/classification.py` | Hoofd Step 0 beslisboom; `_select_step_0_4b_features()` is de nieuwe helper |
| `manufacturing_pipeline/analysis/step0_section_tools.py` | OCP-native doorsnede-extractie, as-selectie |
| `manufacturing_pipeline/analysis/assembly_analysis.py` | Assembly pipeline; `classify_solid()` roept `classify_step0()` aan |
| `classification_step_review.md` | Levend ontwerpdocument, nu v3.10 |
| `test_regression_step0.py` | Regressietests voor losse onderdelen |
| `data/stepfile/` | Testbestanden: 2 assemblies + ~10 losse onderdelen |

---

## 🔍 Stap 0 beslisboom (samenvatting v3.10)

```
Step 0.1  → Ronde as / bewerkte as (cylinder + axiale check)
Step 0.2  → Ronde buis / rechthoekige koker (hollow + constant cross-section)
Step 0.3  → Gesloten constant profiel (hollow section signature)
Step 0.4a → Plaat (face-analyse, dikte < threshold)
Step 0.4b → Gezette plaat (open constant doorsnede + reentrant corners > 0)
              ⬆ NEW: alternate-axis fallback voor gespiegelde onderdelen
Step 0.5  → Profiel (doorsnede met gaten of bijzondere vorm)
Step 0.6  → Fallthrough naar legacy classify_solid() (Steps 1-4)
```

---

## 💡 Tips voor volgende sessie

1. **Als een onderdeel verkeerd geclassificeerd wordt**: gebruik `classify_step0_detailed_trace()` — het toont welke stap gekozen werd en waarom, inclusief `note: "alternatieve doorsnede-as gebruikt"` bij 0.4b fallback.

2. **Als `vertex-pca` problemen geeft**: check of `planar_face_normal_candidates` genoeg kandidaten geeft (minstens 2). Zo niet → het onderdeel heeft mogelijk te weinig vlakke vlakken voor goede as-detectie.

3. **Solid-naam mismatch in assemblies**: als classificaties correct zijn maar namen fout toegewezen, zie `SOLID_TO_NAME_MAPPING_ANALYSIS.md` in de workspace root voor de bekende oplossingsrichtingen.

4. **Thresholds aanpassen**: in `manufacturing_pipeline/analysis/classification_variables.py` — altijd regressietest daarna draaien.
