# Documentation Cleanup Matrix

Doel: inventariseer welke documenten nu afspraken bevatten over classificatie, featuresemantiek, unfold en XML-bronautoriteit, zodat de volgende opschoonstap gecontroleerd kan gebeuren.

Dit document is stap 1 van de documentatie-opschoning:
- nog niets samenvoegen of verwijderen;
- eerst vastleggen wat actief, tijdelijk of historisch is;
- daarna pas bronkeuzes en migratie uitvoeren.

---

## 1. Statuscategorieen

| Status | Betekenis |
|---|---|
| `actief` | Huidige bron voor inhoudelijke afspraken of uitvoering |
| `tijdelijk_werkdocument` | Nodig voor lopend besluit- of migratiewerk, maar niet bedoeld als blijvende eindbron |
| `operationeel` | Procedure of workflow, geen inhoudelijke bron van semantische afspraken |
| `referentie` | Achtergrond, uitleg of technisch overzicht; niet leidend bij bronconflict |
| `historisch` | Handover, analyse of scratch-document; alleen bewaren als context |

---

## 2. Actieve en tijdelijke documenten in docs/

| Document | Domein | Huidige rol | Status | Behouden | Opmerking voor stap 2 |
|---|---|---|---|---|---|
| `docs/PIPELINE_STEP_00_OVERVIEW.md` | overview | Overzicht van de normatieve stapdocumenten | `actief` | Ja | Nieuwe ingang voor de opgeschoonde documentstructuur |
| `docs/PIPELINE_STEP_01_CLASSIFICATION.md` | classificatie | Herkenbaar stapdocument voor classificatieafspraken | `actief` | Ja | Doelbron voor classificatie; oude classificatiedocs zijn migratiebron |
| `docs/PIPELINE_STEP_02_SHEET_FEATURES.md` | plaatfeatures | Herkenbaar stapdocument voor plaatfeature- en holeafspraken | `actief` | Ja | Doelbron voor sheet-hole semantiek |
| `docs/PIPELINE_STEP_03_PROFILE_FEATURES.md` | profiel | Herkenbaar stapdocument voor profielmaatvoering en profielfeatures | `actief` | Ja | Doelbron voor profielafspraken |
| `docs/PIPELINE_STEP_04_UNFOLD.md` | unfold | Herkenbaar stapdocument voor unfoldafspraken | `actief` | Ja | Doelbron voor actieve unfoldroute en thresholds |
| `docs/PIPELINE_STEP_05_XML_EXPORT_AUTHORITY.md` | XML autoriteit | Herkenbaar stapdocument voor XML bronautoriteit | `actief` | Ja | Doelbron voor finale veldschrijfregels |
| `docs/PIPELINE_VARIABLES.md` | variabelen | Index van alle beslissingsvariabelen en centrale codebron | `actief` | Ja | Verwijst naar één centrale codebron |
| `docs/CLASSIFICATION_AUTHORITY_PLAN.md` | bronautoriteit, fallback, audit | Centrale kapstok voor bronrangorde en auditvolgorde | `tijdelijk_werkdocument` | Ja | Wordt voorlopig leidend voor authority-regels totdat een definitief contract per veld bestaat |
| `docs/FEATURE_DETECTION_ROADMAP.md` | roadmap, XML-fasering | Leidend voor uitvoeringsvolgorde per XML-fase | `actief` | Ja | Behouden als roadmap; bevat wel een verouderde testreferentie naar `test_final_verification.py` |
| `docs/archive/reference/ARCHIVE_classification.md` | classificatie | Voormalige classificatiereferentie | `historisch` | Ja | Alleen nog naslagwerk; niet meer operationeel |
| `docs/archive/reference/ARCHIVE_holedetection_review.md` | plaat/profiel gaten, thread, countersink | Voormalige hole-review | `historisch` | Ja | Alleen nog naslagwerk; niet meer operationeel |
| `docs/archive/reference/ARCHIVE_Unfold_review.md` | unfold, bendvelden | Voormalige unfold-review | `historisch` | Ja | Alleen nog naslagwerk; niet meer operationeel |
| `docs/xml_workdocument_classification_matrix.md` | XML veldinventaris per classificatie | Groot werkdocument met veldinventaris, huidige bronnen en gaten | `tijdelijk_werkdocument` | Ja | Later opsplitsen in definitief XML-contract en resterende implementatietodo's |
| `docs/xml_control_xml_gezette_plaat_procedure.md` | gezette plaat controle-XML | Procedure + veldmatrix voor een deelgebied | `tijdelijk_werkdocument` | Ja | Waarschijnlijk deels opgaan in definitief XML-contract en deels in validatieprocedure |
| `docs/XML_STATUS_WORKFLOW.md` | XML validatieproces | Operationele snapshot- en validatieworkflow | `operationeel` | Ja | Geen bron voor veldsemantiek; alleen procesdocument |
| `docs/README.md` | documentindex | Index van docs | `operationeel` | Ja | Na stap 2 herschrijven zodat 'actuele documentatie' niet meer tijdelijke werkdocumenten en referentiedocs door elkaar zet |
| `docs/archive/reference/ARCHIVE_ENGINE.md` | engine-overzicht | Voormalige engine-uitleg | `historisch` | Ja | Alleen nog naslagwerk; niet meer operationeel |
| `docs/archive/reference/ARCHIVE_pipeline_flow.md` | pipeline-overzicht | Voormalige flowvisualisatie | `historisch` | Ja | Alleen nog naslagwerk; niet meer operationeel |
| `docs/naming_strategy.md` | naamgeving | Specifieke strategie voor naming | `referentie` | Ja | Buiten huidige authority-scope, maar mogelijk relevant voor XML-identiteit |
| `docs/thickness_estimator_validation_protocol.md` | validatieprotocol | Gespecialiseerd protocol | `referentie` | Ja | Alleen meenemen als dikteautoriteit opnieuw wordt uitgewerkt |
| `docs/thickness_estimator_validation_matrix.md` | validatieset | Invulmatrix voor testvergelijking | `referentie` | Ja | Testartefact, geen semantische bron |

