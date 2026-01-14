# Vergelijking: Pipeline vs Spaceclaim XML

**Bron XML:** Results20251218135432.xml (Spaceclaim/ERP data)

---

## Samenvatting Vergelijking

| Onderdeel | Eigenschap | Spaceclaim | Pipeline | Status |
|-----------|------------|------------|----------|--------|
| **10000703900** | Dikte | 2 mm | 0.46 mm | ❌ Afwijking |
| | Zettingen | 9 | 48 | ❌ Afwijking |
| | Gaten | 9 | 18 (AAG) | ❌ Afwijking |
| | Uitslag X | 1829 mm | 1828 mm | ✅ Match |
| | Uitslag Y | 1159 mm | 1119 mm | ⚠️ Klein verschil |
| | Unfold | True | Ja | ✅ Match |
| **10001059687** | Dikte | 5 mm | 5 mm | ✅ Match |
| | Zettingen | 6 | 77 | ❌ Afwijking |
| | Gaten | 21 | 42 (AAG) | ❌ Afwijking |
| | Uitslag X | 1179 mm | 1177 mm | ✅ Match |
| | Uitslag Y | 548 mm | 547 mm | ✅ Match |
| | Unfold | True | Ja | ✅ Match |
| **10001059694** | Dikte | 5 mm | 3 mm (corr.) | ⚠️ Klein verschil |
| | Zettingen | 3 | 31 | ❌ Afwijking |
| | Gaten | 8 | 4 (AAG) | ❌ Afwijking |
| | Uitslag X | 883 mm | 883 mm | ✅ Match |
| | Uitslag Y | 528 mm | 526 mm | ✅ Match |
| | Unfold | True | Ja | ✅ Match |
| **10001057925** | Dikte | 5 mm | 5 mm | ✅ Match |
| | Zettingen | 6 | 98 | ❌ Afwijking |
| | Gaten | 29 | 58 (AAG) | ❌ Afwijking |
| | Uitslag X | 1179 mm | 1177 mm | ✅ Match |
| | Uitslag Y | 548 mm | 547 mm | ✅ Match |
| | Unfold | True | Ja | ✅ Match |
| **10000890089** | Dikte | 20 mm | 20 mm | ✅ Match |
| | Zettingen | 0 | 0 | ✅ Match |
| | Gaten | 9 | 9 | ✅ Match |
| | Uitslag X | 1200 mm | 1200 mm | ✅ Match |
| | Uitslag Y | 40 mm | 40 mm | ✅ Match |
| **10000890096** | Dikte | 5 mm | 40 mm (AAG) | ❌ Afwijking |
| | Zettingen | 0 | 9 | ❌ Afwijking |
| | Gaten | 3 | 0 (AAG) | ❌ Afwijking |
| | Uitslag X | 310 mm | 310 mm | ✅ Match |
| | Uitslag Y | 40 mm | 40 mm | ✅ Match |
| **10000707475** | Type | Koker 40×40×2 | Koker 40×40 | ✅ Match |
| | Dikte | 2 mm | 36 mm (wanddikte) | ⚠️ AAG interpreteert anders |
| | Lengte | 747 mm | 747 mm | ✅ Match |
| **10000705057** | Type | Other | Gebogen plaatwerk | ⚠️ Classificatie verschil |
| | Aantal | 3 stuks | 1 stuk | ❌ Afwijking |

---

## Gedetailleerde Vergelijking per Onderdeel

### 10000703900_Rev_00 (Plaatwerk)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 3D Sheet | Gebogen plaatwerk | ✅ |
| Dikte | 2 mm | 0.46 mm | ❌ |
| Zettingen | 9 | 48 (AAG) | ❌ |
| Gaten | 9 | 18 (AAG) | ❌ |
| Uitslag X | 1829 mm | 1828 mm | ✅ |
| Uitslag Y | 1159 mm | 1119 mm | ⚠️ |
| Buitencontour | 6302 mm | - | - |
| Totale contour | 6534 mm | 10693 mm (snijlengte) | - |
| Unfold | True | Ja | ✅ |
| Materiaal | rvs kgw≤8 #2 | - | - |
| Gewicht | 30.3 kg | - | - |

**Gatdiameters Spaceclaim:** 8× Ø6.5mm (3.25 radius)
**Gatdiameters Pipeline:** 8× Ø6.5mm + 1× 20.2×19.5mm rechthoek

---

### 10001059687_Rev_00 (Plaatwerk)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 3D Sheet | Gebogen plaatwerk | ✅ |
| Dikte | 5 mm | 5 mm | ✅ |
| Zettingen | 6 | 77 (AAG) | ❌ |
| Gaten | 21 | 42 (AAG) | ❌ |
| Uitslag X | 1179 mm | 1177 mm | ✅ |
| Uitslag Y | 548 mm | 547 mm | ✅ |
| Unfold | True | Ja | ✅ |
| Gewicht | 17.9 kg | - | - |

**Gatdiameters Spaceclaim:** 6× Ø6.5mm, 5× Ø8.5mm, 4× Ø10.5mm, 4× Ø13mm
**Zethoeken Spaceclaim:** -90°, -90°, -90°, 90°, -90°, 105°

---

### 10001059694_Rev_00 (Plaatwerk)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 3D Sheet | Gebogen plaatwerk | ✅ |
| Dikte | 5 mm | 182 mm (AAG fout) | ❌ |
| Zettingen | 3 | 31 (AAG) | ❌ |
| Gaten | 8 | 4 (AAG) | ❌ |
| Uitslag X | 883 mm | 883 mm | ✅ |
| Uitslag Y | 528 mm | 526 mm | ✅ |
| Unfold | True | Ja | ✅ |
| Gewicht | 10.3 kg | - | - |

