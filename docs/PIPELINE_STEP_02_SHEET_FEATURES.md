# Pipeline Step 02 Sheet Features

Doel: leg de afspraken vast voor plaatfeatures, vooral hole-semantiek en afgeleide snijdata.

## Scope

Deze stap bepaalt onder meer:
- `Sheet_NrHoles`
- `Sheet_HoleRadii`
- `Sheet_HoleContours`
- `Sheet_ThreadedHoles`
- `Sheet_CountersunkHoles`
- `Sheet_CountersunkAngles`

## Normatieve bronnen

- Hoofddocument: dit document
- Centrale variabelenbron: `manufacturing_pipeline/core/decision_variables.py`

## Primaire codepaden

- `manufacturing_pipeline/analysis/cut_features.py`
- `manufacturing_pipeline/analysis/features/cut_features_extractors.py`
- `manufacturing_pipeline/analysis/features/cut_features_sheet_helpers.py`
- `manufacturing_pipeline/analysis/features/hole_detection.py`

## Actieve afspraken

1. Semantische hole-velden volgen `cut_features`-semantiek en niet viewer/debug-labels.
2. Open contouren zijn geen productie-gaten.
3. Countersink is semantisch exclusief en mag onderliggende subgaten niet dubbel laten meetellen.
4. Flat-pattern artefactfilters en countersink-pairing horen bij de centrale variabelenbron.
