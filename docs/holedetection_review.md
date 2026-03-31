# Hole Detection Review (actueel)

## Doel
Dit document beschrijft uitsluitend de huidige, actieve hole-detection criteria
en beslislogica in:
- `manufacturing_pipeline/analysis/step_processing.py`
- `manufacturing_pipeline/analysis/cut_features.py`
- `manufacturing_pipeline/analysis/iso_standards.py`
- `manufacturing_pipeline/reporting/xml_exporter.py`

Doel van dit document:
- per feature vastleggen welke thresholds actief zijn
- per feature samenvatten welke rekenmethode wordt gebruikt
- vastleggen hoe de uiteindelijke beslissing wordt genomen
- een stabiele basis maken voor gecontroleerde verbeteringen

## Begrippen
- `cylindrical hole`: intern cilindrisch vlak dat als gat wordt geïnterpreteerd.
- `shaped hole`: niet-cirkelvormig gat zoals sleuf, rechthoek of polygoon.
- `turned part`: as-symmetrisch onderdeel waarbij interne cylinders ook boring/freesbewerking kunnen zijn.
- `flat pattern`: ontvouwen plaatgeometrie.
- `countersink`: conisch verzonken gat, herkend via conische faces.
- `major match`: diameter-match op nominale buitendiameter van metrische draad.
- `tapped match`: diameter-match op interne draad / tapboordiameter-logica.

## Architectuuroverzicht
De actieve code is opgebouwd in drie lagen:

1. `step_processing.py`
   - gedeelde kern voor detectie van cilindrische gaten en vormgaten
2. `cut_features.py`
   - wrappers per classificatiegroep
   - vertaling van ruwe detecties naar `hole_types`, counts en contouren
3. `xml_exporter.py`
   - mapping van `CutFeatures` naar `Sheet_*` of `Tube_*` velden

Belangrijke architectuurnoot:
- de kern van de geometrische gatdetectie is gedeeld
- plaat en gezette plaat gebruiken dezelfde wrapper
- profiel gebruikt een aparte wrapper met andere post-filters en thread-logica

---

## Primaire strategie: gesloten contour als basis

**Aantal gaten en snijlengte worden bepaald op basis van gesloten binnencontouren.**

`_detect_closed_inner_contours(shape)` is de leidende methode voor:
- `nr_holes` (aantal gaten)
- `hole_contours` (snijlengte per gat, gemeten perimeterlengte uit geometrie)
- `total_contour` (totale snijlengte = sum(gatcontouren) + buitencontour)

Reden:
- werkt voor elke vorm: rond, sleuf, rechthoek, polygoon
- perimeter is direct gemeten uit geometrie (niet berekend via 2πr of formules)
- geen afhankelijkheid van vormclassificatie (slot/rect/poly)
- werkt op flat pattern (plaat) én op 3D solid (profiel, via vlakke faces)

De cylinder-detectie blijft nodig uitsluitend voor labels:
- tapgaten (`thread`): diameter-matching via ISO 68-1
- verzonken gaten (`countersunk`): conische face matching met fallback via coaxiale cilindrische paren

Volgorde in de wrappers (`cut_features.py`):
1. `_detect_closed_inner_contours` → aantal + snijlengte
2. `detect_holes` + thread/countersink logica → labels (thread/countersunk/round)
3. Als `closed_contours` niet leeg: overschrijf `hole_contours` en `nr_holes` met gesloten contour data

Profiel-noot (actief):
- in de profiel-wrapper worden `closed_contours` eerst gefilterd op profiel-uiteinde-openingen
- die gefilterde contouren tellen dus niet mee in `nr_holes` en `hole_contours`

---

## Feature-overzicht
0. Gesloten binnencontouren (primair: aantal + snijlengte)
1. Cilindrische gaten (voor labels: thread/countersunk/round)
2. Vormgaten (fallback als geen closed_contours)
3. Duplicaatfilter tussen rond en vormgat
4. Tapgat-herkenning
5. Verzonken gat-herkenning
6. Standalone conische gaten
7. Wrapper-specifieke verschillen: plaat versus profiel

