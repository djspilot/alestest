# Classificatie Step Review - STEP 0 (v3.11)

## Doel
Dit document beschrijft de actuele STEP 0 beslisboom zoals geimplementeerd in
`manufacturing_pipeline/analysis/classification.py`.

Wijzigingen:
- **v3.7**: Stap 0.1 axiale slice-check voor ronde massieve assen.
- **v3.8**: Dmax-bepaling via eindzone-sampling (frac 0.02..0.98) vervangt Dcore.
- **v3.9**: Gesloten-hol labels `RONDE_BUIS` en `RECHTHOEKIGE_KOKER` mappen beide naar eindklasse `profiel`.
- **v3.10**: Stap 0.4b alternate-axis fallback voor gespiegelde onderdelen.
- **v3.11**: Stap 0.4a aangepast:
  - `near-rectangle` is geen harde plaat-poort meer,
  - vlakke plaat vereist nu expliciet `reentrant_corners == 0` en `dikteConstant == True`,
  - `near-rectangle + bbox_ratio <= 0.30` blijft alleen het high-confidence STOP pad.

## Kerntermen
- `section`: 2D doorsnede van een solid.
- `core section`: representatieve doorsnede uit het dominante section-cluster.
- `holes`: aantal interne lussen in een section.
- `reentrant_corners`: aantal concave hoeken in een section.
- `dikteConstant`: proxy op basis van top-2 face area verschil.

## Beslisboom Overzicht
1. `0.1` Slice-validatie (poort + ronde-as bewerkingscheck)
2. `0.2` Gesloten-hol (buis/koker)
3. `0.3` Open profiel (L/U/I/T)
4. `0.4a` Vlakke plaat (met confidence-tier)
5. `0.4b` Gezette plaat (constant-dikte open sectie)
6. `0.5` Massief profiel fallback

Stopgedrag:
- Zodra een stap matcht met `fallthrough=False`: STOP.
- `0.1` zonder stabiele extrusie-as geeft `ANDERS` met `fallthrough=True` (door naar Step 1).
- `0.4a` kan als low-confidence `PLAAT` met `fallthrough=True` doorgeven naar Step 1.
- `0.5` `ANDERS` is low-confidence en geeft `fallthrough=True` (door naar Step 1).

---

## Stap 0.1 - Slice-validatie (poort)

Primaire criteria:
- stabiele extrusie-as gevonden
- minimaal 3 geldige dwarsdoorsneden
- dominant section cluster >= `STEP0_CLUSTER_RATIO_MIN` (nu 0.30)

Dwarsdoorsnede-sampleposities:
- fracties: `(0.20, 0.35, 0.50, 0.65, 0.80)`

### Subcheck: ronde massieve as met axiale slice (v3.8)
Deze check draait alleen als de `core section` lijkt op een ronde massieve as:
- `holes == 0`
- `reentrant_corners == 0`
- `compactness >= ROUND_SHAFT_CORE_COMPACTNESS_MIN` (0.90)
- `bbox_ratio >= ROUND_SHAFT_CORE_BBOX_RATIO_MIN` (0.95)
- `length_ratio >= ROUND_SHAFT_MIN_LENGTH_RATIO` (3.0)

Definities:
$$A_{axial} = \text{oppervlakte axiale doorsnede}$$
$$A_{exp} = D_{max} \times L$$
$$\text{ratio} = \frac{A_{axial}}{A_{exp}}$$

Beslisregel:
- Als $\text{ratio} < ROUND\_SHAFT\_AXIAL\_AREA\_RATIO\_MIN$ (0.975):
  - classificeer direct **ANDERS** in stap `0.1`
  - reden: ronde massieve as met axiale diameterafname (afgedraaid/bewerkt)

Exit:
- geen stabiele extrusie-as -> **ANDERS** met `fallthrough=True`
- onvoldoende stabiele secties of as-check faalt -> **ANDERS** (STOP)
- anders -> door naar `0.2`

