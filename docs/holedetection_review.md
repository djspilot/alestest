# Hole Detection Review (baseline na rollback)

## Doel
Dit document beschrijft de actuele en gevalideerde hole-detection werkwijze in de manufacturing pipeline,
na rollback van de regressie-commit voor hole-metrics.

Scope:
- `manufacturing_pipeline/analysis/step_processing.py`
- `manufacturing_pipeline/analysis/cut_features.py`
- `manufacturing_pipeline/analysis/iso_standards.py`
- `manufacturing_pipeline/analysis/features/cut_features_extractors.py`
- `manufacturing_pipeline/analysis/features/cut_features_geometry_helpers.py`

## Korte status
- ISO threadtabellen zijn actief (M3 t/m M24).
- Thread- en countersink-classificatie gebeurt in `cut_features`.
- Voor plaatdelen is de primaire telling/snijlengte gebaseerd op gesloten binnencontouren.
- De regressie waarbij `threaded_holes=0` ontstond via een alternatieve validatieroute is teruggedraaid.

## Definitie van "waarheid" in deze baseline
Voor productie-uitvoer gelden in deze baseline:
- `nr_holes`: aantal gaten op basis van gesloten binnencontouren wanneer beschikbaar.
- `hole_contours`: snijlengte per gat op basis van geometrisch gemeten perimeter.
- `threaded_holes`: bepaald via ISO-diametermatching op cilindrische gaten en contour-labeling.
- `countersunk_holes`: bepaald via cone-face matching met coaxiale fallback.

Belangrijk:
- Geometrische kandidaattypes in viewer/debug (`cylindrical`, `closed_contour`, `irregular_contour`) zijn niet hetzelfde als semantische productie-labels (`thread`, `countersunk`, `hole`).

## Detectievolgorde
1. Detecteer cilindrische gaten (`detect_holes`).
2. Detecteer gevormde gaten/contouren (`detect_shaped_holes`).
3. Dedupliceer overlap tussen rond en gevormd (`deduplicate_holes`).
4. Detecteer gesloten binnencontouren (`_detect_closed_inner_contours`).
5. Label contouren met thread/countersink info (`_label_contours_from_holes`).
6. Bereken productievelden (`nr_holes`, `hole_contours`, `threaded_holes`, `countersunk_holes`).

## Feature 1: cilindrische gaten
Actieve ingang:
- `detect_holes(cq_object, filter_bores=True, is_flat_pattern=False, is_turned=None, face_data=None)`

Kerncriteria:
- Interne cylinderfaces.
- Split-face groepering op as/diameter/positie-consistentie.
- Hoekdekking per groep moet boven drempel liggen.
- Optioneel bore-filter voor turned parts.

Uitkomst:
- Geometrische ronde gatkandidaten met diameter, positie, depth en debugcriteria.

## Feature 2: shaped holes
Actieve ingang:
- `detect_shaped_holes(shape, face_data=None)`

Kerncriteria:
- Planar faces, inner wires als kandidaten.
- Uitsluiting van pure cirkelwires.
- Classificatie in slot/rect/poly/irregular op edgepatroon.

Uitkomst:
- Geometrische vormgatkandidaten met perimeter en contourinformatie.

## Feature 3: gesloten binnencontouren
Actieve ingang:
- `_detect_closed_inner_contours(shape)`

Kerncriteria:
- Alleen gesloten inner wires tellen mee als contourgat.
- Perimeter komt uit geometrische meting (`LinearProperties/Mass`).
- Duplicaatreductie op dimensie/perimeter/centrum.

Uitkomst:
- Robuuste snijlengte per gat en basis voor `nr_holes`.

## Feature 4: thread-detectie (ISO)
Actieve bron:
- `manufacturing_pipeline/analysis/iso_standards.py`

Kernpunten:
- Tabelgestuurde matching op major/tapped diameters.
- Plaat-specifieke disambiguatie voorkomt foutieve threadlabels.
- Labeling wordt toegepast in `cut_features_extractors` en contour-labeling helpers.

## Feature 5: countersink-detectie
Kernpunten:
- Primair: cone-face detectie.
- Fallback: coaxiale cilindrische paren (voor STEP-exporten zonder expliciete cone surface).

## Niet-gesloten contouren: verplichte opmerking in procedure
In deze baseline geldt expliciet:
- Niet-gesloten contouren worden niet als gat geteld in `nr_holes`.
- Niet-gesloten contouren leveren geen gat-snijlengte in `hole_contours`.
- Als zulke contourfragmenten worden gezien in de detectiestap, moeten ze als opmerking/debug-reden worden vastgelegd als:
  - `open_contour_candidate_not_counted`
  - met reden: `contour is niet gesloten, daarom niet meegeteld als gat`.

Procedure-afspraak:
- Open contour = signaal voor kwaliteitscontrole/modelreview, geen productie-gat.
- Alleen gesloten contouren of gevalideerde cilindrische gaten tellen mee in productiecijfers.

## Verwachte validatie op referentiebestand 336027
Verwachte baseline-uitkomst:
- `nr_holes = 14`
- `threaded_holes = 4`
- `countersunk_holes = 0`

Als een route hiervan afwijkt (bijv. `threaded_holes = 0`), dan is dat een regressie in de route of serialisatie,
niet automatisch een regressie in ISO-threadlogica zelf.

## Wijzigingsbeleid vanaf nu
Bij elke wijziging in hole-detection:
1. Test op minimaal 2 referentiebestanden (waaronder 336027).
2. Vergelijk expliciet:
   - `nr_holes`
   - `threaded_holes`
   - `countersunk_holes`
   - `sum(hole_contours)`
3. Documenteer impact op beslislogica in dit document.
4. Geen merge als thread/countersink-semantiek impliciet verandert zonder expliciete akkoord.
