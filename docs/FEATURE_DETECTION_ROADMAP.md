# Feature Detection Roadmap (v3)

Doel: bouw een feature-aware pipeline die classificatie robuuster maakt bij complexe platen en profielen, zonder de huidige pipeline te breken.

---

## XML uitrol-roadmap (huidige prioriteit)

Onderstaande volgorde is leidend voor de manufacturing pipeline. De feature-detection v3 techniek blijft ondersteunend, maar de uitvoering gebeurt eerst via gecontroleerde XML-invulling per stap.

### Fase 1 — Vlakke plaatdelen: naam, aantallen, afmetingen
- Scope: alleen niet-gezette plaatdelen
- XML velden minimaal: `Sheet_PartName`, `Sheet_Name`, `Sheet_Count`, `Sheet_BoxX`, `Sheet_BoxY`, `Sheet_Thickness`
- Acceptatie: waarden matchen referentie XML per onderdeel

### Fase 2 — Gezette plaatdelen: unfold + vlakke afmetingen
- Scope: gezette plaatdelen met ontvouwpoging
- XML velden minimaal: `Sheet_UnfoldSuccess`, `Sheet_BoxX`, `Sheet_BoxY`, `Sheet_FilePathDXF` (indien beschikbaar)
- Acceptatie: ontvouwde maatvoering volgt referentie XML en fallback is expliciet gelogd

### Fase 3 — Profielen: afmetingen vastleggen
- Scope: profielonderdelen (koker, buis, strip, etc.)
- XML velden minimaal: naam/aantal + profielafmetingen volgens referentie
- Acceptatie: profielmaten per onderdeel gelijk aan verwachte XML output

### Fase 4 — Plaatgaten en snijdata
- Scope: plaatdelen (vlak + gezet)
- XML velden minimaal:
  - `Sheet_NrHoles`, `Sheet_HoleRadii`
  - `Sheet_AreaNoHoles` (bruto), netto-oppervlakte, `Sheet_BoxArea` (`Sheet_BoxX * Sheet_BoxY`)
  - `Sheet_OuterContour`, `Sheet_TotalContour`, gatcontourlengtes
- Acceptatie: gatentelling, diameters en snijlengtes matchen referentie XML

### Fase 5 — Profielgaten en snijdata
- Scope: profielonderdelen met boor-/snijfeatures
- XML velden minimaal: aantal gaten, diameters, gaten-snijlengtes, relevante contourdata
- Acceptatie: profielgatdata komt overeen met referentie XML per onderdeel

### Validatieprincipe (voor alle fases)
- Iedere fase wordt gevalideerd met vaste STEP/XML-paren (input STEP + verwachte XML)
- Release naar volgende fase pas na "match" op de afgesproken velden
- Bij mismatch: veldniveau-diff loggen en fase niet promoveren

---

## Doelen

- Verhoog classificatie-accuratesse naar 90-95% op de vaste set STEP-bestanden.
- Herken productie-features (gaten, sleuven, pockets) expliciet en herleid productie-intent.
- Behoud huidige outputs (PDF, Excel, XML) en bestaande CLI-routes.
- Maak de beslisregels traceerbaar (uitlegbaar voor productie).
- Borg stapsgewijze XML-invulling met referentievalidatie per fase.

## Niet-doelen

- Geen vervanging van alle bestaande analyses in 1 keer.
- Geen breuk in bestaande CLI of API gedrag zonder een opt-in vlag.
- Geen volledig nieuwe dataset of opslagmodel in deze fase.

---

## Architectuur (concept)

Nieuwe modulelaag naast de bestaande analysis pipeline:

- manufacturing_pipeline/feature_detection/
  - base_body.py          # base-body extractie / feature suppression
  - feature_graph.py      # AAG/feature graph en relaties
  - recognizers/          # herkenners per feature-type
  - classifier_v3.py      # classificatie op basis van base body + features
  - pipeline.py           # v3 orchestratie

Koppelingen met bestaande code:

- Reuse: STEP parsing, reporting, export (Excel/XML)
- Vervang: alleen classificatiebeslissing (via v3 pipeline)

---

## Dataflow (hoog niveau)

1. Laad STEP -> solide modellen
2. Bouw adjacency graph (AAG) -> candidate features
3. Detecteer features (holes, slots, pockets)
4. Suppress features -> base body
5. Classificeer base body (plaat/profiel/anders)
6. Voeg feature-info toe aan rapporten

---

## Integratie strategie

- Nieuwe opt-in vlag: `--feature-v3` (alleen als v3 actief is)
- Houd bestaande default flow ongewijzigd
- Maak fallback mogelijk: v3 -> v2 (face-based) bij errors
- Houd XML-export compatibel met bestaande ERP velden en volg de fasevolgorde hierboven

---

## Milestones

M1. XML Fase 1 afronden (vlakke plaatdelen)
- Naamgeving, aantallen, basisafmetingen op referentieniveau
- Validatie op vaste STEP/XML-paarset

M2. XML Fase 2 afronden (gezette plaatdelen)
- Ontvouwingspad stabiel voor productiegebruik
- Ontvouwde afmetingen en statusvelden correct in XML

M3. XML Fase 3 afronden (profielafmetingen)
- Profielmaten betrouwbaar in XML
- Geen regressie op plaatdelen

M4. XML Fase 4 afronden (plaatgaten + snijdata)
- Aantal/diameter gaten + contour/snijlengtes
- Bruto/netto/box-oppervlak gevalideerd

M5. XML Fase 5 afronden (profielgaten)
- Gatvelden en snijdata voor profielen op referentieniveau
- End-to-end ERP-validatie

M6. Feature-v3 verdieping (parallel spoor)
- Feature library (holes/slots/pockets)
- Base-body/classifier verbetering voor hogere robuustheid

---

## Test en acceptatie

- Gebruik `test_final_verification.py` als baseline
- Gebruik per fase een vaste set STEP/XML referentieparen
- Voeg `test_feature_detection_v3.py` toe met:
  - Expected feature counts
  - Base body dimensies binnen tolerantie
  - Classificatie consistent met v2 op eenvoudige modellen
- Voeg XML-fasevalidatie toe met veldniveau checks (naam, aantal, afmetingen, gaten, contouren)

---

## Beslissingen nodig

- Preciese acceptatiecriteria voor v3 (accuracy drempel)
- Definitie van feature priority (bij conflicts)
- Release plan: aparte tag of release notes
- Welke XML velden zijn "hard required" per fase en welke mogen leeg blijven

---

## Risico's

- Complexe features kunnen base body vervormen
- Feature detection kan meer rekenkosten vragen
- Foutieve feature-suppressie kan classificatie verslechteren

---

## Referenties

- [docs/ENGINE.md](ENGINE.md)
- [CLASSIFICATION_METHODOLOGY.md](../CLASSIFICATION_METHODOLOGY.md)
