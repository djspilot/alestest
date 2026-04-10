# Pipeline Step 04 Unfold

Doel: leg alle actieve unfold-afspraken vast in één herkenbaar stapdocument.

## Scope

Deze stap bepaalt onder meer:
- `Sheet_UnfoldSuccess`
- vlakke maatvoering (`Sheet_BoxX`, `Sheet_BoxY` in unfold-context)
- bend count, bend angles, bend radii en bend lengths

## Normatieve bronnen

- Hoofddocument: dit document
- Centrale variabelenbron: `manufacturing_pipeline/core/decision_variables.py`
- Runtime threshold loader: `manufacturing_pipeline/core/thresholds.py`

## Primaire codepaden

- `manufacturing_pipeline/core/runtime_unfold.py`
- `manufacturing_pipeline/core/runtime_analysis.py`
- `manufacturing_pipeline/reporting/xml_exporter.py`

## Actieve afspraken

1. De actieve route is `runtime_unfold.run_unfold_to_step(...)`.
2. Legacy of alternatieve unfoldimplementaties zijn niet leidend voor productieroutes.
3. Unfold-thresholds horen centraal te staan en mogen alleen via gecontroleerde runtime-overrides worden aangepast.
4. Technische fallback heeft niet automatisch dezelfde autoriteit als een gevalideerde unfold-uitkomst.