Stopregel:
- er is geen enkele globale "eerste match stopt alles" regel zoals bij Step 0
- alle subdetectoren leveren kandidaten op
- de wrapper beslist daarna hoe deze kandidaten worden gelabeld en geteld
- **voor aantal en snijlengte geldt: `closed_contours` wint altijd als die niet leeg is**

---

## Feature 0 - Gesloten binnencontouren (`_detect_closed_inner_contours`)

Actieve functie:
- `_detect_closed_inner_contours(shape: TopoDS_Shape) -> List[Dict]`

### Doel
Vind alle unieke gesloten binnencontouren exclusief de buitencontour. Vormt de primaire basis voor `nr_holes` en `hole_contours` (snijlengte per gat).

### Werkwijze
- Itereer over alle faces in de shape
- Per face: neem `outer_wire = BRepTools.OuterWire_s(face)` als referentie buitencontour
- Alle overige wires op die face → binnencontour-kandidaten
- Per kandidaat: bereken perimeter via `BRepGProp.LinearProperties_s(wire)` → `.Mass()`
- Sla op: `{perimeter, center(x,y,z), normal(nx,ny,nz), dim("WxH")}`

### Deduplicatie
Binnencontouren worden gegroepeerd per `(round(perimeter, 2), dim)` bucket.
Een contour wordt als duplicaat gezien als:
- centrumafstand `dist_sq < 0.01`
- of het centrumverschil ligt vrijwel in de normaalrichting: `dot > 0.9`

### Koppeling met cylindrische gaten voor labels
Na `_detect_closed_inner_contours` wordt `_label_contours_from_holes()` aangeroepen:
- Per gesloten contour: zoek dichtstbijzijnde cilindrische gat op centrumafstand ≤ 10 mm
- Gebruik diameter van dat gat voor thread/countersink-matching
- Ongematchte contouren → label `hole`

### Werkt op
- **Flat pattern** (plaat/gezette plaat): alle gaten zijn inner wires op het vlakke patroon
- **3D solid** (profiel): gaten die een planaire wandface snijden

### Samenvatting
`nr_holes` en `hole_contours` worden uitsluitend van gesloten contouren afgeleid als `closed_contours` niet leeg is. Labels (thread/countersunk/round) volgen daarna via matching met cylindrische gaten.

Profiel-uitzondering (actief):
- vóór de telling worden profiel-uiteinde-openingen uit `closed_contours` verwijderd
- daarmee beïnvloeden koker/holprofiel-einden de gatentelling en snijlengte niet

---

## Feature 1 - Cilindrische gaten (`detect_holes`)

Actieve functie:
- `detect_holes(cq_object, filter_bores=True, is_flat_pattern=False, is_turned=None, face_data=None)`

### Doel
Vind interne cilindrische vlakken die een bruikbaar gat representeren.

### Broncriteria op face-niveau
Een face wordt alleen kandidaat als:
- surface type = `GeomAbs_Cylinder`
- bij normale 3D analyse: face orientation = `TopAbs_REVERSED`
- bij flat pattern analyse: orientation-check wordt losgelaten

### Extra filter voor flat patterns
- er is géén harde afkap meer op `diameter > 100 mm`
- grote gaten blijven toegestaan, maar krijgen extra artefact-filters:
   - dieptegate (alleen als thickness-proxy beschikbaar):

$$
depth \le max(20.0, 3.0 \cdot thickness\_ref)
$$

   - groepshoekgate voor grote diameter:
      - bij `diameter > 100 mm` geldt in flat-pattern `total_angle > 300°`

### Rekenmethode
Per cilindrische face wordt berekend:
- `diameter = 2 * radius`
- `angle_deg = degrees(abs(u_max - u_min))`
- `arc_length = radius * abs(u_max - u_min)`
- `depth = area / arc_length`

Deze `depth` is dus geen expliciete boorlengte uit topologie, maar een afgeleide maat:

$$
depth = \frac{A_{cilinder}}{r \cdot \Delta u}
$$

waarbij bij een volledige cilinder in de praktijk geldt:

$$
A \approx 2\pi r \cdot depth
$$

