# Pipeline Step 03 Profile Features

Doel: leg de afspraken vast voor profieltype, profielmaatvoering en profielgatsemantiek.

## Scope

Deze stap bepaalt onder meer:
- `Tube_Type`
- `Tube_Width`
- `Tube_Height`
- `Tube_Thickness`
- `Tube_Length`
- `Tube_NrHoles`

## Normatieve bronnen

- Hoofddocument: dit document
- Centrale variabelenbron: `manufacturing_pipeline/core/decision_variables.py`

## Primaire codepaden

- `manufacturing_pipeline/analysis/profile_features.py`
- `manufacturing_pipeline/analysis/features/cut_features_profile_helpers.py`
- `manufacturing_pipeline/analysis/features/cut_features_extractors.py`

## Actieve afspraken

1. Profielherkenning en profielmaatvoering zijn een eigen stap, niet alleen een restcategorie van classificatie.
2. Profiel-holetelling mag profieluiteinden niet als gaten meetellen.
3. Profiel-specifieke pairing- en end-opening regels horen bij de centrale variabelenbron.
