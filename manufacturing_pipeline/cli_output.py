"""
CLI output utilities.

Pure printing helpers for consistent console output formatting.
"""
from typing import List, Dict, Any, Optional


def print_section_header(title: str, width: int = 60) -> None:
    """Print a section header with separators."""
    print("\n" + "=" * width)
    print(title)
    print("=" * width)


def print_subsection(title: str) -> None:
    """Print a subsection header."""
    print(f"\n[{title}]")


def print_disabled(section: str) -> None:
    """Print that a section is disabled."""
    print(f"\n[{section}] - UITGESCHAKELD")


def format_currency_eur(value: float) -> str:
    """Format value as Euro currency."""
    return f"€{value:.2f}"


def format_hours(value: float) -> str:
    """Format value as hours."""
    return f"{value:.2f} uur"


def print_holes_summary(holes: List[Any], production_only: bool = False) -> None:
    """Print hole detection summary."""
    if production_only:
        return
    print(f"Detected {len(holes)} holes.")
    for i, hole in enumerate(holes[:10]):
        print(f"  Hole {i+1}: Diameter={hole.diameter:.2f}, Depth={hole.depth:.2f}")
    if len(holes) > 10:
        print(f"  ... and {len(holes) - 10} more holes")


def print_geometry_summary(geom_props: Dict, production_only: bool = False) -> None:
    """Print geometry properties summary."""
    if production_only:
        return
    print(f"Volume: {geom_props['volume']:.2f} mm³, Surface Area: {geom_props['surface_area']:.2f} mm²")


def print_iso2768_summary(mfg_requirements: Dict, production_only: bool = False) -> None:
    """Print ISO 2768 tolerance analysis summary."""
    if production_only:
        return
    print("\n[ISO 2768] Tolerance Analysis...")
    iso_rec = mfg_requirements["iso2768_recommendation"]
    print(f"  Recommended: {iso_rec['designation']}")
    print(f"  Tolerance Table:")
    for tol in iso_rec["tolerance_table"]:
        print(f"    {tol['dimension']:.1f}mm: {tol['tolerance']}")


def print_iso286_summary(holes_with_fits: List[Dict], production_only: bool = False) -> None:
    """Print ISO 286 hole & fit analysis summary."""
    if production_only:
        return
    print("\n[ISO 286] Hole & Fit Analysis...")
    print(f"  Analyzed {len(holes_with_fits)} unique hole diameters:")
    for h in holes_with_fits[:5]:
        fit = h["fit_recommendation"]
        print(f"    Ø{h['diameter']:.1f}mm (×{h['count']}): {fit['fit']} - {fit['description']}")
        if h["possible_thread"]:
            print(f"      Possible thread: {h['possible_thread']['designation']}")
    if len(holes_with_fits) > 5:
        print(f"    ... and {len(holes_with_fits) - 5} more diameters")


def print_threads_summary(threads: List[Dict], thread_summary: Dict, iso_standards, production_only: bool = False) -> None:
    """Print thread detection summary."""
    if production_only:
        return
    print(f"  Detected {len(threads)} potential threaded holes:")
    for des, count in sorted(thread_summary.items()):
        print(f"    {des}: {count}× (tap drill: {iso_standards.get_tap_drill_size(des)}mm)")


def print_surface_finish_summary(mfg_requirements: Dict, production_only: bool = False) -> None:
    """Print ISO 1302 surface finish summary."""
    if production_only:
        return
    print("\n[ISO 1302] Surface Finish Requirements...")
    surface_finish = mfg_requirements["surface_finish"]
    print(f"  Default Ra: {surface_finish['default_ra']} μm")
    print(f"  Recommendation: {surface_finish['general_recommendation']}")
    for sf in surface_finish.get("by_face_type", [])[:3]:
        print(f"    {sf['face_type']}: Ra {sf['recommended_ra']} μm ({sf['typical_process']})")


def print_edge_analysis_summary(edge_analysis: Dict, production_only: bool = False) -> None:
    """Print ISO 13715 chamfers & fillets summary."""
    if production_only:
        return
    print("\n[ISO 13715] Chamfers & Fillets...")
    print(f"  Chamfers: {edge_analysis['chamfers']['count']} (avg: {edge_analysis['chamfers']['average_size']}mm)")
    print(f"  Fillets: {edge_analysis['fillets']['count']} (avg radius: {edge_analysis['fillets']['average_radius']}mm)")
    print(f"  Note: {edge_analysis['edge_note']}")


def print_mass_summary(mass_steel: Optional[Dict], mass_alu: Optional[Dict], production_only: bool = False) -> None:
    """Print EN 10025/573 mass estimation summary."""
    if production_only:
        return
    print("\n[EN 10025/573] Mass Estimation...")
    if mass_steel:
        print(f"  Steel S235JR: {mass_steel['primary']['mass_kg']:.2f} kg")
    if mass_alu:
        print(f"  Aluminum 6061: {mass_alu['primary']['mass_kg']:.2f} kg")


