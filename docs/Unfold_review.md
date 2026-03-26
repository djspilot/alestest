# Unfold Review (Current Pipeline)

Dit document vat de huidige unfold-logica samen, met exacte criteria en thresholds zoals nu in code gebruikt.

## 1) Actieve route in run_analysis

run_unfold_to_step (core/utils.py) is een dunne wrapper om unfold_sheet_metal (analysis/freecad_unfold.py) heen.
Er is één implementatie. De wrapper map alleen veldnamen naar het formaat dat run_analysis verwacht.

## 2) Criteria en thresholds in run_unfold_to_step

### Selectie van solids en base faces
- run_unfold_to_step zelf doet geen solid/base-face selectie; het is een wrapper.
- De selectie gebeurt in unfold_sheet_metal:
  - Bij meerdere solids wordt 1 solid gekozen (`shape.Solids[0]`).
  - Base faces zijn alle vlakke faces, gesorteerd op oppervlakte.
  - Aantal pogingen is `min(max_attempts, len(base_candidates))` met standaard `max_attempts=5`.

### K-factor
- Vaste k-factor lookup: alle plaatdiktes mappen naar 0.44.
- Gebruikte dikte buckets: 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0.

### Unfold score (beste resultaat)
- Er wordt geen aparte scoreformule gebruikt in de actieve route.
- De eerste geslaagde unfold-poging wordt geaccepteerd en teruggegeven.

### Dikte-detectie
- In run_unfold_to_step wordt geen dikte uit unfold afgeleid.
- De wrapper retourneert `thickness = 0` (dikte uit analysepad blijft leidend).

### Resultaatvelden
- fold_lines: aantal fold lines.
- fold_details: per fold lijn lengte en centrum.
- bends_logical: uit SheetTree nodes (bend_dir, bend_angle, innerRadius).
- flat_length, flat_width: uit bbox van flat_compound.

### Timeout
- In de actieve route via `run_unfold_to_step` is er geen 180s subprocess-timeout.
- Als FreeCADCmd fallback wordt gebruikt, geldt in `freecad_unfold.py` een timeout van 300 seconden.

## 3) Criteria en thresholds in freecad_unfold.py (alternatieve route)

### Standaard parameters
- k_factor default: 0.44
- max_attempts default: 5
- max_bends default: None

### FreeCADCmd fallback
- _unfold_via_freecadcmd(...) gebruikt timeout van 300 seconden.

### Bend fallback op cilindrische faces
- Alleen cylinders met:
  - angle_rad > 0.3 (ongeveer > 17 graden)
  - length > 5 mm
- Deduplicatie op key: (round(angle_deg, 1), round(length, 1)).
- Bij dubbel: kleinste radius wint (inner radius).
- Optioneel limiteren op max_bends.

### Merge van gesplitste bends
- Primaire regel is nu geometrisch: segmenten worden samengevoegd als ze collineair zijn.
- Criteria voor 1 fysieke zetlijn:
  - zelfde segment-as (X of Y in vlak patroon)
  - zelfde lijn-offset op de loodrechte as binnen tolerantie (`offset_tol`, standaard 2.0 mm)
  - vergelijkbare zethoek (en radius) per segment
  - segmenten moeten in elkaars verlengde liggen (kleine gap), niet als overlappende/gestapelde lijnen
- Dit dekt expliciet onderbrekingen door gaten:
  - 2 segmenten in elkaars verlengde => 1 zetlijn
  - 3 segmenten in elkaars verlengde => 1 zetlijn
- Resultaat is een lijst `bend_line_groups` met per fysieke zetlijn o.a.:
  - `id`, `segment_count`, `segment_indices`, `pos_along_length`

### Routeverschillen (belangrijk)
- **Direct FreeCAD route**: heeft toegang tot `foldLines` geometrie en gebruikt collineaire merge.
- **FreeCADCmd subprocess route**: gebruikt hetzelfde `bend_angles/bend_radii` pad; als geen segmentgeometrie beschikbaar is, wordt niet agressief op sequence gemerged (om foutieve 5 -> 1 merges te voorkomen).

## 4) Error handling

UNFOLD_ERROR_MESSAGES vertaalt foutcodes uit SheetMetalUnfolder, o.a.:
- 1: volume onbruikbaar
- 3: ongeldige of inconsistente dikte
- 5: onnodige edges (refine shape nodig)
- 11/12: niet-ondersteunde bend-child structuur
- 17: niet-ondersteund oppervlaktype
- 21: section wire niet gesloten
- 26: niet-ondersteund curve type in unbendFace

## 5) Korte conclusie voor debugging

Voor de huidige pipeline is run_unfold_to_step in core/utils.py leidend. Diagnose van "Unfold failed" in de viewer moet daarom eerst op die route gebeuren (wrapper -> unfold_sheet_metal, met stages SheetTree/Bend_analysis/unfold_tree2 en error_details per poging).

Pipeline-prioriteit: viewer is alleen een visualisatie van pipeline-data; we passen geen viewer-specifieke correctie toe die afwijkt van manufacturing-pipeline output.