### Groepering van split faces
Kandidaten worden gegroepeerd als ze tegelijk voldoen aan:
- diameter verschil `<= 0.01 mm`
- as-richtingen parallel: `abs(abs(dot) - 1.0) <= 0.01`
- assen collineair: `dist_sq < 0.01`
- projectiecentrum langs as: `abs(t1 - t2) < 5.0 mm`

### Gat-validatie op groepsniveau
Een groep wordt alleen geaccepteerd als de som van face-hoeken groot genoeg is:
- flat pattern: `total_angle > 160°`
- normale 3D analyse: `total_angle > 270°`
- extra voor grote flat-pattern gaten (`diameter > 100 mm`): `total_angle > 300°`

### Bore-filter voor draaidelen
Alleen actief als:
- `filter_bores=True`
- `is_turned=True`
- bounding box beschikbaar

Dan geldt:
- `min_dim = kleinste bounding-box maat`
- als `max_depth > 0.5 * min_dim` -> kandidaat wordt als boring gezien en verworpen

### Samenvatting beslissing
Een cilindrisch gat wordt opgenomen als:
- het een interne cylinder is
- de split-face groep voldoende omtrekhoek heeft
- het niet door het boringfilter wordt weggegooid

---

## Feature 2 - Vormgaten (`detect_shaped_holes`)

Actieve functie:
- `detect_shaped_holes(shape, face_data=None)`

### Doel
Vind niet-cirkelvormige openingen op planaire faces.

### Broncriteria
Alleen planaire faces worden onderzocht:
- surface type = `GeomAbs_Plane`

Per face worden alle wires verzameld en gesorteerd op bounding-box diagonaal.

Actieve aanname:
- grootste wire = buitencontour
- alle overige wires = kandidaat-gaten

### Cirkel-uitsluiting
Een wire wordt niet als shaped hole behandeld als:
- het exact 1 cirkel-edge bevat
- of exact 2 cirkel-edges bevat die samen een cirkel vormen

### Vormclassificatie
Per inner wire wordt gekeken naar aantallen lijnen en cirkelbogen:

#### Slot
- `lines == 2`
- `circles == 2`

Afgeleide maten:
- `width = 2 * avg(radius)`
- `total_len = max(line_lengths) + 2 * avg(radius)`
- `dim = "{total_len}x{width}"`

#### Rect (R)
- `lines >= 4`
- `circles >= 4`

Dimensies uit wire bounding box:
- `dim = "max_dim x mid_dim"`

#### Rect / Poly
- `lines >= 3`
- `circles == 0`
- `Rect` als `lines == 4`
- anders `Poly`

### Deduplicatie tussen shaped holes onderling
Shaped holes worden samengevoegd per `(type, dim)` bucket.

Een tweede shaped hole wordt als duplicaat gezien als:
- centrumafstand `dist_sq < 0.01`
- of het centrumverschil vrijwel in de normal-richting ligt: `dot > 0.9`

### Samenvatting beslissing
Een vormgat wordt opgenomen als:
- het op een planair vlak als inner wire verschijnt
- het geen pure cirkel is
- de edge-samenstelling overeenkomt met Slot, Rect (R), Rect of Poly

### Methodevolgorde voor irregulaire contouren (primair + fallback)
Voor het pad "andere holes zijn al gedetecteerd, maar irregulair nog niet" geldt nu deze volgorde:
1. **Face Boundary (primair):** haal per planaire face eerst de wire-set op, behandel grootste wire als buitencontour en alle overige wires als hole-kandidaten.
2. **Shaped classificatie:** classificeer kandidaten als Slot/Rect (R)/Rect/Poly op basis van line/arc samenstelling.
3. **Recovery Bucket (fallback):** alleen kandidaten die niet in stap 2 landen, worden via endpoint hashing + wire walking opnieuw opgebouwd tot gesloten contour.

Rationale:
- Face Boundary volgt direct de topologische definitie van OpenCASCADE (outer wire + inner wires)
- hierdoor worden line+arc combinaties eerst kernel-native benaderd, vóór reconstructie-fallback

