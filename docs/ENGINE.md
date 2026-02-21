# Engine: Technische Beschrijving

Dit document beschrijft hoe de ALES Manufacturing Pipeline intern werkt, welke methoden worden gebruikt voor feature-detectie, en hoe de resultaten zich verhouden tot SpaceClaim/AutoPOL.

---

## Inhoudsopgave

- [Overzicht](#overzicht)
- [STEP-verwerking](#step-verwerking)
- [Gatdetectie](#gatdetectie)
- [Zetdetectie (bends)](#zetdetectie-bends)
- [Plaatwerk ontvouwen](#plaatwerk-ontvouwen)
- [AAG Feature Recognition](#aag-feature-recognition)
- [Onderdeelclassificatie](#onderdeelclassificatie)
- [ISO-normen](#iso-normen)
- [Pipeline caching](#pipeline-caching)
- [Vergelijking met SpaceClaim](#vergelijking-met-spaceclaim)
- [Bekende beperkingen](#bekende-beperkingen)

---

## Overzicht

De engine analyseert STEP-bestanden in meerdere stappen:

```
┌──────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌──────────┐
│  CadQuery │    │  Vlak-    │    │  Feature  │    │  ISO      │    │ Rapport  │
│  /OCP     │───▶│  analyse  │───▶│  detectie │───▶│  normen   │───▶│ generatie│
│           │    │           │    │           │    │           │    │          │
│  Laad     │    │  Planair  │    │  Gaten    │    │  2768     │    │  PDF     │
│  STEP     │    │  Cilindr. │    │  Zetten   │    │  286      │    │  Excel   │
│  Parse    │    │  Conisch  │    │  Draad    │    │  1302     │    │  XML     │
│  B-Rep    │    │  Toroidal │    │  Afschuining│  │  68-1     │    │  JSON    │
└──────────┘    └───────────┘    └───────────┘    └───────────┘    └──────────┘
```

**Kerntechnologie:** OpenCascade (OCP) via CadQuery. Dit is dezelfde B-Rep kernel die ook door FreeCAD en andere CAD-systemen wordt gebruikt. STEP-bestanden worden als Boundary Representation (B-Rep) geladen — elke geometrische entiteit (vlakken, randen, vertices) is direct beschikbaar.

---

## STEP-verwerking

**Bestand:** `manufacturing_pipeline/analysis/step_processing.py`

### Laden en parsen

1. CadQuery laadt het STEP-bestand als `cq.Workplane`
2. Alle solids worden geextraheerd (assemblies bevatten meerdere solids)
3. Per solid worden berekend:
   - **Volume** — via OCP's `GProp_GProps` (exacte B-Rep berekening)
   - **Oppervlakte** — som van alle vlakoppervlakten
   - **Bounding box** — minimale omsluitende doos (lengte, breedte, hoogte)

### Vlakclassificatie

Elk vlak van het 3D-model wordt geclassificeerd op basis van het geometrische type:

| Vlaktype | OCP Type | Wat het betekent |
|----------|----------|------------------|
| Planair | `GeomAbs_Plane` | Plat vlak — bovenkant, zijkant, gatwand |
| Cilindrisch | `GeomAbs_Cylinder` | Rond vlak — gat, as, zetting |
| Conisch | `GeomAbs_Cone` | Kegelvormig — verzinking, tapse gaten |
| Toroidaal | `GeomAbs_Torus` | Ringvormig — afrondingen, filets |
| Sferisch | `GeomAbs_Sphere` | Bolvormig — zeldzaam in plaatwerk |
| B-Spline | `GeomAbs_BSplineSurface` | Vrije-vormvlakken |

---

## Gatdetectie

De pipeline gebruikt **twee complementaire methoden** om gaten betrouwbaar te detecteren:

### Methode 1: Cilindrische vlakken

```
Bovenaanzicht gat:          Zijaanzicht:
                            ┌─────────────┐
    ╭───────╮               │             │
    │  GAT  │               │  cilindrisch│
    │       │               │  vlak       │
    ╰───────╯               │  (REVERSED) │
                            └─────────────┘
```

- Zoekt alle cilindrische vlakken op het model
- Filtert op **orientatie**: `REVERSED` = intern (gat), `FORWARD` = extern (as/cilinder)
- Groepeert gesplitste vlakken (bijv. 2x 180 = 1 volledig gat)
- **Minimale hoek:** 270 voor 3D-vormen, 160 voor ontvouwen patronen
- **Maximale diameter:** 100mm op ontvouwen patronen (anders is het geen gat)

**Sterk in:** doorlopende gaten, diepe gaten, schroefgaten

### Methode 2: Inner wires (vormgaten)

```
Bovenaanzicht plaatdeel:
    ┌────────────────────────┐
    │                        │  ← Outer wire (omtrek)
    │   ╭──╮    ┌────┐      │
    │   │  │    │    │      │  ← Inner wires (gaten)
    │   ╰──╯    └────┘      │
    │                        │
    │        ╭────────╮      │
    │        │        │      │
    │        ╰────────╯      │
    └────────────────────────┘
```

- Analyseert planaire vlakken: de eerste wire is altijd de buitenomtrek
- Alle overige wires zijn **gaten** (inner wires)
- Classificeert gatvorm via geometrie:
  - **Rond** — alleen cirkelbogen
  - **Sleuf** — 2 lijnen + 2 bogen
  - **Rechthoek** — 4 lijnen
  - **Complex** — overige combinaties
- Gebruikt **Isoperimetrisch Quotient** (IQ = 4piA/P^2) voor classificatie:
  - IQ ≈ 1.0 → cirkel
  - IQ < 0.9 → sleuf of vormgat

**Sterk in:** lasersnijgaten, sleuven, rechthoekige openingen, complexe vormen

### Dubbeltellingpreventie

Bij plaatwerk verschijnen gaten op **zowel de boven- als onderkant**. De pipeline lost dit op met twee strategieen:

| Strategie | Methode | Wanneer |
|-----------|---------|---------|
| `largest_face` | Tel gaten alleen op het grootste planaire vlak | Standaard (3D) |
| `all_faces_div2` | Tel alle inner wires, deel door 2 | Na ontvouwen |

---

## Zetdetectie (bends)

**Bestanden:** `part_analyzer.py`, `aag_analyzer.py`, `compare_erp.py`

### Hoe zettingen worden gedetecteerd

Een zetting in 3D verschijnt als een **cilindrisch vlak** tussen twee planaire vlakken:

```
Zijaanzicht zetting:

    ─────────┐
             │ ← planair vlak
             │
             ╰──────── ← cilindrisch vlak (= de zetting)
                      │
                      │ ← planair vlak
                      └─────────
```

Elke fysieke zetting heeft **twee cilindrische vlakken**: binnenradius en buitenradius. De pipeline groepeert deze paren.

### Productie-relevante zettingen

**Niet alle zettingen tellen mee voor ERP-calculatie.** De businessregels:

| Criterium | Waarde | Reden |
|-----------|--------|-------|
| Hoek | 10–170 | Buiten dit bereik is het geen zetting |
| Radius | 0.3–15mm | < 0.3mm = afronding/fillet, > 15mm = walsen |
| Lengte (hoek ≥ 45) | ≥ 10mm | Te kort = rand, geen zetbewerking |
| Lengte (hoek < 45) | ≥ 2mm | Kleine hoeken bij korte lengte nog wel relevant |

### Profielherkenning (bend_count_erp = 0)

Aangekochte profielen worden **niet** als "te zetten" geteld. De pipeline herkent:

```
Koker (gesloten):        Hoekprofiel (L):        U-profiel:

┌──────────┐             │                       │          │
│          │             │                       │          │
│          │             │                       │          │
│          │             └──────────              └──────────┘
└──────────┘
4 zettingen ≈ 360        1 zetting               2 zettingen
→ ERP: 0 zettingen       → ERP: 0 zettingen      → ERP: 0 zettingen
```

Detectiecriteria voor profielen:
- **Koker:** 4 zettingen die samen ~360 vormen
- **Hoekprofiel:** aspect ratio > 3:1, zetting over > 90% van de lengte, standaardmaten (20, 25, 30, 40, 50, 60mm...)
- **U/C-profiel:** 2-3 zettingen over volledige lengte

### AAG Zetgroepering (SpaceClaim-compatibel)

De AAG-analyzer voert een 3-staps groepering uit om overeen te komen met hoe SpaceClaim zettingen telt:

1. **Binnen/buitenradius paren** — Match cilindrische vlakken met dezelfde hoek (±5) en lengteverhouding (>90%). Houd alleen de binnenradius.
2. **Wrapper-filter** — Als er zettingen > 1000mm lang zijn EN er kortere zettingen bestaan, filter de lange eruit.
3. **Aangrenzende groepering** — SpaceClaim groepeert kleine zetsegmenten (< 50mm) die samen 1 langere zetbewerking vormen tot 1 telling.

---

## Plaatwerk ontvouwen

**Bestand:** `manufacturing_pipeline/analysis/freecad_unfold.py`

### Werkwijze

De pipeline gebruikt FreeCAD's SheetMetal workbench voor het ontvouwen:

```
3D model                    Ontvouwen (flat pattern)
┌────────┐                  ┌──────────────────────┐
│        │                  │                      │
│   ┌────┘   ──ontvouw──▶  │    ○    ○    ○       │
│   │                       │                      │
│   └────┐                  │   ┌──────┐           │
│        │                  │   │      │           │
└────────┘                  └───┴──────┴───────────┘

                            → DXF export
                            → Afmetingen (L x B)
                            → Gatdetectie op vlak patroon
```

### Multi-poging strategie

1. Probeer het **grootste planaire vlak** als basisvlak
2. Bij falen: probeer het **2e en 3e grootste** planaire vlak
3. Bij samenstellingen: probeer **elk solid apart**
4. Bij volledig falen: bereken **theoretische ontvouwing** uit zetgeometrie

### K-factor

De K-factor bepaalt waar de neutrale lijn ligt in een zetting. Standaardwaarde: **0.44** voor alle diktes. Dit is een vereenvoudiging — in werkelijkheid varieert de K-factor per materiaal en dikte.

### Wanneer ontvouwen faalt

| Reden | Toelichting |
|-------|------------|
| Niet-uniforme dikte | Variabele plaatdikte |
| Complexe zettingen | Gewalste, conische of lofted bochten |
| Samengestelde delen | Gelaste of geklonken constructies |
| Foutieve geometrie | Problemen in het STEP-bestand zelf |

Bij falen valt de pipeline terug op 3D bounding box afmetingen en cilindrische-vlak zetdetectie.

---

## AAG Feature Recognition

**Bestand:** `manufacturing_pipeline/scripts/aag_analyzer.py`

### Attributed Adjacency Graph

De AAG is een graaf waar:
- **Nodes** = vlakken van het 3D-model
- **Edges** = randen tussen vlakken, met convexiteit-attribuut

```
        Convex (buitenhoek)              Concaaf (binnenhoek)
              ╱                                ╲
    ─────────╱                                  ╲─────────
             ╲                                  ╱
              ╲─────────              ─────────╱

    → Typisch: buitenkant               → Typisch: binnenkant
      van een zetting                     van een zetting
```

### Voordelen boven geometrie-only detectie

| Aspect | Geometrie-only | AAG |
|--------|---------------|-----|
| Gaten in gebogen vlakken | Kan missen | Herkent via topologie |
| Overlappende features | Lastig te scheiden | Graaf-segmentatie |
| Sleuf vs. gat | Alleen op vorm | IQ + topologische context |
| Snijlengte-berekening | Niet mogelijk | Somt rand-lengtes op |
| Lasersnijtijd-schatting | Niet mogelijk | Uit totale snijlengte |

### Lasersnijtijd

De AAG-analyzer berekent een snijtijdschatting op basis van:
- Totale snijlengte (buitenomtrek + gatcontouren)
- Materiaaldikte
- Snelheidsaannames per dikte

---

## Onderdeelclassificatie

**Bestand:** `manufacturing_pipeline/analysis/part_analyzer.py`

De pipeline classificeert elk onderdeel automatisch:

```
                        ┌─────────────────┐
                        │  Analyseer      │
                        │  geometrie      │
                        └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
              │ Plaatwerk? │ │Profiel│ │ Draaideel?│
              │            │ │   ?   │ │           │
              │ Uniforme   │ │Koker  │ │ Rotatie-  │
              │ dikte?     │ │Hoek-L │ │ symmetrie?│
              │ Zettingen? │ │U/C    │ │ Cilinders?│
              └─────┬──────┘ └───┬───┘ └─────┬─────┘
                    │            │            │
                    ▼            ▼            ▼
              SHEETMETAL    PROFILE      TURNED_PART
```

### Classificatielogica

1. **Plaatwerk** — Twee of meer parallelle planaire vlakken met uniforme afstand (dikte 0.5–25mm)
2. **Profiel** — Plaatwerk met zettingen over > 90% van de totale lengte + standaardafmetingen
3. **Draaideel** — Dominante cilindrische geometrie met rotatie-symmetrie
4. **Samenstelling** — Meerdere solids in een STEP-bestand
5. **Overig** — Fraasdelen, gietwerk, etc.

### Redenering-systeem

De analyzer houdt bij **waarom** beslissingen worden genomen. Elke classificatie bevat een reasoning trail:

```
Voorbeeld reasoning:
├── Dikte gedetecteerd: 3.0mm (2 parallelle vlakken, afstand 3.0mm)
├── Type: PLAATWERK (uniforme dikte, zettingen aanwezig)
├── 4 zettingen gedetecteerd, maar profiel (koker) → ERP zettingen: 0
└── Ontvouwen: geslaagd (basisvlak: grootste planair vlak)
```

---

## ISO-normen

**Bestand:** `manufacturing_pipeline/analysis/iso_standards.py`

| Norm | Implementatie | Details |
|------|--------------|---------|
| **ISO 2768** | Algemene toleranties | Klassen f/m/c/v (lineair) en H/K/L (geometrisch). Tolerantie op basis van nominale maat. |
| **ISO 286** | Passingen | Gatbasis-systeem (H7/h6, H7/g6, etc.). IT-graden 1–18. Berekent boven/ondermaat. |
| **ISO 1302** | Oppervlakteruwheid | Ra/Rz-waarden geschat op basis van bewerkingsproces (laser, frezen, draaien, etc.). |
| **ISO 68-1/261** | Metrisch draad | Draaddetectie M3–M68. Grof/fijn spoed. Voorboordiameters. |
| **ISO 13715** | Randcondities | Detectie van afschuiningen en afrondingen. Standaardmaten. |
| **EN 10025** | Staalsoorten | S235, S275, S355, C45, 42CrMo4, 304/316 RVS. Dichtheidstabellen. |
| **EN 573** | Aluminiumlegeringen | 1050, 5083, 6061, 6082, 7075. Dichtheidstabellen. |

---

## Pipeline caching

Het Full Mode pipeline-systeem ondersteunt checkpoint/resume:

```
load_step ──▶ detect_holes ──▶ geometry ──▶ faces ──▶ topology ──▶ classification
                                                                         │
complete ◀── pdf_correlation ◀── mass ◀── chamfers ◀── threads ◀── fits ◀┘
```

- Resultaten worden per stage opgeslagen in `.pipeline_cache/`
- Cache wordt ongeldig als het STEP-bestand wijzigt (MD5-hash)
- Het wissen van een stage wist ook alle afhankelijke stages
- `--status` toont voortgang, `--from <stage>` hervat

---

## Vergelijking met SpaceClaim

### Wat is SpaceClaim?

SpaceClaim (Ansys) is een commerciele CAD-tool die ALES gebruikt voor werkvoorbereiding. In combinatie met AutoPOL genereert het een XML/Excel-export die direct in het ERP-systeem wordt ingelezen. De ALES Pipeline is gebouwd als open-source alternatief dat dezelfde output kan genereren.

### Architectuurverschillen

```
SpaceClaim/AutoPOL:                    ALES Pipeline:

┌──────────────┐                       ┌──────────────┐
│  SpaceClaim  │  (proprietary)        │  CadQuery    │  (open-source)
│  + AutoPOL   │                       │  + OCP       │
│              │                       │  + FreeCAD   │
│  Ontvouwen   │  (eigen algoritme)    │  Ontvouwen   │  (SheetMetal WB)
│  Feature det.│  (intern)             │  Feature det.│  (AAG + geometrie)
│              │                       │              │
│  → XML       │                       │  → XML       │  (zelfde formaat)
│  → Excel     │                       │  → Excel     │  (zelfde 26 kolommen)
└──────────────┘                       └──────────────┘
```

### Feature-voor-feature vergelijking

#### Gatdetectie

| Aspect | SpaceClaim | ALES Pipeline |
|--------|-----------|---------------|
| Methode | Proprietary (vanuit ontvouwen patroon) | Dubbel: cilindrische vlakken + inner wires |
| Vormgaten (sleuven, etc.) | Ja | Ja (inner wire methode) |
| Dubbeltellingpreventie | Automatisch (vanuit flat) | largest_face of all_faces_div2 |
| Nauwkeurigheid | Referentie | Gelijk bij standaard plaatwerk, kan afwijken bij complexe assemblies |

#### Zetdetectie

| Aspect | SpaceClaim | ALES Pipeline |
|--------|-----------|---------------|
| Methode | Vanuit ontvouwlijnen | Cilindrische vlakken + AAG groepering |
| Kleine segmenten (<50mm) | Groepeert tot 1 zetbewerking | AAG doet dit ook (3-staps groepering) |
| Minimale hoek | Inclusief kleine hoeken (10+) | AAG: 10+, standaard: 30+ |
| Minimale lengte | ~2mm (bij kleine hoeken) | AAG: 2mm (hoek<45), 10mm (hoek>=45) |
| Profielherkenning | Handmatig/deels automatisch | Automatisch (koker, hoek-L, U/C) |

**Bekende afwijking:** Bij korte zetsegmenten (<50mm) die samen een langere zetbewerking vormen, kan de groepering anders uitpakken dan SpaceClaim. De AAG-analyzer benadert SpaceClaim's logica maar is niet identiek.

#### Ontvouwen

| Aspect | SpaceClaim | ALES Pipeline |
|--------|-----------|---------------|
| Algoritme | Proprietary | FreeCAD SheetMetal Workbench |
| K-factor | Per materiaal/dikte | Vast: 0.44 (alle diktes) |
| Vlakke afmetingen | Referentie | Kan afwijken door verschil in K-factor/basisvlak |
| Slagingspercentage | Hoog | Lager bij complexe geometrie (multi-poging strategie) |

**Bekende afwijking:** De ontvouwen afmetingen (lengte x breedte) kunnen afwijken van SpaceClaim omdat:
1. SpaceClaim een ander K-factor model gebruikt
2. SpaceClaim mogelijk een ander basisvlak selecteert
3. De ALES Pipeline valt terug op 3D bounding box bij falen

#### Volume en gewicht

| Aspect | SpaceClaim | ALES Pipeline |
|--------|-----------|---------------|
| Volume 3D | Exact (B-Rep) | Exact (B-Rep, zelfde kernel) |
| Volume in XML-export | Exact | **Benadering** (bounding box L×B×H) |
| Gewicht | Materiaal-specifiek | XML: staal (7.85 g/cm3), vergelijkingstool: aluminium (2.7 g/cm3) |

#### Excel-output (26 kolommen)

De pipeline genereert exact hetzelfde 26-koloms Excel-formaat als SpaceClaim:

| # | Kolom | Pipeline status |
|---|-------|----------------|
| 6 | Dikte | Exact |
| 11 | Oppervlakte | Exact (na ontvouwen) of benadering (L×B) |
| 12 | Snijlengte | Alleen met `--aag` (anders 0) |
| 16 | Snijgaten | Exact bij standaard plaatwerk |
| 17 | Aantalzet | Exact (met AAG groepering) |
| 18 | Tegenzet | Beschikbaar (met AAG) |
| 19 | Boorgaten | Nog niet geimplementeerd (altijd 0) |
| 22 | Gewicht | Staal-dichtheid (7.85 g/cm3) |

### Vergelijkingstool

De ingebouwde vergelijkingstool (`compare_erp.py`) valideert de pipeline-output tegen SpaceClaim-referentiedata:

```bash
python manufacturing_pipeline/scripts/compare_erp.py data/parts/ --aag -v
```

Output met kleurcodering:
- **Groen:** afwijking ≤ 1%
- **Oranje:** afwijking 1–10%
- **Rood:** afwijking > 10%

De tool matcht onderdelen primair op **volume** (betrouwbaarste — blijft gelijk ongeacht ontvouwen).

---

## Bekende beperkingen

### vs. SpaceClaim

| Gebied | Beperking | Impact |
|--------|-----------|--------|
| Vlakke afmetingen | Kunnen afwijken door K-factor verschil | Laag — volume is leidend |
| Boorgaten | Niet onderscheiden van lasersnijgaten | Kolom "Boorgaten" altijd 0 |
| Netto oppervlakte | Gatoppervlakten niet afgetrokken | OppervNetto = OppervBruto |
| Zetgroepering | Benadering van SpaceClaim-logica | Kan 1-2 zettingen verschil geven |
| Snijlengte | Alleen beschikbaar in AAG-modus | 0 in standaardmodus |
| Gewicht materiaal | Vast (staal of aluminium) | Geen materiaalherkenning uit STEP |

### Algemeen

| Gebied | Beperking | Workaround |
|--------|-----------|-----------|
| Ontvouwen falen | Complexe geometrie, variabele dikte | Fallback naar 3D bounding box + theoretische berekening |
| Profiel-detectie | Heuristiek (aspect ratio + standaardmaten) | Kan niet-standaard profielen missen |
| Multi-solid matching | Volume-gebaseerd (5% tolerantie) | Bij veel gelijkvormige delen kan mismatch optreden |
| FreeCAD-afhankelijkheid | Vereist FreeCAD installatie voor ontvouwen | `--no-unfold` als FreeCAD niet beschikbaar |

### Roadmap verbeteringen

- Materiaalherkenning uit STEP-metadata
- Variabele K-factor per materiaal/dikte
- Boorgat vs. lasersnijgat onderscheid
- Netto oppervlakteberekening (minus gaten)
- Verbeterde zetgroepering op basis van machine-learning
