# Pipeline Variables

Doel: één document dat aangeeft waar alle beslissende variabelen van de pipeline staan.

## Canonieke codebron

De centrale codebron is:
- `manufacturing_pipeline/core/decision_variables.py`

## Compatibiliteitslagen

Deze modules blijven bestaan voor bestaande imports of runtime loading, maar lezen uit de centrale bron:
- `manufacturing_pipeline/analysis/classification_variables.py`
- `manufacturing_pipeline/core/thresholds.py`

## Variabelengroepen

| Groep | Centrale bron |
|---|---|
| Classificatie | `CLASSIFICATION_VARIABLES` |
| Classificatie-review thresholds | `CLASSIFICATION_REVIEW_THRESHOLDS` |
| Sheet-feature regels | `SHEET_FEATURE_DECISION_VARIABLES` |
| Hole-detection regels | `HOLE_DETECTION_DECISION_VARIABLES` |
| Profile-feature regels | `PROFILE_FEATURE_DECISION_VARIABLES` |
| Unfold-defaults | `UNFOLD_DEFAULT_THRESHOLDS` |
