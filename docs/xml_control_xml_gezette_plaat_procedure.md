# Controle-XML Procedure Voor Gezette Plaat

## Doel

Dit document beschrijft de werkwijze om een gezette plaat STEP-bestand via de manufacturing pipeline te verwerken naar een aparte controle-XML.

Deze controle-XML is niet bedoeld als definitieve productie-XML, maar als inspectie-output waarmee per veld gecontroleerd kan worden:

- welke velden uit `Voorbeeldxml` al gevuld worden
- welke velden leeg blijven
- welke velden inhoudelijk nog niet correct of niet stabiel genoeg zijn
- welke extra data de pipeline al heeft, maar niet in `Voorbeeldxml` voorkomt

## Scope

Deze procedure geldt voor classificatie `gezette_plaat`.

De controle-XML moet gebruikt worden voor:

- handmatige validatie per STEP
- gap-analyse van ontbrekende XML-velden
- besluitvorming over welke extra pipeline-data onderdeel moet worden van de definitieve XML

## Uitgangspunten

- `Voorbeeldxml` is de referentie voor de minimale gewenste veldset
- de huidige manufacturing pipeline blijft leidend voor inhoudelijke brondata
- velden buiten `Voorbeeldxml` worden apart gemarkeerd als `extra beschikbare data`
- spelling- en legacy-onregelmatigheden uit `Voorbeeldxml` worden niet automatisch overgenomen in het nieuwe contract

## Beoogde output

Per gezette plaat willen we een aparte XML kunnen genereren met:

1. alle relevante `Sheet_*` velden uit `Voorbeeldxml`
2. vaste lege tags voor velden die nog niet gevuld kunnen worden
3. optioneel extra tags voor data die wij al hebben, maar die niet in `Voorbeeldxml` staat
4. voldoende traceability om handmatig per STEP te controleren wat er gebeurd is

## Procedure

### Stap 1 - Selecteer een referentie STEP

Gebruik een STEP-bestand dat in de pipeline als `gezette_plaat` wordt geclassificeerd.

Doel van deze stap:

- bevestigen dat de classificatie correct is
- zorgen dat de controle-XML echt over een bent-sheet case gaat

### Stap 2 - Verwerk het bestand via de manufacturing pipeline

De pipeline moet minimaal deze gegevens produceren of proberen te produceren:

- classificatie
- sheet dikte
- basisafmetingen
- bend count
- bend angles
- bend inner radii
- bend lengths
- hole count en hole metrics
- contour- en area-metrics
- unfold status
- eventuele DXF output

### Stap 3 - Bouw een aparte controle-XML

Deze XML is gescheiden van de uiteindelijke standaard XML-output.

Werkafspraak:

- één gezette plaat resulteert in één `CalculationResult`
- de veldset volgt primair `Voorbeeldxml`
- ontbrekende velden worden niet weggelaten, maar bewust leeg gezet wanneer dat nuttig is voor controle

### Stap 4 - Vergelijk handmatig per veld

Bij review van de controle-XML wordt per veld bepaald:

- klopt de inhoud inhoudelijk voor deze STEP
- komt de waarde uit de juiste bron
- is het veld terecht leeg
- ontbreekt hier nog implementatie
- hoort dit veld in de definitieve XML of alleen in de controle-XML

### Stap 5 - Leg beslissing per veld vast

Per veld volgt uiteindelijk één van deze statussen:

- `definitieve_xml`
- `alleen_controle_xml`
- `voorlopig_niet_opnemen`

## Veldmatrix Gezette Plaat