### Nieuwe fallback: recovery bucket voor gemengde contouren (line + arc)
Actieve uitbreiding:
- inner-wire kandidaten die niet direct als bekende vorm zijn herkend, gaan naar een recovery bucket
- recovery reconstrueert gesloten lussen uit edge-fragmenten via endpoint hashing + wire walking
- als een gesloten lus valide is, wordt deze alsnog toegevoegd als shaped hole (`Recovered contour` of afgeleide Slot/Rect/Poly)

Validatie in fallbackpad:
- minimale lusgrootte: `>= 3` edges
- closure gate: begin/eindpunt binnen tolerance
- perimeter gate: `> 0`

Output-impact:
- recovered holes worden meegeteld in shaped hole output
- debug payload bevat `contour_points` (exacte polyline punten)
- viewer kan deze contouren direct als exacte rand tekenen in plaats van benaderde primitives

Output-notitie (actueel):
- vormgaten worden wel meegeteld en gemeten
- maar niet als aparte labelcategorie naar XML geschreven
- in output `hole_types` vallen deze onder generiek `hole`

---

## Feature 3 - Deduplicatie rond versus vormgat (`deduplicate_holes`)

Actieve functie:
- `deduplicate_holes(circular_holes, shaped_holes)`

### Doel
Voorkom dat ronde subdelen van een vormgat dubbel geteld worden.

### Actieve logica
Een rond gat wordt alleen als potentieel duplicaat gezien als:
- as van het ronde gat voldoende parallel is aan shaped normal:
  - `dot >= 0.7`

Daarna wordt uit `shaped["dim"]` bepaald:
- `max_dim`
- `min_dim`

### Veiligheidsregel
Een rond gat blijft zelfstandig als:

$$
circ\_diam < 0.25 \cdot min\_dim
$$

Reden:
- een klein boorgat vlak naast een grote opening mag niet verdwijnen

### Duplicaatregel
Een rond gat wordt verwijderd als:

$$
dist(center_{round}, center_{shaped}) < 0.8 \cdot max\_dim
$$

### Samenvatting beslissing
Deze stap verwijdert alleen ronde gaten.
Shaped holes blijven altijd bestaan.

Belangrijke systeemnoot:
- als `detect_shaped_holes` een vals positief shaped hole genereert,
  kan deze stap echte ronde gaten verwijderen
- deze stap corrigeert geen foutieve shaped hole detecties

---

## Feature 4 - Tapgat-herkenning

Actieve lookup:
- `iso_standards.identify_thread_from_diameter(diameter, tolerance)`

Lookup-tolerantie in wrappers:
- `tolerance = 0.20 mm`

### ISO lookup-logica
De functie probeert meerdere matches te vinden:
- match op major diameter van metrische draad
- match op interne draad / minor-diameter logica
- match op tapped boordiameter-logica

Resultaat:
- lijst met mogelijke thread matches

Actieve providerstatus:
- `analysis/iso_standards.py` is weer actief
- metrische threadtabellen voor M3 t/m M24 (major + tap drill) worden gebruikt

### Beslislogica voor plaat (`extract_cut_features_for_sheet`)
1. zoek alle thread matches met `tolerance=0.20`
2. splits in:
   - `tapped_matches`: designation bevat `"tapped"`
   - `major_matches`: designation bevat geen `"tapped"`
3. bepaal depth gate:

$$
depth\_gate\_ok = (hole\_depth \le 0) \;\text{of}\; (hole\_depth \ge 0.5 \cdot hole\_diameter)
$$

4. als zowel `tapped_matches` als `major_matches` aanwezig zijn (ambigu):
   - filter `tapped_matches` op delta-criterium:

$$
0.8 \le (major\_diameter - hole\_diameter) \le 1.4
$$

   - houd tapped alleen aan als:
      - `depth_gate_ok = True`
      - `hole_diameter <= 6.2 mm`

5. als alleen `tapped_matches` aanwezig is:
   - behoud tapped alleen als `depth_gate_ok = True`

6. als na filtering tapped overblijft:
   - label wordt `thread`

7. anders:
   - label blijft `round`/`hole`

