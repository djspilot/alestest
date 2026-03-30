# Core vs Analysis Boundary Plan

## Doel

Deze notitie legt vast hoe `manufacturing_pipeline/core` en `manufacturing_pipeline/analysis` van elkaar gescheiden moeten blijven tijdens verdere refactors.

De korte conclusie:

- verplaats `analysis/` niet grootschalig naar `core/`
- maak `core/` dunner als runtime- en orchestratie-laag
- consolideer verdere domeinlogica binnen `analysis/`

## Huidige observatie

De codebase laat nu dit patroon zien:

- `core/` bevat:
  - runtime orchestration
  - config
  - paths
  - dependency checks
  - cache
  - CLI/API-facing analyseflow
- `analysis/` bevat:
  - geometrie- en topologie-analyse
  - classificatie
  - gatdetectie
  - profielherkenning
  - BOM/assembly logica
  - plaatwerk/unfold domeinlogica

De grootste overlap zit niet in de mappenstructuur zelf, maar in:

- `core/runtime_analysis.py`
- `analysis/step_processing.py`
- unfold code verspreid over `core/` en `analysis/`

## Richtlijn

Gebruik deze simpele scheiding:

### `core/` is voor:

- runtime setup
- environment detection
- subprocess execution
- dependency bootstrap
- file/path/config management
- pipeline orchestration
- cache/job lifecycle
- API/CLI integration helpers

### `analysis/` is voor:

- geometry logic
- classification rules
- thresholds
- topology interpretation
- feature detection
- sheet metal interpretation
- assembly/BOM interpretation
- domain result shaping

### `reporting/` is voor:

- XML
- Excel
- PDF
- viewer/timeline output shaping waar nodig

## Wat niet doen

- `analysis/` onder `core/` hangen als algemene cleanup
- domeinregels in `core/` blijven toevoegen
- nieuwe business logic in compat wrappers stoppen
- runtime concerns in `analysis/` stoppen als ze alleen infrastructuur zijn

## Concreet oordeel per probleemgebied

### 1. `core/runtime_analysis.py`

Status:

- bevat legitieme runtime orchestration
- bevat ook te veel domeinbeslissingen

Voorbeelden van domeinvervuiling:

- classificatie-threshold evaluatie
- analyse-criteria samenbouw
- inhoudelijke beslissingen rond onderdeeltype

Richting:

- orchestration in `core/` houden
- domeinbeslislogica verplaatsen naar `analysis/`

### 2. `analysis/step_processing.py`

Status:

- nog steeds een brede façade
- deels wrapper, deels echte analyse-orchestratie

Richting:

- behouden als compat module
- echte implementaties verder verplaatsen naar:
  - `analysis/io/`
  - `analysis/features/`
  - `analysis/sheetmetal/`

### 3. Unfold / FreeCAD grens

Status:

- runtime provisioning zit in `core/`
- unfold interpretatie zit in `analysis/`
- de grens is beter dan eerder, maar nog niet helemaal scherp

Juiste splitsing:

- `core/`
  - runtime install
  - command discovery
  - subprocess execution
  - doctor/bootstrap
- `analysis/`
  - base-face keuze
  - bend interpretation
  - flat-pattern metrics
  - unfold result normalization

## Bestanden die waarschijnlijk in `core/` moeten blijven

- `core/config.py`
- `core/paths.py`
- `core/cache.py`
- `core/file_utils.py`
- `core/python_dependencies.py`
- `core/freecad_runtime.py`
- `core/runtime_unfold.py`
- `core/runtime_reporting.py`

Voorwaarde:

- houd ze infrastructuur-gericht
- voeg daar geen nieuwe classificatie- of geometrieheuristiek toe

## Bestanden die in `analysis/` moeten blijven

- `analysis/classification_core/*`
- `analysis/geometry/*`
- `analysis/features/*`
- `analysis/bom/*`
- `analysis/io/step_file_io.py`
- `analysis/profile_classifier.py`
- `analysis/profile_features.py`
- `analysis/part_analyzer.py`
- `analysis/freecad_unfold.py`

