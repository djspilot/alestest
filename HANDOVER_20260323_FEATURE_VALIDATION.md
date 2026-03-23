# Handover 23-03-2026 - Featurevalidatie met fallback-context

## 1. Wat is afgerond

1. Step 0/CadQuery stabilisatie:
   - CadQuery wrappers worden nu consistent omgezet naar OCP shapes in:
     - `manufacturing_pipeline/analysis/step0_section_tools.py`
     - `manufacturing_pipeline/analysis/assembly_analysis.py`

2. Gedragscheck op referentie `803041-7028`:
   - Step 0 geeft `PLAAT` (`0.4a`) met `fallthrough=True`.
   - Eindclassificatie in volledige flow blijft `ANDERS`.
   - Fallback-keten werkt dus nog zoals ontworpen.

3. Testinfrastructuur:
   - `pytest.ini` toegevoegd en afgestemd op stabiele testdiscovery.
   - `tests/test_xml_export.py` omgezet naar pytest-smoke tests.
   - Standaardrun: `python -m pytest -q` -> **22 passed**.

4. Warning cleanup:
   - In-house NumPy deprecation opgelost in Step 0 tooling.
   - Ruis uit third-party deprecations gefilterd in pytest-config.

## 2. Huidige status

- Branch: `main`
- Repo staat functioneel op een stabiel punt voor de volgende fase.
- Focus verschuift van classificatiebeslissing naar feature-correctheid per klasse, inclusief fallback-pad.

## 3. Plan voor morgen (concreet)

### Fase A - Testmatrix per classificatie

Maak een matrix met per testcase:
- `solid_id` / referentiebestand
- Verwachte Step 0 uitkomst (`0.4a`, `0.4b`, `0.4c`, dependency, etc.)
- Verwachte fallthrough (`True/False`)
- Verwachte final class (`plaat` / `profiel` / `anders`)
- Verwachte subtype waar van toepassing

### Fase B - Featurevalidatie met fallback-invloed

Voer per testcase twee checks uit:
1. Step 0 trace check (welke regel triggerde)
2. Final feature check (welke featurewaarden uiteindelijk in BOM/XML staan)

Belangrijk: test mag alleen groen zijn als **zowel pad als eindresultaat** klopt.

### Fase C - Start met profiel/tube

Begin met `profiel` op subtypes:
1. `RONDE_BUIS`
2. `RECHTHOEKIGE_KOKER`

Valideer minimaal deze XML-velden:
- `Tube_Diameter`
- `Tube_Thickness`
- `Tube_Length`
- `Tube_NrHoles`
- `Tube_PartCode`

Voor elk veld:
- definieer bronfeature,
- definieer expected fallback-gedrag,
- voeg ten minste 1 positieve en 1 negatieve testcase toe.

## 4. Risico's/let op

1. Grote assemblies met vergelijkbare solids kunnen nog mapping-onzekerheid geven als er geen unieke geometrische discriminatie is.
2. Bij fallback-routes niet alleen label checken; feature-waarden kunnen ongemerkt van bron wisselen.
3. Houd gegenereerde artifacts (XML snapshots/debug dumps) buiten standaard commits.

## 5. Praktische startcommando's

```bash
cd c:\Data\DS\Python\Spaceclaim_verv\alestest
python -m pytest -q
```

Optioneel gericht:
```bash
python -m pytest tests/test_xml_export.py -q
```
