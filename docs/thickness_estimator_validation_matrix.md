# Thickness Estimator Validatiematrix

Deze matrix hoort bij `docs/thickness_estimator_validation_protocol.md`.

Status van deze matrix:

- Ronde: 1
- Testset: bevroren
- Doel: `main` versus branch `Thicknessestimator` vergelijken
- Werkwijze: strikt sequentieel, pas naar volgende stap bij expliciete `GO`

## Stap 1 Status

Uitgevoerd op: 2026-04-02

Technische controle:

- Alle 9 bestanden uit de bevroren testset bestaan op de genoteerde paden.
- Protocol en matrix gebruiken dezelfde testset.
- De testset is daarmee technisch uitvoerbaar.

Huidige stapstatus:

- Technisch: `GO`
- Inhoudelijk: `GO`

Stap 1 is hiermee afgerond op `2026-04-02`.

De bevroren testset en validatierol per bestand zijn inhoudelijk akkoord. De validatieronde mag daarom door naar stap 2: verwachte waarheid vastleggen.

## Bevroren Testset

Deze testset wordt in ronde 1 niet meer aangepast. Als een bestand in stap 1 niet akkoord is, stopt de validatie en wordt de testset eerst herzien voordat stap 2 start.

| Bestand | Pad | Validatierol |
|---|---|---|
| `05-01-5340.STEP` | `data/stepfile/features/05-01-5340.STEP` | Vlakke plaat kandidaat met features/uitsparingen |
| `336027_rev[B].STEP` | `data/stepfile/features/336027_rev[B].STEP` | Tweede vlakke plaat kandidaat met features |
| `10000362951_Rev_01.step` | `data/stepfile/Zetwerk/10000362951_Rev_01.step` | Eenvoudige gezette plaat |
| `10000869069_Rev_00.step` | `data/stepfile/Zetwerk/10000869069_Rev_00.step` | Tweede eenvoudige gezette plaat |
| `10001073529_Rev_00.step` | `data/stepfile/Zetwerk/10001073529_Rev_00.step` | Complexere gezette plaat |
| `10001073530_Rev_00.stp` | `data/stepfile/Zetwerk/10001073530_Rev_00.stp` | Probleemgeval en complexere gezette plaat |
| `10000182371_Rev_01.step` | `data/stepfile/profiel/10000182371_Rev_01.step` | Niet-plaatwerk kandidaat: profiel |
| `803143-7015.stp` | `data/stepfile/profiel/803143-7015.stp` | Tweede niet-plaatwerk kandidaat: profiel |
| `10000986417_Rev_00.step` | `data/stepfile/samenstelling/10000986417_Rev_00.step` | Assemblage of non-sheet referentie |

## Stap 2: Verwachte Waarheid

Ga pas verder naar stap 3 als deze sectie voldoende is ingevuld voor de kritieke onderdelen. Als de verwachte waarheid nog onduidelijk is, eerst deze stap afronden en nog niet verder testen.

Deze velden worden handmatig ingevuld op basis van engineering-kennis of handmatige inspectie, niet op basis van de huidige pipeline-output.

Huidige stapstatus:

- Technisch: `GO`
- Inhoudelijk: `GO`
- Afgerond op: `2026-04-02`

| Part | Verwachte dikte | Verwachte classificatie | Verwacht unfold | Verwacht aantal zettingen | Verwachte uitslag/opmerking |
|---|---:|---|---|---:|---|
| `05-01-5340.STEP` | `3 mm` | `PROFIEL` | `nee` | `0` | Handmatige geometrie-inspectie: rechthoekig kokerprofiel ca. `20 x 40 x 3 mm`, lengte ca. `775 mm` |
| `336027_rev[B].STEP` | `3 mm` | `PLAAT (vlak)` | `nee` | `0` | Handmatige geometrie-inspectie: vlak plaatdeel ca. `99 x 400 x 3 mm` met veel gaten/features |
| `10000362951_Rev_01.step` | `5 mm` | `GEZETTE PLAAT` | `ja` | `>=1` | Handmatige geometrie-inspectie: meerdere plaatsegmenten en cilinderparen bevestigen constante dikte `5 mm` |
| `10000869069_Rev_00.step` | `5 mm` | `GEZETTE PLAAT` | `ja` | `>=1` | Handmatige geometrie-inspectie: grote vlakparen en cilinderparen bevestigen constante dikte `5 mm` |
| `10001073529_Rev_00.step` | `5 mm` | `GEZETTE PLAAT` | `ja` | `>=1` | Handmatige geometrie-inspectie: grote vlakparen en cilinderparen bevestigen constante dikte `5 mm` |
| `10001073530_Rev_00.stp` | `5 mm` | `GEZETTE PLAAT` | `ja` | `>=1` | Probleemgeval thickness/unfold: handmatige geometrie-inspectie bevestigt constante dikte `5 mm` ondanks huidige unfold-failures |
| `10000182371_Rev_01.step` | `2.5 mm` | `PROFIEL` | `nee` | `0` | Handmatige geometrie-inspectie: cilindrisch profiel/buisdeel met dominante radii `10` en `12.5 mm`, wanddikte `2.5 mm` |
| `803143-7015.stp` | `2 mm` | `PROFIEL` | `nee` | `0` | Handmatige geometrie-inspectie: rond buisprofiel ca. `OD 40 mm`, `ID 36 mm`, lengte ca. `2620 mm` |
| `10000986417_Rev_00.step` | `n.v.t.` | `SAMENSTELLING / NON-SHEET` | `nee` | `0` | Referentiegeval buiten plaatwerk; geen unfold-kandidaat |