Rationale voor plaat:
- kleine gaten met ambigu M-major versus M-tapped overlap (zoals Ø5.0) worden niet meer direct als clearance afgewezen
- tegelijk blijft een ondergrens op diepte actief om onwaarschijnlijke taplabels te beperken
- grote ambigu gaten blijven conservatief (geen taplabel) door de `<= 6.2 mm` grens

### Legacy gate (niet meer actief voor plaat)
De vorige gate is vervangen en is niet meer de primaire beslisregel:

$$
major\_diameter \le 1.35 \cdot hole\_depth
$$

### Beslislogica voor profiel (`extract_cut_features_for_profile`)
1. zoek alle thread matches met `tolerance=0.20`
2. splits in `tapped_matches` en `major_matches`
3. alleen als:
   - `tapped_matches` bestaat
   - `major_matches` leeg is
   -> label = `thread`

Dus voor profiel is de thread-logica strenger dan voor plaat.

### Disambiguatie-uitzondering voor kleine profielgaten

Situatie:
- zowel `tapped_matches` als `major_matches` aanwezig (ambigu)
- voorbeeld: Ø5.0 mm matcht op M5 major (Ø5.0) én M6 tapped (tapboord Ø5.0)

Actieve uitzondering (alleen profiel):
- condities: `diameter <= 6.0 mm` AND `depth <= max(6.0, diameter × 1.5)`
- voor elke tapped match:

$$
0.8 \le (major\_diameter - hole\_diameter) \le 1.4
$$

Als match gevonden → label = `thread`, doorgaan bij eerste treffer.

Rationale:
- voor kleine gaten in een profielwand (dunne sectie) is de kans dat een gat als tapgat is uitgevoerd groter dan als speling-gat
- de delta-eis filtert op de typische relatie Mx tapboor -> M(x+1) major
- voorbeeld M6: tapboord Ø5.0, major Ø6.0 → delta = 1.0 ✓
- bij grotere gaten (> 6 mm) blijft de strenge regel van kracht

Als geen uitzondering van toepassing is:
- ambigu → label blijft `round`

### Samenvatting beslissing
Een cilindrisch gat wordt alleen tapgat als ISO-diametermatching sterk genoeg is.

Belangrijke systeemnoot:
- de huidige logica gebruikt alleen diameter en beperkte plausibility-regels
- schroefdraad wordt niet direct topologisch herkend
- dit maakt de detectie gevoelig voor ambigue diameters


## Feature 5 - Verzonken gat-herkenning (`_detect_countersunk_holes`)

Actieve functie:
- `_detect_countersunk_holes(cq_object, cylindrical_holes)`

### Doel
Koppel conische faces aan reeds gevonden cilindrische gaten.

### Brondetectie conische faces
Een conische face wordt alleen meegenomen als:
- surface type = `GeomAbs_Cone`
- genormaliseerde as geldig is
- included angle > 0

### Conische face parameters
Per cone worden vastgelegd:
- `axis`
- `origin`
- `included_angle = 2 * degrees(abs(semi_angle))`
- `inner_radius`
- `outer_radius`

Als circle edges aanwezig zijn:
- `inner_radius = min(circle_radii)`
- `outer_radius = max(circle_radii)`

### Match-criteria cone ↔ cylinder
Per cilindrisch gat wordt over alle cones gezocht met:
- as-paralleliteit: `axis_dot >= 0.97`
- radiale afstand tot as:

$$
radial\_dist \le max(1.0, 1.25 \cdot hole\_radius)
$$

- axiale afstand:

$$
axial\_dist \le max(25.0, 6.0 \cdot hole\_radius)
$$

- included angle tussen `55°` en `150°`

### Scorefunctie
Beste cone wordt gekozen op minimum van:

$$
score = radial\_dist + 10 \cdot (1 - axis\_dot) + 0.05 \cdot axial\_dist
$$

### Samenvatting beslissing
Als minimaal één cone voldoende goed matcht:
- gatlabel = `countersunk`
- teller `countersunk_holes += 1`
- angle wordt opgeslagen

### Fallback zonder cone-face: coaxiale cilindrische paren

