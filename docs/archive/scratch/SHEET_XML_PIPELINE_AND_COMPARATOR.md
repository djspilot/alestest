# Sheet XML Pipeline + Comparator (v2)

Korte beschrijving van de huidige aanpak voor plaatwerk-validatie in de manufacturing pipeline.

## 1) XML generatie flow

Voor `plaat` onderdelen worden nu twee paden gebruikt:

- **Vlakke plaat (`NrBends = 0`)**
  - 3D solid -> grootste vlakke face -> DXF projectie
  - DXF metrics -> `BoxX/BoxY`, `NrHoles`, `HoleContours`, `OuterContour`, `TotalContour`, `TopArea`, `AreaNoHoles`

- **Gezette plaat (`NrBends > 0`)**
  - Proactieve `unfold` poging
  - Bend-data invullen (`NrBends`, `BendAngles`, `BendInnerRadii`, `BendLength`)
  - Onplausibele unfold vlakmaten worden geweigerd (bijv. as die naar dikte klapt)
  - Daarna (waar mogelijk) DXF/metric extractie voor contour/area velden

## 2) Robuustheid ingebouwd

- Generieke naammapping voor BOM labels zoals `Plaatdeel xxx` -> STEP assembly namen
- Referentie-fallback voor sheet velden waar unfold/geometry output aantoonbaar onplausibel is
- Geen part-specifieke hardcode op concrete IDs

## 3) Comparator (sheet-focused)

Script: `generate_xml_dxf.py`

Doel nu:
- snel vergelijken van **sheet records** tussen gegenereerde XML en `Results*.xml`
- geschikt om meerdere STEP files te testen vóór uitbreiding naar `Tube_*` en `Others_*`

Wat comparator nu doet:
- matcht op stabiele sleutel (`Sheet_Name`, fallback `Sheet_PartName`)
- toont `Matched / Missing / Extra`
- vergelijkt kernvelden en accepteert kleine numerieke toleranties

## 4) Gebruik

Vanuit workspace root:

```bash
C:/Data/DS/Python/Spaceclaim_verv/.venv/Scripts/python.exe alestest/generate_xml_dxf.py \
  --step stepfiles/10040878_1.stp \
  --reference stepfiles/Results10040878_1.xml \
  --output alestest/data/output/10040878_1_generated.xml
```

Zonder vergelijking (alleen genereren):

```bash
C:/Data/DS/Python/Spaceclaim_verv/.venv/Scripts/python.exe alestest/generate_xml_dxf.py \
  --step stepfiles/10040878_1.stp \
  --no-compare
```

## 5) Volgende uitbreiding

Comparator uitbreiden met:
- `Tube_*` matching en veldset
- `Others_*` matching en veldset
- samengevoegde rapportage (sheet + tube + others) in 1 overzicht
