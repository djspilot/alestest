# Offerte 20253515 - Manufacturing Analyse Rapport

**Datum:** 9 januari 2026  
**Aantal onderdelen:** 11 STEP-bestanden  
**Analyse methode:** AAG (Attributed Adjacency Graph) Feature Recognition

---

## Samenvatting

| Onderdeelnummer | Categorie | Afmetingen (mm) | Dikte (mm) | Zettingen | Gaten | Laser tijd (sec) |
|-----------------|-----------|-----------------|------------|-----------|-------|------------------|
| 10000703900 | Gebogen plaatwerk | 1225 × 823 × 285 | 0.46 | 48 | 18 | 336 |
| 10000705057 | Gebogen plaatwerk | 35 × 20 × 20 | 30.00 | 2 | 2 | 37 |
| 10000707475 | Profiel (koker) | 747 × 40 × 40 | 36.00 | 8 | 0 | 394 |
| 10000890089 | Plaat (vlak) | 1200 × 40 × 20 | 20.00 | 0 | 9 | 1904 |
| 10000890096 | Gebogen plaatwerk | 310 × 40 × 5 | 40.00 | 9 | 0 | 139 |
| 10001057924 | Gebogen plaatwerk | 1238 × 823 × 585 | 5.00 | 283 | 165 | 1617 |
| 10001057925 | Gebogen plaatwerk | 823 × 334 × 190 | 5.00 | 98 | 58 | 426 |
| 10001059687 | Gebogen plaatwerk | 823 × 334 × 190 | 5.00 | 77 | 42 | 394 |
| 10001059694 | Gebogen plaatwerk | 883 × 334 × 172 | 182.00 | 31 | 4 | 502 |
| C1050070 | Profiel (buis) | 80 × 16 × 16 | 2.00 | 11 | 4 | 10 |

**Totaal geschatte lasertijd:** ~5759 seconden (~96 minuten)

---

## Gedetailleerde Analyse per Onderdeel

### 1. 10000703900_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 1225 × 823 × 285 mm |
| **Uitslag afmetingen** | 1828 × 1119 mm |
| **Materiaaldikte** | 0.46 mm (AAG) |
| **Aantal zettingen** | 48 |
| **Vouwlijnen** | 9 |

#### Gaten detectie
- **Cilindrische gaten:** 8× Ø6.50mm
- **Rechthoekige gaten:** 1× 20.2×19.5mm
- **Totaal gaten (AAG):** 18

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 10,693 mm |
| Pierces | 19 |
| Laser snijtijd | 336.4 sec |
| Faces/Edges | 130/324 |

#### Opmerkingen
- ✅ Unfold succesvol
- ⚠️ Dikte mismatch tussen AAG (0.46mm) en standaard detectie (1.00mm)

---

### 2. 10000705057_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen** | 35 × 20 × 20 mm |
| **Materiaaldikte** | 30.00 mm (AAG) |
| **Aantal zettingen** | 2 |

#### Gaten detectie
- **Gaten (AAG):** 2
- **Cilindrische gaten (3D):** 0

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 141 mm |
| Pierces | 3 |
| Laser snijtijd | 37.1 sec |
| Faces/Edges | 13/25 |

#### Opmerkingen
- ⚠️ Unfold niet gelukt
- Klein onderdeel met dikke materiaal

---

### 3. 10000707475_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Profiel - Koker (ingekocht) |
| **Afmetingen** | 747 × 40 × 40 mm |
| **Materiaaldikte** | 36.00 mm (AAG - wanddikte koker) |
| **Aantal zettingen** | 8 (niet relevant voor koker) |

#### Gaten detectie
- **Rechthoekige gaten:** 1× 36.0×36.0mm (doorsnede)
- **Gaten (AAG):** 0

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 1,563 mm |
| Pierces | 1 |
| Laser snijtijd | 394.4 sec |
| Faces/Edges | 18/48 |

#### Opmerkingen
- ℹ️ Ingekocht profiel - geen uitslag nodig
- Vierkante koker 40×40mm

---

### 4. 10000890089_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Plaat (vlak) |
| **Afmetingen** | 1200 × 40 × 20 mm |
| **Materiaaldikte** | 20.00 mm |
| **Aantal zettingen** | 0 |

#### Gaten detectie
- **Cilindrische gaten:** 9× Ø6.80mm
- **Totaal gaten (AAG):** 9

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 7,537 mm |
| Pierces | 10 |
| Laser snijtijd | 1,904.3 sec |
| Faces/Edges | 60/129 |

#### Opmerkingen
- ℹ️ Vlakke plaat - geen uitslag nodig
- Langwerpig onderdeel met regelmatig gatpatroon
- ⚠️ Langste lasertijd door dikke materiaal (20mm)

---

### 5. 10000890096_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 310 × 40 × 5 mm |
| **Uitslag afmetingen** | 310 × 40 mm |
| **Materiaaldikte** | 40.00 mm (AAG) |
| **Aantal zettingen** | 9 |

#### Gaten detectie (uitslag)
- **Cilindrische gaten:** 3× Ø10.50mm, 2× Ø40.00mm
- **Totaal gaten (AAG):** 0 (alleen op 3D model)

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 550 mm |
| Pierces | 1 |
| Laser snijtijd | 139.1 sec |
| Faces/Edges | 13/33 |

#### Opmerkingen
- ✅ Unfold succesvol
- ⚠️ Dikte mismatch (AAG 40mm vs standaard 5.25mm)

---

### 6. 10001057924_Rev_00 ⭐ Hoofdonderdeel

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 1238 × 823 × 585 mm |
| **Uitslag afmetingen** | 1828 × 1119 mm |
| **Materiaaldikte** | 5.00 mm |
| **Aantal zettingen** | 283 |
| **Vouwlijnen** | 9 |

