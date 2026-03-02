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
import re
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# Try to import CAD libraries
try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND, TopAbs_FACE, TopAbs_EDGE
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
    part_class: str = ""  # Classification: "plaat", "profiel", "anders"
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


def get_solid_topology_counts(solid) -> Tuple[int, int]:
    """Return (face_count, edge_count) for a solid."""
    if not HAS_OCP:
        return (0, 0)
    try:
        face_count = 0
        edge_count = 0
        face_exp = TopExp_Explorer(solid, TopAbs_FACE)
        while face_exp.More():
            face_count += 1
            face_exp.Next()

        edge_exp = TopExp_Explorer(solid, TopAbs_EDGE)
        while edge_exp.More():
            edge_count += 1
            edge_exp.Next()

        return (face_count, edge_count)
    except Exception:
        return (0, 0)


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

    # Surface area comparison helps distinguish similar-size parts
    sa1 = _get_solid_surface_area(solid1)
    sa2 = _get_solid_surface_area(solid2)
    if sa1 > 0 and sa2 > 0:
        sa_diff = abs(sa1 - sa2) / max(sa1, sa2)
        if sa_diff > (tolerance * 2):
            return False

    # Topology comparison: different face/edge counts => different geometry
    f1, e1 = get_solid_topology_counts(solid1)
    f2, e2 = get_solid_topology_counts(solid2)
    if f1 != 0 and f2 != 0:
        if f1 != f2 or e1 != e2:
            return False

    return True


# =============================================================================
# FASTENER DETECTION
# =============================================================================

def identify_fastener(solid, volume: float, dims: Tuple[float, float, float]) -> Optional[Dict]:
    """
    Identify if a solid is a standard fastener.

    Checks against known bolt, nut, and washer dimensions.
    
    NOT fasteners: sheet metal parts (plaatdelen) or profiles that happen to match
    fastener dimensions are rejected first using face analysis and bounding box checks.
    """
    sorted_dims = sorted(dims)
    min_dim = sorted_dims[0]
    mid_dim = sorted_dims[1]
    max_dim = sorted_dims[2]
    
    # REJECT if face analysis indicates this is a plate (most reliable check)
    # Plates have two dominant parallel faces (top/bottom) that comprise >50% of surface area
    # Lower threshold (50%) accounts for industrial plates with holes/cutouts
    if _is_plate_by_face_analysis(solid, threshold=50.0):
        return None
    
    # REJECT if this looks like a thin sheet metal part (plaatdeel) by bbox
    # Plaatdelen have thickness_ratio < 0.15 and high aspect_ratio
    thickness_ratio = min_dim / mid_dim if mid_dim > 0 else 0
    aspect_ratio = max_dim / min_dim if min_dim > 0 else 0
    
    if thickness_ratio < 0.15 and aspect_ratio > 5.0:
        # This is a plaatdeel (sheet metal), not a fastener
        return None
    
    # REJECT if this looks like a profiel (beam profile)
    # Profielen have length_ratio >= 5.0 and cross_ratio 0.5-2.0 with high volume fill
    bbox_volume = min_dim * mid_dim * max_dim
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
    length_ratio = max_dim / mid_dim if mid_dim > 0 else 0
    cross_ratio = mid_dim / min_dim if min_dim > 0 else 0
    
    if (min_dim >= 5.0 and length_ratio >= 5.0 and 0.5 <= cross_ratio <= 2.0 and
        volume_ratio > 0.5):
        # This looks like a profiel (beam), not a fastener
        return None

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
# SOLID CLASSIFICATION
# =============================================================================

def _solid_bbox_sorted(solid) -> Tuple[float, float, float]:
    """Get bounding box dimensions sorted [smallest, middle, longest]."""
    dims = get_solid_bounding_box(solid)
    return tuple(sorted(dims))


