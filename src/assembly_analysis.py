"""
Assembly Analysis Module - Bill of Materials (BOM) Generation

Analyzes STEP assemblies to generate:
- Hierarchical Bill of Materials (BOM)
- Part counting and grouping
- Sub-assembly detection
- Standard fastener identification
- Total assembly cost estimation

Based on Dutch/European manufacturing standards.
"""

import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# Try to import CAD libraries
try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False


# =============================================================================
# STANDAARD BEVESTIGINGSMIDDELEN DATABASE
# =============================================================================

STANDARD_FASTENERS = {
    # Bout/Schroef diameters naar ISO metrisch
    "M3": {"type": "bout", "d": 3.0, "head_d": 5.5, "head_h": 2.0},
    "M4": {"type": "bout", "d": 4.0, "head_d": 7.0, "head_h": 2.8},
    "M5": {"type": "bout", "d": 5.0, "head_d": 8.5, "head_h": 3.5},
    "M6": {"type": "bout", "d": 6.0, "head_d": 10.0, "head_h": 4.0},
    "M8": {"type": "bout", "d": 8.0, "head_d": 13.0, "head_h": 5.3},
    "M10": {"type": "bout", "d": 10.0, "head_d": 16.0, "head_h": 6.4},
    "M12": {"type": "bout", "d": 12.0, "head_d": 18.0, "head_h": 7.5},
    "M16": {"type": "bout", "d": 16.0, "head_d": 24.0, "head_h": 10.0},
    "M20": {"type": "bout", "d": 20.0, "head_d": 30.0, "head_h": 12.5},
}

# Moer afmetingen (DIN 934 / ISO 4032)
STANDARD_NUTS = {
    "M3": {"d": 3.0, "s": 5.5, "h": 2.4},
    "M4": {"d": 4.0, "s": 7.0, "h": 3.2},
    "M5": {"d": 5.0, "s": 8.0, "h": 4.0},
    "M6": {"d": 6.0, "s": 10.0, "h": 5.0},
    "M8": {"d": 8.0, "s": 13.0, "h": 6.5},
    "M10": {"d": 10.0, "s": 17.0, "h": 8.0},
    "M12": {"d": 12.0, "s": 19.0, "h": 10.0},
    "M16": {"d": 16.0, "s": 24.0, "h": 13.0},
    "M20": {"d": 20.0, "s": 30.0, "h": 16.0},
}

# Ring/Sluitring afmetingen (DIN 125 / ISO 7089)
STANDARD_WASHERS = {
    "M3": {"d_inner": 3.2, "d_outer": 7.0, "h": 0.5},
    "M4": {"d_inner": 4.3, "d_outer": 9.0, "h": 0.8},
    "M5": {"d_inner": 5.3, "d_outer": 10.0, "h": 1.0},
    "M6": {"d_inner": 6.4, "d_outer": 12.0, "h": 1.6},
    "M8": {"d_inner": 8.4, "d_outer": 16.0, "h": 1.6},
    "M10": {"d_inner": 10.5, "d_outer": 20.0, "h": 2.0},
    "M12": {"d_inner": 13.0, "d_outer": 24.0, "h": 2.5},
    "M16": {"d_inner": 17.0, "d_outer": 30.0, "h": 3.0},
    "M20": {"d_inner": 21.0, "d_outer": 37.0, "h": 3.0},
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BOMItem:
    """Single item in Bill of Materials."""
    item_number: str
    part_name: str
    description: str
    quantity: int
    unit: str = "stuks"
    material: str = ""
    mass_per_unit_kg: float = 0.0
    total_mass_kg: float = 0.0
    is_purchased: bool = False
    is_fastener: bool = False
    fastener_size: str = ""
    unit_cost: float = 0.0
    total_cost: float = 0.0
    children: List["BOMItem"] = field(default_factory=list)
    level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass
class AssemblyAnalysis:
    """Complete assembly analysis result."""
    assembly_name: str
    total_parts: int
    unique_parts: int
    total_fasteners: int
    bom: List[BOMItem]
    flat_bom: List[BOMItem]  # Flat list without hierarchy
    summary: Dict[str, Any]
    fastener_summary: Dict[str, int]
    material_summary: Dict[str, float]  # kg per material
    total_mass_kg: float
    estimated_assembly_time_hours: float
    estimated_total_cost: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assembly_name": self.assembly_name,
            "total_parts": self.total_parts,
            "unique_parts": self.unique_parts,
            "total_fasteners": self.total_fasteners,
            "bom": [item.to_dict() for item in self.bom],
            "flat_bom": [item.to_dict() for item in self.flat_bom],
            "summary": self.summary,
            "fastener_summary": self.fastener_summary,
            "material_summary": self.material_summary,
            "total_mass_kg": self.total_mass_kg,
            "estimated_assembly_time_hours": self.estimated_assembly_time_hours,
            "estimated_total_cost": self.estimated_total_cost,
        }


