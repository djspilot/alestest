# Test Feature Plan (Layer 1)

## Doel
Layer 1 valideert de gedeelde feature-kern voor:
- gaten
- tapgaten
- verzonken gaten

Deze laag test bewust de gedeelde detectie-logica los van classificatie-uitkomst.

## Architectuurbeslissing
De code gebruikt een gedeelde kern voor hole-feature detectie, aangeroepen via wrappers:
- `extract_cut_features_for_sheet(...)` voor vlakke plaat en gezette plaat
- `extract_cut_features_for_profile(...)` voor profiel

Daarom starten we met een feature-gedreven testlaag (Layer 1) i.p.v. direct per classificatie.

## Layer 1 Scope
1. Cylindrische gaten worden als `round` gelabeld als er geen thread/countersink match is.
2. Tapgat-detectie op diameter-match werkt en verhoogt `threaded_holes`.
3. Verzonken gat-detectie krijgt voorrang op tapgat (`countersunk` boven `thread`).
4. Ambigue thread-match (tapped + major) wordt niet als tapgat gelabeld.
5. Vormgaten (`Slot`, `Rect`) geven correcte `hole_types` en contourberekening.

## Implementatie
Layer 1 tests staan in:
- `tests/test_feature_layer1.py`

Deze tests isoleren de feature-kern met gerichte monkeypatches en draaien zonder zware STEP-analyse.

## Vervolg (Layer 2 en 3)
- Layer 2: wrapper-specifiek gedrag (sheet flat-pattern pad, profiel bore-filter)
- Layer 3: end-to-end XML-asserties per classificatie (Sheet_* en Tube_*)
