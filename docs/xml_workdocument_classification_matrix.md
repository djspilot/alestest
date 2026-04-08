# XML Werkdocument Per Classificatie

## Doel

Dit document beschrijft de huidige stand van de XML-opbouw in de manufacturing pipeline en het plan om naar een complete, consistente XML-output te komen.

De focus ligt op drie vragen:

1. Welke XML-gegevens horen per classificatie in de eindoutput te staan?
2. Welke gegevens zijn in de huidige manufacturing pipeline al beschikbaar?
3. Welke gegevens ontbreken nog of bestaan alleen impliciet in de XML-exportlaag?

Dit document is bedoeld als werkdocument voor implementatie. Het vervangt geen formeel XML-contract, maar maakt wel expliciet waar de huidige code staat en waar het gat zit tussen analyse-output en definitieve XML-output.

## Huidige situatie

Er bestaan op dit moment twee relevante XML-routes:

- Een lichte route: `export_to_xml(result, output_path)` in `manufacturing_pipeline/reporting/xml_exporter.py`
- Een rijkere BOM-route: `export_bom_to_xml(...)` in `manufacturing_pipeline/reporting/xml_exporter.py`

De lichte route schrijft XML op basis van een generiek result-dict.
De BOM-route bouwt classificatiebewuste XML op en doet daarbij extra analyse en fallback-logica.

Dat betekent:

- de gewenste complete XML-opbouw is inhoudelijk al deels aanwezig
- de manufacturing pipeline levert nog niet overal een canoniek classificatie-specifiek result-model
- de exporter doet nog inhoudelijk werk dat eigenlijk upstream in analysis thuishoort

## Bronnen voor dit werkdocument

- `manufacturing_pipeline/reporting/xml_exporter.py`
- `manufacturing_pipeline/api/routes.py`
- `manufacturing_pipeline/api/analysis_service.py`
- `manufacturing_pipeline/analysis/cut_features.py`
- `manufacturing_pipeline/analysis/profile_features.py`
- `docs/FEATURE_DETECTION_ROADMAP.md`
- `docs/pipeline_flow.md`
- `docs/holedetection_review.md`
- `docs/overhaul.md`

## Hoofdconclusie

De inhoudelijke featuredata voor plaat en profiel bestaat al voor een groot deel, maar zit nog verspreid over:

- runtime analysis output
- visuals/debug payloads
- cut-feature extractie
- profile feature extractie
- XML-exporter-specifieke fallback-logica

De kern van het vervolgwerk is daarom niet alleen extra detectie bouwen, maar vooral:

- één canoniek XML-contract per classificatie vastleggen
- één canoniek analysis-resultmodel invoeren
- de XML-exporter terugbrengen tot een pure writer/mappinglaag

## Doelbeeld

De gewenste eindsituatie is:

- één classificatiebewust resultmodel uit de analysis pipeline
- één XML-writer die alleen nog velden wegschrijft
- dezelfde XML-logica voor API-download, totale XML en losse part-XML
- altijd een `DocumentControl` blok in de finale XML
- regressietests op veldniveau per classificatie

## Matrix Per Classificatie

### 1. Vlakke plaat

| Onderdeel | XML-velden | Al aanwezig in pipeline | Ontbreekt of is nog zwak | Huidige bron |
|---|---|---|---|---|
| Identiteit | `Sheet_PartName`, `Sheet_Name`, `Sheet_Count`, `Sheet_Type` | Ja | Nog niet als formeel contract buiten exporter | result + BOM export |
| Materiaal | `Sheet_Material` | Gedeeltelijk | Vaak nog inferred in exporter | xml_exporter |
| Basisgeometrie | `Sheet_Thickness`, `Sheet_BoxX`, `Sheet_BoxY` | Ja | Nog niet canoniek als `sheet_data` object | analysis result |
| Hole count | `Sheet_NrHoles` | Ja | Bronselectie is route-afhankelijk | production + cut features |
| Hole radii | `Sheet_HoleRadii` | Ja | Niet altijd direct uit analysis contract | cut features |
| Hole contours | `Sheet_HoleContours` | Ja | Nog XML-specifiek opgebouwd | cut features |
| Hole types | `Sheet_HoleTypes` | Gedeeltelijk | Nog niet gegarandeerd op elke route | visuals/cut features |
| Thread data | `Sheet_ThreadedHoles` | Ja | Semantiek bestaat, contract nog niet expliciet | cut features |
| Countersink data | `Sheet_CountersunkHoles`, `Sheet_CountersunkAngles` | Ja | Semantiek bestaat, contract nog niet expliciet | cut features |
| Area data | `Sheet_BoxArea`, `Sheet_AreaNoHoles`, `Sheet_TotalArea`, `Sheet_TopArea`, `Sheet_BottomArea` | Gedeeltelijk | Berekening zit nog deels in exporter | xml_exporter |
| Contour data | `Sheet_OuterContour`, `Sheet_TotalContour` | Gedeeltelijk | Nog niet upstream gestandaardiseerd | AAG + cut features |
| Weight | `Sheet_Weight` | Gedeeltelijk | Nog afgeleid in exporter | xml_exporter |
| Unfold/DXF status | `Sheet_UnfoldSuccess`, `Sheet_FilePathDXF` | Deels | Voor vlakke plaat nog niet als vaste outputafspraak | unfold/export layer |

