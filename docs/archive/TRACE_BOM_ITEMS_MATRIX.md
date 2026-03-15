# FASE 2: BOM Items Through Classification Matrix

**Datum**: 5 maart 2026  
**Assembly**: 10000986417_Rev_00.stp (8 BOM items)

---

## Sample Item Trace: 10000503252_Rev_00 (Item [3])

**Probleem**: Dit item wordt `anders` geclassificeerd, maar zou `profiel` moeten zijn.

### Stap-voor-stap Matrix Trace:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ITEM [3]: 10000503252_Rev_00 (Vierkante koker 88.9×88.9×1162mm)            │
│ Qty: 2 | Current Class: anders | Expected: profiel                          │
└─────────────────────────────────────────────────────────────────────────────┘

STAP 1A: HOLLOW TUBE CHECK
─────────────────────────────
  ✓ Aspect (mid/max) >= 0.5: ?
  ✓ Volume ratio <= 0.7: ?
  ✓ Cylindrical % >= 60%: ?
  ➜ RESULT: ❌ FAALT

STAP 1B: VARIABLE THICKNESS CHECK
──────────────────────────────────
  ✓ Length ratio >= 5: 88.9 / 88.9 = 1.0 >= 5? ❌ FAALT
  (Vierkante koker has equal mid/smallest, niet langwerpig in die dimensies)
  ➜ RESULT: ❌ FAALT

STAP 1C: CLOSED CONSTANT SECTION CHECK
─────────────────────────────────────────
  Gate check:
    ✓ smallest >= 5: 88.9 >= 5? ✅
    ✓ longest/middle >= 5: 1162 / 88.9 = 13.1 >= 5? ✅
    ✓ 0.5 <= middle/smallest <= 2.0: 88.9 / 88.9 = 1.0? ✅
  
  Gate PASSED → run closed section test:
    ✓ closed_ratio >= 0.75: ?
    ✓ perimeter_cv <= 0.08: ?
    ✓ edge_span <= 2: ?
  
  ➜ RESULT: ❌ FAALT (closed section test niet geslaagd)

STAP 1.5: BENT SHEET CHECK
──────────────────────────
  ✓ thickness <= 100: 88.9 <= 100? ✅
  ✓ edge_count >= 8: ? (vierkante koker: ~12 edges) ✅ waarschijnlijk
  ✓ volume_ratio 0.10-0.50: ? (hoek profiel)
  ✓ top2% <= 60: ?
  ✓ aspect >= 2.0: 1162 / 88.9 = 13.1 >= 2.0? ✅
  ✓ exclusions: ?
  
  ➜ RESULT: ❌ FAALT (volume_ratio waarschijnlijk > 0.50)

STAP 2A: PLATE (FACE ANALYSIS)
───────────────────────────────
  top2_planar_percent > 50: ?
  ➜ RESULT: ❌ FAALT

STAP 2B: THIN PLATE
───────────────────
  smallest < 25: 88.9 < 25? ❌ FAALT
  ➜ RESULT: ❌ FAALT

STAP 3: PROFILE (SOLID BEAM)
────────────────────────────
  Gate check:
    ✓ smallest >= 5: 88.9 >= 5? ✅
    ✓ length_ratio >= 5: 1162 / 88.9 = 13.1 >= 5? ✅
    ✓ 0.5 <= cross_ratio <= 2.0: 1.0? ✅
  
  Gate PASSED → check volume:
    volume_ratio > 0.5: ? (waarschijnlijk > 0.5 voor massief staal)
    ➜ Should return profiel here! ✅
  
  ➜ RESULT: ❌ FAALT (doorgeruld naar STAP 4)

STAP 4: DEFAULT
───────────────
  Alles gefaald
  ✅ CLASSIFICATIE: anders
```

---

## Volledige BOM Output (Alle 8 Items)

| # | Part Name | Qty | Huidge Class | Expected | Rule Applied | Issue |
|---|-----------|-----|--------------|----------|--------------|-------|
| [0] | 10000255318_Rev_00 | 4 | **plaat** ✅ | plaat | bent_sheet_metal | STAP 1.5: Bent sheet met < 360° |
| [1] | 10000520810_Rev_00 | 2 | **plaat** ✅ | plaat | plate_face | STAP 2A: Face analysis |
| [2] | 10000418502_Rev_00 | 8 | **plaat** ✅ | plaat | plate_face | STAP 2A: Face analysis |
| [3] | 10000503252_Rev_00 | 2 | **anders** ❌ | **profiel** | default_anders | **PROBLEM: STAP 4** |
| [4] | 10000503253_Rev_00 | 2 | **profiel** ✅ | profiel | closed_constant_section | STAP 1C: Closed section |
| [5] | 10000520371_Rev_00 | 1 | **anders** ❌ | ?plaat? | standard_hollow_tube | STAP 1A: Foutief als hol! |
| [6] | 10000596440_Rev_00 | 2 | **anders** ❌ | ?plaat? | standard_hollow_tube | STAP 1A: Foutief als hol! |
| [7] | 10000940837_Rev_00 | 4 | **plaat** ✅ | plaat | plate_face | STAP 2A: Face analysis |

---

## Diagnose: Waarom Item [3] Faalt

**10000503252_Rev_00** is een **vierkante koker 88.9×88.9×1162mm** (waarschijnlijk EN 10210 standaard).

**Waarschijnlijke reden voor falen STAP 1C:**
- Gate passed (longest/middle = 13.1 ✅)
- Maar `_detect_closed_constant_cross_section()` faalt waarschijnlijk omdat:
  - Slicing test faalt (holle profielen zijn moeilijk te detecteren via slicing)
  - Perimeter variatie > 0.08 (holle boxen hebben andere signatures)
  - Of `section_samples < 3`

**Waarschijnlijke oorzaak STAP 3:**
- Gaat DOOR gate van STAP 3 ✅
- Maar...
- OF: `volume_ratio` is eigenlijk **TOO HIGH** (massief staal, niet hol)
- OF: Volume check faalt om andere redenen

---

## Actie Vereist

**Voor Item [3]:**
1. Meet exact: volume_ratio, volume, bbox volume
2. Check waarom STAP 1C faalt (section slicing niet?
3. Check waarom STAP 3 volume check faalt

**Voor Items [5] [6]:**
1. Dit zijn waarschijnlijk **gezette platen** (not holle buizen!)
2. STAP 1A detecteert ze FOUTIEF als `standard_hollow_tube`
3. Oorzaak: cylindrical_pct >= 60% triggert, maar ze zijn gebogen niet echt hol
4. Fix: STAP 1A moet beterberedeneerd worden (cylindrical% is niet genoeg)

---

## Volgende Stap (FASE 2.5)

Een debug script schrijven dat PER ITEM precies toont:
- Gemeten waarden voor elke stap
- Waarom elke check faalt
- Aanbevelingen voor threshold-aanpassingen

Dit zal ons helpen bepalen welke thresholds beter moeten.
