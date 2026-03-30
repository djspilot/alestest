# Handover 24-03-2026 - Hole detection and assembly follow-up

## 1. Afgerond

1. Hole detection voor profieldeel 05-01-5340 is functioneel hersteld.
   - Doelstatus nu gehaald: 6 holes totaal, 4 threaded, 2 countersunk.

2. De profielspecifieke false positive op shaped holes aan een hol profieluiteinde is gefixt.
   - Dit gebeurt in de profile wrapper, niet generiek op sheet-niveau.
   - Daardoor blijft sheet-gedrag ongemoeid.

3. XML-output is aangepast zodat shaped holes als generieke hole meetellen in plaats van aparte shaped labels.

4. Extra contour-output is toegevoegd:
   - Sheet_FeatExtTotL
   - Tube_FeatExtTotL

5. Layer 1 regressies voor de recente hole-fixes staan groen.

## 2. Relevante codewijzigingen

- manufacturing_pipeline/analysis/cut_features.py
  - profile thread disambiguation voor kleine ambigue holes
  - inferred countersink pairs voor stepped cylindrical geometry
  - profile-only filter voor hollow end opening shaped-hole false positives

- manufacturing_pipeline/tests/test_feature_layer1.py
  - regressietests voor thread disambiguation
  - regressietests voor inferred countersinks
  - regressietest voor profile end-opening shaped-hole filtering

- holedetection_review.md
  - bijgewerkt met de nieuwe detectieregels en huidige diagnosecontext

## 3. Teststatus

- Gerichte Layer 1 suite: groen
- Laatste bekende regressiestatus: 28 passed wanneer timeline API test wordt genegeerd
- Bekende externe ruis: manufacturing_pipeline/tests/test_timeline_api.py vraagt fastapi in deze omgeving

## 4. Open issue

Assembly: 10001073426_Rev_00-aangepast.stp

Focus-onderdelen:
- 10001073529_Rev_00
- 10001073530_Rev_00

Huidige assembly XML:
- 10001073529_Rev_00 -> Sheet_NrHoles = 22
- 10001073530_Rev_00 -> Sheet_NrHoles = 30

Referentie XML:
- 10001073529_Rev_00 -> 29 holes
- 10001073530_Rev_00 -> 37 holes

Belangrijk:
- Dit lijkt geen regressie door de recente profiel-fix.
- Er zijn signalen dat assembly mapping of exporter-associatie tussen BOM-naam en solid nog niet klopt.
- Standalone runs en assembly runs laten niet exact hetzelfde gedrag zien voor unfold en holecount-context.

## 5. Waarschijnlijk volgende stap

Controleer in xml_exporter en assembly flow welke part_solid werkelijk gekoppeld wordt aan:
- 10001073529_Rev_00
- 10001073530_Rev_00

Werkvolgorde:

1. Trace BOM item naam naar gekoppelde solid in assembly export.
2. Vergelijk die solid-signatuur met de standalone gegenereerde XML per onderdeel.
3. Pas daarna opnieuw beoordelen of er echt holes missen of dat de verkeerde solid aan de naam hangt.

## 6. Praktische startcommando's

```powershell
cd C:\Data\DS\Python\Spaceclaim_verv\alestest
python -m pytest manufacturing_pipeline/tests/test_feature_layer1.py -q
python -m pytest -q --ignore=manufacturing_pipeline/tests/test_timeline_api.py
```