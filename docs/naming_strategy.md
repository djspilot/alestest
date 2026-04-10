# Naamgeving Strategie Implementatie

## Generiek Plan

**Als de solid geen eigen unieke naam heeft:** gebruik `stp_naam + "-p1"`  
**Anders:** gebruik de solid naam uit de STEP file

### XML Output Structuur

```xml
<Sheet_PartName>stepfile naam</Sheet_PartName>
<Sheet_Name>solid naam OF stp naam + "-p1"</Sheet_Name>
```

## Implementatie Details

### 1. Naming Strategy Pipeline
**Bestand:** `manufacturing_pipeline/reporting/xml_exporter.py`  
**Regels:** 354-428

```python
# Base name for generated part names
base_name = step_path.stem  # Bijv. "10001075561_Rev_00"
```

**Prioriteit volgorde:**
1. **STEP assembly structure names** → Gebruik namen uit `NEXT_ASSEMBLY_USAGE_OCCURRENCE`
2. **STEP product names** → Gebruik namen uit `PRODUCT('10001075562_Rev_00')`
3. **Generated fallback** → `f"{base_name}-p{generated_idx}"` (bijv. "10001075561_Rev_00-p1")

**Code (regel 410-421):**
```python
elif not new_part_name and step_product_names and product_name_idx < len(step_product_names):
    # Use next PRODUCT_DEFINITION name
    new_part_name = step_product_names[product_name_idx]
    product_name_idx += 1

if not new_part_name:
    # Generate name: "Silo 2-p1", "Silo 2-p2", etc.
    new_part_name = f"{base_name}-p{generated_idx}"
    generated_idx += 1

# Update BOM item with proper name
bom_item['part_name'] = new_part_name
```

### 2. XML Export voor Sheet Items
**Bestand:** `manufacturing_pipeline/reporting/xml_exporter.py`  
**Functie:** `_process_plaat_item()`  
**Regels:** 677-1120

**Parameter doorgave (regel 463-469):**
```python
calc_result = _process_plaat_item(
    bom_item,
    step_path,
    step_path.stem,      # ← source_step_name = STEP filenaam
    work_dir,
    material,
    k_factor,
    part_solid,
    reference_values,
)
```

**Naamgeving logic (regel 694-707):**
```python
part_name = bom_item.get('part_name', 'Unknown')  # Van naming strategy
quantity = bom_item.get('quantity', 1)
output_part_name = source_step_name           # ALTIJD stepfile naam
output_sheet_name = part_name                 # Solid naam OF fallback

# XML structuur
calc_result = ET.Element('CalculationResult')
ET.SubElement(calc_result, 'Sheet_PartName').text = output_part_name
ET.SubElement(calc_result, 'Sheet_Name').text = output_sheet_name
```

### 3. STEP Naam Extractie
**Bestand:** `manufacturing_pipeline/analysis/assembly_analysis.py`  
**Functie:** `parse_step_product_names()`  
**Regels:** 921-1018

**Prioriteit hiërarchie:**
1. `PRODUCT('10001075562_Rev_00', ...)` namen
2. `SHAPE_REPRESENTATION('10001075562_Rev_00', ...)` namen  
3. `PRODUCT_DEFINITION('...', '10001075562_Rev_00', ...)` namen (legacy)

**Filtering (regel 964-984):**
- Exclusief: Assembly aliases uit FILE_NAME header (_000 suffix)
- Exclusief: Materiaal labels (AISI patterns)
- Exclusief: Skeleton geometry strings
- Exclusief: NONE waarden
- Exclusief: Generieke namen (Part_1, Plaatdeel, etc.)

## Verificatie Test

### Test Input
**Bestand:** `data/input/10001075561_Rev_00.step`

**STEP entities:**
- Regel 1167: `PRODUCT('10001075562_Rev_00','10001075562_Rev_00','',...)`
- Regel 1699: `PRODUCT('10001075563_Rev_00','10001075563_Rev_00','',...)`

### Test Output
**Bestand:** `data/output/test_naming_verify.xml`

```xml
<CalculationResult>
  <Sheet_PartName>10001075561_Rev_00</Sheet_PartName>      <!-- STEP filenaam ✓ -->
  <Sheet_Name>10001075563_Rev_00</Sheet_Name>              <!-- Solid naam uit STEP ✓ -->
  ...
</CalculationResult>
```

### Fallback Scenario (geen solid naam)

Als een STEP file **geen** PRODUCT namen bevat:

