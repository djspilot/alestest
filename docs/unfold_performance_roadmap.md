# Unfold Performance Roadmap

## Doel

De unfold-keten sneller, voorspelbaarder en beter meetbaar maken zonder de functionele uitkomst te veranderen.

Focusgebieden:

- lagere latency per unfold-run
- minder cold-start overhead van FreeCAD
- minder mislukte base-face pogingen
- hergebruik van succesvolle resultaten
- betere operationele grenzen voor productie

## Huidige situatie

De huidige unfold-implementatie zit vooral in [manufacturing_pipeline/analysis/freecad_unfold.py](../manufacturing_pipeline/analysis/freecad_unfold.py) en probeert meerdere base faces per part, met FreeCAD-documenten, SheetMetalUnfolder en exportstappen binnen dezelfde run.

Dat betekent dat de grootste kosten waarschijnlijk zitten in:

- FreeCAD import en runtime-opstart
- documentaanmaak en cleanup per poging
- het opnieuw analyseren van base faces
- export van flat STEP en DXF
- herhaalde runs voor dezelfde input

## Succescriteria

We beschouwen de roadmap als geslaagd als:

- mediane unfold-tijd aantoonbaar daalt op een vaste benchmarkset
- P95-tijd daalt of stabiel blijft terwijl throughput stijgt
- cold-start tijd zichtbaar afneemt
- herhaalde unfold van hetzelfde bestand vrijwel direct uit cache kan komen
- failure rate door ongeschikte base-face keuzes afneemt

## Fase 0: Baseline en meting

Doel: eerst weten waar de tijd echt zit.

Werkitems:

- meet per run de totale unfold-tijd
- meet per fase:
  - STEP load
  - FreeCAD import / runtime-init
  - base-face selectie
  - SheetTree-opbouw
  - Bend_analysis
  - unfold_tree2
  - flat STEP export
  - DXF export
- log aantal attempts per job
- log gebruikte face-index en reden van falen per poging
- sla timings op per job voor vergelijking tussen builds

Deliverable:

- een vaste timing-output per unfold-run, bruikbaar in CLI en API

## Fase 1: Cold-start omlaag

Doel: minder tijd verliezen voordat de echte analyse begint.

Werkitems:

- FreeCAD en SheetMetalUnfolder vroeg pre-warmen bij service-start
- runtime-validatie één keer uitvoeren in plaats van per job
- importpad en environment lookup beperken tot startup
- waar mogelijk één langlevende worker hergebruiken

Prioriteit:

1. pre-warm imports
2. hergebruik runtime tussen jobs
3. alleen fallback-sporen gebruiken als primaire route faalt

## Fase 2: Hergebruik en caching

Doel: dezelfde input niet opnieuw volledig ontbuigen.

Werkitems:

- cache unfold-resultaten op basis van:
  - STEP file hash
  - relevante thresholds/config
  - unfolder/runtime-versie
- cache ook artefacten:
  - flat STEP
  - DXF
  - samenvattende metadata
- controleer cache vóór zware analyse
- hanteer retentiebeleid voor oude artefacten

Verwacht effect:

- herhaalde jobs voor hetzelfde bestand worden bijna direct afgehandeld

## Fase 3: Minder attempts per part

Doel: het aantal dure mislukte pogingen reduceren.

Werkitems:

- rangschik base-face kandidaten strenger op waarschijnlijkheid
- beperk standaard het aantal attempts
- geef voorkeur aan grote, vlakke, stabiele faces
- stop sneller als meerdere initiële pogingen dezelfde foutklasse geven
- markeer parts die structureel niet geschikt zijn voor unfold

Mogelijke heuristieken:

- grootste planare face eerst
- vergelijkbare normale vectoren clusteren
- kandidaatfilter op vlakheid, area en oriëntatie

## Fase 4: Export en I/O hot paths

Doel: onnodige file- en documentkosten verlagen.

Werkitems:

- export alleen uitvoeren als het resultaat succesvol is
- tijdelijke FreeCAD-documenten minimaliseren
- objectaanmaak en cleanup strakker organiseren
- flat pattern-dimensies berekenen zonder extra zware conversies waar mogelijk
- hergebruik bestaande outputbestanden wanneer validatie dat toestaat

## Fase 5: Operationele grenzen

Doel: voorkomen dat zware CAD-jobs de service onbruikbaar maken.

Werkitems:

- max concurrent unfold-jobs instellen
- timeout per job definiëren
- limieten voor opslag per job en per retention window
- duidelijke status voor queue, running, failed en cached
- alerts op herhaalde runtime-fouten of overmatige latency

## Aanbevolen volgorde

1. Fase 0: baseline en meting
2. Fase 1: cold-start omlaag
3. Fase 3: minder attempts per part
4. Fase 2: caching en artifact reuse
5. Fase 4: export- en I/O-optimalisatie
6. Fase 5: operationele grenzen en alerts

## Eerste implementatiestap

De beste eerste stap is het toevoegen van timing-instrumentatie rond `run_unfold_to_step(...)` en de interne unfold-fasen, zodat we per wijziging kunnen zien wat het effect is.