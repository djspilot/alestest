# Vergelijking V2: Pipeline (gefilterd) vs Spaceclaim XML

**Na filtering van productie-zettingen**

---

## Samenvatting

| Onderdeel | Type_SC | Type_PL | Dikte_SC | Dikte_PL | Zet_SC | Zet_PL | Gat_SC | Gat_PL | Match |
|-----------|---------|---------|----------|----------|--------|--------|--------|--------|-------|
| 10000703900 | Sheet | COMPLEX | 2mm | 0.46mm | 9 | **16** | 9 | 18 | ⚠️ |
| 10000705057 | Other | COMPLEX | - | 30mm | - | 2 | - | 2 | - |
| 10000707475 | Tube | KOKER | 2mm | 36mm | - | 8 | 0 | 0 | ✅ |
| 10000890089 | 2D | PLAAT* | 20mm | 20mm | 0 | **0** | 9 | 9 | ✅ |
| 10000890096 | 2D | PLAAT | 5mm | 40mm | 0 | **0** | 3 | 0 | ⚠️ |
| 10001057924 | Assembly | COMPLEX | - | 5mm | - | 68 | - | 165 | - |
| 10001057925 | Sheet | COMPLEX | 5mm | 5mm | 6 | **14** | 29 | 58 | ⚠️ |
| 10001059687 | Sheet | COMPLEX | 5mm | 5mm | 6 | **12** | 21 | 42 | ⚠️ |
| 10001059694 | Sheet | COMPLEX | 5mm | 182mm | 3 | **6** | 8 | 4 | ⚠️ |
| C1050070 | - | KOKER | - | 2mm | - | 4 | - | 4 | - |

*Opmerking: 10000890089 wordt door AAG als KOKER geclassificeerd i.p.v. PLAAT vanwege aspect ratio*

---

## Vergelijking Zettingen (Voor en Na Filter)

| Onderdeel | Spaceclaim | AAG Oud (raw) | AAG Nieuw (filtered) | Verbetering |
|-----------|------------|---------------|----------------------|-------------|
| 10000703900 | 9 | 48 | **16** | ✅ 67% dichter |
| 10000705057 | - | 2 | **2** | - |
| 10000707475 | - | 8 | **8** | Koker, n.v.t. |
| 10000890089 | 0 | 0 | **0** | ✅ Perfect |
| 10000890096 | 0 | 9 | **0** | ✅ Perfect |
| 10001057924 | - | 283 | **68** | ✅ 76% gefilterd |
| 10001057925 | 6 | 98 | **14** | ✅ 86% gefilterd |
| 10001059687 | 6 | 77 | **12** | ✅ 84% gefilterd |
| 10001059694 | 3 | 31 | **6** | ✅ 81% gefilterd |

---

## Verbeteringen

### ✅ Wat werkt goed:
1. **Vlakke platen** (10000890089, 10000890096): 0 zettingen correct
2. **Filter ratio**: 67-86% van ongeldige bends gefilterd
3. **Type classificatie**: PLAAT/KOKER/COMPLEX herkenning werkt

### ⚠️ Wat nog afwijkt:
1. **Zettingen nog ~2× hoger** dan Spaceclaim
   - Mogelijke oorzaak: interne filets/radii tellen nog mee
   - Verbetering: filter op bend_length > 50mm (langere zettingen)
   
2. **Dikte detectie nog problematisch**
   - 10000703900: 0.46mm i.p.v. 2mm
   - 10001059694: 182mm i.p.v. 5mm
   
3. **Gaten telling** hoger dan Spaceclaim
   - AAG telt meer inner wires als gaten

---

## Aanbevelingen voor Verdere Verbetering

### 1. Zettingen filter aanscherpen
```python
# Huidige filter:
bend_angle: 45-135° of 170-180°
bend_radius: 0.3-15mm
bend_length: ≥10mm

# Voorgestelde filter:
bend_length: ≥50mm  # Langere zettingen
```

### 2. Dikte validatie
```python
# Valideer tegen bounding box
if thickness > min(bbox.X, bbox.Y, bbox.Z):
    thickness = standard_detection_thickness
```

### 3. Gaten matching met Spaceclaim
- Vergelijk gatdiameters, niet alleen aantal
- Filter gaten < 5mm (mogelijk slots/features)

---

## CSV Export

```csv
Onderdeel;Type_SC;Type_PL;Dikte_SC;Dikte_PL;Zet_SC;Zet_PL;Gat_SC;Gat_PL
10000703900;Sheet;COMPLEX;2;0.46;9;16;9;18
10000705057;Other;COMPLEX;;30;;2;;2
10000707475;Tube;KOKER;2;36;;8;0;0
10000890089;2D;PLAAT;20;20;0;0;9;9
10000890096;2D;PLAAT;5;40;0;0;3;0
10001057924;Assembly;COMPLEX;;5;;68;;165
10001057925;Sheet;COMPLEX;5;5;6;14;29;58
10001059687;Sheet;COMPLEX;5;5;6;12;21;42
10001059694;Sheet;COMPLEX;5;5;3;6;8;4
C1050070;;KOKER;;2;;4;;4
```
