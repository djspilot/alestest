# Unfold Review (Current Pipeline)

Dit document vat de huidige unfold-logica samen, met exacte criteria en thresholds zoals nu in code gebruikt.

## 1) Actieve route in run_analysis

run_unfold_to_step (core/utils.py) is een dunne wrapper om unfold_sheet_metal (analysis/freecad_unfold.py) heen.
Er is één implementatie. De wrapper map alleen veldnamen naar het formaat dat run_analysis verwacht.

## 2) Criteria en thresholds in run_unfold_to_step

### Selectie van solids en base faces
- Solids worden gesorteerd op volume (grootste eerst).
- Alleen top 3 solids worden geprobeerd.
- Voor elk solid worden alle vlakke faces (Plane) verzameld.
- Alleen top 10 grootste vlakke faces worden geprobeerd als base face.

### K-factor
- Vaste k-factor lookup: alle plaatdiktes mappen naar 0.44.
- Gebruikte dikte buckets: 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0.

### Unfold score (beste resultaat)
- Score = (aantal fold lines * 1000000) + vlakke oppervlakte.
- Fold lines wegen dus extreem zwaar t.o.v. oppervlakte.

### Dikte-detectie
- Zoekt vlakke faces, pakt grootste als referentie.
- Zoekt tegenoverliggende face met normal dot < -0.9.
- Dikte = afstand tussen die faces (eerste valide match in top 10 kandidaten).

### Resultaatvelden
- fold_lines: aantal fold lines.
- fold_details: per fold lijn lengte en centrum.
- bends_logical: uit SheetTree nodes (bend_dir, bend_angle, innerRadius).
- flat_length, flat_width: uit bbox van flat_compound.

### Timeout
- Subprocess timeout staat op 180 seconden.

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
- _merge_adjacent_bends(...) merge alleen als exact gelijk:
  - angle gelijk
  - radius gelijk
- Er is geen tolerantie (geen fuzzy merge).

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

Voor de huidige pipeline is run_unfold_to_step in core/utils.py leidend. Diagnose van "Unfold failed" in de viewer moet daarom eerst op die route gebeuren (solids top3, faces top10, timeout 180s, SheetTree/Bend_analysis/unfold_tree2 stages).