---

## 3. Historische documenten in docs/archive/

| Document of groep | Domein | Status | Behouden | Reden |
|---|---|---|---|---|
| `docs/archive/classification/*` | historische classificatie-analyses | `historisch` | Ja | Bevat waardevolle ontwerpcontext, maar niet meer als huidige bron aanwijzen |
| `docs/archive/handovers/HANDOVER_STEP0_CLASSIFICATION.md` | step 0 classificatie | `historisch` | Ja | Implementatie-/handovercontext, geen actieve specificatie |
| `docs/archive/handovers/HANDOVER_STEP0_ASSEMBLY_TESTING_20260320.md` | classificatie edge cases | `historisch` | Ja | Bewaart test- en foutcontext |
| `docs/archive/handovers/HANDOVER_HOLLOW_DETECTION_20260319.md` | hollow fallback | `historisch` | Ja | Alleen nog relevant als herkomst van vroegere fallbackkeuzes |
| `docs/archive/handovers/HANDOVER_20260324_HOLE_DETECTION.md` | hole fixes | `historisch` | Ja | Historisch verslag; inhoudelijke eindafspraken horen in `docs/PIPELINE_STEP_02_SHEET_FEATURES.md` |
| `docs/archive/handovers/HANDOVER_20260323_FEATURE_VALIDATION.md` | featurevalidatie | `historisch` | Ja | Houdt oude teststrategie vast; niet leidend |
| `docs/archive/handovers/HANDOVER_UNFOLD_USER_CONTOUR_RECOVERY_20260327.md` | unfold hole fallback | `historisch` | Ja | Relevante blijvende regels moeten in actieve docs staan, niet hier |
| `docs/archive/test-runs/*` | testrapporten en werkwijzen | `historisch` | Ja | Testhistorie, geen broncontract |
| `docs/archive/scratch/*` | losse analyses en notities | `historisch` | Ja | Alleen context; niet gebruiken als actieve afspraak |
| `docs/archive/plans/*` | oude plannen | `historisch` | Ja | Alleen bewaren voor terugblik |
| `docs/archive/reference/*` | voormalige operationele docs | `historisch` | Ja | Bewust hernoemd met `ARCHIVE_` zodat direct zichtbaar is dat ze niet actueel zijn |

---

## 4. Voorlopige bronkeuze per onderwerp

