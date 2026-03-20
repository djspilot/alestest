# Classificatie Step Review - STEP 0 (v3.10)

## Doel
Dit document legt de huidige STEP 0 beslisboom vast zoals geimplementeerd in
`manufacturing_pipeline/analysis/classification.py`.

Wijzigingen:
- **v3.7**: Stap 0.1 axiale slice-check voor ronde massieve assen.
- **v3.8**: Dmax-bepaling via eindzone-sampling (frac 0.02…0.98) vervangt Dcore.
  Axiale slice probeert `basis_u` eerst, fallback naar `basis_v` bij NONE.
- **v3.9**: Gesloten-hol labels `RONDE_BUIS` en `RECHTHOEKIGE_KOKER`
  mappen in de 3-klasse einduitkomst beide naar `profiel`.
- **v3.10**: Stap `0.4b` heeft een alternatieve-as fallback.
  Als de primaire as een convexe kern-sectie geeft (`holes==0`, `reentrant==0`),
  worden alternatieve assen getest en wordt de beste concave kandidaat gekozen.

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
4. `0.4a` Vlakke plaat (high confidence)
5. `0.4b` Gezette plaat (constant-dikte open sectie)
6. `0.5` Massief profiel fallback

Stopgedrag:
- Zodra een stap matcht met `fallthrough=False`: STOP.
- `0.1` zonder stabiele extrusie-as geeft `ANDERS` met `fallthrough=True` (door naar Step 1).
- `0.4a` kan bij lage confidence met `fallthrough=True` doorgeven naar Step 1.
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
- `compactness >= ROUND_SHAFT_CORE_COMPACTNESS_MIN` (0.90) — alleen voor cirkels
- `bbox_ratio >= ROUND_SHAFT_CORE_BBOX_RATIO_MIN` (0.95) — idem
- `length_ratio >= ROUND_SHAFT_MIN_LENGTH_RATIO` (3.0)

#### Hoe Dmax wordt bepaald (v3.8)
Stap 1: sample dwarsdoorsneden op 11 fracties langs de extrusie-as:

```
fracs = (0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98)
```

**Waarom niet 0.0 / 1.0?**
Slicen op exact frac=0.00 of 1.00 snijdt op de grens van het solid. De BRep-sectie
levert dan vrijwel altijd een lege of degenererende polygoon terug (geen edges).
0.02 en 0.98 zijn veilige eindposities die eindzone-bewerkingen (schouders, afdraaiingen)
daadwerkelijk treffen zonder grens-artefacten.

Stap 2: per doorsnede wordt de buitenomvang gemeten:
```
dim = max(bbox_width, bbox_height)   # bounding-box van de dwarsdoorsnede-polygoon
Dmax = max(dim) over alle 11 doorsneden
```

**Waarom bounding-box en niet equivalent diameter?**
- Bounding-box is onafhankelijk van gaten/draadprofielen in de sectie.
- Gaten (frac=0.05: draad/boring) verlagen de vlakoppervlakte maar NIET de bounding-box.
- Schouders (frac=0.98: Ø25 op een Ø20 schacht) verhogen de bounding-box wel.
- Zo geeft Dmax altijd de grootste aanwezige buitenomtrek, ook bij eindzone-bewerkingen.

#### Axiale slice
Na Dmax-bepaling wordt een longitudinale (axiale) doorsnede gemaakt — een vlak
parallel aan de extrusie-as door het middelpunt (`axis.origin`).

Vlakrichting: probeer `core_sec.basis_u` eerst; als die geen geldige sectie
geeft (bijv. als `basis_u` toevallig parallel loopt met een vlak vlak),
gebruik dan `basis_v` als fallback.

Definities:
$$A_{axial} = \text{oppervlakte axiale doorsnede}$$
$$A_{exp} = D_{max} \times L$$
$$\text{ratio} = \frac{A_{axial}}{A_{exp}}$$

Beslisregel:
- Als $\text{ratio} < ROUND\_SHAFT\_AXIAL\_AREA\_RATIO\_MIN$ (0.975):
  - classificeer direct **ANDERS** in stap `0.1`
  - reden: ronde massieve as met axiale diameterafname (afgedraaid/bewerkt)

Intuïtie:
- Een onbewerkte ronde as heeft overal diameter ≈ Dmax → axiale doorsnede ≈ rechthoek D×L → ratio ≈ 1.0.
- Een afgedraaide as met schouder heeft het merendeel van de lengte diameter < Dmax → axiale doorsnede kleiner → ratio << 1.

Voorbeeldwaarden:
| Part | Dmax | L | A_exp | A_axial | ratio | uitkomst |
|------|------|---|-------|---------|-------|---------|
| 10000182371 (as Ø20, schouder Ø25) | 25.0 | 133 | 3325 | 2679 | 0.806 | ANDERS |
| 10000550594 (ax. reductie) | ~20 | ~133 | ~2660 | 2596 | 0.971 | ANDERS |

Exit:
- geen stabiele extrusie-as → **ANDERS** met `fallthrough=True` (door naar Step 1)
- te weinig/stabiele secties onvoldoende, of as-check faalt → **ANDERS** (STOP)
- anders → door naar `0.2`

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

## Stap 0.4a - Vlakke plaat
Criteria:
- `holes == 0`
- near-rectangle
- high confidence bij `bbox_ratio <= 0.30`

Exit:
- high confidence -> `PLAAT`, `fallthrough=False` (STOP)
- lage confidence -> `PLAAT`, `fallthrough=True` (door naar Step 1)

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

## Kernparameters (nieuw in v3.7)
In `manufacturing_pipeline/analysis/classification_variables.py`:
- `ROUND_SHAFT_CORE_COMPACTNESS_MIN = 0.90`
- `ROUND_SHAFT_CORE_BBOX_RATIO_MIN = 0.95`
- `ROUND_SHAFT_MIN_LENGTH_RATIO = 3.0`
- `ROUND_SHAFT_AXIAL_AREA_RATIO_MIN = 0.975`

## Verwachte impact
- Ronde massieve assen met duidelijke eindbewerking schuiven van `PROFIEL`
  naar `ANDERS` al in stap `0.1`.
- Gesloten-hol buis/koker route (`0.2`) valt in de eindklasse onder `profiel`.