Actieve uitbreiding:
- als geen conische faces aanwezig zijn, of voor niet-gematchte gaten,
  wordt een tweede pad gebruikt op basis van cilindrische paren

Doel:
- verzonken gaten blijven herkennen in STEP-exporten zonder expliciete `GeomAbs_Cone`

Matchcriteria cilindrisch paar:
- as-paralleliteit: `axis_dot >= 0.995`
- radiale afstand tot elkaars as: `radial_dist <= 3.5 mm`
- axiale afstand centra: `axial_dist <= 40.0 mm`
- diameter ratio:

$$
1.65 \le \frac{d_{groot}}{d_{klein}} \le 2.35
$$

- dieptegate groot gat (verzonken deel ondieper):

$$
depth_{groot} \le max(8.0, 0.7 \cdot d_{groot})
$$

- dieptevolgorde:

$$
depth_{klein} \ge depth_{groot}
$$

Beslissing:
- bij geldige pair krijgt de grote diameter-index label `countersunk`
- als fallback wordt `included_angle = 90.0` opgeslagen (synthetische hoek)

Belangrijke noot:
- cone-face matching blijft primair
- pair-fallback vult alleen ontbrekende countersink-matches aan

---

## Feature 6 - Standalone conische gaten (`_detect_standalone_countersunk_holes`)

Actieve functies:
- `_detect_standalone_countersunk_holes(...)`
- `_group_conical_countersink_faces(...)`
- `_candidate_matches_cylindrical_hole(...)`

### Doel
Vang STEP-varianten af waar alleen een conische countersink zichtbaar is en geen bruikbare cilindrische hole-face.

### Groepering van conische faces
Conische faces worden samengevoegd als:
- `axis_dot >= 0.999`
- `radial_dist <= 0.2`
- `axial_dist <= 1.0`
- `abs(angle_diff) <= 1.0°`
- `abs(inner_radius_diff) <= 0.3 mm`

### Kandidaatfilter
Een grouped countersink kandidaat blijft alleen over als:
- `inner_radius > 0`
- `55° <= included_angle <= 150°`
- hij niet al matcht met een cilindrisch gat

### Matchcheck tegen bestaande cylindrische gaten
Een standalone kandidaat wordt als “reeds gekoppeld” gezien als:
- `axis_dot >= 0.97`
- `radial_dist <= max(1.0, min(candidate_inner_radius, hole_radius) * 0.8)`
- `axial_dist <= max(40.0, hole_radius * 8.0)`

### Huidige wrapper-beslissing
Belangrijke actieve logica:
- standalone countersinks worden momenteel niet als `countersunk` gelabeld
- ze worden in beide wrappers als `thread` toegevoegd

Actief gedrag:
- `hole_types.append("thread")`
- `threaded_holes += 1`

Belangrijke systeemnoot:
- dit is bewust conservatief om false positive countersinks te vermijden
- functioneel betekent dit wel dat standalone conische gaten nu niet als verzonken gat in XML verschijnen

---

## Feature 7 - Wrapperverschillen plaat versus profiel

### Plaat / gezette plaat (`extract_cut_features_for_sheet`)
Actieve keuzes:
- `filter_bores=True`
- `is_flat_pattern=True` alleen als unfold succesvol is
- anders 3D analyse
- shaped holes blijven actief
- outer contour wordt berekend
- box dimensions worden berekend

Extra plate-specific thread gate:
- plausibility check op verhouding nominale draadmaat versus hole depth

### Profiel (`extract_cut_features_for_profile`)
Actieve keuzes:
- altijd 3D analyse
- `filter_bores=False`
- daarna eigen profiel-filter op diepte

Profiel bore-filter:
- bepaal `longest_dim` uit bounding box
- verwijder cilindrische gaten als:
$$
hole\_depth > 0.30 \cdot longest\_dim
$$

### Profiel end-face shaped-hole filter

Doel:
- voorkom dat de holle profielkern op het uiteinde als vormgat wordt meegeteld

