# Handover: Unfold User Contour Recovery (Lines + Arcs)

## Doel
Deze wijziging voegt een robuuste fallback toe voor hole-detectie op unfold/flat geometry:
- gemengde gebruikerscontouren (lijn + boog combinaties) terugvinden
- als gesloten contour terugbrengen in de pipeline
- exact als contour tonen in de viewer

Dit document gebruikt de aanpak uit `docs/newfacesholes.md` en past die in op de bestaande productie-logica die inmiddels is vastgelegd in `docs/PIPELINE_STEP_02_SHEET_FEATURES.md`.

## Inpassing in bestaande architectuur
Bestaande leidende regel blijft geldig:
1. Gesloten binnencontouren zijn primair voor `nr_holes` en `hole_contours`.
2. Cylindrische detectie blijft primair voor labels (`thread`, `countersunk`).
3. Deduplicatie en wrapper-flow blijven actief.

Nieuwe toevoeging zit als fallback tussen shaped detectie en final merge:
- als een inner wire niet als slot/rect/poly wordt herkend, gaat hij naar een recovery bucket
- recovery bouwt uit edge-fragmenten opnieuw gesloten contouren via endpoint-hashing + wire walking
- recovered contouren worden als shaped hole kandidaat toegevoegd (type `Recovered contour`)

## Recovery-strategie
### 1) Recovery bucket
Input naar recovery bucket:
- inner wires die eerder als `unknown` werden afgewezen
- alleen contouren op planaire faces

Per kandidaat bewaren we:
- edges (topologie)
- center
- normal
- bbox-based dimensies
- perimeter

### 2) Vertex hashing
Voor elk edge-eindpunt maken we een hash-key op tolerantieraster.
Doel:
- snelle lookup van aangrenzende edges
- robuuste verbinding ondanks kleine numerieke afwijkingen

### 3) Wire walking
Loop door het endpoint-netwerk:
- start op ongebruikte edge
- volg door naar buren op aansluitende endpoint key
- sluit wanneer startpoint opnieuw bereikt wordt

Validatie van lus:
- minimaal 3 unieke edges
- gesloten (begin/eind binnen tolerantiewaarde)
- perimeter > minimale drempel

### 4) Fallback-classificatie
Recovered contouren krijgen type `Recovered contour` en familie `recovered_mixed`.
Deze vallen functioneel onder shaped-hole output (`hole` label in XML), tenzij later apart gemapt.

## Viewer-impact
Voor hole overlays voegen we ondersteuning toe voor exacte contourpunten:
- pipeline stuurt optioneel `contour_points` per hole-item
- viewer tekent dan die punten direct als line loop
- als `contour_points` ontbreekt, blijft bestaande heuristische shape-rendering actief

Voordeel:
- recovered contouren worden exact zichtbaar
- probe/select/focus workflow blijft onveranderd

## Compatibiliteit en risico
Compatibel met huidige regels:
- closed-contours-first principe blijft leidend
- thread/countersink regels blijven intact
- dedup gedrag blijft ongewijzigd voor bestaande typen

Risicobeperking:
- recovery werkt alleen op eerder afgewezen shaped-kandidaten
- perimeter en closure gates beperken false positives
- viewer gebruikt fallback op oude rendering als exacte contour ontbreekt

## Testfocus
Minimaal valideren op:
1. Unfold part met slot-achtige mixed contour (line+arc) die eerder werd afgewezen.
2. Klassieke ronde gaten (geen regressie op thread/countersink labels).
3. Viewer overlay: recovered contour zichtbaar, selecteerbaar, camera focus werkt.
4. XML velden: aantallen/snijlengtes blijven consistent met closed contour output.

## Implementatiestappen
1. `step_processing.detect_shaped_holes`:
- recovery bucket + wire walking fallback toevoegen
- recovered candidates inclusief perimeter/contourpunten toevoegen aan shaped output

2. `core/utils` hole visuals payload:
- `contour_points` doorgeven als aanwezig

3. viewer (`ViewerCanvas`):
- `HoleOutline` laten tekenen op exacte contour als `contour_points` aanwezig is

4. Geen wijziging aan de bestaande hoofdcriteria uit `docs/PIPELINE_STEP_02_SHEET_FEATURES.md`; alleen uitbreiding van fallbackpad.