| Veld | In Voorbeeldxml | Huidige bron | Huidige status | Voor controle-XML | Voor definitieve XML |
|---|---|---|---|---|---|
| `Sheet_PartName` | Ja | BOM / result naming | Beschikbaar | Ja | Ja |
| `Sheet_Name` | Ja | BOM / solid naming | Beschikbaar | Ja | Ja |
| `Sheet_Type` | Ja | XML export mapping | Beschikbaar | Ja | Ja |
| `Sheet_Thickness` | Ja | analysis / cut features / cross-section / reference | Beschikbaar, route-afhankelijk | Ja | Ja |
| `Sheet_Count` | Ja | BOM quantity | Beschikbaar | Ja | Ja |
| `Sheet_NrBends` | Ja | production / unfold / cross-section | Beschikbaar | Ja | Ja |
| `Sheet_NrHoles` | Ja | production / cut features | Beschikbaar | Ja | Ja |
| `Sheet_NrMarkingLines` | Ja | Niet beschikbaar als stabiele pipeline-output | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_TopArea` | Ja | xml_exporter berekening / analyse-afleiding | Beschikbaar, nog exporter-gedreven | Ja | Ja |
| `Sheet_Volume` | Ja | geometry / xml_exporter | Beschikbaar | Ja | Ja |
| `Sheet_AreaNoHoles` | Ja | cut/area afleiding | Beschikbaar, nog niet overal canoniek | Ja | Ja |
| `Sheet_TotalArea` | Ja | exporter berekening | Beschikbaar | Ja | Ja |
| `Sheet_BoxArea` | Ja | exporter berekening | Beschikbaar | Ja | Ja |
| `Sheet_BoxX` | Ja | dims / unfold / cross-section | Beschikbaar, betekenis expliciteren | Ja | Ja |
| `Sheet_BoxY` | Ja | dims / unfold / cross-section | Beschikbaar, betekenis expliciteren | Ja | Ja |
| `Sheet_OuterContour` | Ja | AAG / cut metrics | Gedeeltelijk | Ja | Ja |
| `Sheet_TotalContour` | Ja | AAG / cut metrics | Gedeeltelijk | Ja | Ja |
| `Sheet_HoleContours` | Ja | cut features | Beschikbaar | Ja | Ja |
| `Sheet_HoleRadii` | Ja | cut features | Beschikbaar | Ja | Ja |
| `Sheet_MarkingLength` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_BendLength` | Ja | unfold / cross-section | Beschikbaar, route-afhankelijk | Ja | Ja |
| `Sheet_BendAngles` | Ja | unfold / cross-section | Beschikbaar, route-afhankelijk | Ja | Ja |
| `Sheet_BendInnerRadii` | Ja | unfold / cross-section | Beschikbaar, route-afhankelijk | Ja | Ja |
| `Sheet_UnfoldSuccess` | Ja | unfold output | Beschikbaar | Ja | Ja |
| `Sheet_FilePath` | Ja | Niet standaard aanwezig | Ontbreekt / legacy | Ja, optioneel leeg | Besluit nodig |
| `Sheet_Material` | Ja | inferred / material config | Beschikbaar | Ja | Ja |
| `Sheet_OrderNr` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_DeliveryDate` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_Weight` | Ja | exporter berekening | Beschikbaar | Ja | Ja |
| `Sheet_Time` | Ja | Niet als stabiele productiewaarde beschikbaar | Ontbreekt / legacy | Ja, optioneel leeg | Besluit nodig |
| `Sheet_Cost` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_NrHolesCS` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_HolesCS` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_FilePathDXF` | Ja | unfold/export path | Deels beschikbaar | Ja | Waarschijnlijk ja |
| `Sheet_AP_Queue` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_AP_POLP` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_AP_Machine` | Ja | Niet beschikbaar als stabiele pipeline-output | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_AP_PDF` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_AP_Priority` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_AP_Status` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Alleen indien ERP vereist |
| `Sheet_ProfileExists` | Ja | Niet beschikbaar in huidige sheet-contract | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_Id_Object` | Ja | Niet standaard aanwezig | Ontbreekt / traceability | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_Id_Source` | Ja | Niet standaard aanwezig | Ontbreekt / traceability | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_Id_ParentObject` | Ja | Niet standaard aanwezig | Ontbreekt / traceability | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_Id_ParentSource` | Ja | Niet standaard aanwezig | Ontbreekt / traceability | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_FilePathPNG` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_FilePathPNG_Unfold` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_FilePathPNG_BendDrawing` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_BendTable` | Ja | Niet standaard beschikbaar | Ontbreekt | Ja, optioneel leeg | Besluit nodig |
| `Sheet_IsLocked` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_ContourString` | Ja | Niet beschikbaar als stabiele standaardoutput | Ontbreekt | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_NestedArea` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_FilePathPDF_BendDrawing` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_OriginalName` | Ja | Gedeeltelijk afleidbaar | Deels beschikbaar | Ja | Controle-XML kandidaat |
| `Sheet_AddedDocument` | Ja | Niet beschikbaar | Ontbreekt | Nee | Nee |
| `Sheet_MaterialPriceKg` | Ja | Niet beschikbaar | Ontbreekt | Nee | Alleen indien ERP vereist |
| `Sheet_MaterialPrice` | Ja | Niet beschikbaar | Ontbreekt | Nee | Alleen indien ERP vereist |
| `Sheet_Machine` | Ja | Niet beschikbaar als stabiel veld | Ontbreekt | Ja, optioneel leeg | Besluit nodig |
| `Sheet_AssemblyLevel` | Ja | Niet standaard aanwezig | Ontbreekt / traceability | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_HasBevel` | Ja | Niet beschikbaar | Ontbreekt | Ja, optioneel leeg | Besluit nodig |
| `Sheet_BBox3D` | Ja | Niet standaard aanwezig | Ontbreekt | Ja, optioneel | Controle-XML kandidaat |
| `Sheet_Notes` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Controle-XML kandidaat |
| `Sheet_Thread` | Ja | Niet als exact legacy veld, maar semantiek wel beschikbaar | Beschikbaar als moderne variant | Ja, via mappingbesluit | Besluit nodig |
| `Sheet_SmallHoles` | Ja | Niet beschikbaar | Ontbreekt | Ja, leeg | Besluit nodig |
| `Sheet_Warning` | Ja | Niet als vast veld, wel afleidbaar | Deels beschikbaar | Ja | Controle-XML kandidaat |
| `Sheet_User_Poedercoaten` | Ja | Niet beschikbaar | Ontbreekt | Nee | Alleen indien ERP vereist |
| `Sheet_User_Gewicht_Bruto` | Ja | Niet beschikbaar | Ontbreekt | Nee | Alleen indien ERP vereist |

## Extra beschikbare data buiten Voorbeeldxml

De huidige pipeline kan voor gezette plaat al data leveren die niet expliciet in `Voorbeeldxml` staat, maar inhoudelijk wel sterk is:

- `Sheet_HoleTypes`
- `Sheet_ThreadedHoles`
- `Sheet_CountersunkHoles`
- `Sheet_CountersunkAngles`
- `Sheet_FeatExtTotL`
- `Sheet_BottomArea`

Voor deze velden geldt voorlopig:

- wel opnemen in de analyse van het plan
- nog niet automatisch verplicht maken voor de definitieve XML
- eerst per veld beslissen of het productie- of alleen controlegegevens zijn

## Besluitvoorstel per veldgroep

### Direct meenemen in controle-XML

- alle kernvelden uit `Voorbeeldxml` die productie-inhoud bevatten
- alle bend-velden
- alle hole-, contour-, area- en weight-velden
- `Sheet_FilePathDXF`
- traceability-velden die helpen bij handmatige controle

### Alleen voorlopig leeg opnemen in controle-XML

- ERP-velden
- planning- en queue-velden
- prijsvelden
- legacy velden zonder huidige bron

### Niet standaard meenemen in eerste versie

- PNG/PDF-afgeleide paden
- nested / lock velden
- gebruikersvelden zonder functionele noodzaak

## Handmatige validatie per STEP

Bij controle van een gezette plaat controle-XML moet minimaal worden nagegaan:

1. Is de classificatie echt `gezette_plaat`?
2. Kloppen `Sheet_Thickness`, `Sheet_BoxX`, `Sheet_BoxY` inhoudelijk?
3. Kloppen `Sheet_NrBends`, `Sheet_BendAngles`, `Sheet_BendInnerRadii`, `Sheet_BendLength`?
4. Kloppen `Sheet_NrHoles`, `Sheet_HoleContours`, `Sheet_HoleRadii`?
5. Kloppen `Sheet_OuterContour`, `Sheet_TotalContour`, `Sheet_AreaNoHoles`, `Sheet_TotalArea`?
6. Is `Sheet_UnfoldSuccess` logisch gezien de case?
7. Is `Sheet_FilePathDXF` aanwezig waar verwacht?
8. Welke velden blijven leeg terwijl ze volgens proceswens wel nodig zijn?

## Open beslissingen voor gezette plaat

- Wat is de definitieve betekenis van `Sheet_BoxX` en `Sheet_BoxY` bij gezette plaat: altijd unfolded of context-afhankelijk?
- Willen we `Sheet_FilePath` naast `Sheet_FilePathDXF` behouden?
- Moeten `Sheet_ThreadedHoles` en `Sheet_CountersunkHoles` standaard naar de eind-XML, ook al staan ze niet als zodanig in `Voorbeeldxml`?
- Willen we traceability-velden zoals `Sheet_Id_*`, `Sheet_OriginalName` en `Sheet_AssemblyLevel` alleen in controle-XML of ook in definitieve XML?
- Welke legacy velden zijn nog echt procesrelevant, en welke kunnen vervallen?

## Aanbevolen volgende stap

De logische volgende stap is een implementatie-notitie maken voor de losse controle-XML generator voor gezette plaat, met:

- invoer: één STEP + pipeline-resultaat
- output: één `CalculationResult` volgens de tabel hierboven
- statusmarkering per veld: gevuld, leeg, ontbrekende bron, beslissing nodig

Daarna kan dezelfde methodiek worden toegepast op `vlakke_plaat`.