## Stap 3 en 4: Main Versus Branch

Deze sectie wordt pas ingevuld nadat stap 1 en stap 2 expliciet akkoord zijn.

| Part | Main thickness | Branch thickness | Main classification | Branch classification | Main unfold | Branch unfold | Main bends | Branch bends | Main holes | Branch holes | Oordeel |
|---|---:|---:|---|---|---|---|---:|---:|---:|---:|---|
| `05-01-5340.STEP` |  |  |  |  |  |  |  |  |  |  |  |
| `336027_rev[B].STEP` |  |  |  |  |  |  |  |  |  |  |  |
| `10000362951_Rev_01.step` |  |  |  |  |  |  |  |  |  |  |  |
| `10000869069_Rev_00.step` |  |  |  |  |  |  |  |  |  |  |  |
| `10001073529_Rev_00.step` |  |  |  |  |  |  |  |  |  |  |  |
| `10001073530_Rev_00.stp` |  | `5.0 mm` |  | `GEBOGEN PLAATWERK / COMPLEX` |  | `nee` |  | `5` |  | `37` | Branch: dikte en bends correct, unfold faalt nog |
| `10000182371_Rev_01.step` |  |  |  |  |  |  |  |  |  |  |  |
| `803143-7015.stp` |  |  |  |  |  |  |  |  |  |  |  |
| `10000986417_Rev_00.step` |  |  |  |  |  |  |  |  |  |  |  |

## Afwijkingen En Notities

Gebruik dit blok om per onderdeel kort vast te leggen:

1. Wat is veranderd.
2. Waarom is het veranderd.
3. Gewenst, acceptabel, onverklaard of ongewenst.
4. Vervolgactie nodig ja of nee.

### `05-01-5340.STEP`

- Directe geometrie-inspectie buiten de pipeline wijst op een rechthoekig kokerprofiel.
- Bounding box hoofdsolid: ca. `20 x 775 x 40 mm`.
- Buiten- en binnenvlakken liggen op ongeveer `x = +/-10` en `x = +/-7`, en op `z = +/-20` en `z = +/-17`.
- Daaruit volgt een wanddikte van ongeveer `3 mm`.
- Verwachte uitkomst voor validatie: `PROFIEL`, geen unfold, `0` zettingen.

### `336027_rev[B].STEP`

- Directe geometrie-inspectie buiten de pipeline wijst op een vlak plaatdeel.
- Bounding box hoofdsolid: ca. `99 x 400 x 3 mm`.
- Er is 1 solid met veel vlakke en cilindrische faces; de cilindrische faces horen bij gaten/features, niet bij bends.
- Grootste vlakke faces zijn tweemaal ca. `21008.934 mm²`, passend bij de twee hoofdzijden van een vlakke plaat.
- Verwachte uitkomst voor validatie: `PLAAT (vlak)`, dikte `3 mm`, geen unfold, `0` zettingen.

### `10000362951_Rev_01.step`

- Directe geometrie-inspectie buiten de pipeline wijst op een eenvoudige gezette plaat.
- Bounding box hoofdsolid: ca. `53 x 81 x 123 mm`.
- Meerdere planaire face-paren liggen consequent `5 mm` uit elkaar, onder meer op `z = 0/5`, `x = -28/-23`, `x = -43/-38` en een schuin vlakpaar op `-48.005/-43.005`.
- Cilinderparen met dezelfde as tonen radii `5` en `10 mm`, wat past bij constante plaatdikte `5 mm` rond bends.
- Verwachte uitkomst voor validatie: `GEZETTE PLAAT`, dikte `5 mm`, unfold `ja`, minstens één zetting.

### `10000869069_Rev_00.step`

