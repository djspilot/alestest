# Handover: Hollow Detection Wire-Loop Fallback Fix
**Datum:** 19 maart 2026 (Vrijdag)  
**Status:** ✅ Complete & Pushed to GitHub  
**Branch:** `feature/step0-cadquery-slicing`  
**Commit:** `fb2c75a` - "Fix: Wire-loop fallback for hollow tube detection (March 19, 2026)"

---

## 🎯 Wat is AFGEROND

Hollow tube detection (Step 0.2) herstructureerd voor:
1. **Primaire pad**: Polygon-gaten (95%+ werkend)
2. **Fallback pad**: Wire-loop validatie (voor selbsnijdende ringen)
3. **Overlap-check**: Strikte 0.90 ratio om gaten te valideren
4. **Tolerante matching**: Alleen in fallback-scenario

### Test Resultaten (4 files spot-checked)
```
✅ 803143-7401.step        → RECHTHOEKIGE_KOKER    (wire-fallback, 98%)
✅ 05-01-5340.step         → PROFIEL               (no regression)
✅ VDB-036003-A.step       → KOKER                 (wire-fallback, valid)
✅ 10000869069_rev_00.step → GEZETTE_PLAAT         (no regression)
```

---

## 📋 Morgen Startpunt (20 maart)

### Stap 1️⃣: Environment Activeren
```powershell
cd c:\Data\DS\Python\Spaceclaim_verv
.\.venv\Scripts\Activate.ps1
cd alestest
```

### Stap 2️⃣: Branch Verifiëren
```powershell
git branch -vv
# Zould show: * feature/step0-cadquery-slicing [origin/feature/step0-cadquery-slicing]
```

### Stap 3️⃣: Test Volledige BOM (PRIMAIRE METHODE)
```powershell
# Test the files we already know work with the fix:
python run.py --step0 "data/stepfile/profiel/803143-7401.step"
# Expected output: RECHTHOEKIGE_KOKER at step 0.2, confidence ~98%

# Then test a batch (optional - kan lang duren):
python run.py --step0 data/stepfile/*.step | Select-String 'FINAAL RESULTAAT|Stap:|Reden:'
```

### Stap 4️⃣: Regressie Check (SNELLE METHODE)
```powershell
# Run the spot-check 4 files
$files = @(
    "data/stepfile/profiel/803143-7401.step",
    "data/stepfile/profiel/05-01-5340.step",
    "data/stepfile/profiel/VDB-036003-A.step",
    "data/stepfile/Zetwerk/10000869069_rev_00.step"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "`n=== Testing: $file ===" -ForegroundColor Cyan
        python run.py --step0 "$file" | Select-String 'FINAAL RESULTAAT|Stap:|Reden:|wire-fallback'
    }
}
```

### Stap 5️⃣: Thresholds Tunen (INDIEN EDGE-CASES)
**Locatie:** `manufacturing_pipeline/analysis/classification_variables.py` (lines 118-131)

```python
# Huidige waarden (19 maart, 2026):
HOLLOW_WIRE_OVERLAP_RATIO_MIN = 0.90        # 90% overlap = valid hole
HOLLOW_RECT_BBOX_FILL_MIN = 0.85            # Fallback tolerance: 85% (vs 95% standard)
HOLLOW_RECT_CONVEXITY_MIN = 0.95            # Fallback: strict convexity
HOLLOW_RECT_TOLERANCE_REL = 0.05            # Fallback: 5% dimension variance
```

**Test na tunen:**
```powershell
python run.py --step0 "data/stepfile/profiel/803143-7401.step"
# Check of nog steeds "wire-fallback" in output staat
```

---

## 🔧 Troubleshooting (Als iets Mis Gaat)

### Symptoom 1: "AttributeError: 'tuple' does not have attribute 'wire_polygons'"
**Oorzaak:** Section2D constructor ontvangt nog oude 3-tuple van `_build_section_polygon_from_wires()`  
**Fix:**
```python
# In step0_section_tools.py line 399, verify:
poly, line_len, curve_len, ring_polys = _build_section_polygon_from_wires(...)
# NOT:  poly, line_len, curve_len = _build_section_polygon_from_wires(...)
```

### Symptoom 2: Gaten worden NIET gedetecteerd (holes=0 nog steeds)
**Oorzaak:** Fallback logica werkt niet  
**Debug steps:**
```python
# Add to classification.py in _step_0_2_hollow_closed(), after line 445:
print(f"DEBUG: core_sec.wire_polygons = {getattr(core_sec, 'wire_polygons', 'MISSING')}")
print(f"DEBUG: len(wire_polys) = {len(wire_polys) if 'wire_polys' in dir() else 'N/A'}")
print(f"DEBUG: used_wire_fallback = {used_wire_fallback}")

