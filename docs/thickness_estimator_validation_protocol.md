# Thickness Estimator Validatieprotocol

## Doel

Dit protocol beschrijft hoe de branch `Thicknessestimator` stapsgewijs wordt gevalideerd voordat wijzigingen verantwoord naar `main` kunnen worden gemerged.

De focus ligt eerst op correcte diktebepaling en daarna pas op de impact op unfold.

Belangrijke werkwijze:

1. We voeren het protocol strikt sequentieel uit.
2. We ronden steeds eerst de huidige stap af.
3. Pas bij een expliciete `GO` gaat de validatie door naar de volgende stap.
4. Bij `NO-GO` stopt de validatie en wordt eerst de oorzaak opgelost.

## Waarom Aparte Validatie

In de huidige pipeline wordt dikte niet pas tijdens unfold bepaald. De eerste numerieke dikte ontstaat al in de analysefase via `manufacturing_pipeline/analysis/part_analyzer.py`.

Pas daarna gebruikt de runtime-flow die analyse in `manufacturing_pipeline/core/runtime_analysis.py`, en alleen voor gebogen plaatwerk wordt later unfold geprobeerd via `manufacturing_pipeline/core/runtime_unfold.py`.

Daarom moeten diktevalidatie en unfold-validatie gescheiden worden beoordeeld:

1. Eerst bewijzen dat de nieuwe thickness estimator beter of minstens niet slechter is dan `main`.
2. Daarna pas beoordelen of unfold hierdoor verbetert of nog aparte fouten bevat.

## Pipeline-Context

De functionele volgorde in de pipeline is:

1. STEP laden en geometrie analyseren.
2. Dikte bepalen in de analysefase.
3. Onderdeel classificeren.
4. Features detecteren.
5. Alleen voor gebogen plaatwerk: unfold proberen.

Dit betekent:

- Dikte hoort primair bij analyse, niet bij unfold.
- Unfold mag een latere correctie of extra controle doen, maar is niet de eerste bron van waarheid voor dikte.

## Scope Van Dit Protocol

Deze validatie heeft minimaal betrekking op:

- `manufacturing_pipeline/analysis/part_analyzer.py`
- `manufacturing_pipeline/analysis/thickness_estimator.py`
- `manufacturing_pipeline/core/runtime_analysis.py`
- `manufacturing_pipeline/core/runtime_unfold.py`
- `docs/archive/reference/ARCHIVE_Unfold_review.md`

## Validatiedoelen

De branch is pas merge-klaar als onderstaande vragen positief beantwoord kunnen worden:

1. Bepaalt de branch de plaatdikte correcter dan `main`?
2. Verandert de classificatie alleen waar dat gewenst is?
3. Verbetert unfold of blijft deze minstens stabiel?
4. Zijn eventuele regressies uitlegbaar en acceptabel?
5. Is de impact op downstream output beheersbaar?

## Testset Samenstellen

Gebruik een vaste regressieset van STEP-bestanden. Niet alleen het probleemgeval.

Aanbevolen minimale set:

1. Twee vlakke platen.
2. Twee eenvoudige gezette platen.
3. Twee complexere gezette platen.
4. Het probleemgeval `10001073530_Rev_00.stp`.
5. Een of twee onderdelen die geen plaatwerk zijn.
6. Optioneel een deel met veel gaten of uitsparingen.

De set moet tijdens de hele validatie gelijk blijven.

## Bevroren Testset Ronde 1

Voor deze validatieronde wordt de testset nu expliciet bevroren op onderstaande bestanden.

Belangrijk:

- Deze lijst verandert niet meer tijdens deze validatieronde.
- De kolom `Validatierol` beschrijft de beoogde spreiding van de set.
- De exacte engineering-waarheid per onderdeel wordt pas in stap 2 ingevuld.

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

Deze bevroren set dekt daarmee:

1. Twee vlakke plaat-kandidaten.
2. Twee eenvoudige gezette platen.
3. Twee complexere gezette platen, inclusief het probleemgeval.
4. Twee duidelijke niet-plaatwerk-kandidaten.
5. Eén samenstelling/non-sheet referentie.

De invulmatrix voor deze ronde staat in `docs/thickness_estimator_validation_matrix.md`.

## Go/No-Go Regels Per Stap

Dit protocol wordt niet als bulk-run uitgevoerd. Elke stap heeft een stopmoment.

### Stap 1: Testset Bevriezen

Doel:

1. De validatieset inhoudelijk vastzetten.
2. Bevestigen dat alle gekozen bestanden bestaan en bewust zijn geselecteerd.
3. Vastleggen dat tijdens ronde 1 geen STEP-bestanden meer worden toegevoegd of vervangen.

`GO` naar stap 2 als:

1. De lijst compleet is.
2. Alle paden bestaan.
3. De validatierol per bestand akkoord is.

`NO-GO` als:

1. Bestandsnamen of paden niet kloppen.
2. De set niet representatief genoeg is.
3. Er twijfel is over de rol van een bestand.

Huidige status ronde 1:

- Technisch: `GO`
- Inhoudelijk: `GO`
- Stapstatus: afgerond op `2026-04-02`

### Stap 2: Verwachte Waarheid Vastleggen

Doel:

1. Per STEP de engineering-verwachting noteren.
2. Verwachte dikte, classificatie en unfold-verwachting handmatig vastleggen.

`GO` naar stap 3 als:

1. Voor elk bestand minimaal de verwachte classificatie bekend is.
2. Voor kritieke onderdelen de verwachte dikte bekend is.
3. Het probleemgeval `10001073530_Rev_00.stp` expliciet op `5 mm` staat.

`NO-GO` als:

1. De waarheid nog vooral uit pipeline-output komt.
2. Kritieke verwachtingen ontbreken.

Huidige status ronde 1:

- Technisch: `GO`
- Inhoudelijk: `GO`
- Stapstatus: afgerond op `2026-04-02`

### Stap 3: Baseline Op Main Draaien

Doel:

1. Voor elk STEP-bestand de huidige `main`-uitkomst vastleggen.
2. Nog geen oordeel geven, alleen de baseline registreren.

`GO` naar stap 4 als:

1. Alle runs op `main` voltooid zijn.
2. De matrix volledig is ingevuld voor `main`.

`NO-GO` als:

1. Runs incompleet zijn.
2. Outputbestanden ontbreken.
3. Er onduidelijkheid is over welke code of branch werkelijk draaide.

### Stap 4: Branch Thicknessestimator Draaien

Doel:

1. Exact dezelfde STEP-set op de branch draaien.
2. Dezelfde velden invullen als voor `main`.

`GO` naar stap 5 als:

1. Alle branch-runs voltooid zijn.
2. De matrix volledig is ingevuld.

`NO-GO` als:

1. Niet alle STEP's zijn uitgevoerd.
2. Branch-output niet reproduceerbaar is.

### Stap 5: Dikte Eerst Beoordelen

Doel:

1. Eerst alleen thickness vergelijken.
2. Nog niet doorgaan naar unfold-conclusies als thickness nog niet stabiel is.

`GO` naar stap 6 als:

1. De dikte-uitkomsten uitlegbaar zijn.
2. Er geen onverklaarde grote regressies zijn.
3. Het probleemgeval inhoudelijk verbetert.

`NO-GO` als:

1. Dikte nog fout of onverklaard is.
2. Nieuwe regressies eerst opgelost moeten worden.

### Stap 6: Classificatie Beoordelen

Doel:

1. Controleren of diktewijzigingen gewenste classificatie-impact hebben.

`GO` naar stap 7 als:

1. Classificatie gelijk blijft waar dat correct is.
2. Wijzigingen logisch en verdedigbaar zijn.

`NO-GO` als:

1. Niet-plaatwerk onterecht plaatwerk wordt.
2. Correct plaatwerk onterecht terugvalt.