#### Beoordeling vlakke plaat

Vlakke plaat is het verst uitgewerkt. Vrijwel alle functionele gegevens bestaan al, maar nog niet als stabiel en formeel resultmodel tussen analysis en reporting.

### 2. Gezette plaat

| Onderdeel | XML-velden | Al aanwezig in pipeline | Ontbreekt of is nog zwak | Huidige bron |
|---|---|---|---|---|
| Basis sheet velden | Alle relevante `Sheet_*` basisvelden | Grotendeels ja | Zelfde contractprobleem als vlakke plaat | result + BOM export |
| Bend count | `Sheet_NrBends` | Ja | Nog route-afhankelijk | production/unfold/cross-section |
| Bend angles | `Sheet_BendAngles` | Ja, in BOM-route | Niet als standaard analysis output | BOM export |
| Bend radii | `Sheet_BendInnerRadii` | Ja, in BOM-route | Niet als standaard analysis output | BOM export |
| Bend lengths | `Sheet_BendLength` | Ja, in BOM-route | Niet als standaard analysis output | BOM export |
| Flat dims | `Sheet_BoxX`, `Sheet_BoxY` in ontvouwde context | Ja, deels | Betekenis nog niet overal formeel vastgelegd | unfold/cross-section |
| Unfold status | `Sheet_UnfoldSuccess` | Ja | Nog geen universeel contract | unfold output |
| DXF path | `Sheet_FilePathDXF` | Deels | Nog geen stabiele end-to-end waarde | export layer |
| Holes / threads / countersinks | Relevante `Sheet_*` holevelden | Ja | Aanwezig, maar nog niet overal op hetzelfde niveau ontsloten | cut features |

#### Beoordeling gezette plaat

Gezette plaat heeft al veel inhoudelijke logica, maar die logica leeft nog te veel in de XML-exportlaag. Voor een robuuste pipeline moet bend- en unfold-informatie upstream in het analysis-resultaat landen.

### 3. Profiel

| Onderdeel | XML-velden | Al aanwezig in pipeline | Ontbreekt of is nog zwak | Huidige bron |
|---|---|---|---|---|
| Identiteit | `Tube_PartName`, `Tube_Name`, `Tube_Count` | Ja, in BOM-route | Niet in de lichte standaard XML-route | BOM export |
| Type | `Tube_Type` | Ja | Niet consequent beschikbaar in elke route | profile features |
| Basisafmetingen | `Tube_Thickness`, `Tube_Width`, `Tube_Height` | Ja | Nog niet als canoniek `profile_data` model | profile features |
| Bounding box | `Tube_BoxDeltaX`, `Tube_BoxDeltaY`, `Tube_BoxDeltaZ` | Ja | Nog niet overal standaard output | profile features |
| Radii | `Tube_InnerRadius`, `Tube_OuterRadius` | Ja | Nog route-gebonden | profile features |
| Materiaal | `Tube_Material` | Ja | Materiaalafspraak nog niet overal expliciet | xml_exporter |
| Weight | `Tube_Weight` | Ja | Nog afgeleid in exporter | xml_exporter |
| Status | `Tube_Success`, `Tube_FilePath` | Ja | Betekenis en kwaliteitsregel nog expliciet vastleggen | BOM export |
| Hole count | `Tube_NrHoles` | Ja | Alleen in rijkere route goed gekoppeld | cut features |
| Hole metrics | `Tube_HoleContours`, `Tube_HoleRadii`, `Tube_HoleTypes` | Ja | Niet in standaard XML-route | cut features |
| Thread/countersink | `Tube_ThreadedHoles`, `Tube_CountersunkHoles`, `Tube_CountersunkAngles` | Ja | Nog niet universeel ontsloten | cut features |

#### Beoordeling profiel

Profiel is inhoudelijk verder dan de standaard XML-download laat zien. De feature-extractie bestaat al, maar wordt nog niet via één canonieke Tube-uitvoer beschikbaar gemaakt.

### 4. Anders

| Onderdeel | XML-velden | Al aanwezig in pipeline | Ontbreekt of is nog zwak | Huidige bron |
|---|---|---|---|---|
| Identiteit | `Others_PartName`, `Others_Name` | Ja | Geen groot probleem | BOM export |
| Type | `Others_Type` | Ja | Nu nog erg generiek | BOM export |
| Count | `Others_Count` | Ja | Geen groot probleem | BOM export |
| Verrijking | Eventueel materiaal, bbox, gewicht, status | Nee / niet afgesproken | Nog geen functionele afspraak nodig | n.v.t. |

#### Beoordeling anders

