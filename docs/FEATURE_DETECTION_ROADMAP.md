# Feature Detection Roadmap (v3)

Doel: bouw een feature-aware pipeline die classificatie robuuster maakt bij complexe platen en profielen, zonder de huidige pipeline te breken.

---

## Doelen

- Verhoog classificatie-accuratesse naar 90-95% op de vaste set STEP-bestanden.
- Herken productie-features (gaten, sleuven, pockets) expliciet en herleid productie-intent.
- Behoud huidige outputs (PDF, Excel, XML) en bestaande CLI-routes.
- Maak de beslisregels traceerbaar (uitlegbaar voor productie).

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

---

## Milestones

M1. Specificatie + datascope
- Definieer feature types en criteria
- Vastzetten testset (bestaande 5 STEP files + 2 nieuwe)

M2. Feature library (basis)
- Cylindrische gaten
- Sleuven / shape holes
- Enkelvoudige pockets

M3. Base body extractie
- Feature suppression strategie
- Validatie van base body stabiliteit

M4. Classifier v3
- Plaat/profiel/anders op base body
- Feature-aware uitzonderingen (DIN/EN/ISO blijft in export)

M5. Integratie en rapportage
- Rapporten met feature summary
- Export mapping naar ERP

M6. Validatie
- Accuracy rapport op alle files
- Vergelijking v2 vs v3

---

## Test en acceptatie

- Gebruik `test_final_verification.py` als baseline
- Voeg `test_feature_detection_v3.py` toe met:
  - Expected feature counts
  - Base body dimensies binnen tolerantie
  - Classificatie consistent met v2 op eenvoudige modellen

---

## Beslissingen nodig

- Preciese acceptatiecriteria voor v3 (accuracy drempel)
- Definitie van feature priority (bij conflicts)
- Release plan: aparte tag of release notes

---

## Risico's

- Complexe features kunnen base body vervormen
- Feature detection kan meer rekenkosten vragen
- Foutieve feature-suppressie kan classificatie verslechteren

---

## Referenties

- [docs/ENGINE.md](ENGINE.md)
- [CLASSIFICATION_METHODOLOGY.md](../CLASSIFICATION_METHODOLOGY.md)
