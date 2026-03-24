# Profile Pipeline

Headless Python module voor het classificeren van stalen profielen uit STEP-bestanden. Geen visuele componenten — puur data in, data uit. Bedoeld om in andere pipelines te pluggen.

## Installatie

Vereisten:
```bash
conda install -c conda-forge pythonocc-core shapely numpy scipy
```

## Gebruik

### Als Python module

```python
from profile_pipeline import classify_step_file, PipelineConfig

# Standaard (5 secties, alle output)
results = classify_step_file("model.stp")

for solid in results:
    print(solid.name, solid.classification.label)
    # → "Solid 1" "RECHTHOEKIGE_KOKER"

# Aangepaste configuratie
config = PipelineConfig(
    num_sections=3,              # sneller: minder secties
    section_range=(0.20, 0.80),  # vermijd uiteinden
    template_accept_threshold=0.10,  # strenger matchen
    include_vertices=False,      # geen 3D vertices in output
    include_features=True,       # wel section features
    reader_strategy="flat_first",
)

results = classify_step_file(
    "model.stp",
    config=config,
    output_json="output.json",   # optioneel: schrijf JSON
)
```

### Als CLI tool

```bash
# Standaard
python -m profile_pipeline model.stp

# Met opties
python -m profile_pipeline model.stp \
    -n 3 \
    --range-start 0.20 \
    --range-end 0.80 \
    --threshold 0.10 \
    -o result.json \
    -v

# Minimale output (snel, geen polygonen/features)
python -m profile_pipeline model.stp --no-polygons --no-features -n 3
```

### In een bestaande pipeline pluggen

```python
from profile_pipeline import classify_step_solids, PipelineConfig
from step_profile_classifier import read_step_solids_flat

# Je eigen STEP reader
solids = read_step_solids_flat("model.stp")

# Filter op specifieke solids
config = PipelineConfig(
    num_sections=5,
    solid_filter=lambda solid, idx: idx < 10,  # alleen eerste 10
)

results = classify_step_solids(solids, config=config)

# Direct naar je ERP/database
for r in results:
    erp_record = {
        "part_name": r.name,
        "profile_type": r.classification.label,
        "method": r.classification.method,
        "bbox_min": r.bounding_box_min,
        "bbox_max": r.bounding_box_max,
    }
    # db.insert(erp_record)
```

## Configuratie-opties

| Parameter | Default | Beschrijving |
|-----------|---------|-------------|
| `num_sections` | `5` | Aantal dwarsdoorsnedes langs de extrusie-as |
| `section_range` | `(0.15, 0.85)` | Begin- en eindfractie voor sectiepositie |
| `template_accept_threshold` | `0.12` | Max template-afstand voor acceptatie |
| `min_valid_sections` | `3` | Minimum geldige secties voor classificatie |
| `cluster_stability_ratio` | `0.60` | Min fractie secties in dominante cluster |
| `include_vertices` | `False` | 3D vertices meegeven in output |
| `include_polygon_coords` | `True` | Polygoon-coördinaten meegeven |
| `include_features` | `True` | Berekende features meegeven |
| `include_top_matches` | `True` | Template match ranking meegeven |
| `reader_strategy` | `"flat_first"` | STEP reader volgorde |
| `solid_filter` | `None` | Callable `(solid, index) → bool` |

## Output structuur

```python
SolidResult(
    name="Solid 1",
    instance_id="step_0",
    classification=ClassificationResult(
        label="RECHTHOEKIGE_KOKER",
        method="rule",
        variant=None,
    ),
    sections=[SectionResult(...)],
    core_section=SectionResult(...),
    cluster_size=5,
    sections_total=5,
    axis_direction=[0, 0, 1],
    bounding_box_min=[-50, -25, 0],
    bounding_box_max=[50, 25, 1154],
)
```

## Ondersteunde profielen

| Label | Beschrijving |
|-------|-------------|
| `ROND_STAAL` | Massief rond profiel |
| `RONDE_BUIS` | Ronde holle buis |
| `PLAT_STAAL` | Platte stalen strip |
| `RECHTHOEKIGE_KOKER` | Rechthoekige koker (RHS) |
| `I_FAMILY` | I/H profiel (IPE, HEA, HEB) |
| `U_FAMILY` | U profiel (UNP, UPE) |
| `L_FAMILY` | Hoekprofiel |
| `T_FAMILY` | T profiel |
| `ANDERS` | Niet-geclassificeerd |
