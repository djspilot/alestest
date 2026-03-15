# ALES Manufacturing Pipeline — Tijdlijn

> Zie [README.md](README.md) voor volledige documentatie, installatie-instructies en gebruik.

## v3.0 — Profile Router Integration (15 maart 2026)

**Nieuw: Pre-routing classificatie**

De pipeline heeft nu een **profile router** die vóór alle analyse draait. Deze bepaalt op basis van cross-sectie analyse welk type onderdeel het is:

| Route | Beschrijving | Profiellabels |
|-------|-------------|---------------|
| **PLAAT** | Vlakke plaat / plaatwerk | `PLAT_STAAL` |
| **PROFIEL** | Stalen profiel (ingekocht) | `I_FAMILY`, `U_FAMILY`, `L_FAMILY`, `T_FAMILY`, `RECHTHOEKIGE_KOKER` |
| **ROND** | Rond staal / buis / draaistuk | `ROND_STAAL`, `RONDE_BUIS` |
| **OVERIG** | Niet-geclassificeerd | `ANDERS` |

**Wat is er veranderd:**
- `manufacturing_pipeline/analysis/profile_classifier.py` — Cross-sectie profiel classifier (template matching + rule-based)
- `manufacturing_pipeline/analysis/router.py` — Router module met `route_step_file()`, `route_solid()`, `map_profile_label()`
- `manufacturing_pipeline/core/models.py` — `RouteCategory` enum (PLAAT/PROFIEL/ROND/OVERIG)
- Quick mode: router draait als stap [2/7] na STEP laden
- Full mode: router draait vóór geometry stages, resultaat in JSON output
- `profile_pipeline/` imports nu uit manufacturing_pipeline (sys.path hack verwijderd)

**Analyse flow (quick mode):**
```
[1/7] STEP laden
[2/7] Profile Router → PLAAT / PROFIEL / ROND / OVERIG
[3/7] AAG Feature Recognition
[4/7] Geometrie analyse
[5/7] Unfold (indien plaatwerk)
[6/7] Gaten detectie
[7/7] Resultaten opslaan
```

---

## v2.3 — GEZETTE PLAAT Feature Validation (10 maart 2026)

- Naamkoppeling (solid → part naam) werkt correct
- CRITICAL BUG: `Sheet_BoxY` incorrect (238mm i.p.v. 272mm)
- NrHoles incorrect: 6 gevonden i.p.v. 11

---

## v2.2 — Profile Robustness + Koker Dikte Fix (4 maart 2026)

- Hard profile override op doorsnede-gedrag (multi-slice cross-section check)
- Rectangular tube dikteberekening gecorrigeerd (analytische hollow-box vergelijking)
- XML output geverifieerd

---

## v2.1.2 — Fase 1: Gaten + Snijdata (3 maart 2026)

- Cut Features Detection voor Plaat/Gezette Plaat
- Gatdetectie: cylindrisch + vormgaten met perimeters
- XML export: Sheet_NrHoles, Sheet_HoleContours, Sheet_HoleRadii, Sheet_OuterContour, Sheet_TotalContour

---

## v2.1.1 — XML Naming Fix (2 maart 2026)

- Sheet_PartName gebruikt nu source STEP filename

---

## v2.1 — Standard Profile Detection (2 maart 2026)

- Hollow tube detection (EN 10210-2)
- Variable thickness profile detection (DIN 1026 UNP, I-beams)
- Bent sheet exclusion
- Generic geometry-based fallback