def print_manufacturing_process_summary(mfg_requirements: Dict, production_only: bool = False) -> None:
    """Print manufacturing process summary."""
    if production_only:
        return
    print("\n[Manufacturing Process]")
    mfg_proc = mfg_requirements["manufacturing_process"]
    print(f"  Primary: {mfg_proc['primary']}")
    print(f"  Secondary: {', '.join(mfg_proc['secondary'])}")
    print(f"  Complexity: {mfg_proc['complexity']}")


def print_werkvoorbereiding_summary(werkvoorbereiding_data: Dict, modules, production_only: bool = False) -> None:
    """Print werkvoorbereiding (manufacturing preparation) summary."""
    if production_only:
        return
    
    # Cost Estimate
    if modules.cost_estimation:
        cost = werkvoorbereiding_data["cost_estimate"]
        print(f"\n[Kostprijsberekening]")
        print(f"  Kostprijs per stuk: €{cost['cost_per_piece']:.2f}")
        print(f"  Materiaalkosten: €{cost['breakdown']['material']:.2f}")
        print(f"  Bewerkingskosten: €{cost['breakdown']['machining']:.2f}")
        print(f"  Bewerkingstijd: {cost['time_estimate']['total_time_hours']:.2f} uur")
        print(f"  Uurtarief: €{cost['hourly_rate']:.2f}/uur")
    else:
        print_disabled("Kostprijsberekening")

    # Tool List
    if modules.tool_list:
        tools = werkvoorbereiding_data["tool_list"]
        print(f"\n[Gereedschapslijst] ({len(tools)} gereedschappen)")
        for tool in tools[:5]:
            print(f"  - {tool['designation']}: €{tool['estimated_cost']:.2f}")
        if len(tools) > 5:
            print(f"  ... en {len(tools) - 5} meer")
    else:
        print_disabled("Gereedschapslijst")

    # Outsourcing
    if modules.outsourcing:
        outsource = werkvoorbereiding_data["outsourcing"]
        print(f"\n[Uitbesteding]")
        print(f"  Categorie: {outsource['primary_category']}")
        print(f"  Doorlooptijd: {outsource['estimated_lead_time_days']} werkdagen")
        print(f"  Aanbeveling: {outsource['recommendation']}")
    else:
        print_disabled("Uitbesteding")

    # Surface Treatment
    if modules.surface_treatment:
        treatments = werkvoorbereiding_data["surface_treatment_options"]
        if treatments and isinstance(treatments, list) and len(treatments) > 0:
            if isinstance(treatments[0], dict) and "warning" not in treatments[0]:
                print(f"\n[Oppervlaktebehandeling Opties]")
                for t in treatments[:3]:
                    print(f"  - {t['name']} ({t['standard']})")
    else:
        print_disabled("Oppervlaktebehandeling")

    # Purchase Spec
    if modules.purchase_spec:
        purchase = werkvoorbereiding_data["purchase_specification"]
        print(f"\n[Inkoop Specificatie]")
        print(f"  Materiaal: {purchase['material']['name']}")
        print(f"  Ruw formaat: {purchase['raw_material']['dimensions']}")
        print(f"  Ruw gewicht: {purchase['raw_material']['mass_per_piece_kg']:.2f} kg")
        print(f"  Certificaat: {purchase['certification']}")
    else:
        print_disabled("Inkoop Specificatie")


def print_sheetmetal_summary(sheetmetal_data: Dict, modules, production_only: bool = False) -> None:
    """Print sheet metal analysis summary."""
    if production_only or not sheetmetal_data:
        return
    
    if sheetmetal_data.get("error"):
        print("  Geen plaatwerk detectie mogelijk (geometrie niet geschikt)")
        return

    if modules.sheetmetal_analysis:
        print(f"\n[Plaatwerk Detectie]")
        print(f"  Plaatdikte: {sheetmetal_data['thickness']['value']:.1f}mm")
        std_text = "(standaard)" if sheetmetal_data['thickness']['is_standard'] else "(niet-standaard)"
        print(f"  Status: {std_text}")

    if modules.bend_detection:
        bending = sheetmetal_data.get('bending', {})
        print(f"\n[Buiging Detectie]")
        print(f"  Aantal buigingen: {bending.get('bend_count', 0)}")
        print(f"  Min. binnenradius: {bending.get('min_inner_radius', 0):.1f}mm")
        if bending.get('bends'):
            for b in bending['bends'][:3]:
                print(f"    Buiging {b['id']}: {b['angle']}° R{b['radius']}mm")

    if modules.kantbank_tooling:
        tooling = sheetmetal_data.get('tooling', {})
        print(f"\n[Kantbank Gereedschap]")
        print(f"  Aanbevolen V-matrijs: {tooling.get('recommended_v_die', 'N/A')}")
        print(f"  V-opening: {tooling.get('v_opening_mm', 0)}mm")
        print(f"  Buigkracht: {tooling.get('bend_force_kN_per_m', 0):.1f} kN/m")

    if modules.flat_pattern:
        flat = sheetmetal_data.get('flat_pattern', {})
        print(f"\n[Uitslag Berekening]")
        print(f"  K-factor: {flat.get('k_factor_used', 0):.2f}")
        print(f"  Methode: {flat.get('calculation_method', 'DIN 6935')}")

    # Warnings
    warnings = sheetmetal_data.get('warnings', [])
    if warnings:
        print(f"\n[Waarschuwingen]")
        for w in warnings:
            print(f"  ⚠ {w}")