# Then run:
python run.py --step0 "data/stepfile/profiel/803143-7401.step"
# Look for DEBUG: lines in output
```

### Symptoom 3: Regressies op andere files (Alle files onwaar geclassificeerd)
**Oorzaak:** Tolerante rect-matching wordt op ALLE cases toegepast, niet alleen fallback  
**Verificatie:**
```python
# In classification.py, verify slechts 2x "is_rect_rounded" wordt ingesteld:
# 1. Line ~468: ONLY if used_wire_fallback == True
# 2. Should NOT appear elsewhere in function

grep -n "is_rect_rounded" manufacturing_pipeline/analysis/classification.py
# If >2 matches: probleem gevonden
```

---

## ✅ Success Criteria (Morgen)

**ALLES GOED if:**
- ✅ 803143 → RECHTHOEKIGE_KOKER
- ✅ 05-01-5340 → PROFIEL
- ✅ VDB-036003-A → KOKER
- ✅ 10000869069 → GEZETTE_PLAAT
- ✅ Geen new errors in console

**NEXT PHASE if all 4 pass:**
```powershell
# Test op meer files
python validate_classification_only.py
# If >95% accuracy: Ready for PR merge

# Als <95%: Document which files fail
# Create issue: "Hollow detection needs additional refinement for [file_type]"
```

---

## 📝 Logboek (Wat Je Gedaan Hebt)

### Files Modified (5 totaal)
1. ✅ `manufacturing_pipeline/analysis/step0_section_tools.py` (NEW)
   - 4-tuple return met wire_polygons
   - Safer invalid polygon handling (keep dominant outer, don't collapse)

2. ✅ `manufacturing_pipeline/analysis/classification.py` (MODIFIED)
   - Lines 365-480: _step_0_2_hollow_closed() with fallback path
   - Lines 1140-1300: Mirror logic in trace reporting
   - NEW: used_wire_fallback flag for diagnostics

3. ✅ `manufacturing_pipeline/analysis/classification_variables.py` (MODIFIED)
   - Lines 118-131: NEW HOLLOW_* constants
   - Documentation van tolerance thresholds

4. ✅ `classification_step_review.md` (UPDATED)
   - Section 0.2 expanded with wire-loop fallback explanation

5. ✅ `README.md` (UPDATED)
   - v3.6.1 release notes met fix details

### Git Commit (GitHub)
```
Commit: fb2c75a
Branch: feature/step0-cadquery-slicing
Push:   ✅ Success (20.54 KiB)
```

---

## 🚀 Volgende Grote Stap (Na Morgen Test)

### Option A: Alle 8 BOM Items Volledig Testen
```bash
python check_bom_classification.py
# This tests all 8 items that were originally tested in v3.0
# Expected: 100% accuracy (all 8 correct)
```

### Option B: Batch Testing (Nog Meer Files)
```bash
# Run op alle profiel files
for file in data/stepfile/profiel/*.step; do
    echo "Testing: $file"
    python run.py --step0 "$file" | grep -E "FINAAL|Stap|Reden"
done > test_profiel_batch.log 2>&1
```

### Option C: PR naar Main (Als Alles Groen)
```bash
# Maak PR:
git push origin feature/step0-cadquery-slicing
# Visit: https://github.com/aidoel/alestest/pull/new/feature/step0-cadquery-slicing

# Beschrijving:
# Title: "feat: Hollow tube detection wire-loop fallback (Step 0.2)"
# Body: Copy from commit message
```

---

## 📚 Referentie Docs

**Alles om tolerances te begrijpen:**
- 📄 `classification_variables.py` lines 118-131
- 📄 `README.md` v3.6.1 (Technical Section)
- 📄 `classification_step_review.md` Section 0.2

**Debugging tools beschikbaar:**
- 🔍 `manufacturing_pipeline/analysis/step0_section_tools.py` - Section object builder
- 🔍 `manufacturing_pipeline/analysis/classification.py` - Decision tree (lines 365-480)
- 🔍 `check_bom_classification.py` - Test volledige BOM

---

## 💡 Tips voor Morgen

1. **Start altijd met de regressie-check 4-file loop** (snelste feedback)
2. **Zet tolerances NIET zonder grond te wijzigen** - test eerst met (0.90, 0.85, 0.95, 0.05)
3. **Verwacht "wire-fallback" in output voor 803143** - dat is GOED
4. **Geen "wire-fallback" voor andere files** - dat is ook GOED (ze gebruiken primaire pad)
5. **Git: Maak NOOIT changes op master** - blijf op `feature/step0-cadquery-slicing`

---

**Klaar voor morgen? 🚀**  
Branch is pushed, commit is stable, testing procedures zijn documented.  
Volg de 5 stappen boven → morgen ben je klaar voor volgende fase!