| Onderwerp | Voorlopig leidend document | Niet leidend maar relevant |
|---|---|---|
| Overzicht pipeline | `docs/PIPELINE_STEP_00_OVERVIEW.md` | `docs/archive/reference/ARCHIVE_pipeline_flow.md`, `docs/archive/reference/ARCHIVE_ENGINE.md` |
| Classificatiebeslissing | `docs/PIPELINE_STEP_01_CLASSIFICATION.md` | `docs/archive/reference/ARCHIVE_classification.md`, `docs/archive/classification/*`, handovers |
| Hole-semantiek | `docs/PIPELINE_STEP_02_SHEET_FEATURES.md` | `docs/archive/reference/ARCHIVE_holedetection_review.md`, historische hole handovers, XML werkdocumenten |
| Profielmaatvoering en profielfeatures | `docs/PIPELINE_STEP_03_PROFILE_FEATURES.md` | `docs/archive/reference/ARCHIVE_classification.md`, `docs/archive/reference/ARCHIVE_ENGINE.md` |
| Unfold- en bendafspraken | `docs/PIPELINE_STEP_04_UNFOLD.md` | `docs/archive/reference/ARCHIVE_Unfold_review.md`, `docs/xml_control_xml_gezette_plaat_procedure.md`, oude unfold handovers |
| XML bronautoriteit | `docs/PIPELINE_STEP_05_XML_EXPORT_AUTHORITY.md` | `docs/CLASSIFICATION_AUTHORITY_PLAN.md`, `docs/xml_workdocument_classification_matrix.md` |
| XML-fasering en uitvoeringsvolgorde | `docs/FEATURE_DETECTION_ROADMAP.md` | `docs/PIPELINE_STEP_05_XML_EXPORT_AUTHORITY.md` |
| XML-veldinventaris | `docs/xml_workdocument_classification_matrix.md` | `docs/xml_control_xml_gezette_plaat_procedure.md`, `Voorbeeldxml` |
| XML-validatieprocedure | `docs/XML_STATUS_WORKFLOW.md` | losse handovers en snapshots |
| Alle beslissingsvariabelen | `docs/PIPELINE_VARIABLES.md` | `manufacturing_pipeline/core/decision_variables.py`, compatibiliteitslagen |

---

## 5. Concreet opgeschoonde problemen die nu zichtbaar zijn

1. `docs/README.md` presenteert meerdere tijdelijke werkdocumenten alsof ze allemaal blijvende actuele bronnen zijn.
2. XML-inhoudelijke afspraken staan nu verspreid over minstens vier plekken: roadmap, authority-plan, XML werkdocument en gezette-plaat procedure.
3. Historische handovers bevatten nog inhoud die inhoudelijk belangrijk was, maar formeel al naar actieve docs had moeten worden gemigreerd.
4. `docs/FEATURE_DETECTION_ROADMAP.md` noemt `test_final_verification.py`, maar dat bestand bestaat niet in deze workspace.
5. Voormalige uitlegdocs zijn nu bewust hernoemd met `ARCHIVE_`, zodat direct zichtbaar is dat ze niet als contractuele bron gelezen mogen worden.
6. De code had geen echte ene beslissingsbron: classificatie, unfold en featuremodules gebruikten deels verschillende of hardcoded variabelen.

---

## 6. Uitkomst van stap 1

Na deze inventaris geldt voorlopig:
- inhoudelijke afspraken lezen we primair uit de nieuwe `PIPELINE_STEP_*` documenten en `PIPELINE_VARIABLES.md`;
- de centrale codebron voor beslissingsvariabelen is `manufacturing_pipeline/core/decision_variables.py`;
- `archive/reference/ARCHIVE_classification.md`, `archive/reference/ARCHIVE_holedetection_review.md`, `archive/reference/ARCHIVE_Unfold_review.md`, `archive/reference/ARCHIVE_ENGINE.md` en `CLASSIFICATION_AUTHORITY_PLAN.md` blijven voorlopig migratiebron;
- `FEATURE_DETECTION_ROADMAP.md` blijft leidend voor volgorde en fasering, niet voor detailsemantiek per veld;
- `xml_workdocument_classification_matrix.md` en `xml_control_xml_gezette_plaat_procedure.md` blijven tijdelijk werkmateriaal, nog niet de definitieve eindspecificatie;
- alles onder `docs/archive/` is historisch en mag niet meer als primaire bron worden gebruikt.

## 7. Klaar voor stap 2

Stap 2 kan nu gericht uitgevoerd worden als bronharmonisatie:
- per onderwerp een definitieve actieve bron aanwijzen;
- overlap uit tijdelijke werkdocumenten migreren;
- `docs/README.md` herschrijven naar een schonere indeling: actief, tijdelijk, operationeel, historisch.