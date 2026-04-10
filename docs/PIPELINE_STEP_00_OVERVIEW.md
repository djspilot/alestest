# Pipeline Step 00 Overview

Doel: één herkenbaar overzichtsdocument voor de manufacturing pipeline, zonder inhoudelijke detailafspraken van alle stappen door elkaar te trekken.

## Leidend gebruik

Dit document is alleen bedoeld voor:
- globale flow;
- stapindeling;
- verwijzing naar de normatieve stapdocumenten;
- verwijzing naar de centrale codebron voor beslissingsvariabelen.

Dit document is niet bedoeld als contractuele bron voor thresholds of fallbackregels.

## Stapindeling

1. `PIPELINE_STEP_01_CLASSIFICATION.md`
2. `PIPELINE_STEP_02_SHEET_FEATURES.md`
3. `PIPELINE_STEP_03_PROFILE_FEATURES.md`
4. `PIPELINE_STEP_04_UNFOLD.md`
5. `PIPELINE_STEP_05_XML_EXPORT_AUTHORITY.md`
6. `PIPELINE_VARIABLES.md`

## Centrale codebron

De centrale codebron voor beslissingsvariabelen staat in:
- `manufacturing_pipeline/core/decision_variables.py`

Compatibiliteitslagen:
- `manufacturing_pipeline/analysis/classification_variables.py`
- `manufacturing_pipeline/core/thresholds.py`

## Flow op hoofdlijnen

1. Classificatie bepaalt de primaire route en betekenis van het onderdeel.
2. Sheet-features bepalen semantische gaten- en snijdata voor plaatdelen.
3. Profile-features bepalen profieltype, maatvoering en profielgatsemantiek.
4. Unfold bepaalt vlakke maatvoering en bendvelden voor gezette plaat.
5. XML export bepaalt de finale veldschrijfregels en bronautoriteit.
