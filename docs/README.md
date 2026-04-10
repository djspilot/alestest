# Docs

Technische documentatie voor de ALES Manufacturing Pipeline.

## Actuele documentatie

| Document | Beschrijving |
|----------|-------------|
| [pipeline_step_00_overview.md](pipeline_step_00_overview.md) | Overzicht van de gestandaardiseerde stapdocumenten en centrale variabelenbron |
| [pipeline_step_01_classification.md](pipeline_step_01_classification.md) | Actieve afspraken voor classificatie |
| [pipeline_step_02_sheet_features.md](pipeline_step_02_sheet_features.md) | Actieve afspraken voor plaatfeatures en hole-semantiek |
| [pipeline_step_03_profile_features.md](pipeline_step_03_profile_features.md) | Actieve afspraken voor profielmaatvoering en profielfeatures |
| [pipeline_step_04_unfold.md](pipeline_step_04_unfold.md) | Actieve afspraken voor unfold en bendvelden |
| [pipeline_step_05_xml_export_authority.md](pipeline_step_05_xml_export_authority.md) | Actieve afspraken voor XML-veldautoriteit |
| [pipeline_variables.md](pipeline_variables.md) | Centrale uitleg van beslissingsvariabelen en compatibiliteitslagen |
| [thickness_estimator_validation_protocol.md](thickness_estimator_validation_protocol.md) | Validatieprotocol voor branch Thicknessestimator: dikte eerst, unfold daarna |
| [thickness_estimator_validation_matrix.md](thickness_estimator_validation_matrix.md) | Bevroren Ronde 1-testset en invulmatrix voor main versus Thicknessestimator |
| [naming_strategy.md](naming_strategy.md) | Naamgeving strategie voor onderdelen in XML-output |
| [feature_detection_roadmap.md](feature_detection_roadmap.md) | Roadmap voor feature-detectie en XML uitrol per fase |
| [xml_status_workflow.md](xml_status_workflow.md) | XML validatie workflow en snapshot-bewaring |
| [xml_workdocument_classification_matrix.md](xml_workdocument_classification_matrix.md) | Werkdocument met matrix per classificatie: aanwezig, ontbrekend en plan |
| [xml_control_xml_gezette_plaat_procedure.md](xml_control_xml_gezette_plaat_procedure.md) | Procedure en veldmatrix voor losse controle-XML van gezette plaat |

## Overhaul (lopend)

| Document | Beschrijving |
|----------|-------------|
| [overhaul.md](overhaul.md) | Refactoring overzicht en scope |
| [overhaul_phases.md](overhaul_phases.md) | Fase-voor-fase verwijderplan |
| [overhaul_test_results.md](overhaul_test_results.md) | Testresultaten per overhaul-fase |

## Archief

Oudere handovers, testresultaten en scratch-notities staan in [`archive/`](archive/).

Gearchiveerde voormalige operationele documenten:

| Document | Beschrijving |
|----------|-------------|
| [archive/reference/ARCHIVE_ENGINE.md](archive/reference/ARCHIVE_ENGINE.md) | Voormalige engine-uitleg; nu alleen naslagwerk |
| [archive/reference/ARCHIVE_classification.md](archive/reference/ARCHIVE_classification.md) | Voormalige classificatiereferentie; nu alleen naslagwerk |
| [archive/reference/ARCHIVE_pipeline_flow.md](archive/reference/ARCHIVE_pipeline_flow.md) | Voormalige flowdiagrammen; nu alleen naslagwerk |
| [archive/reference/ARCHIVE_holedetection_review.md](archive/reference/ARCHIVE_holedetection_review.md) | Voormalige hole-review; nu alleen naslagwerk |
| [archive/reference/ARCHIVE_Unfold_review.md](archive/reference/ARCHIVE_Unfold_review.md) | Voormalige unfold-review; nu alleen naslagwerk |

## Migratiestatus

De documenten [archive/reference/ARCHIVE_classification.md](archive/reference/ARCHIVE_classification.md), [archive/reference/ARCHIVE_holedetection_review.md](archive/reference/ARCHIVE_holedetection_review.md), [archive/reference/ARCHIVE_Unfold_review.md](archive/reference/ARCHIVE_Unfold_review.md) en `CLASSIFICATION_AUTHORITY_PLAN.md` blijven voorlopig bruikbaar als migratiebron, maar de herkenbare stapdocumenten hierboven zijn de nieuwe doelstructuur.
