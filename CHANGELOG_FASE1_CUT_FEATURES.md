# Changelog: Fase 1 - Cut Features Detection

**Datum:** 3 maart 2026  
**Versie:** 2.1.2  
**Scope:** Gaten + Snijdata voor Plaat en Gezette Plaat

---

## ✅ Geïmplementeerd

### Nieuwe Features

**1. Gatdetectie (Cylindrisch + Vormgaten)**
- **Cylindrische gaten:** Hergebruikt `detect_holes()` uit step_processing.py
- **Vormgaten (slots/rectangles):** Hergebruikt `detect_shaped_holes()` uit step_processing.py
- **Deduplicatie:** Voorkomt dubbele detectie van gaten
- **Output:** Aantal gaten, contourlengte per gat, radii per gat

**2. Snijlengte Berekening**
- **Gatcontours:** Perimeter van elke hole inner wire
  - Cylindrisch: 2πr
  - Vormgaten: uit wire of geschat uit dimensions
- **Buitencontour:** Outer wire perimeter van grootste planaire face
- **Totale snijlengte:** sum(gatcontours) + buitencontour

**3. Box Dimensions Extraction**
- X- en Y-dimensies van bounding box
- Gebruikt voor platte delen en na unfold

**4. Flat vs 3D Analyse Strategie**
- **Gezette plaat + successful unfold:** Analyseer flat pattern (nauwkeuriger)
- **Plaat of unfold failed:** Analyseer 3D solid
- **Source tracking:** XML bevat `source='flat'` of `source='3d'` voor traceability

### XML Export Integratie

**Nieuwe/Gepopuleerde XML Fields voor Sheet Metal:**
```xml
<Sheet_NrHoles>2</Sheet_NrHoles>                    <!-- Totaal gaten -->
<Sheet_HoleContours>31.73,123.2</Sheet_HoleContours> <!-- Comma-separated perimeters (mm) -->
<Sheet_HoleRadii>5.05,15.4</Sheet_HoleRadii>       <!-- Comma-separated radii (mm) -->
<Sheet_OuterContour>606.98</Sheet_OuterContour>     <!-- Outer perimeter (mm) -->
<Sheet_TotalContour>761.91</Sheet_TotalContour>     <!-- Total cut length (mm) -->
```

**Bestaande Fields (unchanged):**
- `Sheet_BoxX`, `Sheet_BoxY` - blijven gevuld via unfold of geometry analyse
- `Sheet_NrBends`, `Sheet_BendAngles` - blijven werken zoals voorheen

### Code Architectuur

**Nieuwe Module:** `manufacturing_pipeline/analysis/cut_features.py`

**Functie:**
```python
extract_cut_features_for_sheet(
    solid: TopoDS_Shape,
    unfold_result: Optional[Dict] = None,
    part_classification: str = "plaat"
) -> Optional[CutFeatures]
```

**Flow:**
1. Bepaal analyse domain (flat pattern of 3D)
2. Detect cylindrische gaten
3. Detect vormgaten
4. Dedupliceer overlaps
5. Bereken hole contours
6. Bereken outer contour
7. Bereken bounding box
8. Return `CutFeatures` dataclass

**Dataclass:**
```python
@dataclass
class CutFeatures:
    nr_holes: int
    hole_contours: List[float]
    hole_radii: List[float]
    outer_contour: float
    total_contour: float
    box_x: float
    box_y: float
    source: str  # "flat" or "3d"
    nr_cylindrical: int
    nr_shaped: int
    shaped_types: List[str]
```

**XML Exporter Integration:**
- Conditionally activated alleen voor `plaat` en `gezette_plaat` classificaties
- Graceful fallback: bij failure gebruikt approximations (2*(L+W))
- Import guard: `HAS_CUT_FEATURES` flag voor backwards compatibility

---

## 🔒 Veiligheid: Geen Breaking Changes

### Bestaande Code NIET Gewijzigd

✅ **step_processing.py:**
- `detect_holes()` - unchanged
- `detect_shaped_holes()` - unchanged
- Alle signaturen identiek

✅ **Classificatielogica:**
- Plaat/Profiel/Anders decision tree - unchanged
- Thresholds - unchanged
- Bend detection - unchanged

✅ **Unfold integratie:**
- FreeCAD unfold flow - unchanged
- Flat pattern generation - unchanged

✅ **Backwards compatibility:**
- Als `cut_features.py` niet beschikbaar → fallback naar oude placeholders
- Als extractie faalt → fallback naar 2*(L+W) approximatie voor outer contour
- Existing tests blijven werken

---

## 🧪 Validatie

### Test File: 10040878_1.stp

**Assembly BOM:**
- MD-20-11832_1 (plaat) - **CUT FEATURES EXTRACTED ✓**
- MD-20-11302_2 (profiel) - skipped (Fase 2)
- 10040853_1 (anders) - skipped
- 10040876_1 (profiel) - skipped (Fase 2)
- 10040854_1 (plaat) - **CUT FEATURES EXTRACTED ✓**

**MD-20-11832_1 Results:**
```
Holes: 2 (cyl: 1, shaped: 1)
Outer contour: 606.98 mm
Total cut length: 761.91 mm
Hole contours: 31.73mm, 123.2mm
Hole radii: 5.05mm, 15.4mm
Source: 3d
```

**MD-20-11854_1 Results:**
```
Holes: 3 (shaped only)
Outer contour: 191.83 mm
Total cut length: 280.63 mm
Source: 3d
```

**Command:**
```bash
python test_bom_to_xml.py ../stepfiles/10040878_1.stp
```

**Output XML:**
- `..\stepfiles\10040878_1_bom_features.xml`

---

## 📋 Volgende Stappen

### Fase 2 (Future): Profiel Gaten + Snijdata

**Scope:**
- Extend cut_features voor `profiel` classificatie
- Tube_NrHoles, Tube_HoleContours, Tube_OuterContour
- Cross-section perimeter als "outer contour"
- Geen unfold (altijd 3D analyse)

**Functie:**
```python
extract_cut_features_for_profile(
    solid: TopoDS_Shape,
    part_classification: str = "profiel"
) -> Optional[CutFeatures]
```

**Implementation Note:**
- Placeholder functie bestaat al in cut_features.py
- Retourneert momenteel None met info log

---

## 🎯 Gebruik

### Via XML Exporter (test_bom_to_xml.py):

```bash
python test_bom_to_xml.py path/to/assembly.stp
```

Automatisch actief voor plaat/gezette_plaat items in BOM.

### Via CLI (run.py):

```bash
python run.py -f mypart.stp --excel
```

Genereert Excel met classificatie, maar geen XML in standaard flow.  
Voor XML: gebruik `test_bom_to_xml.py` direct.

---

## 📝 Technische Details

### Externe Dependencies:
- **CadQuery/OCP:** Shape conversie, bounding box
- **OCP.TopExp:** Face exploration voor outer contour
- **OCP.BRepGProp:** Perimeter/area calculaties
- **step_processing:** detect_holes, detect_shaped_holes (hergebruikt)

### Logging:
- Logger name: `[CutFeatures]`
- Info level: extraction milestones
- Debug level: dimension parsing
- Error level: exceptions with traceback

### Performance:
- Minimal overhead: hergebruikt bestaande detectie
- No extra STEP load
- Happens during XML export (eenmalig per BOM item)

---

## ✍️ Auteur

ALES Manufacturing Pipeline  
Datum: 3 maart 2026  
Commit: TBD (na documentatie update)