def print_assembly_summary(assembly_data: Dict, production_only: bool = False) -> None:
    """Print assembly/BOM analysis summary."""
    if production_only or not assembly_data or assembly_data.get("error"):
        return
    
    summary = assembly_data.get("summary", {})
    print(f"\n[Stuklijst / Bill of Materials]")
    print(f"  Totaal onderdelen: {assembly_data.get('total_parts', 0)}")
    print(f"  Unieke onderdelen: {assembly_data.get('unique_parts', 0)}")
    print(f"  Bevestigingsmiddelen: {assembly_data.get('total_fasteners', 0)}")
    print(f"  Te vervaardigen: {summary.get('manufactured_parts', 0)}")
    print(f"  Inkoop onderdelen: {summary.get('purchased_parts', 0)}")

    print(f"\n[Massa & Kosten]")
    print(f"  Totale massa: {assembly_data.get('total_mass_kg', 0):.3f} kg")
    print(f"  Geschatte montage tijd: {assembly_data.get('estimated_assembly_time_hours', 0):.2f} uur")
    print(f"  Geschatte totale kosten: €{assembly_data.get('estimated_total_cost', 0):.2f}")

    # Fastener summary
    fasteners = assembly_data.get("fastener_summary", {})
    if fasteners:
        print(f"\n[Bevestigingsmiddelen Overzicht]")
        for desc, count in fasteners.items():
            print(f"  {count}× {desc}")

    # BOM Preview (first 5 items)
    flat_bom = assembly_data.get("flat_bom", [])
    if flat_bom:
        print(f"\n[Stuklijst Preview (eerste 5)]")
        print(f"  {'Item':<6} {'Naam':<25} {'Aantal':<8} {'Massa (kg)':<12}")
        print(f"  {'-'*6} {'-'*25} {'-'*8} {'-'*12}")
        for item in flat_bom[:5]:
            print(f"  {item.get('item_number', ''):<6} {item.get('part_name', '')[:25]:<25} {item.get('quantity', 0):<8} {item.get('total_mass_kg', 0):.3f}")
        if len(flat_bom) > 5:
            print(f"  ... en {len(flat_bom) - 5} meer onderdelen")


def print_simple_cost_table_preview(simple_cost_table_data: Dict, production_only: bool = False) -> None:
    """Print simple cost table preview."""
    if production_only or not simple_cost_table_data:
        return
    
    headers = simple_cost_table_data.get('headers', [])
    rows = simple_cost_table_data.get('rows', [])

    print(f"\n[Kostentabel] ({len(rows)} onderdelen)")
    print(f"  Kolommen: {', '.join(headers)}")
    print(f"  Totaal: €{simple_cost_table_data.get('grand_total', 0):.2f}")

    # Show first few rows
    for row in rows[:5]:
        artikel = row.get('artikel', '')[:20]
        totaal = row.get('totaal', 0)
        print(f"    {artikel:<20} €{totaal:.2f}")
    if len(rows) > 5:
        print(f"    ... en {len(rows) - 5} meer onderdelen")


def print_production_info_table(detailed_parts: List[Dict]) -> None:
    """Print production information table."""
    print("\n" + "="*100)
    print("PRODUCTIE INFORMATIE / PRODUCTION DATA")
    print("="*100)
    # Print header
    headers = ["CalcID", "ArtikelNr", "Aantal", "Vorm", "Dikte", "L x B", "Gaten", "Dia", "Zet", "TegenZet"]
    print(f"{headers[0]:<8} {headers[1]:<12} {headers[2]:<6} {headers[3]:<8} {headers[4]:<6} {headers[5]:<15} {headers[6]:<6} {headers[7]:<12} {headers[8]:<4} {headers[9]:<8}")
    print("-" * 100)
    
    for part in detailed_parts:
        pd = part.get("production_data", {})
        l_x_b = f"{pd.get('Lengte',0)}x{pd.get('Breedte',0)}"
        dia = str(pd.get('DiaSnijgat', []))
        if len(dia) > 12:
            dia = dia[:9] + "..."
        
        print(f"{pd.get('CalcID', '')[:8]:<8} {pd.get('ArtikelNr', '')[:12]:<12} {pd.get('Aantal', 0):<6} {pd.get('Vorm', '')[:8]:<8} {pd.get('Dikte', 0):<6} {l_x_b:<15} {pd.get('Snijgaten', 0):<6} {dia:<12} {pd.get('ZetAantal', 0):<4} {pd.get('Aantaltegenzet', 0):<8}")
    print("="*100 + "\n")