**Gatdiameters Spaceclaim:** 3× Ø8.5mm, 3× Ø10.2mm, 2× Ø10.5mm
**Zethoeken Spaceclaim:** 90°, 90°, -105°

---

### 10001057925_Rev_00 (Plaatwerk)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 3D Sheet | Gebogen plaatwerk | ✅ |
| Dikte | 5 mm | 5 mm | ✅ |
| Zettingen | 6 | 98 (AAG) | ❌ |
| Gaten | 29 | 58 (AAG) | ❌ |
| Uitslag X | 1179 mm | 1177 mm | ✅ |
| Uitslag Y | 548 mm | 547 mm | ✅ |
| Unfold | True | Ja | ✅ |
| Gewicht | 18.2 kg | - | - |

**Gatdiameters Spaceclaim:** 4× Ø6.5mm, 13× Ø8.5mm, 4× Ø10.5mm, 4× Ø13mm + grote gaten
**Zethoeken Spaceclaim:** -90°, -90°, 90°, -90°, -90°, 105°

---

### 10000890089_Rev_00 (Vlakke Plaat)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 2D | Plaat (vlak) | ✅ |
| Dikte | 20 mm | 20 mm | ✅ |
| Zettingen | 0 | 0 | ✅ |
| Gaten | 9 | 9 | ✅ |
| Afmetingen X | 1200 mm | 1200 mm | ✅ |
| Afmetingen Y | 40 mm | 40 mm | ✅ |
| Unfold | True | N.v.t. | ✅ |
| Gewicht | 7.5 kg | - | - |

**Gatdiameters:** 9× Ø6.8mm ✅ **Perfecte match!**

---

### 10000890096_Rev_00 (Plaatwerk)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | 2D | Gebogen plaatwerk | ⚠️ |
| Dikte | 5 mm | 40 mm (AAG fout) | ❌ |
| Zettingen | 0 | 9 (AAG) | ❌ |
| Gaten | 3 | 0 (AAG) | ❌ |
| Afmetingen X | 310 mm | 310 mm | ✅ |
| Afmetingen Y | 40 mm | 40 mm | ✅ |
| Unfold | True | Ja | ✅ |
| Gewicht | 0.46 kg | - | - |

**Gatdiameters Spaceclaim:** 3× Ø10.5mm

---

### 10000707475_Rev_00 (Koker/Buis)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | Tube R_40x40x2 | Profiel Koker | ✅ |
| Profiel | 40×40 mm | 40×40 mm | ✅ |
| Wanddikte | 2 mm | 36 mm (AAG fout) | ❌ |
| Lengte | 747 mm | 747 mm | ✅ |
| Features | 0 | 0 | ✅ |
| Gewicht | 1.76 kg | - | - |

---

### 10000705057_Rev_00 (Overig)

| Parameter | Spaceclaim | Pipeline | Match |
|-----------|------------|----------|-------|
| Type | Other | Gebogen plaatwerk | ❌ |
| Aantal | 3 stuks | 1 stuk | ❌ |
| Volume | 9479 mm³ | - | - |

**Opmerking:** Spaceclaim classificeert dit als "Other" (inkoopdeel), pipeline probeert te analyseren als plaatwerk.

---

## Conclusies

### ✅ Goed werkend
- **Uitslag afmetingen** - Zeer nauwkeurig (1-2mm verschil)
- **Unfold detectie** - 100% match
- **Vlakke platen** - Perfecte match (10000890089)
- **Profielherkenning** - Type en afmetingen correct

### ⚠️ Aandachtspunten
- **AAG zettingen tellen** - Telt veel meer zettingen dan Spaceclaim (bv. 48 vs 9)
  - Mogelijke oorzaak: AAG telt alle cylindrische buigvlakken, Spaceclaim alleen productie-zettingen
- **AAG gaten tellen** - Inconsistent (soms meer, soms minder)
- **Dikte detectie** - AAG geeft soms onrealistische waardes (0.46mm, 182mm)

### ❌ Verbeterpunten
1. **Zettingen definitie** - AAG moet productie-relevante zettingen tellen, niet alle buigvlakken
2. **Dikte validatie** - AAG dikte moet gevalideerd worden tegen standaard detectie
3. **"Other" classificatie** - Inkoopdelen beter herkennen

---

## Ruwe Data Vergelijking (CSV formaat)

```csv
Onderdeel;Type_SC;Type_PL;Dikte_SC;Dikte_PL;Zet_SC;Zet_PL;Gat_SC;Gat_PL;BoxX_SC;BoxX_PL;BoxY_SC;BoxY_PL;Unfold
10000703900;Sheet;Plaatwerk;2;0.46;9;48;9;18;1829;1828;1159;1119;True
10001059687;Sheet;Plaatwerk;5;5;6;77;21;42;1179;1177;548;547;True
10001059694;Sheet;Plaatwerk;5;3;3;31;8;4;883;883;528;526;True
10001057925;Sheet;Plaatwerk;5;5;6;98;29;58;1179;1177;548;547;True
10000890089;2D;Plaat;20;20;0;0;9;9;1200;1200;40;40;True
10000890096;2D;Plaatwerk;5;40;0;9;3;0;310;310;40;40;True
10000707475;Tube;Koker;2;36;-;8;0;0;747;747;40;40;-
10000705057;Other;Plaatwerk;-;30;-;2;-;2;-;35;-;20;False
```

---

*Vergelijking gegenereerd op basis van Results20251218135432.xml*