def _is_plate_by_face_analysis(solid, threshold: float = 60.0) -> bool:
    """Check if solid is a plate by analyzing face areas.
    
    A plate has two large parallel faces (top/bottom) that dominate the surface area.
    If the top 2 faces comprise > threshold% of total surface area, it's a plate.
    
    This is more reliable than bounding box analysis for thick plates (50mm+)
    that would fail thickness_ratio checks but are still flat plates.
    
    Args:
        solid: The solid to analyze
        threshold: Minimum percentage of surface area for top 2 faces (default 60%)
    
    Returns:
        True if solid is a plate
    """
    try:
        face_areas = []
        exp = TopExp_Explorer(solid, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            props = GProp_GProps()
            if hasattr(BRepGProp, "SurfaceProperties_s"):
                BRepGProp.SurfaceProperties_s(face, props)
            else:
                BRepGProp.SurfaceProperties(face, props)
            face_areas.append(props.Mass())
            exp.Next()
        
        if len(face_areas) < 2:
            return False
        
        face_areas.sort(reverse=True)
        total_area = sum(face_areas)
        
        if total_area == 0:
            return False
        
        top2_area = face_areas[0] + face_areas[1]
        top2_percent = (top2_area / total_area) * 100.0
        
        return top2_percent > threshold
    except:
        return False


def _is_shell_solid(solid, max_thickness_mm: float = 20.0) -> bool:
    """
    Detect if solid is a thin shell/sheet metal part (including bent sheets).
    
    Uses volume-to-surface-area ratio to detect thin shells.
    Sheet metal parts have high surface area relative to their volume.
    
    Args:
        solid: The solid to analyze
        max_thickness_mm: Maximum typical sheet metal thickness (default 20mm)
    
    Returns:
        True if solid appears to be thin shell/sheet metal
    """
    try:
        volume = get_solid_volume(solid)
        surface_area = _get_solid_surface_area(solid)
        
        if volume <= 0 or surface_area <= 0:
            return False
        
        # For a thin shell: surface_area ≈ 2 × area × (top + bottom)
        # volume ≈ area × thickness
        # So: SA/V ≈ 2/thickness
        # If thickness = 3mm: SA/V ≈ 0.67
        # If thickness = 5mm: SA/V ≈ 0.40
        # If thickness = 10mm: SA/V ≈ 0.20
        # If thickness = 20mm: SA/V ≈ 0.10
        
        sa_v_ratio = surface_area / volume
        
        # Estimate effective thickness from SA/V ratio
        # For sheet metal: effective_thickness ≈ 2 / SA_V_ratio
        estimated_thickness = 2.0 / sa_v_ratio if sa_v_ratio > 0 else 999
        
        # Sheet metal if estimated thickness < max_thickness_mm
        return estimated_thickness < max_thickness_mm
        
    except:
        return False


def classify_solid(solid) -> str:
    """
    Classify a solid based on its geometry.
    
    Returns one of: "plaat", "profiel", "anders"
    
    Classification logic:
    - PLAAT: Detected by face analysis (top 2 faces > 60% surface area) OR
             traditional thin plate criteria (thickness<25mm, thickness_ratio<0.15, aspect>5) OR
             sheet metal criteria (thin thickness, high SA/V ratio = bent sheets)
    - PROFIEL: smallest≥5mm, length_ratio≥5.0, cross_ratio 0.5-2.0, constant cross-section
    - ANDERS: everything else (machined parts, complex geometry)
    
    Key insight:
    Face-based detection is more reliable for thick plates (50mm+) that would fail
    bounding box thickness_ratio checks but are still flat plates.
    Sheet metal (bent) detection uses SA/V ratio to catch formed parts.
    """
    dims = _solid_bbox_sorted(solid)  # [smallest, middle, longest]
    smallest, middle, longest = dims
    
    # Calculate ratios
    volume = get_solid_volume(solid)
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
    
    aspect_ratio = longest / smallest if smallest > 0 else 0
    thickness_ratio = smallest / middle if middle > 0 else 0
    length_ratio = longest / middle if middle > 0 else 0
    cross_ratio = middle / smallest if smallest > 0 else 0
    
    # PLAAT check: Use face analysis as primary method (more reliable)
    # Lower threshold (50%) for industrial plates with holes/cutouts/weld preparations
    if _is_plate_by_face_analysis(solid, threshold=50.0):
        return "plaat"
    
    # Fallback: traditional thin plate check for very thin plates (< 25mm)
    # thickness_ratio < 0.15 means thickness is less than 15% of width = flat
    if smallest < 25.0 and thickness_ratio < 0.15 and aspect_ratio > 5.0:
        return "plaat"
    
    # PROFIEL check BEFORE sheet metal detection (to avoid false positives)
    # Profiles/tubes can have similar SA/V as bent sheets, so check profiles first
    # Primary criteria: rectangular cross section (cross_ratio 0.5-2.0), elongated (length_ratio >= 5.0)
    if smallest >= 5.0 and length_ratio >= 5.0 and 0.5 <= cross_ratio <= 2.0:
        # Secondary check: must have significant volume fill
        # High volume_ratio (>0.5) = definitely solid profiel
        # Medium volume_ratio (0.15-0.5) = could be profiel with internal features OR formed plate
        
        if volume_ratio > 0.5:
            # Clear case: solid rectangular beam
            return "profiel"
        elif volume_ratio >= 0.15:
            # Ambiguous: could be profiel with internal features or formed plate
            # Use surface complexity as tiebreaker (lower = likely profiel)
            # Formed plates with bends have higher surface area relative to volume
            try:
                surface_area = _get_solid_surface_area(solid)
                if surface_area > 0:
                    # Surface to volume ratio: profiel should have lower SA/V than formed sheet
                    sa_v_ratio = surface_area / volume
                    # Rough threshold: constant profiel < 1.5 cm^-1, formed plate > 1.0 cm^-1
                    if sa_v_ratio < 1.2:  # More surface fill = solid
                        return "profiel"
            except:
                pass
    
    # Sheet metal detection - works for flat AND bent sheets
    # Detects thin shells using SA/V ratio (independent of bounding box distortion from bends)
    # This catches bent sheets that fail planar checks
    # Only after profiel check to avoid false positives on hollow tubes
    if _is_shell_solid(solid, max_thickness_mm=20.0):
        return "plaat"
    
    # Default: includes machined parts, complex geometry
    return "anders"


def _get_solid_surface_area(solid) -> float:
    """Calculate total surface area of a solid."""
    try:
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        
        props = GProp_GProps()
        if hasattr(BRepGProp, "SurfaceProperties_s"):
            BRepGProp.SurfaceProperties_s(solid, props)
        else:
            BRepGProp.SurfaceProperties(solid, props)
        return props.Mass()  # For surface, Mass() returns area
    except:
        return 0.0


# =============================================================================
# STEP FILE ASSEMBLY STRUCTURE PARSING
# =============================================================================

def parse_step_assembly_structure(step_file_path: str) -> Optional[Dict[str, int]]:
    """
    Parse STEP file to extract assembly structure and part counts.
    
    Uses NEXT_ASSEMBLY_USAGE_OCCURRENCE entries to accurately count parts.
    Handles instance suffixes (e.g., "part.1", "part.2") to correctly group
    identical parts.
    
    Args:
        step_file_path: Path to STEP file
        
    Returns:
        Dict mapping part names to their counts, or None if parsing fails
        
    Example:
        {
            "10040853_1": 2,
            "10040854_1": 2,
            "MD-20-11302_2": 2
        }
    
    Note:
        This method is more accurate than geometric comparison for assemblies,
        as it uses the explicit assembly structure from the STEP file.
    """
    if not step_file_path or not os.path.exists(step_file_path):
        return None
        
    try:
        with open(step_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # STEP format: NEXT_ASSEMBLY_USAGE_OCCURRENCE('pos','','part_name.instance',...)
        # This represents actual part instances in the assembly
        assembly_pattern = r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('(\d+)','','([^']+)'"
        assembly_items = re.findall(assembly_pattern, content)
        
        if not assembly_items:
            return None
        
        # Count parts, removing instance suffixes (.1, .2, etc.)
        # Example: "10040854_1.1" -> "10040854_1"
        parts_count = defaultdict(int)
        for pos, full_name in assembly_items:
            # Remove instance suffix to get base part name
            base_name = re.sub(r'\.\d+$', '', full_name)
            parts_count[base_name] += 1
        
        return dict(parts_count) if parts_count else None
        
    except Exception as e:
        # Fail silently and fall back to geometric analysis
        return None


def parse_step_product_names(step_file_path: str) -> Optional[List[str]]:
    """
    Parse STEP file to extract PRODUCT_DEFINITION names.
    
    This is a fallback when NEXT_ASSEMBLY_USAGE_OCCURRENCE is not present.
    Returns product names in order of appearance, which typically matches
    the order of solids in the geometry.
    
    Filters out:
    - Main assembly name (matches filename stem)
    - Frame/Skeleton helper geometry
    - Duplicate suffixes (_1, _2, etc.) are kept as they represent instances
    
    Args:
        step_file_path: Path to STEP file
        
    Returns:
        List of product names in order, or None if parsing fails
        
    Example:
        ["31686-404", "31686-362", "DIN 1026 - U 160 - 600", ...]
    """
    if not step_file_path or not os.path.exists(step_file_path):
        return None
        
    try:
        from pathlib import Path
        
        with open(step_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Get the main assembly name from filename
        main_assembly_name = Path(step_file_path).stem
        
        # STEP format: PRODUCT_DEFINITION('name','name',#ref,#ref);
        # Extract the first name field (product ID)
        product_pattern = r"PRODUCT_DEFINITION\('([^']+)'"
        product_names = re.findall(product_pattern, content)
        
        if not product_names:
            return None
        
        # Filter the product names
        filtered_names = []
        for name in product_names:
            # Skip main assembly (exact match with filename)
            if name == main_assembly_name:
                continue
            
            # Skip Frame/Skeleton helper geometry
            if name.startswith('Frame') or name.startswith('Skeleton'):
                continue
            
            # Skip skeleton suffix items (helper geometry)
            if '_skeleton' in name.lower():
                continue
            
            filtered_names.append(name)
        
        return filtered_names if filtered_names else None
        
    except Exception as e:
        return None


# =============================================================================
# ASSEMBLY ANALYSIS
# =============================================================================

def analyze_assembly(
    cq_object,
    assembly_name: str = "Assembly",
    default_material: str = "steel_s235",
    include_fastener_costs: bool = True,
    step_file_path: Optional[str] = None
) -> AssemblyAnalysis:
    """
    Analyze a STEP assembly and generate hierarchical BOM.

    Args:
        cq_object: CadQuery workplane or compound
        assembly_name: Name for the assembly
        default_material: Default material for cost estimation
        include_fastener_costs: Include fastener costs in total
        step_file_path: Optional path to STEP file for accurate assembly structure parsing

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

    # Try to get part counts from STEP file assembly structure first
    step_parts_count = None
    if step_file_path:
        step_parts_count = parse_step_assembly_structure(step_file_path)
    
    # Collect all solids
    solids = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()

    # Group identical solids
    grouped_solids = []  # [(representative_solid, count, volume, dims, part_name)]

    # If we have STEP assembly structure, use part names to identify unique parts
    part_name_to_solid = {}
    
    for idx, solid in enumerate(solids):
        volume = get_solid_volume(solid)
        dims = get_solid_bounding_box(solid)

        # Check if matches existing group
        found = False
        for i, (rep, count, vol, d, pname) in enumerate(grouped_solids):
            if solids_are_equal(solid, rep):
                grouped_solids[i] = (rep, count + 1, vol, d, pname)
                found = True
                break

        if not found:
            part_name = f"Part_{len(grouped_solids) + 1}"
            grouped_solids.append((solid, 1, volume, dims, part_name))
            part_name_to_solid[part_name] = solid

    # If we have STEP part counts, try to match them to our grouped solids
    if step_parts_count:
        # Update counts based on STEP assembly structure
        step_parts_list = list(step_parts_count.keys())
        for i, (solid, geom_count, vol, dims, pname) in enumerate(grouped_solids):
            # Try to find matching part name from STEP
            if i < len(step_parts_list):
                step_part_name = step_parts_list[i]
                step_count = step_parts_count[step_part_name]
                # Update with accurate count from STEP file
                grouped_solids[i] = (solid, step_count, vol, dims, step_part_name)
    
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

    for i, (solid, count, volume, dims, part_name) in enumerate(grouped_solids):
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
                part_class="",
                unit_cost=fastener_info.get("unit_cost", 0.10),
                total_cost=fastener_info.get("unit_cost", 0.10) * count,
                level=0,
            )
        else:
            # Regular part
            
            # Check FIRST if part name indicates a standard profile/section
            # (DIN, EN, ISO standards should be classified as "anders" - purchased items)
            part_class = None
            if part_name:
                name_upper = part_name.upper()
                # Standard profiles from catalogs (purchased, not manufactured plates)
                is_standard = any(std in name_upper for std in ['DIN ', 'DIN-', 'EN ', 'EN-', 'ISO ', 'ISO-'])
                
                if is_standard:
                    # These are purchased standard profiles, not custom plates
                    part_class = "anders"
            
            # If not a standard profile, classify based on geometry
            if part_class is None:
                part_class = classify_solid(solid)
            
            # Map classification to Dutch part type
            part_type_map = {
                "plaat": "Plaatdeel",
                "profiel": "Profieldeel",
                "anders": "Verspaamd deel"
            }
            part_type = part_type_map.get(part_class, "Verspaamd deel")

            # Estimate mass
            mat_key = "steel" if "steel" in default_material else "alu" if "alu" in default_material else "steel"
            density = densities.get(mat_key, 7850)
            mass_per_unit = volume / 1e9 * density

            # Estimate cost (rough)
            # Machining: €60/hour, assume 5 min per 1000 mm³
            machining_time_hours = (volume / 1000) * (5/60) / 60
            unit_cost = mass_per_unit * 2.0 + machining_time_hours * 60

            # Use STEP part name if available, otherwise generate generic name
            display_name = part_name if not part_name.startswith("Part_") else f"{part_type} {item_num}"

            item = BOMItem(
                item_number=item_num,
                part_name=display_name,
                description=f"{dims[0]:.1f}×{dims[1]:.1f}×{dims[2]:.1f} mm",
                quantity=count,
                unit="stuks",
                material=default_material,
                mass_per_unit_kg=mass_per_unit,
                total_mass_kg=mass_per_unit * count,
                is_purchased=False,
                is_fastener=False,
                part_class=part_class,
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
    export_csv: str = None,
    step_file_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Complete assembly analysis for werkvoorbereiding.

    Args:
        cq_object: CadQuery workplane or shape
        assembly_name: Name for the assembly
        material: Default material code
        export_csv: Optional path to export BOM as CSV
        step_file_path: Optional path to STEP file for accurate assembly structure parsing

    Returns:
        Dict with complete assembly analysis
    """
    analysis = analyze_assembly(cq_object, assembly_name, material, step_file_path=step_file_path)

    if export_csv:
        export_bom_csv(analysis, export_csv)

    result = analysis.to_dict()
    result["bom_table"] = generate_bom_table(analysis)

    return result