- Directe geometrie-inspectie buiten de pipeline wijst op een eenvoudige gezette plaat.
- Bounding box hoofdsolid: ca. `68.5 x 854.5 x 65 mm`.
- Grote vlakke face-paren liggen consequent `5 mm` uit elkaar, onder meer op `z = 0/5` en `x = 25.625/30.625`.
- Cilinderparen met dezelfde as tonen radii `5` en `10 mm`, wat past bij constante plaatdikte `5 mm` rond bends.
- Verwachte uitkomst voor validatie: `GEZETTE PLAAT`, dikte `5 mm`, unfold `ja`, minstens één zetting.

### `10001073529_Rev_00.step`

- Directe geometrie-inspectie buiten de pipeline wijst op een complexere gezette plaat.
- Bounding box hoofdsolid: ca. `100 x 1903 x 95 mm`.
- Grootste vlakke face-paren liggen consequent `5 mm` uit elkaar, onder meer op `z = 0/-5` en `x = 45/50`.
- Cilinderparen met dezelfde as tonen radii `5` en `10 mm`, wat past bij constante plaatdikte `5 mm` rond bends.
- Verwachte uitkomst voor validatie: `GEZETTE PLAAT`, dikte `5 mm`, unfold `ja`, minstens één zetting.

### `10001073530_Rev_00.stp`

- Directe geometrie-inspectie buiten de pipeline wijst op een complexere gezette plaat.
- Bounding box hoofdsolid: ca. `100 x 1903 x 60 mm`.
- Grootste vlakke face-paren liggen consequent `5 mm` uit elkaar, onder meer op `z = 0/-5` en `x = 45/50`.
- Cilinderparen met dezelfde as tonen radii `5` en `10 mm`, wat past bij constante plaatdikte `5 mm` rond bends.
- Verwachte uitkomst voor validatie: `GEZETTE PLAAT`, dikte `5 mm`, unfold `ja`, minstens één zetting.
- Dit blijft het doelgerichte probleemgeval, omdat de huidige pipeline ondanks deze geometrie nog steeds op thickness/unfold kan falen.
- Branch-run op `2026-04-02` via `run.py --analyze` geeft nu wel correcte analyse-uitkomst voor dikte en bends: `Dikte 5.0 mm`, `Zettingen 5`.
- Unfold faalt nog steeds inhoudelijk: `Interne SheetMetal fout tijdens unfold: TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`.
- In dezelfde run worden daarnaast ook `SheetTree error=3` meldingen gezien op meerdere base faces (`Plaatdikte ongeldig voor dit vlak`, `Ongeldige dikte - plaatdikte niet consistent of te complex`).
- Hole-detectie in dezelfde branch-run: `37` totaal (`30` cilindrisch, `7` shaped).
- Let op: de timing/samenvatting van de run markeert stap `[5/7] Unfold` nog als `OK`, terwijl de functionele unfold feitelijk is mislukt. Dat is een aparte statusrapportage-bug.

### `10000182371_Rev_01.step`

- Directe geometrie-inspectie buiten de pipeline wijst op een profiel/buisdeel, niet op plaatwerk.
- Bounding box hoofdsolid: ca. `27.06 x 27.06 x 133 mm`.
- Face-verdeling: vooral cilindrische huiden (`14` cylinders, `5` planes, `2` torus, `2` cone), wat niet past bij een vlak of gezet plaatdeel.
- Dominante cilinderparen op dezelfde as tonen radii `10` en `12.5 mm`, passend bij een wanddikte van `2.5 mm`.
- Verwachte uitkomst voor validatie: `PROFIEL`, geen unfold, `0` zettingen.

### `803143-7015.stp`

- Directe geometrie-inspectie buiten de pipeline wijst op een rond profiel of buisdeel, niet op plaatwerk.
- Bounding box hoofdsolid: ca. `40 x 40 x 2620 mm`.
- Face-verdeling is eenvoudig: `4` cilindrische huiden en `2` vlakke eindvlakken.
- Cilinderparen op dezelfde as tonen radii `18` en `20 mm`, passend bij een wanddikte van `2 mm`.
- Verwachte uitkomst voor validatie: `PROFIEL`, geen unfold, `0` zettingen.

### `10000986417_Rev_00.step`

- Referentiegeval voor samenstelling of non-sheet gedrag binnen deze ronde.
- Dit onderdeel valt buiten de scope van plaatdikte- en unfold-validatie voor plaatwerk.
- Verwachte uitkomst voor validatie: `SAMENSTELLING / NON-SHEET`, geen unfold, `0` zettingen.

## Volgende Fase

Stap 2 is afgerond. De volgende actieve validatiefase is unfold-validatie op dezelfde bevroren testset.

Focus voor de volgende fase:

1. `unfold success/fail`
2. foutredenen per part
3. aantal zettingen uit de run
4. waar beschikbaar flat output, uitslag en plaatmaten