---

## Stap 0.2 - Gesloten-hol (koker/buis)
Criteria:
- `holes == 1`
- outer+inner near-circle -> `RONDE_BUIS`
- outer+inner near-rectangle -> `RECHTHOEKIGE_KOKER`

3-klasse eindmapping:
- `RONDE_BUIS` -> `profiel`
- `RECHTHOEKIGE_KOKER` -> `profiel`

Wire-loop fallback:
- gebruikt bij complexe/afgeronde ringen als polygon-hole reconstructie faalt
- overlapdrempel: `HOLLOW_WIRE_OVERLAP_RATIO_MIN` (0.90)

Exit:
- match -> STOP
- geen match -> door naar `0.3`

---

## Stap 0.3 - Open profiel (L/U/I/T)
Criteria:
- `holes == 0`
- `reentrant_corners > 0`
- bent-sheet veto (`_is_bent_sheet_geometry == False`)
- template-match in open families (I/U/L/T) met score <= 0.12

Exit:
- match -> `PROFIEL` (STOP)
- geen match -> door naar `0.4a`

---

## Stap 0.4a - Vlakke plaat (v3.11)
Doel:
- vlakke platen (ook niet-rechthoekige contourplaten) herkennen,
- maar gezette/open concave doorsneden niet als vlakke plaat laten stoppen.

Harde criteria (plaat-kandidaat):
- `holes == 0`
- `reentrant_corners == 0`
- `dikteConstant == True`

Confidence-tier:
- High confidence STOP:
  - `near-rectangle == True`
  - `bbox_ratio <= 0.30`
  - resultaat: `PLAAT`, `fallthrough=False`
- Low confidence (contourplaat of dikkere sectie):
  - zelfde harde criteria, maar zonder high-confidence shape-score
  - resultaat: `PLAAT`, `fallthrough=True` (door naar Step 1)

Belangrijk:
- `near-rectangle` is in v3.11 alleen een high-confidence gate, geen harde toegangseis voor `PLAAT`.

---

## Stap 0.4b - Gezette plaat
Criteria:
- `holes == 0`
- `reentrant_corners > 0`
- `dikteConstant == True`

As-selectie:
- primair via `find_extrusion_axis`
- fallback: bij `holes==0` en `reentrant_corners==0` op primaire as,
  evalueer alternatieve assen (`planar-face-normal`, `vertex-pca`) en kies
  de kandidaat met `holes==0` en hoogste `reentrant_corners`

Uitkomst:
- match -> `GEZETTE_PLAAT` (STOP)
- geen match -> door naar `0.5`

---

## Stap 0.5 - Massief profiel fallback
Dimensionele fallback op:
- smallest >= `PROFILE_SMALLEST_MIN_MM`
- length_ratio >= `PROFILE_LENGTH_RATIO_MIN`
- cross_ratio binnen `[PROFILE_CROSS_RATIO_MIN, PROFILE_CROSS_RATIO_MAX]`
- volume_ratio strong/weak + SA/V tiebreak

Uitkomst:
- `PROFIEL` of `ANDERS`

---

## Kernparameters
In `manufacturing_pipeline/analysis/classification_variables.py`:
- `ROUND_SHAFT_CORE_COMPACTNESS_MIN = 0.90`
- `ROUND_SHAFT_CORE_BBOX_RATIO_MIN = 0.95`
- `ROUND_SHAFT_MIN_LENGTH_RATIO = 3.0`
- `ROUND_SHAFT_AXIAL_AREA_RATIO_MIN = 0.975`

## Verwachte impact v3.11
- Niet-rechthoekige vlakke contourplaten vallen minder snel onterecht uit in 0.4a.
- Scheiding `vlak` versus `gezet` wordt explicieter:
  - vlak: `reentrant == 0`
  - gezet: `reentrant > 0` met constante dikte.
- High-confidence snelle STOP blijft bestaan voor duidelijke rechthoekige plaatdoorsneden.