# =============================================================================
# GEOMETRY HELPERS
# =============================================================================

def get_solid_volume(solid) -> float:
    """Calculate volume of a solid in mm³."""
    if not HAS_OCP:
        return 0.0
    try:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        return props.Mass()
    except Exception:
        return 0.0


def get_solid_bounding_box(solid) -> Tuple[float, float, float]:
    """Get bounding box dimensions of a solid."""
    if not HAS_OCP:
        return (0, 0, 0)
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        box = Bnd_Box()
        BRepBndLib.Add_s(solid, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return (xmax - xmin, ymax - ymin, zmax - zmin)
    except Exception:
        return (0, 0, 0)


def solids_are_equal(solid1, solid2, tolerance: float = 0.01) -> bool:
    """
    Check if two solids are geometrically equal.

    Uses volume and bounding box comparison.
    """
    vol1 = get_solid_volume(solid1)
    vol2 = get_solid_volume(solid2)

    if vol1 == 0 or vol2 == 0:
        return False

    # Volume within tolerance
    vol_diff = abs(vol1 - vol2) / max(vol1, vol2)
    if vol_diff > tolerance:
        return False

    # Bounding box dimensions
    bb1 = sorted(get_solid_bounding_box(solid1))
    bb2 = sorted(get_solid_bounding_box(solid2))

    for d1, d2 in zip(bb1, bb2):
        if d1 == 0 and d2 == 0:
            continue
        if abs(d1 - d2) / max(d1, d2, 0.001) > tolerance:
            return False

    return True


# =============================================================================
# FASTENER DETECTION
# =============================================================================

def identify_fastener(solid, volume: float, dims: Tuple[float, float, float]) -> Optional[Dict]:
    """
    Identify if a solid is a standard fastener.

    Checks against known bolt, nut, and washer dimensions.
    """
    sorted_dims = sorted(dims)
    min_dim = sorted_dims[0]
    mid_dim = sorted_dims[1]
    max_dim = sorted_dims[2]

    # Washer detection: very thin, circular-ish
    if min_dim < 5 and mid_dim / min_dim > 5 and abs(mid_dim - max_dim) / max(mid_dim, 1) < 0.3:
        # Likely a washer
        for size, spec in STANDARD_WASHERS.items():
            if (abs(mid_dim - spec["d_outer"]) < 2 and
                abs(min_dim - spec["h"]) < 0.5):
                return {
                    "type": "ring",
                    "size": size,
                    "standard": "DIN 125 / ISO 7089",
                    "description": f"Sluitring {size}",
                    "is_purchased": True,
                    "unit_cost": 0.05,
                }

    # Nut detection: hexagonal profile, height ~ 0.8 × diameter
    for size, spec in STANDARD_NUTS.items():
        if (abs(max_dim - spec["s"]) < 2 and
            abs(min_dim - spec["h"]) < 1.5 and
            mid_dim / max_dim > 0.8):  # Roughly hexagonal
            return {
                "type": "moer",
                "size": size,
                "standard": "DIN 934 / ISO 4032",
                "description": f"Zeskantmoer {size}",
                "is_purchased": True,
                "unit_cost": 0.08,
            }

    # Bolt detection: cylindrical with head
    for size, spec in STANDARD_FASTENERS.items():
        # Check if diameter matches and length is reasonable
        if (abs(min_dim - spec["d"]) < 1 or abs(mid_dim - spec["d"]) < 1):
            if max_dim > spec["d"] * 2:  # At least 2× diameter length
                return {
                    "type": "bout",
                    "size": size,
                    "standard": "DIN 931 / ISO 4014",
                    "description": f"Zeskantbout {size}×{int(max_dim)}",
                    "is_purchased": True,
                    "unit_cost": 0.15 + max_dim * 0.005,
                }

    return None


# =============================================================================
# ASSEMBLY ANALYSIS
# =============================================================================

def analyze_assembly(
    cq_object,
    assembly_name: str = "Assembly",
    default_material: str = "steel_s235",
    include_fastener_costs: bool = True
) -> AssemblyAnalysis:
    """
    Analyze a STEP assembly and generate hierarchical BOM.

    Args:
        cq_object: CadQuery workplane or compound
        assembly_name: Name for the assembly
        default_material: Default material for cost estimation
        include_fastener_costs: Include fastener costs in total

    Returns:
        AssemblyAnalysis with complete BOM data
    """
    if not HAS_OCP:
        return AssemblyAnalysis(
            assembly_name=assembly_name,
            total_parts=0,
            unique_parts=0,
            total_fasteners=0,
            bom=[],
            flat_bom=[],
            summary={"error": "OCP library not available"},
            fastener_summary={},
            material_summary={},
            total_mass_kg=0,
            estimated_assembly_time_hours=0,
            estimated_total_cost=0,
        )

    # Get underlying solid/compound
    try:
        if hasattr(cq_object, 'val'):
            shape = cq_object.val().wrapped
        elif hasattr(cq_object, 'wrapped'):
            shape = cq_object.wrapped
        else:
            shape = cq_object
    except Exception:
        shape = cq_object

    # Collect all solids
    solids = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()

    # Group identical solids
    grouped_solids = []  # [(representative_solid, count, volume, dims)]

    for solid in solids:
        volume = get_solid_volume(solid)
        dims = get_solid_bounding_box(solid)

        # Check if matches existing group
        found = False
        for i, (rep, count, vol, d) in enumerate(grouped_solids):
            if solids_are_equal(solid, rep):
                grouped_solids[i] = (rep, count + 1, vol, d)
                found = True
                break

        if not found:
            grouped_solids.append((solid, 1, volume, dims))

    # Generate BOM items
    bom_items = []
    flat_bom = []
    fastener_summary = defaultdict(int)
    material_summary = defaultdict(float)
    total_fasteners = 0
    total_mass = 0.0
    total_cost = 0.0

    # Material densities
    densities = {
        "steel": 7850,
        "alu": 2700,
        "stainless": 7900,
        "brass": 8500,
    }

    for i, (solid, count, volume, dims) in enumerate(grouped_solids):
        item_num = f"{i+1:03d}"

        # Check if fastener
        fastener_info = identify_fastener(solid, volume, dims)

        if fastener_info:
            # It's a fastener
            total_fasteners += count
            fastener_summary[fastener_info["description"]] += count

            mass_per_unit = volume / 1e9 * densities["steel"]

            item = BOMItem(
                item_number=item_num,
                part_name=fastener_info["description"],
                description=f"{fastener_info['standard']}",
                quantity=count,
                unit="stuks",
                material="Staal verzinkt",
                mass_per_unit_kg=mass_per_unit,
                total_mass_kg=mass_per_unit * count,
                is_purchased=True,
                is_fastener=True,
                fastener_size=fastener_info["size"],
                unit_cost=fastener_info.get("unit_cost", 0.10),
                total_cost=fastener_info.get("unit_cost", 0.10) * count,
                level=0,
            )
        else:
            # Regular part
            # Classify based on geometry
            sorted_dims = sorted(dims)
            min_dim = sorted_dims[0]
            max_dim = sorted_dims[2]

            if min_dim < max_dim * 0.05:
                part_type = "Plaatdeel"
            elif max_dim / min_dim > 5:
                part_type = "Langwerpig deel"
            else:
                part_type = "Verspaamd deel"

            # Estimate mass
            mat_key = "steel" if "steel" in default_material else "alu" if "alu" in default_material else "steel"
            density = densities.get(mat_key, 7850)
            mass_per_unit = volume / 1e9 * density

            # Estimate cost (rough)
            # Machining: €60/hour, assume 5 min per 1000 mm³
            machining_time_hours = (volume / 1000) * (5/60) / 60
            unit_cost = mass_per_unit * 2.0 + machining_time_hours * 60

            item = BOMItem(
                item_number=item_num,
                part_name=f"{part_type} {item_num}",
                description=f"{dims[0]:.1f}×{dims[1]:.1f}×{dims[2]:.1f} mm",
                quantity=count,
                unit="stuks",
                material=default_material,
                mass_per_unit_kg=mass_per_unit,
                total_mass_kg=mass_per_unit * count,
                is_purchased=False,
                is_fastener=False,
                unit_cost=unit_cost,
                total_cost=unit_cost * count,
                level=0,
            )

            material_summary[default_material] += mass_per_unit * count

        total_mass += item.total_mass_kg
        if include_fastener_costs or not item.is_fastener:
            total_cost += item.total_cost

        bom_items.append(item)
        flat_bom.append(item)

    # Estimate assembly time
    # Rule of thumb: 2 min per fastener, 5 min per regular part
    assembly_time = (total_fasteners * 2 + (len(bom_items) - total_fasteners) * 5) / 60

    # Summary
    summary = {
        "total_solids": len(solids),
        "unique_parts": len(grouped_solids),
        "fasteners": total_fasteners,
        "manufactured_parts": len(bom_items) - len([b for b in bom_items if b.is_fastener]),
        "purchased_parts": len([b for b in bom_items if b.is_purchased]),
    }

    return AssemblyAnalysis(
        assembly_name=assembly_name,
        total_parts=len(solids),
        unique_parts=len(grouped_solids),
        total_fasteners=total_fasteners,
        bom=bom_items,
        flat_bom=flat_bom,
        summary=summary,
        fastener_summary=dict(fastener_summary),
        material_summary=dict(material_summary),
        total_mass_kg=total_mass,
        estimated_assembly_time_hours=assembly_time,
        estimated_total_cost=total_cost,
    )


def generate_bom_table(analysis: AssemblyAnalysis) -> List[List[str]]:
    """
    Generate a printable BOM table.

    Returns list of rows: [Item, Description, Qty, Unit, Material, Mass, Cost]
    """
    header = ["Item", "Beschrijving", "Aantal", "Eenheid", "Materiaal", "Massa (kg)", "Kosten (€)"]
    rows = [header]

    for item in analysis.flat_bom:
        rows.append([
            item.item_number,
            f"{item.part_name}\n{item.description}",
            str(item.quantity),
            item.unit,
            item.material,
            f"{item.total_mass_kg:.3f}",
            f"{item.total_cost:.2f}",
        ])

    # Totals row
    rows.append([
        "",
        "TOTAAL",
        str(analysis.total_parts),
        "",
        "",
        f"{analysis.total_mass_kg:.3f}",
        f"{analysis.estimated_total_cost:.2f}",
    ])

    return rows


def export_bom_csv(analysis: AssemblyAnalysis, filepath: str):
    """Export BOM to CSV file."""
    import csv

    rows = generate_bom_table(analysis)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(rows)


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def analyze_assembly_complete(
    cq_object,
    assembly_name: str = "Assembly",
    material: str = "steel_s235",
    export_csv: str = None
) -> Dict[str, Any]:
    """
    Complete assembly analysis for werkvoorbereiding.

    Args:
        cq_object: CadQuery workplane or shape
        assembly_name: Name for the assembly
        material: Default material code
        export_csv: Optional path to export BOM as CSV

    Returns:
        Dict with complete assembly analysis
    """
    analysis = analyze_assembly(cq_object, assembly_name, material)

    if export_csv:
        export_bom_csv(analysis, export_csv)

    result = analysis.to_dict()
    result["bom_table"] = generate_bom_table(analysis)

    return result