Voor `anders` is de minimale set aanwezig. De belangrijkste open vraag is functioneel: blijft dit bewust een minimale restcategorie, of willen we ook verrijkte data opnemen?

### 5. DocumentControl en totale XML

| Onderdeel | XML-velden | Al aanwezig in pipeline | Ontbreekt of is nog zwak | Huidige bron |
|---|---|---|---|---|
| BOM tellingen | `Aantal_BOM`, `Aantal_Verwerkt`, `Aantal_Plaat`, `Aantal_Profiel`, `Aantal_Anders` | Ja, in BOM-route | Niet in lichte XML-route | BOM export |
| Status | `Status`, `Classificatie_Status`, `Waarschuwingen` | Ja, in BOM-route | Niet universeel aanwezig | BOM export |
| Controleverschillen | `Controle_Verschil_BOM_Exported` | Ja | Alleen BOM-route | BOM export |

#### Beoordeling DocumentControl

Voor een complete productie-XML moet `DocumentControl` altijd aanwezig zijn. Dat is nu nog geen universele eigenschap van de standaard XML-export.

## Overzicht Beschikbaar vs Ontbrekend

### Reeds beschikbaar

- Basisresultaat per part met `category`, `part_type`, `thickness`, `dimensions`, `production`, `flat_dimensions`, `aag_details`
- Plaat-hole semantiek via `cut_features`
- Profiel feature extractie via `profile_features`
- Een rijkere XML-opbouw in de BOM-route
- Bestaande validatieverwachting voor `DocumentControl`

### Nog ontbrekend

- Eén actueel XML-contractdocument per classificatie
- Eén canoniek resultmodel tussen analysis en reporting
- Eén uniforme XML-exportroute voor alle outputvormen
- Profiel en `anders` als volwaardige standaard XML-output in de actieve API-route
- Universele `DocumentControl`
- Regressietests op veldniveau per classificatie

## Plan van aanpak

### Fase 1 - Contract expliciet maken

Doel:

- per classificatie vastleggen welke XML-velden verplicht zijn
- per veld vastleggen: bron, fallback, validatieregel, eigenaar

Aanpak:

- begin met `plaat`
- splits `plaat` direct in `vlakke_plaat` en `gezette_plaat`
- gebruik de huidige schema-definitie in `xml_exporter.py` als startpunt

### Fase 2 - Canoniek resultmodel invoeren

Doel:

- analysis levert een classificatiebewuste datastructuur
- XML-export consumeert alleen nog gestructureerde velden

Voorgestelde richting:

- `sheet_data`
- `profile_data`
- `others_data`
- `document_control`
- `export_meta`

### Fase 3 - Plaat volledig afronden

Doel:

- alle `Sheet_*` velden direct uit pipeline-output
- exporter doet geen inhoudelijke feature-analyse meer

Volgorde:

1. vlakke plaat
2. gezette plaat
3. veldniveau validatie op vaste STEP/XML-paren

### Fase 4 - Profiel aansluiten

Doel:

- bestaande profiel extractie koppelen aan een vaste `Tube_*` output
- profiel-hole data rechtstreeks uit cut features modelleren

### Fase 5 - Anders minimalistisch vastzetten

Doel:

- minimale set stabiliseren
- daarna beslissen of verrijking wenselijk is

### Fase 6 - Eén XML-route afdwingen

Doel:

- API download
- totale XML
- losse part-XML

allemaal via dezelfde class-aware writer laten lopen.

### Fase 7 - Regressietests toevoegen

Doel:

- veldniveau asserts per classificatie
- golden/reference XML vergelijkingen
- validatie op `DocumentControl`

## Aanbevolen uitvoervolgorde

1. Detailmatrix voor `vlakke_plaat` uitschrijven
2. Detailmatrix voor `gezette_plaat` uitschrijven
3. Canoniek `sheet_data` model invoeren
4. XML-writer los trekken van exporter-logica voor sheet
5. Detailmatrix voor `profiel` uitschrijven
6. Canoniek `profile_data` model invoeren
7. `anders` contract finaliseren
8. `DocumentControl` universeel maken
9. Eén exportpad afdwingen
10. Regressietests per classificatie toevoegen

## Open beslissingen

- Blijft `anders` bewust minimaal?
- Zijn `Sheet_BoxX` en `Sheet_BoxY` voor gezette plaat altijd ontvouwde maten?
- Is `Sheet_FilePathDXF` verplicht of conditioneel?
- Welke velden zijn hard fail en welke alleen warning in validatie?
- Willen we één gedeeld XML-schemaobject of aparte schema's per classificatie?

## Eerste concrete vervolgstap

De eerstvolgende praktische stap is het maken van een detailmatrix voor `plaat` op veldniveau, met per veld:

- XML-veld
- classificatie
- verplicht of optioneel
- huidige bron
- fallbackbron
- huidige status
- ontbrekende implementatie
- validatiebestand

Dat document kan vervolgens direct gebruikt worden als implementatievolgorde voor de XML-uitrol.
