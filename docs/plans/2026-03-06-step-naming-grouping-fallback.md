# STEP Naming/Grouping Fallback Plan

## Doel
Naamgeving en groepering van solids in `analyze_assembly()` robuust maken voor verschillende STEP-exporters, met prioriteit op:
- `10001091875_Rev_00.step` (shape-rep gestuurd)
- `10040878_1.stp` (assembly/NAUO gestuurd)

## Probleem
De huidige grouping gebruikt alleen `parse_step_shape_rep_name_counts()` voor sequentiele naamtoewijzing. Als die parser niets retourneert, vallen alle solids terug op generieke namen (`Part_n`), ook wanneer `parse_step_assembly_structure()` wel bruikbare part-counts heeft.

## Aanpak
1. Bepaal een naambron in vaste prioriteitsvolgorde:
   - `shape_rep_counts` (primair)
   - `step_parts_count` uit NAUO parser (fallback)
   - generieke `Part_n` (laatste fallback)
2. Bouw de `solid_names` sequentie op basis van de gekozen bron en trunc op `len(solids)`.
3. Vul eventuele rest aan met `Part_n`.
4. Houd de rest van classificatielogica ongewijzigd (geen threshold tuning in deze wijziging).
5. Registreer een regression-check script voor de twee target files.

## Acceptatiecriteria
1. `10001091875_Rev_00.step` blijft expliciete STEP-namen tonen in BOM (geen regressie).
2. `10040878_1.stp` gebruikt expliciete namen vanuit assembly fallback en heeft duidelijk minder/geen generieke `Part_n` in BOM.
3. Voor bestanden zonder bruikbare naambronnen blijft gedrag veilig: generieke fallback zonder crash.

## Validatie
- Draai een gerichte naming-check over de twee target files.
- Draai een korte scan over huidige output STEP/STP files om te bevestigen dat fallback robuust werkt op gemengde schema's.

## Out of Scope
- Aanpassen van classificatiedrempels (`plaat/profiel/anders`).
- Grote refactor van XML-export naming pipeline.