### Stap 7: Unfold Pas Daarna Beoordelen

Doel:

1. Pas nu unfold evalueren op basis van een geaccepteerde diktebasis.

`GO` naar merge-besluit als:

1. Unfold gelijk blijft of verbetert.
2. Failures beter verklaarbaar worden.

`NO-GO` als:

1. Unfold alleen schijnbaar verbetert op foutieve dikte.
2. Nieuwe regressies ontstaan in flat output of sheet-metal validatie.

## Huidige Fase

Ronde 1 staat nu op het volgende punt:

1. Stap 1: `GO`
2. Stap 2: `GO`
3. Volgende actieve inhoudelijke fase: unfold-validatie op de bevroren testset

Praktisch betekent dit:

- De verwachte waarheid voor dikte, classificatie en zettingen is voldoende vastgelegd.
- De volgende validatie concentreert zich op `unfold success/fail`, foutredenen, en waar beschikbaar flat output.
- Nieuwe dikte-discussies vallen alleen nog terug open als een unfold-resultaat daar direct aanleiding toe geeft.

## Per STEP Handmatig Vastleggen

Voor elk testbestand wordt vooraf een referentie ingevuld op basis van engineering-kennis of handmatige inspectie:

1. Verwachte dikte.
2. Verwachte classificatie.
3. Verwacht wel of geen unfold.
4. Verwacht aantal zettingen als dat bekend is.
5. Verwachte vlakke maat of uitslag als dat bekend is.

Belangrijk:
De verwachting mag niet uit de huidige pipeline zelf komen.

## Uitvoerstappen

Voor elk STEP-bestand voer je eerst dezelfde run op `main` uit en daarna exact dezelfde run op de branch `Thicknessestimator`.

Per run leg je minimaal vast:

1. Category.
2. Type.
3. Thickness.
4. Constant thickness ja of nee.
5. Number of bends.
6. Unfold success of fail.
7. Foutmelding bij unfold.
8. Holes totaal.
9. Totale snijlengte als beschikbaar.
10. Flat length en flat width als beschikbaar.

## Te Vergelijken Bronnen

Gebruik per run dezelfde outputbronnen:

- console-output van `run.py`
- analysebestand in `data/output`
- timingbestand in `data/output`
- eventuele debugregels uit FreeCAD-unfold
- viewer alleen als secundaire controle, niet als primaire waarheid

## Vergelijkingsmatrix

Houd een vaste tabel bij met per STEP:

| Part | Expected thickness | Main thickness | Branch thickness | Expected classification | Main classification | Branch classification | Main unfold | Branch unfold | Oordeel |
|---|---:|---:|---:|---|---|---|---|---|---|

Onder de tabel noteer je per afwijking:

1. Wat is veranderd.
2. Waarom is het veranderd.
3. Is dit gewenst, acceptabel of ongewenst.
4. Is vervolgactie nodig.

## Beoordeling Van Dikte

Dikte wordt eerst apart beoordeeld, nog zonder unfold-conclusie.

Een STEP krijgt:

1. `PASS` als branch dichter bij de verwachte dikte zit dan `main`.
2. `PASS` als branch correct blijft waar `main` al correct was.
3. `FAIL` als branch slechter wordt dan `main`.
4. `REVIEW` als de uitkomst verandert maar de verwachte waarheid nog niet hard vastligt.

## Beoordeling Van Classificatie

Controleer of nieuwe dikte-effecten doorwerken in classificatie.

Classificatie is acceptabel als:

1. Verbeteringen logisch zijn.
2. Correcte bestaande classificaties behouden blijven.
3. Niet-plaatwerk niet ineens onterecht plaatwerk wordt.
4. Gebogen plaatwerk niet door verkeerde dikte terugvalt naar een andere categorie.

## Beoordeling Van Unfold

Unfold wordt pas beoordeeld nadat dikte apart is goedgekeurd.

Controleer:

1. Succesratio omhoog, gelijk of omlaag.
2. Aantal `invalid thickness` meldingen.
3. Aantal `SheetTree error` meldingen.
4. Of flat output beschikbaar komt waar verwacht.
5. Of er geen false positives ontstaan.

Belangrijke regel:
Een betere unfold op basis van foutieve dikte telt niet als echte verbetering.

## Acceptatiecriteria Voor Merge Van Alleen Thickness Estimator

De thickness estimator mag pas richting `main` als minimaal het volgende gehaald wordt:

1. Geen regressie op bekende correcte vlakke platen.
2. `10001073530_Rev_00.stp` gaat naar de juiste dikte van `5 mm`.
3. Minstens 80 procent van de testset blijft gelijk of verbetert op dikte.
4. Geen onverwachte verslechtering van classificatie bij niet-plaatwerk.
5. Debugreden van de estimator is per onderdeel uitlegbaar.

## Acceptatiecriteria Voor Latere Unfold-Merge

Pas nadat thickness akkoord is:

1. Unfold-success rate daalt niet.
2. `invalid thickness` failures nemen af op relevante parts.
3. Nieuwe unfold-fixes veroorzaken geen onterechte unfolds.
4. Flat output is geometrisch plausibel.
5. Falen levert specifiekere en bruikbare foutmeldingen op.

## Aanbevolen Merge-Strategie

Gebruik geen grote gecombineerde merge.

Aanbevolen volgorde:

1. Commit alleen de thickness estimator en integratie in `manufacturing_pipeline/analysis/part_analyzer.py`.
2. Commit daarna alleen tests voor de estimator.
3. Commit daarna pas documentatie-updates.
4. Losse unfold-fixes daarna apart in `manufacturing_pipeline/core/runtime_unfold.py`.

Voordeel:

- thickness kan zelfstandig worden gevalideerd
- unfold kan later apart worden beoordeeld
- regressies blijven herleidbaar

## Uitvoervolgorde In De Praktijk

Voer het protocol in deze volgorde uit, met stopmoment na iedere stap:

1. Stap 1: testset vastleggen en `GO/NO-GO` beslissen.
2. Stap 2: verwachte waarheid per STEP noteren en opnieuw `GO/NO-GO` beslissen.
3. Stap 3: baseline runs op `main` uitvoeren.
4. Stap 4: branch runs op `Thicknessestimator` uitvoeren.
5. Stap 5: eerst alleen dikte vergelijken.
6. Stap 6: daarna classificatie vergelijken.
7. Stap 7: pas daarna unfold vergelijken.
8. Alle delta's labelen als gewenst, acceptabel, onverklaard of ongewenst.
9. Alleen bij voldoende resultaat thickness richting `main` brengen.
10. Daarna verder met unfold-validatie als aparte fase.

## Stopcriteria

De validatie stopt en merge wordt uitgesteld als:

1. Meerdere STEP-bestanden onverklaarde dikteverschuivingen tonen.
2. Niet-plaatwerk foutief als plaatwerk wordt geclassificeerd.
3. Unfold ogenschijnlijk verbetert terwijl dikte nog fout is.
4. De branch andere pipeline-output wijzigt zonder duidelijke verklaring.

## Eerste Concrete Uitvoerset

Start met deze minimale set:

1. `10001073530_Rev_00.stp`.
2. Een vlakke plaat uit `data/stepfile`.
3. Een eenvoudige gezette plaat uit `data/stepfile`.
4. Een complexer plaatwerkdeel uit `data/stepfile`.
5. Een niet-plaatwerk onderdeel uit `data/stepfile`.

## Resultaat Van Deze Fase

Na uitvoering van dit protocol moet een van deze conclusies mogelijk zijn:

1. Thickness estimator is veilig genoeg om apart naar `main` te mergen.
2. Thickness estimator is inhoudelijk beter, maar nog niet breed genoeg gevalideerd.
3. Thickness estimator lost het doelgeval op, maar veroorzaakt te veel regressierisico.
4. Thickness estimator moet eerst verder worden aangescherpt voordat merge verantwoord is.