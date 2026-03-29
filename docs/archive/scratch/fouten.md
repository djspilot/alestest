Je hebt gelijk - de SVG was te vol en chaotisch. Laat me het op een schonere manier uitleggen:

---

## 🔴 Probleem 1: BoxX en BoxY zijn hetzelfde

**Voorbeeld:** Een plaat van 257.77 × 88.55 mm

```
┌─────────────────────────────────────┐
│                                     │ ▲
│                                     │ │
│           257.77 mm                 │ │ 88.55 mm
│                                     │ │
│                                     │ ▼
└─────────────────────────────────────┘

SpaceClaim zegt:  BoxX = 257.77, BoxY = 88.55  ✅
Pipeline zegt:    BoxX = 257.73, BoxY = 257.73 ❌
                                              ↑
                                          FOUT! Beide gelijk
```

**Oorzaak:** In `xml_exporter.py` worden BoxX én BoxY op de grootste waarde gezet.

---

## 🔴 Probleem 2: Profiel wordt als "plaat" herkend

**Voorbeeld:** Een buis/profiel (MD-20-11302_2.2)

```
     ╭───────╮
    ╱         ╲           SpaceClaim: "anders" (profiel) ✅
   │   (tube)  │          Pipeline:   "plaat"           ❌
    ╲         ╱
     ╰───────╯
```

**Oorzaak:** De router die profielen herkent (`router.py`) wordt NIET gebruikt door de classificatie in `assembly_analysis.py`. Ze zijn niet met elkaar verbonden!

```
HOOR TE ZIJN:                          IS NU:

┌──────────┐      ┌────────────────┐    ┌──────────┐    ┌────────────────┐
│ router.py│ ───► │assembly_analysis│    │ router.py│    │assembly_analysis│
│(herkent  │      │  (gebruikt     │    │(draait   │    │(negeert router │
│ profiel) │      │  router result)│    │ in vacuum)│   │  - eigen logica)│
└──────────┘      └────────────────┘    └──────────┘    └────────────────┘
                         ✅                    ✗                ✗
```

---

## ✅ Wat moet er gebeuren?

| Bestand | Fix |
|---------|-----|
| `xml_exporter.py` | BoxY = tweede grootste dimensie (niet kopie van BoxX) |
| `assembly_analysis.py` | Roep `router.py` aan en gebruik diens profiel-herkenning |

---

Is dit duidelijker? Of wil je een andere vorm van visualisatie?