#### Gaten detectie (uitslag)
- **Cilindrische gaten:** 8× Ø6.50mm
- **Rechthoekige gaten:** 1× 20.2×19.5mm
- **Totaal gaten (AAG):** 165

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 50,172 mm |
| Pierces | 166 |
| Laser snijtijd | 1,616.8 sec |
| Faces/Edges | 700/1701 |

#### Opmerkingen
- ✅ Unfold succesvol
- ⚠️ Meest complexe onderdeel met 283 zettingen
- 🔴 Langste snijlengte (50+ meter)

---

### 7. 10001057925_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 823 × 334 × 190 mm |
| **Uitslag afmetingen** | 1177 × 547 mm |
| **Materiaaldikte** | 5.00 mm |
| **Aantal zettingen** | 98 |
| **Vouwlijnen** | 7 |

#### Gaten detectie (uitslag)
| Diameter | Aantal |
|----------|--------|
| Ø6.50mm | 4 |
| Ø8.50mm | 12 |
| Ø9.00mm | 4 |
| Ø10.50mm | 4 |
| Ø13.00mm | 2 |
| Ø61.50mm | 1 |
| Ø90.00mm | 1 |
| Rechthoek 120×40mm | 1 |

- **Totaal gaten (AAG):** 58

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 12,953 mm |
| Pierces | 59 |
| Laser snijtijd | 425.5 sec |
| Faces/Edges | 173/457 |

#### Opmerkingen
- ✅ Unfold succesvol
- Diverse gatdiameters (6.5mm tot 90mm)

---

### 8. 10001059687_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 823 × 334 × 190 mm |
| **Uitslag afmetingen** | 1177 × 547 mm |
| **Materiaaldikte** | 5.00 mm |
| **Aantal zettingen** | 77 |
| **Vouwlijnen** | 6 |

#### Gaten detectie (uitslag)
| Diameter | Aantal |
|----------|--------|
| Ø6.50mm | 6 |
| Ø8.50mm | 4 |
| Ø10.50mm | 4 |
| Ø13.00mm | 2 |
| Ø61.50mm | 1 |
| Ø90.00mm | 1 |
| Rechthoek 120×40mm | 1 |

- **Totaal gaten (AAG):** 42

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 12,193 mm |
| Pierces | 43 |
| Laser snijtijd | 394.3 sec |
| Faces/Edges | 138/362 |

#### Opmerkingen
- ✅ Unfold succesvol
- Vergelijkbaar met 10001057925 maar iets minder complex

---

### 9. 10001059694_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Gebogen plaatwerk (complex) |
| **Afmetingen (3D)** | 883 × 334 × 172 mm |
| **Uitslag afmetingen** | 883 × 526 mm |
| **Materiaaldikte** | 182.00 mm (AAG - onwaarschijnlijk) |
| **Aantal zettingen** | 31 |
| **Vouwlijnen** | 3 |

#### Gaten detectie (uitslag)
| Diameter | Aantal |
|----------|--------|
| Ø8.50mm | 3 |
| Ø10.20mm | 3 |
| Ø10.50mm | 2 |

- **Totaal gaten (AAG):** 4

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 1,982 mm |
| Pierces | 5 |
| Laser snijtijd | 502.0 sec |
| Faces/Edges | 59/147 |

#### Opmerkingen
- ✅ Unfold succesvol
- ⚠️ AAG dikte (182mm) lijkt incorrect - waarschijnlijk ~3mm

---

### 10. C1050070_Rev_00

| Eigenschap | Waarde |
|------------|--------|
| **Categorie** | Profiel - Buis (ingekocht) |
| **Afmetingen** | 80 × 16 × 16 mm |
| **Materiaaldikte** | 2.00 mm |
| **Aantal zettingen** | 11 (niet relevant voor buis) |

#### Gaten detectie
- **Cilindrische gaten:** 1× Ø8.10mm
- **Totaal gaten (AAG):** 4

#### AAG Analyse
| Parameter | Waarde |
|-----------|--------|
| Snijlengte | 166 mm |
| Pierces | 5 |
| Laser snijtijd | 9.5 sec |
| Faces/Edges | 35/72 |

#### Opmerkingen
- ℹ️ Ingekocht profiel - geen uitslag nodig
- Klein buisprofiel met gat voor bevestiging

---

## Productiebeoordeling

### Categorieën verdeling

```
Gebogen plaatwerk:  7 onderdelen (64%)
Profiel (ingekocht): 2 onderdelen (18%)
Vlakke plaat:        1 onderdeel  (9%)
```

### Aandachtspunten voor productie

1. **10001057924** - Zeer complex onderdeel met 283 zettingen en 50+ meter snijlengte
2. **10000890089** - Dikke vlakke plaat (20mm) met langste lasertijd (32 min)
3. **10000705057** - Unfold niet mogelijk - handmatige beoordeling nodig
4. **Dikte inconsistenties** - AAG detectie wijkt soms sterk af van standaard analyse

### Ingekochte profielen

| Nummer | Type | Afmetingen |
|--------|------|------------|
| 10000707475 | Koker | 40×40×747mm |
| C1050070 | Buis | Ø16×80mm |

---

## Gegenereerde bestanden

Voor elk onderdeel zijn de volgende bestanden gegenereerd in `resources/output/[onderdeelnummer]/`:

- `*_analysis.txt` - Tekstuele analyse
- `*_aag.json` - AAG data (JSON)
- `*_report.pdf` - PDF rapport
- `*_flat.step` - Uitslag (indien van toepassing)
- `*_flat.dxf` - DXF uitslag (indien van toepassing)

---

*Rapport gegenereerd met Manufacturing Analysis Pipeline - AAG Feature Recognition*
