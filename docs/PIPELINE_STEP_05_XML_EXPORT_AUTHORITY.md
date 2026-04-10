# Pipeline Step 05 XML Export Authority

Doel: leg de finale veldautoriteit vast voor XML-uitvoer.

## Scope

Deze stap bepaalt:
- welke bron een XML-veld mag schrijven;
- welke fallback toegestaan is;
- welke overrides verboden zijn.

## Normatieve bronnen

- Hoofddocument: dit document
- Werkdocument voor lopende audit: `CLASSIFICATION_AUTHORITY_PLAN.md`

## Primaire codepaden

- `manufacturing_pipeline/reporting/xml_exporter.py`
- `manufacturing_pipeline/core/vps_pipeline.py`

## Actieve afspraken

1. XML-export is finale writer plus autoriteitslaag, geen vrije herstelplek voor businessregels.
2. Een lagere bron mag een hogere semantische bron niet overschrijven.
3. Reference-values moeten uiteindelijk door dezelfde autoriteitsregels lopen als andere bronnen.
