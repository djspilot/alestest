# Research Vragen - Manufacturing Pipeline Verbetering

## Inhoudsopgave
1. [Huidige Systeem Beschrijving](#huidige-systeem-beschrijving)
2. [Huidige Resultaten](#huidige-resultaten)
3. [Technische Onderzoeksvragen](#technische-onderzoeksvragen)
4. [Domein/Business Onderzoeksvragen](#domeinbusiness-onderzoeksvragen)
5. [Data Kwaliteit Vragen](#data-kwaliteit-vragen)
6. [Markt/Concurrentie Onderzoek](#marktconcurrentie-onderzoek)

---

## Huidige Systeem Beschrijving

### Overzicht
We hebben een **manufacturing analysis pipeline** gebouwd die STEP CAD-bestanden analyseert om automatisch productie-relevante features te detecteren. Het doel is om handmatige invoer in ERP-systemen te vervangen/valideren.

### Technologie Stack
- **FreeCAD** (Open source CAD kernel via Python API)
- **SheetMetal Workbench** (FreeCAD addon voor unfold operaties)
- **Python 3.10+**
- **Part module** (OpenCascade geometrie kernel)

### Analyse Methodes

#### 1. Gaten Detectie (Holes)
We gebruiken een **unfold-first strategie**:

```
1. Probeer het onderdeel te "unfolden" (ontbuigen naar vlakke uitslag)
2. Als unfold slaagt:
   - Tel inner wires op alle planar faces van de flat pattern
   - Deel door 2 (top + bottom face hebben beide dezelfde holes)
3. Als unfold faalt:
   - Tel inner wires op de 3D shape
   - Deel door 2
```

**Inner wire methode**: Een "inner wire" is een gesloten contour binnen een planar face die een opening/gat representeert.

#### 2. Zettingen Detectie (Bends)
```
1. Als unfold slaagt:
   - Aantal bends = aantal "fold lines" uit unfold resultaat
2. Als unfold faalt:
   - Detecteer cylindrische faces met:
     - Radius tussen 0.3-15mm (typische buigradius)
     - Hoogte > 15mm (lengte van de buiging)
   - Deel door 2 (binnen + buiten radius)
```

#### 3. Geometrie Extractie
Direct uit de 3D shape:
- **Volume** (mm³)
- **Top Area** (grootste planar face)
- **Total Contour** (som van wire lengths)
- **Weight** (volume × dichtheid aluminium 2.7 g/cm³)
- **Bounding Box** (lengte × breedte × dikte)

#### 4. Multi-Solid Handling
Voor assemblies met meerdere solids:
- Gebruik **grootste solid** (by volume) voor unfold
- Tel holes op **alle solids** samen

#### 5. XML Parsing (Spaceclaim referentie)
- Spaceclaim XML kan meerdere entries per onderdeel bevatten
- We kiezen de entry met de meeste features (holes + bends×10)

### Code Structuur
```
compare_erp.py          # Hoofd vergelijkingstool
├── parse_excel()       # ERP data uit Excel
├── parse_xml()         # Spaceclaim data uit XML
├── analyze_step_file() # Pipeline analyse via FreeCAD subprocess
│   ├── count_holes_on_shape()    # Inner wire counting
│   ├── analyze_3d_shape()        # Face type analyse
│   └── SheetMetalUnfolder        # Unfold operatie
└── compare_results()   # Vergelijking en rapportage
```

---

## Huidige Resultaten

### Vergelijking met Spaceclaim (n=14 onderdelen)
| Metriek | Score |
|---------|-------|
| Gaten - Exact match | **86%** (12/14) |
| Gaten - Binnen ±2 | **86%** (12/14) |
| Bends - Exact match | **64%** (9/14) |

### Vergelijking met ERP (n=17 onderdelen)
| Metriek | Score |
|---------|-------|
| Gaten - Match | **65%** (11/17) |
| Zettingen - Match | **71%** (12/17) |

### Bekende Problemen
| Onderdeel | Probleem | Mogelijke oorzaak |
|-----------|----------|-------------------|
| MD-16-03698_R2 | SC=24, Pipe=68 | Unfold faalt, 3D count te hoog |
| MD-16-03699_R2 | SC=4, Pipe=8 | Overcounting na unfold |
| IFFS-17051 | ERP=1, Pipe=0 | Geen detecteerbare hole in CAD |
| MD-16-03672_2 | ERP=24, Pipe=22 | 2 holes gemist |

---

## Technische Onderzoeksvragen

### A. Unfold Proces

1. **Waarom faalt unfold bij bepaalde onderdelen?**
   - Welke geometrie-eigenschappen veroorzaken failure?
   - Error codes die we zien: 3 (ongeldige dikte), 11 (dubbele buigingen)
   - Is er een patroon in de onderdelen die falen?

2. **Kunnen we unfold failure voorspellen?**
   - Welke checks kunnen we vooraf doen?
   - Is er een "unfoldability score" mogelijk?

3. **Zijn er alternatieve unfold methodes?**
   - Andere libraries (OpenCascade direct, andere CAD tools)?
   - Kan een theoretische unfold berekening helpen?

4. **K-factor optimalisatie**
   - We gebruiken nu vaste K=0.44
   - Zou materiaal-specifieke K-factor helpen?
   - Hoe bepaalt Spaceclaim de K-factor?

### B. Hole Detection

5. **Wat missen we bij hole detection?**
   - Waarom detecteren we soms 2-4 holes te weinig?
   - Zijn er holes die geen "inner wire" genereren?
   - Hoe zit het met countersinks/counterbores?

6. **Wat tellen we teveel?**
   - Wanneer tellen we fillet radii als holes?
   - Hoe onderscheiden we decoratieve openingen van functionele holes?

7. **Slot/langwerpige opening detectie**
   - Telt een slot als 1 hole of meerdere?
   - Hoe detecteren we slots vs ronde gaten?

8. **Hole grootte filtering**
   - Minimum diameter voor een "echt" gat?
   - Maximum diameter (wanneer is het een opening ipv gat)?

### C. Bend Detection

9. **Waarom is bend detectie minder accuraat (64%)?**
   - Missen we buigingen of tellen we teveel?
   - Zijn er buigtypes die we niet herkennen?

10. **Hemming/flattening detectie**
    - Worden dubbelgevouwen randen correct geteld?
    - Hoe gaat Spaceclaim hiermee om?

11. **Complexe buigvormen**
    - Conische buigingen
    - Buigingen met variabele radius
    - Z-bends (2 buigingen dicht bij elkaar)

### D. Geometrie Berekeningen

12. **Waarom wijkt geometry af bij gebogen onderdelen?**
    - Volume/Area/Contour wijkt sterk af (37-46%)
    - Moeten we deze op de flat pattern berekenen ipv 3D?

13. **Welke geometry data is productie-relevant?**
    - Flat pattern afmetingen voor nesting
    - Snijlengte voor laser calculatie
    - Buiglengte voor zetbank tijd

### E. CAD Kwaliteit

14. **Hoe beïnvloedt CAD kwaliteit de analyse?**
    - Slechte tessellation
    - Niet-gesloten solids
    - Duplicate faces
    - Import artefacten

15. **Kunnen we CAD kwaliteit detecteren/rapporteren?**
    - Healing/repair operaties
    - Kwaliteitsscore

---

## Domein/Business Onderzoeksvragen

### F. ERP Data & Workflow

16. **Hoe wordt ERP data momenteel ingevoerd?**
    - Handmatig door werkvoorbereiders?
    - (Deels) automatisch uit CAD?
    - Uit offertes/klant specificaties?

17. **Waarom staat ERP soms op 0 bij onderdelen met features?**
    - Incomplete invoer?
    - Andere definitie van "gat"?
    - Legacy data?

18. **Wat is de huidige workflow?**
    ```
    Klant STEP → ??? → ERP data → Productie
    ```
    - Waar zit Spaceclaim in dit proces?
    - Wie doet de analyse nu?
    - Hoeveel tijd kost dit per onderdeel?

19. **Wat zijn de kosten van fouten?**
    - Verkeerd aantal gaten → verkeerde calculatie → verlies?
    - Hoe vaak komen fouten voor?
    - Wat is de impact per fout type?

### G. Definitie van Features

20. **Wat is de exacte definitie van een "gat" voor ERP?**
    - Alleen ronde geboorde gaten?
    - Alle laser-gesneden openingen?
    - Uitsparingen/uitzettingen?

21. **Hoe worden speciale features geteld?**
    - Langloch/slot: 1 of meer gaten?
    - Countersink: 1 of 2 gaten?
    - Vierkante opening: 1 gat?
    - Grote uitsnede (>100mm): gat of niet?

22. **Wat is een "zetting" in productie-context?**
    - Elke buiging = 1 zetting?
    - Hemming = 1 of 2 zettingen?
    - Radius buiging vs scherpe buiging?

23. **Welke tolerantie is acceptabel?**
    - ±1 gat? ±5%? ±10%?
    - Is 86% accuracy voldoende voor productie?
    - Wat is Spaceclaim's accuracy vs handmatige telling?

### H. Onderdeel Types

24. **Wat is de verdeling van onderdeel types?**
    - % vlakke platen (geen bends)
    - % enkelvoudig gebogen
    - % complex gebogen
    - % assemblies

25. **Welke materialen/diktes zijn gangbaar?**
    - Staal: welke diktes?
    - Aluminium: welke diktes?
    - RVS: welke diktes?
    - Invloed op unfold parameters?

26. **Zijn er onderdeel-categorieën met specifieke regels?**
    - Behuizingen
    - Frames
    - Beugels
    - Panelen

---

## Data Kwaliteit Vragen

### I. Referentie Data

27. **Hoe betrouwbaar is Spaceclaim als ground truth?**
    - Wat is Spaceclaim's eigen accuracy?
    - Zijn er bekende Spaceclaim bugs/beperkingen?
    - Waarom meerdere XML entries per onderdeel?

28. **Hoe betrouwbaar is ERP als ground truth?**
    - Wie voert ERP in en hoe?
    - Wordt ERP gevalideerd/gecorrigeerd?
    - Historische data vs recente data?

29. **Kunnen we een "golden dataset" maken?**
    - Handmatig gevalideerde onderdelen
    - Verschillende complexiteitsniveaus
    - Bekende edge cases

### J. Test Coverage

30. **Hoe representatief is onze test set (37 onderdelen)?**
    - Verdeling over complexiteit
    - Verdeling over materiaal/dikte
    - Verdeling over klanten/sectoren

31. **Welke edge cases missen we?**
    - Zeer kleine onderdelen
    - Zeer grote onderdelen
    - Extreem dunne plaat
    - Extreem dikke plaat

---

## Markt/Concurrentie Onderzoek

### K. Bestaande Oplossingen

32. **Wat doet Spaceclaim/AutoPOL precies?**
    - Welke algoritmes gebruiken zij?
    - Wat zijn hun beperkingen?
    - Licentiekosten?

33. **Welke andere tools bestaan er?**
    - SolidWorks Costing
    - Lantek
    - SigmaNest
    - Andere sheet metal analysis tools

34. **Wat is de state-of-the-art?**
    - Academische papers over CAD feature detection
    - Machine learning approaches
    - Industry best practices

### L. Unieke Waarde

35. **Wat maakt onze oplossing anders/beter?**
    - Open source vs proprietary
    - Integratie mogelijkheden
    - Kosten
    - Specifieke features

36. **Wat zijn de must-have features voor klanten?**
    - Accuracy niveau
    - Snelheid
    - Integratie met bestaande systemen
    - Rapportage formaat

---

## Prioritering Suggestie

### Hoge Prioriteit (Quick Wins)
- Vraag 20-22: Definitie van features (voorkomt verkeerde vergelijkingen)
- Vraag 17: Waarom ERP=0 (data kwaliteit)
- Vraag 23: Acceptabele tolerantie (bepaalt of 86% goed genoeg is)

### Medium Prioriteit (Verbeteringen)
- Vraag 1-3: Unfold failures begrijpen
- Vraag 5-6: Hole detection verfijnen
- Vraag 9-11: Bend detection verbeteren

### Lage Prioriteit (Nice to Have)
- Vraag 32-34: Concurrentie analyse
- Vraag 12-13: Geometry optimalisatie
- Vraag 14-15: CAD kwaliteit detectie

---

## Volgende Stappen

1. **Interview met werkvoorbereiders**: Vragen 16-22, 24-26
2. **Data analyse**: Vragen 27-31 met grotere dataset
3. **Technische deep-dive**: Vragen 1-15 op gefaalde onderdelen
4. **Market research**: Vragen 32-36

---

*Document gegenereerd: 2026-01-03*
*Pipeline versie: compare_erp.py met unfold-first strategie*
