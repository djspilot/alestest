# Stappenplan StepFile

## Doel
- Een alternatieve manufacturing pipeline bouwen binnen dezelfde repository.
- De bestaande STEP-inleesroute via het HTML-scherm behouden.
- De classificatie eerst expliciet en controleerbaar maken, en pas daarna per classificatie de verdieping in.
- Bestaande code uit `alestest` maximaal hergebruiken zonder de huidige pipeline direct te vervangen.

## Advies voor repository-structuur
- Blijf in dezelfde repository werken.
- Maak hiervoor een aparte feature-branch, bijvoorbeeld `feature/stappenplan-stepfile`.
- Gebruik de bestaande modules als bouwstenen, maar zet de nieuwe flow naast de huidige pipeline in plaats van erin.
- Houd de huidige `manufacturing_pipeline/analysis/assembly_analysis.py` voorlopig stabiel als productiepad.
- Bouw de nieuwe route modulair op zodat later pas besloten hoeft te worden of die de huidige pipeline vervangt.

## Advies voor de eerste push
- Push nu alleen de ontwerp- en specificatiedocumenten:
  - `classification_step_review.md`
  - `CLASSIFICATION_THRESHOLDS_MATRIX.md`
  - `STAPPENPLAN_STEPFILE.md`
- Laat de eerste commit documentatiegedreven zijn.
- Bouw `classification.py` pas in een volgende commit, zodat ontwerp en implementatie gescheiden reviewbaar blijven.

## Waarom een aparte branch
- Op `main` staan al andere wijzigingen en gegenereerde XML-bestanden.
- Deze nieuwe flow is een architectuurverandering, geen kleine bugfix.
- Je wilt bestaande code hergebruiken, maar nog niet vastleggen dat de oude pipeline direct vervangen wordt.

## Hoofdlijn van de nieuwe flow

### Stap 1 - STEP inlezen
- Behoud de huidige HTML-ingang.
- Hergebruik de bestaande upload/inleesroute.
- Huidige ingang zit in `api/static/index.html`.

### Stap 2 - Classificatie
- Zet `classification_step_review.md` om naar code in een nieuwe module: `classification.py`.
- Deze module wordt de expliciete beslislaag voor:
  - profiel,
  - vlakke plaat,
  - gezette plaat,
  - anders.
- `classification.py` is op dit moment nog geen bestaande bestandsnaam in de repo, dus die naam is vrij.

### Stap 3 - Classificatiescherm
- Bouw later een scherm waarin zichtbaar zijn:
  - de 4 classificaties,
  - aantallen,
  - artikelnummer,
  - visualisatie,
  - handmatige wijziging van classificatie per artikel.
- Deze stap hoort functioneel bij de nieuwe flow, maar hoeft nog niet in de eerste implementatie te zitten.

### Stap 4 - Verdieping per classificatie
- Pas na classificatie volgt de verdiepende geometrie-analyse.
- Advies: geef iedere analyse een eigen module, zodat verantwoordelijkheden scherp blijven.

#### 4.1 Profielen
- `profile_dimensions.py`
  - afmetingen,
  - lengte,
  - doorsnede,
  - eventuele zaagsnedes of scheve uiteindes.
- `profile_features.py`
  - gaten,
  - tapgaten,
  - verzonken gaten,
  - sleufgaten,
  - overige profiel-features.

#### 4.2 Vlakke platen
- `flat_plate_geometry.py`
  - afmetingen,
  - oppervlaktes,
  - contour,
  - gewicht.
- `flat_plate_features.py`
  - gaten,
  - tapgaten,
  - verzonken gaten,
  - sleufgaten.

#### 4.3 Gezette platen
- `bent_plate_geometry.py`
  - uitslagmaten,
  - oppervlaktes,
  - buiglijnen,
  - radii,
  - hoeken.
- `bent_plate_features.py`
  - gaten,
  - tapgaten,
  - verzonken gaten,
  - sleufgaten.

#### 4.4 Anders
- Geen aparte activiteiten in deze codeflow.
- Alleen doorzetten naar overzicht of XML als restcategorie.

### Stap 5 - PDF/XML inlezen
- Nieuwe stap om externe PDF/XML-resultaten in te lezen.
- Adviesmodule: `pdf_xml_ingest.py`.

### Stap 6 - XML-output en afgeleide bestanden
- `xml_builder.py`
  - XML opbouwen volgens voorbeeld-XML.
- `dxf_export.py`
  - voor alle plaatartikelen een DXF genereren,
  - wegschrijven naar dezelfde locatie als de bron-STEP.
- `xml_merge_results.py`
  - PDF/XML-resultaten verwerken in de uiteindelijke XML.

## Aanbevolen moduleplaats
- Plaats deze alternatieve flow niet los verspreid tussen de bestaande analysis-files.
- Advies: maak er een eigen package van, bijvoorbeeld:

```text
manufacturing_pipeline/
  stepfile/
    classification.py
    profile_dimensions.py
    profile_features.py
    flat_plate_geometry.py
    flat_plate_features.py
    bent_plate_geometry.py
    bent_plate_features.py
    pdf_xml_ingest.py
    xml_builder.py
    dxf_export.py
    xml_merge_results.py
```

## Integratieregel
- De bestaande pipeline blijft voorlopig de standaardroute.
- De nieuwe StepFile-flow wordt eerst parallel opgebouwd en gevalideerd.
- Pas na validatie beslis je of onderdelen uit de oude pipeline worden vervangen.

## Voorgestelde implementatievolgorde
1. Documenten pushen in aparte branch.
2. `classification.py` bouwen op basis van `classification_step_review.md`.
3. Resultaatmodel maken voor de 4 classificaties + aantallen + artikelnummers.
4. Verdiepingsmodules per classificatie bouwen.
5. XML/DXF-kant koppelen.
6. Pas daarna het scherm voor handmatige correctie toevoegen.

## Praktisch branch-advies
1. Maak branch `feature/stappenplan-stepfile` vanaf de huidige stabiele basis.
2. Commit 1: documentatie.
3. Commit 2: `classification.py` + unit tests.
4. Commit 3+: per classificatie een eigen analysemodule.
5. Merge pas naar `main` wanneer de nieuwe flow naast de bestaande pipeline aantoonbaar werkt.

## Besluit
- Ja, dit hoort overzichtelijker in dezelfde repo, maar wel op een aparte branch.
- Niet een nieuwe repository maken.
- Niet direct in `main` ontwikkelen.
- Eerst documentatie en architectuur vastleggen, daarna pas code.