Actieve criteria (alleen profiel-wrapper):
- shaped hole normal is bijna parallel aan lengte-as: `axis_alignment >= 0.95`
- hole center ligt dicht bij profiel-einde: `end_distance <= max(2.0, 0.05 * longest_dim)`
- hole-afmetingen zijn groot t.o.v. doorsnede:
   - `max_dim >= 0.60 * cross_mid_dim`
   - `min_dim >= 0.50 * cross_small_dim`

Als alle criteria waar zijn:
- shaped hole wordt onderdrukt (niet geteld, niet gelabeld)

### Profiel end-face closed-contour filter

Doel:
- voorkom dat de holle profielkern op het uiteinde als gesloten contour-gat wordt meegeteld

Actieve logica:
- dezelfde eindopening-filter wordt ook toegepast op `closed_contours`
- filtering gebeurt vóór `nr_holes` en `hole_contours` uit `closed_contours` worden afgeleid

Gevolg:
- profiel-uiteinden tellen niet mee in gatenaantal
- profiel-uiteinden tellen niet mee in snijlengte van gaten

### Aanvullende methode: inferentie via gestapelde cylinders (`_infer_profile_countersink_pairs`)

**Alleen actief in de profiel-wrapper.**

#### Aanleiding
Sommige STEP-bestanden hebben geen conische face voor de verzinking.
In dat geval is Feature 5 blind voor de countersink.
De gestapelde-cylinder-methode detecteert dan het patroon indirect:
- groot gat (verzonken deel) bovenop klein gat (doorgang)

#### Matchcriteria paar (groot → klein)
- diameter ratio:

$$
1.6 \le \frac{d_{groot}}{d_{klein}} \le 2.6
$$

- as-paralleliteit: `axis_dot >= 0.98`
- radiale afstand centrum tot as: `perp <= 4.0 mm`
- axiale afstand centrum tot centrum:

$$
5.0 \le axial \le 30.0 \text{ mm}
$$

- diepteverschil: `abs(depth_groot - depth_klein) <= 2.0 mm`

#### Scorefunctie (kies beste partner)

$$
score = perp + 0.05 \cdot |axial - 15.0|
$$

#### Uitkomst
- groot-gat index → `inferred_countersunk` set → label = `countersunk`
- klein-gat index → `suppressed_subholes` set → wordt niet apart meegeteld

#### Interactie met Feature 5
- als Feature 5 al een cone-match heeft voor een gat, wordt dat gat niet opnieuw als kandidaat aangeboden
- de inferentie-methode is alleen een fallback voor gaten zonder conische match

Verder:
- shaped holes blijven actief
- outer contour = `0.0`
- `box_x = 0.0`, `box_y = 0.0`
- thread-logica is strenger dan bij plaat

---

## XML mapping

### Plaat / gezette plaat
Wordt naar `Sheet_*` velden geschreven, o.a.:
- `Sheet_NrHoles`
- `Sheet_HoleContours`
- `Sheet_FeatExtTotL` (zelfde inhoud als `Sheet_HoleContours`)
- `Sheet_HoleRadii`
- `Sheet_HoleTypes`
- `Sheet_ThreadedHoles`
- `Sheet_CountersunkHoles`
- `Sheet_CountersunkAngles`

### Profiel
Wordt naar `Tube_*` velden geschreven, o.a.:
- `Tube_NrHoles`
- `Tube_HoleContours`
- `Tube_FeatExtTotL` (zelfde inhoud als `Tube_HoleContours`)
- `Tube_HoleRadii`
- `Tube_HoleTypes`
- `Tube_ThreadedHoles`
- `Tube_CountersunkHoles`
- `Tube_CountersunkAngles`

---

## Kernparameters (actief)

### `detect_holes`
- flat large-cylinder hard reject: verwijderd
- flat large-hole depth gate: `depth <= max(20.0, 3.0 * thickness_ref)`
- face group diameter tolerance: `0.01 mm`
- parallel-axis tolerance: `abs(abs(dot) - 1.0) <= 0.01`
- collinear-axis tolerance: `dist_sq < 0.01`
- center projection tolerance: `abs(t1 - t2) < 5.0 mm`
- minimal total angle flat: `> 160°`
- minimal total angle 3D: `> 270°`
- minimal total angle flat for diameter `> 100 mm`: `> 300°`
- turned-part bore reject: `depth > 0.5 * min_dim`