Voorwaarde:

- refactor naar interne submodules
- legacy top-level modules alleen als compat surface houden

## Bestanden die nu vooral grensproblemen tonen

1. `core/runtime_analysis.py`
2. `analysis/step_processing.py`
3. `analysis/freecad_unfold.py`
4. `core/runtime_unfold.py`
5. `core/unfold_integration.py`
6. `analysis/router.py`
7. `analysis/part_analyzer.py`

## Stapsgewijze aanpak

### Stap 1. Definieer de grens expliciet

Maak deze afspraak leidend:

- `core` mag `analysis` aanroepen
- `analysis` mag alleen `core` gebruiken voor infrastructuurachtige helpers
- `analysis` mag niet afhankelijk worden van `core/runtime_analysis.py`

Doel:

- één richting in hoofdafhankelijkheden

### Stap 2. Bevries `step_processing.py` als compat façade

Doen:

- geen nieuwe business logic meer in `step_processing.py`
- alleen delegatie naar `analysis/io`, `analysis/features`, `analysis/sheetmetal`

Klaar als:

- nieuwe code alleen nog in interne modules landt

### Stap 3. Trek domeincriteria uit `core/runtime_analysis.py`

Doen:

- verplaats classification review / threshold assembly helpers naar `analysis/`
- laat `core/runtime_analysis.py` alleen:
  - stages aanroepen
  - resultaten combineren
  - timeline/progress emitten

Goede kandidaat:

- nieuw intern analysis-module voor runtime-facing analysis decisions

### Stap 4. Normaliseer unfold-verantwoordelijkheden

Doen:

- laat `core/` alleen runtime/platform/install/process concerns houden
- laat `analysis/` alleen inhoudelijke unfold-interpretatie houden

Specifiek:

- behoud `core/freecad_runtime.py` in `core/`
- behoud `analysis/freecad_unfold.py` in `analysis/`
- verplaats alleen grenslogica als de verantwoordelijkheid verkeerd ligt

### Stap 5. Verminder analysis-interne duplicatie verder

Doen:

- blijf grote legacy modules opdelen in interne owners
- wrappers alleen voor compat

Prioriteit:

1. `classification_core/step0.py`
2. `profile_classifier.py`
3. `profile_features.py`
4. resterende orchestration in `step_processing.py`

### Stap 6. Maak dependency-rules controleerbaar

Voeg simpele architectuurregels toe in documentatie en tests:

- `core` mag `analysis` importeren
- `analysis` mag `core.paths`, `core.freecad_runtime`, `core.xcaf_reader` of vergelijkbare infra helpers importeren
- `analysis` mag niet `core.runtime_analysis` of CLI/API orchestration importeren
- wrappers mogen geen nieuwe domeinlogica bevatten

### Stap 7. Maak een kleine import-contract test

Doen:

- test dat verboden imports niet ontstaan
- test dat compat modules alleen bekende surfaces blijven exporteren

Doel:

- voorkomen dat `core` opnieuw dichtslibt met domeinlogica

## Praktische migratievolgorde

Gebruik deze volgorde:

1. `analysis/step_processing.py` verder uitdunnen
2. domeincriteria uit `core/runtime_analysis.py` verplaatsen
3. unfold grens opschonen tussen `core/` en `analysis/`
4. `profile_classifier.py` verder opsplitsen
5. `profile_features.py` verder opsplitsen
6. import-contract tests toevoegen

## Besliskader bij twijfel

Gebruik deze vraag:

> Gaat dit over runtime/infrastructuur of over geometrische/domeininterpretatie?

Als het antwoord runtime/infrastructuur is:

- naar `core/`

Als het antwoord geometrie/domeininterpretatie is:

- naar `analysis/`

## Einddoel

Gewenste situatie:

- `core/` orkestreert
- `analysis/` beslist en interpreteert
- `reporting/` presenteert

Dat is beter dan `analysis/` verplaatsen naar `core/`, omdat het de echte grens bewaakt in plaats van alleen bestanden te verhuizen.
