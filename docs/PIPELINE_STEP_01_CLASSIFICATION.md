# Pipeline Step 01 Classification

Doel: leg alle actieve classificatie-afspraken vast in één stapdocument.

## Scope

Deze stap bepaalt:
- `final_class`
- subtype of route-aanduiding
- fallthrough van Step 0 naar de rest van de beslisboom

## Normatieve bronnen

- Hoofddocument: dit document
- Centrale variabelenbron: `manufacturing_pipeline/core/decision_variables.py`
- Compatibiliteitsmodule: `manufacturing_pipeline/analysis/classification_variables.py`

## Primaire codepaden

- `manufacturing_pipeline/analysis/classification.py`
- `manufacturing_pipeline/analysis/classification_core/step0.py`
- `manufacturing_pipeline/analysis/bom/assembly_analysis.py`
- `manufacturing_pipeline/core/runtime_analysis.py`

## Actieve afspraken

1. Classificatie is een stapbeslissing en mag later niet inhoudelijk door export of featurelogica worden herbeslist.
2. Besliscriteria voor classificatie horen bij één centrale codebron.
3. Documentatie van thresholds hoort de centrale codebron te volgen, niet andersom.
4. Een aparte review-thresholdtabel voor visuals of uitleg mag bestaan, maar alleen als afgeleide weergave, niet als tweede bron.