**Verwachte output:**
```xml
<Sheet_PartName>10001075561_Rev_00</Sheet_PartName>      <!-- STEP filenaam -->
<Sheet_Name>10001075561_Rev_00-p1</Sheet_Name>           <!-- Fallback: stp naam + "-p1" -->
```

**Code flow:**
1. `parse_step_product_names()` retourneert lege lijst (geen namen gevonden)
2. Naming strategy gebruikt fallback: `f"{base_name}-p{generated_idx}"` 
3. `bom_item['part_name']` wordt `"10001075561_Rev_00-p1"`
4. `output_sheet_name = part_name` → XML krijgt fallback naam

## Belangrijke Notities

### Assembly/VPS afspraak: unieke geometrie, behoud van count

Voor assemblies met herhaalde onderdelen geldt:

- de **semantische identiteit** blijft de STEP/XCAF-partnaam;
- het **aantal** blijft de occurrence-count uit de assembly-structuur;
- de VPS-pipeline mag identieke occurrences als **één unieke solid** analyseren;
- XML/BOM-uitvoer moet daarna wel het oorspronkelijke aantal blijven schrijven in `Sheet_Count`, `Tube_Count` of `Others_Count`.

Concreet voor `10040878_1.stp` betekent dit bijvoorbeeld:

- `10040853_1.2` kan één keer geometrisch geanalyseerd worden;
- de count blijft `2` omdat de assembly twee occurrences bevat.

### Tijdelijke STEP-bestandsnamen zijn niet normatief

Bij het uitsplitsen van assemblies mogen namen voor tijdelijke STEP-bestanden worden gesanitizeerd voor filesystemgebruik, bijvoorbeeld `10040853_1.2` -> `10040853_1_2.step`.

Die transportnaam is **niet** de autoritatieve partnaam. De normatieve naam blijft de oorspronkelijke STEP/XCAF-naam en moet in resultaat- en XML-identiteit behouden blijven.

### Reference XML Gebruik
**Reference XML wordt NIET gebruikt voor naamgeving!**

Regel 698-700:
```python
if reference_values is not None:
    # Reference XML is for validating/enriching metrics, not for overriding naming
    ref_qty = int(float(reference_values.get('qty', quantity) or quantity))
```

Reference XML is **alleen** voor:
- Dimensie validatie (lengte, breedte, dikte)
- Zettingen telling (bend count)
- Gaten telling (hole count)
- Kwantiteit verificatie

### Others Items (niet plaat/profiel)
**Bestand:** `manufacturing_pipeline/reporting/xml_exporter.py`  
**Functie:** `_process_others_item()`  
**Regels:** 1176-1186

```python
def _process_others_item(bom_item: Dict[str, Any]) -> Optional[ET.Element]:
    calc_result = ET.Element('CalculationResult')
    ET.SubElement(calc_result, 'Others_PartName').text = bom_item.get('part_name', 'Unknown')
    ET.SubElement(calc_result, 'Others_Name').text = bom_item.get('part_name', 'Unknown')
    ET.SubElement(calc_result, 'Others_Type').text = 'Other'
    ET.SubElement(calc_result, 'Others_Count').text = str(bom_item.get('quantity', 1))
    return calc_result
```

**Others items gebruiken dezelfde naming strategy,** maar:
- `Others_PartName` = solid naam (niet stepfile naam)
- `Others_Name` = solid naam (niet stepfile naam)

**TODO:** Consistency verbetering overwegen voor Others items?

### Tube/Profiel Items
**Bestand:** `manufacturing_pipeline/reporting/xml_exporter.py`  
**Functie:** `_process_profiel_item()`  
**Regels:** 1160-1173

```python
def _process_profiel_item(bom_item: Dict[str, Any], source_step_name: str = '') -> Optional[ET.Element]:
    part_name = bom_item.get('part_name', 'Unknown')
    quantity = bom_item.get('quantity', 1)
    output_part_name = source_step_name if source_step_name else part_name
```

**Tube items gebruiken source_step_name voor Tube_PartName,** net als Sheet items.

## Status

✅ **GENERIEK OPGELOST** - Het plan is correct geïmplementeerd:
- Sheet_PartName = stepfile naam (altijd)
- Sheet_Name = solid naam (van STEP) OF stepfile naam + "-p1" (fallback)
- Naming komt exclusief uit STEP file
- Reference XML wordt niet gebruikt voor naming
- Fallback mechanisme werkt met generische pattern: `{stepfile}-p{index}`

## Datum
4 maart 2026