### `detect_shaped_holes`
- irregulaire methodiekvolgorde: Face Boundary eerst, Recovery Bucket daarna
- shaped dedup center tolerance: `dist_sq < 0.01`
- shaped dedup normal alignment: `dot > 0.9`

### `deduplicate_holes`
- circle/shaped plane alignment: `dot >= 0.7`
- small independent circle guard: `circ_diam < 0.25 * min_dim`
- duplicate distance gate: `dist < 0.8 * max_dim`

### thread detection
- ISO diameter tolerance: `0.20 mm`
- plate plausibility gate: `major_diameter <= 1.35 * hole_depth`
- profiel disambiguatie max diameter: `6.0 mm`
- profiel disambiguatie max depth: `max(6.0, diameter × 1.5)`
- profiel disambiguatie delta-window: `0.8 mm .. 1.4 mm` (major_diameter - hole_diameter)

### countersink detection
- axis alignment: `axis_dot >= 0.97`
- radial gate: `<= max(1.0, 1.25 * hole_radius)`
- axial gate: `<= max(25.0, 6.0 * hole_radius)`
- included angle: `55° .. 150°`

### profiel countersink inferentie (`_infer_profile_countersink_pairs`)
- diameter ratio: `1.6 .. 2.6`
- axis alignment: `axis_dot >= 0.98`
- perpendicular distance: `<= 4.0 mm`
- axial distance: `5.0 mm .. 30.0 mm`
- depth difference: `<= 2.0 mm`
- score: `perp + 0.05 * abs(axial - 15.0)` (minimaliseren)

### standalone countersink grouping
- axis alignment: `axis_dot >= 0.999`
- radial distance: `<= 0.2`
- axial distance: `<= 1.0`
- angle diff: `<= 1.0°`
- inner-radius diff: `<= 0.3 mm`

### profiel-only bore post-filter
- reject if `hole_depth > 0.30 * longest_dim`

### profiel end-face shaped-hole filter
- axis alignment with length axis: `>= 0.95`
- end-distance gate: `<= max(2.0 mm, 0.05 * longest_dim)`
- large opening gate (cross-section relative):
   - `max_dim >= 0.60 * cross_mid_dim`
   - `min_dim >= 0.50 * cross_small_dim`

---

## Bekende actuele zwakke plekken

1. `detect_shaped_holes` gebruikt de aanname dat elke inner wire op een planair vlak een gat is.
   - bij profielen is nu een end-face filter toegevoegd voor grote holle-kern openingen
   - daarnaast is een recovery bucket toegevoegd voor gemengde contourfragmenten op unfold geometry
   - resterend risico: complexe end-features die sterk op een holle kern lijken

2. Thread-detectie is diameter-gedreven.
   - bij ambigue diameters valt de beslissing snel terug naar `round`
   - voor profiel is een disambiguatieregel toegevoegd voor kleine gaten ≤ 6 mm (zie Feature 4)
   - voor plaat is nog geen vergelijkbare disambiguatie geïmplementeerd

3. Standalone countersinks worden momenteel als `thread` geboekt en niet als `countersunk`.
   - voor profiel is een inferentie-methode via gestapelde cylinders toegevoegd als fallback (zie Feature 5)
   - voor plaat is geen gestapelde-cylinder-inferentie aanwezig

4. Profiel-wrapper gebruikt een andere threadbeslissing dan plaat-wrapper.
   - dit kan verschillende uitkomsten geven voor vergelijkbare gaten

5. Countersink-herkenning op plaat vereist een bruikbare conische representatie in STEP.
   - als de conische topologie anders is opgebouwd, wordt geen match gevonden

---

## Aanbevolen verbeterstrategie

1. eerst deze review als referentie gebruiken voor elke wijziging
2. per feature één defect tegelijk aanpakken:
   - shaped-hole false positives
   - tapgat disambiguatie
   - countersink matching
3. na elke wijziging laag 1 tests uitbreiden
4. daarna pas wrapper-tests (laag 2) en XML-tests (laag 3)