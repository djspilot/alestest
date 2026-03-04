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

from manufacturing_pipeline.analysis.classification_variables import (
    PLATE_FACE_TOP2_THRESHOLD_PCT,
    PLATE_THICK_MAX_MM,
    PLATE_THICKNESS_RATIO_MAX,
    PLATE_ASPECT_RATIO_MIN,
    PROFILE_SMALLEST_MIN_MM,
    PROFILE_LENGTH_RATIO_MIN,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_CROSS_RATIO_MAX,
    PROFILE_VOLUME_RATIO_STRONG_MIN,
    PROFILE_VOLUME_RATIO_WEAK_MIN,
    PROFILE_SA_V_RATIO_MAX,
    SCORE_PLATE_TOP2_HIGH_PCT,
    SCORE_PLATE_TOP2_MIN_PCT,
    SCORE_PLATE_SUPPORT_TOP2_PCT,
    SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX,
    SCORE_PLATE_SUPPORT_ASPECT_MIN,
    SCORE_PROFILE_PRIMARY_POINTS,
    SCORE_PLATE_PRIMARY_POINTS,
    SCORE_AMBIGUOUS_MARGIN_MIN,
    # v2.1: Standard profile detection
    STANDARD_TUBE_CYLINDRICAL_MIN_PCT,
    STANDARD_TUBE_VOLUME_RATIO_MAX,
    STANDARD_TUBE_ASPECT_MIN,
    STANDARD_PROFILE_FACE_AREA_TOLERANCE,
    # v2.1: Bent sheet detection
    BENT_SHEET_THICKNESS_MAX_MM,
    BENT_SHEET_MIN_EDGE_COUNT,
    BENT_SHEET_VOLUME_RATIO_MIN,
    BENT_SHEET_VOLUME_RATIO_MAX,
    BENT_SHEET_TOP2_FACES_MAX_PCT,
    BENT_SHEET_ASPECT_RATIO_MIN,
    CROSS_SECTION_SAMPLE_FRACTIONS,
    CROSS_SECTION_MIN_VALID_SAMPLES,
    CROSS_SECTION_CLOSED_RATIO_MIN,
    CROSS_SECTION_PERIMETER_CV_MAX,
    CROSS_SECTION_EDGE_COUNT_SPAN_MAX,
)

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
    classification_trace: Dict[str, Any] = field(default_factory=dict)

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
        top2_percent = _get_top2_face_percent(solid)
        return top2_percent > threshold
    except:
        return False


def _detect_hollow_tube(solid, volume: float, dims: Tuple[float, float, float]) -> bool:
    """Detect hollow cylindrical tubes (purchased standard profiles like EN 10210-2).
    
    Hollow tubes have:
    - High cylindrical face percentage (≥ 60% of surface area)
    - Low volume ratio (hollow = lot of air inside bbox)
    - Reasonable aspect ratio (not extremely flat)
    
    Example: Ø88.9×4×65mm tube has cylindrical faces ~94% and volume_ratio 0.135
    
    Args:
        solid: The solid to analyze
        volume: Volume in mm³
        dims: Sorted bounding box dimensions [smallest, middle, longest]
    
    Returns:
        True if this appears to be a hollow tube
    """
    try:
        min_dim, mid_dim, max_dim = dims
        
        # Check aspect ratio - not too flat
        aspect = mid_dim / max_dim if max_dim > 0 else 0
        if aspect < STANDARD_TUBE_ASPECT_MIN:
            return False
        
        # Check volume ratio - hollow tubes have low ratio
        bbox_volume = min_dim * mid_dim * max_dim
        volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
        if volume_ratio > STANDARD_TUBE_VOLUME_RATIO_MAX:
            return False
        
        # Check cylindrical face percentage
        if not HAS_OCP:
            return False
            
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        
        cylindrical_area = 0.0
        total_area = 0.0
        
        face_exp = TopExp_Explorer(solid, TopAbs_FACE)
        while face_exp.More():
            face = TopoDS.Face_s(face_exp.Current())
            surf_adapter = BRepAdaptor_Surface(face)
            
            # Calculate face area
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()
            total_area += area
            
            # Check if cylindrical
            if surf_adapter.GetType() == GeomAbs_Cylinder:
                cylindrical_area += area
            
            face_exp.Next()
        
        if total_area == 0:
            return False
        
        cylindrical_pct = (cylindrical_area / total_area) * 100
        return cylindrical_pct >= STANDARD_TUBE_CYLINDRICAL_MIN_PCT
        
    except:
        return False


def _is_bent_sheet(solid) -> bool:
    """Detect bent sheet metal parts to exclude from variable thickness check.
    
    Bent sheets have:
    - Many edges (typically > 8) from bends
    - Large radius edges (≥ 1mm) from bending
    - Would otherwise trigger false positive on variable thickness
    
    Args:
        solid: The solid to analyze
    
    Returns:
        True if this appears to be a bent sheet
    """
    try:
        if not HAS_OCP:
            return False
        
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle
        
        large_radius_count = 0
        edge_count = 0
        
        edge_exp = TopExp_Explorer(solid, TopAbs_EDGE)
        while edge_exp.More():
            edge_count += 1
            edge = TopoDS.Edge_s(edge_exp.Current())
            curve_adapter = BRepAdaptor_Curve(edge)
            
            # Check if circular (bend radius)
            if curve_adapter.GetType() == GeomAbs_Circle:
                circle = curve_adapter.Circle()
                radius = circle.Radius()
                if radius >= BENT_SHEET_LARGE_RADIUS_MIN_MM:
                    large_radius_count += 1
            
            edge_exp.Next()
        
        # Bent sheet: many edges and some large radii
        return edge_count > BENT_SHEET_MIN_EDGE_COUNT and large_radius_count > 0
        
    except:
        return False


def _detect_variable_thickness(solid, dims: Tuple[float, float, float]) -> bool:
    """Detect non-constant thickness profiles (UNP, I-beam, etc.).
    
    Variable thickness profiles have:
    - Top 2 faces with significantly different areas (> 20% difference) 
    - Elongated shape (length_ratio ≥ 5.0)
    - NOT bent sheet metal (different failure mode)
    
    Example: DIN 1026 UNP160 has faces differing by >20% in area, length_ratio 9.2
    
    Args:
        solid: The solid to analyze
        dims: Sorted bounding box dimensions [smallest, middle, longest]
    
    Returns:
        True if this appears to be a variable thickness profile
    """
    try:
        # Check if bent sheet first (exclusion)
        if _is_bent_sheet(solid):
            return False
        
        min_dim, mid_dim, max_dim = dims
        
        # Check elongation
        length_ratio = max_dim / min_dim if min_dim > 0 else 0
        if length_ratio < PROFILE_LENGTH_RATIO_MIN:
            return False
        
        # Analyze face areas
        if not HAS_OCP:
            return False
        
        face_areas = []
        face_exp = TopExp_Explorer(solid, TopAbs_FACE)
        while face_exp.More():
            face = TopoDS.Face_s(face_exp.Current())
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()
            face_areas.append(area)
            face_exp.Next()
        
        if len(face_areas) < 2:
            return False
        
        # Get top 2 largest faces
        face_areas_sorted = sorted(face_areas, reverse=True)
        top_area = face_areas_sorted[0]
        second_area = face_areas_sorted[1]
        
        # Check if they differ significantly
        if top_area == 0:
            return False
        
        area_diff = abs(top_area - second_area) / top_area
        return area_diff > STANDARD_PROFILE_FACE_AREA_TOLERANCE
        
    except:
        return False


def _detect_bent_sheet(solid, volume: float, dims: Tuple[float, float, float]) -> bool:
    """Detect bent/formed sheet metal parts (U-profiles, channels, trays).
    
    Bent sheets have been folded/bent rather than solid extruded or drawn:
    - Thin material (thickness < 5mm, typical for sheet metal)
    - Many edges (>=8 from bends/folds)
    - Moderate volume ratio (0.15-0.5: not hollow pipe, not solid profile)
    - Lower top2 face percentage (<60%: distributed faces from bends)
    - Reasonable aspect ratio (elongated)
    
    Example: U-profile (3mm thick, 40×60×201.5mm) has ~14 edges, 35% top2%, vol_ratio 0.33
    
    Args:
        solid: The solid to analyze
        volume: Volume in mm³
        dims: Sorted bounding box dimensions [smallest, middle, longest]
    
    Returns:
        True if this appears to be a bent sheet metal part
    """
    try:
        if not HAS_OCP:
            return False
        
        smallest, middle, longest = dims
        
        # CRITERION 1: Thickness must be thin (typical sheet metal)
        if smallest > BENT_SHEET_THICKNESS_MAX_MM:
            return False
        
        # CRITERION 2: Many edges (from bends/folds)
        edge_count = 0
        edge_exp = TopExp_Explorer(solid, TopAbs_EDGE)
        while edge_exp.More():
            edge_count += 1
            edge_exp.Next()
        
        if edge_count < BENT_SHEET_MIN_EDGE_COUNT:
            return False
        
        # CRITERION 3: Volume ratio in correct range (not hollow pipe, not solid)
        bbox_volume = smallest * middle * longest
        volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
        
        if volume_ratio < BENT_SHEET_VOLUME_RATIO_MIN or volume_ratio > BENT_SHEET_VOLUME_RATIO_MAX:
            return False
        
        # CRITERION 4: Top2 faces not too dominant (distributed from bends)
        top2_pct = _get_top2_face_percent(solid)
        if top2_pct > BENT_SHEET_TOP2_FACES_MAX_PCT:
            return False
        
        # CRITERION 5: Must be reasonably elongated
        aspect_ratio = longest / smallest if smallest > 0 else 0
        if aspect_ratio < BENT_SHEET_ASPECT_RATIO_MIN:
            return False
        
        # CRITERION 6: EXCLUSION - long hollow rectangular sections are profiles, not bent sheets.
        # Examples: 100x50 kokers with long length and low volume ratio.
        profile_cross_ratio = middle / smallest if smallest > 0 else 0
        profile_length_ratio = longest / middle if middle > 0 else 0
        if (
            smallest >= PLATE_THICK_MAX_MM and
            profile_length_ratio >= PROFILE_LENGTH_RATIO_MIN and
            PROFILE_CROSS_RATIO_MIN <= profile_cross_ratio <= PROFILE_CROSS_RATIO_MAX and
            volume_ratio <= STANDARD_TUBE_VOLUME_RATIO_MAX
        ):
            return False

        # CRITERION 7: EXCLUSION - Must NOT be a perfect circular/square cross-section
        # (perfect round/square = tube/rod profile, not bent sheet)
        bent_cross_ratio = smallest / middle if middle > 0 else 0
        if abs(bent_cross_ratio - 1.0) < 0.05:  # Tolerance for rounding: essentially 1.0
            return False  # Exclude perfect cylindrical/square profiles
        
        # All criteria met
        return True
        
    except:
        return False


def _get_top2_face_percent(solid) -> float:
    """Return percentage surface area covered by the two largest faces."""
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
            return 0.0

        face_areas.sort(reverse=True)
        total_area = sum(face_areas)
        if total_area <= 0:
            return 0.0

        return ((face_areas[0] + face_areas[1]) / total_area) * 100.0
    except Exception:
        return 0.0


def _estimate_bend_angle_sum(solid, min_angle_deg: float = 20.0, min_length_mm: float = 5.0) -> float:
    """Estimate total bend angle (degrees) from cylindrical faces.

    Strategy:
    - Collect cylindrical faces
    - Estimate bend length from face area / circumference
    - Ignore very small/short cylinders (holes, fillets)
    - Deduplicate inner/outer bend faces by (angle, length)

    Returns:
        Sum of unique bend angles in degrees
    """
    try:
        if not HAS_OCP:
            return 0.0

        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder

        cylinders = []

        face_exp = TopExp_Explorer(solid, TopAbs_FACE)
        while face_exp.More():
            face = TopoDS.Face_s(face_exp.Current())
            surf = BRepAdaptor_Surface(face, True)

            if surf.GetType() == GeomAbs_Cylinder:
                cyl = surf.Cylinder()
                radius = cyl.Radius()
                if radius <= 0:
                    face_exp.Next()
                    continue

                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()

                circumference = 2.0 * math.pi * radius
                bend_length = area / circumference if circumference > 0 else 0.0

                try:
                    u_min = surf.FirstUParameter()
                    u_max = surf.LastUParameter()
                    angle_deg = abs(math.degrees(u_max - u_min))
                except Exception:
                    angle_deg = 0.0

                if angle_deg >= min_angle_deg and bend_length >= min_length_mm:
                    cylinders.append({
                        "angle_deg": angle_deg,
                        "bend_length": bend_length,
                        "radius": radius,
                    })

            face_exp.Next()

        if not cylinders:
            return 0.0

        unique = {}
        for c in cylinders:
            key = (round(c["angle_deg"], 1), round(c["bend_length"], 1))
            if key not in unique or c["radius"] < unique[key]["radius"]:
                unique[key] = c

        return sum(c["angle_deg"] for c in unique.values())

    except Exception:
        return 0.0


def _get_solid_bbox_extents(solid) -> Optional[Tuple[float, float, float, float, float, float]]:
    """Get raw bbox extents (xmin, ymin, zmin, xmax, ymax, zmax)."""
    if not HAS_OCP:
        return None
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.Add_s(solid, box)
        return box.Get()
    except Exception:
        return None


def _extract_section_signature(
    solid,
    axis_index: int,
    axis_coordinate: float,
    vertex_snap_mm: float = 0.05,
) -> Optional[Dict[str, Any]]:
    """Extract section signature (closed/open, edge count, perimeter) on a plane.

    Args:
        solid: OCP solid
        axis_index: 0=x, 1=y, 2=z
        axis_coordinate: coordinate value along selected axis
        vertex_snap_mm: spatial snap tolerance for vertex graph matching

    Returns:
        dict(edge_count, perimeter, closed) or None when section failed/empty
    """
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX

        if axis_index == 0:
            plane = gp_Pln(gp_Pnt(axis_coordinate, 0.0, 0.0), gp_Dir(1.0, 0.0, 0.0))
        elif axis_index == 1:
            plane = gp_Pln(gp_Pnt(0.0, axis_coordinate, 0.0), gp_Dir(0.0, 1.0, 0.0))
        else:
            plane = gp_Pln(gp_Pnt(0.0, 0.0, axis_coordinate), gp_Dir(0.0, 0.0, 1.0))

        try:
            section_op = BRepAlgoAPI_Section(solid, plane, False)
        except TypeError:
            section_op = BRepAlgoAPI_Section(solid, plane)

        section_op.Build()
        if hasattr(section_op, "IsDone") and not section_op.IsDone():
            return None

        section_shape = section_op.Shape()
        edge_exp = TopExp_Explorer(section_shape, TopAbs_EDGE)

        edge_count = 0
        perimeter = 0.0
        vertex_degree: Dict[Tuple[int, int, int], int] = {}

        while edge_exp.More():
            edge = TopoDS.Edge_s(edge_exp.Current())

            props = GProp_GProps()
            if hasattr(BRepGProp, "LinearProperties_s"):
                BRepGProp.LinearProperties_s(edge, props)
            else:
                BRepGProp.LinearProperties(edge, props)
            edge_length = props.Mass()

            if edge_length > 1e-6:
                edge_count += 1
                perimeter += edge_length

                vertex_exp = TopExp_Explorer(edge, TopAbs_VERTEX)
                vertex_keys: List[Tuple[int, int, int]] = []
                while vertex_exp.More():
                    vertex = TopoDS.Vertex_s(vertex_exp.Current())
                    point = BRep_Tool.Pnt_s(vertex)
                    vertex_keys.append(
                        (
                            int(round(point.X() / vertex_snap_mm)),
                            int(round(point.Y() / vertex_snap_mm)),
                            int(round(point.Z() / vertex_snap_mm)),
                        )
                    )
                    vertex_exp.Next()

                if len(vertex_keys) >= 2:
                    start_key = vertex_keys[0]
                    end_key = vertex_keys[-1]
                    vertex_degree[start_key] = vertex_degree.get(start_key, 0) + 1
                    vertex_degree[end_key] = vertex_degree.get(end_key, 0) + 1

            edge_exp.Next()

        if edge_count == 0:
            return None

        is_closed = edge_count >= 4 and bool(vertex_degree) and all(deg >= 2 for deg in vertex_degree.values())
        return {
            "edge_count": edge_count,
            "perimeter": perimeter,
            "closed": is_closed,
        }
    except Exception:
        return None


def _detect_closed_constant_cross_section(
    solid,
    dims: Tuple[float, float, float],
) -> Tuple[bool, Dict[str, Any]]:
    """Detect closed, near-constant cross-section along dominant length axis.

    This acts as a hard profile signature for long hollow/solid extrusions,
    reducing confusion with bent open-sheet geometries.
    """
    metrics: Dict[str, Any] = {
        "section_samples": 0,
        "section_closed_count": 0,
        "section_closed_ratio": 0.0,
        "section_perimeter_cv": None,
        "section_edge_span": None,
    }

    try:
        if not HAS_OCP:
            return False, metrics

        smallest, middle, longest = dims
        if smallest <= 0 or middle <= 0 or longest <= 0:
            return False, metrics

        length_ratio = longest / middle if middle > 0 else 0.0
        cross_ratio = middle / smallest if smallest > 0 else 0.0

        # Run this expensive check only for plausible profile candidates.
        if not (
            smallest >= PROFILE_SMALLEST_MIN_MM and
            length_ratio >= PROFILE_LENGTH_RATIO_MIN and
            PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX
        ):
            return False, metrics

        bbox_extents = _get_solid_bbox_extents(solid)
        if not bbox_extents:
            return False, metrics

        xmin, ymin, zmin, xmax, ymax, zmax = bbox_extents
        axis_lengths = [xmax - xmin, ymax - ymin, zmax - zmin]
        axis_index = max(range(3), key=lambda idx: axis_lengths[idx])

        axis_min = [xmin, ymin, zmin][axis_index]
        axis_max = [xmax, ymax, zmax][axis_index]
        if axis_max <= axis_min:
            return False, metrics

        signatures: List[Dict[str, Any]] = []
        for fraction in CROSS_SECTION_SAMPLE_FRACTIONS:
            section_pos = axis_min + (axis_max - axis_min) * fraction
            signature = _extract_section_signature(solid, axis_index, section_pos)
            if signature:
                signatures.append(signature)

        metrics["section_samples"] = len(signatures)
        if len(signatures) < CROSS_SECTION_MIN_VALID_SAMPLES:
            return False, metrics

        closed_signatures = [entry for entry in signatures if entry.get("closed")]
        closed_ratio = len(closed_signatures) / len(signatures)
        metrics["section_closed_count"] = len(closed_signatures)
        metrics["section_closed_ratio"] = round(closed_ratio, 3)

        if closed_ratio < CROSS_SECTION_CLOSED_RATIO_MIN:
            return False, metrics

        perimeters = [entry["perimeter"] for entry in closed_signatures if entry.get("perimeter", 0.0) > 0.0]
        if len(perimeters) < 2:
            return False, metrics

        perimeter_avg = sum(perimeters) / len(perimeters)
        if perimeter_avg <= 0:
            return False, metrics

        variance = sum((value - perimeter_avg) ** 2 for value in perimeters) / len(perimeters)
        perimeter_cv = math.sqrt(variance) / perimeter_avg

        edge_counts = [entry["edge_count"] for entry in closed_signatures if entry.get("edge_count", 0) > 0]
        edge_span = (max(edge_counts) - min(edge_counts)) if edge_counts else 999

        metrics["section_perimeter_cv"] = round(perimeter_cv, 4)
        metrics["section_edge_span"] = int(edge_span)

        is_constant = (
            perimeter_cv <= CROSS_SECTION_PERIMETER_CV_MAX and
            edge_span <= CROSS_SECTION_EDGE_COUNT_SPAN_MAX
        )
        return is_constant, metrics

    except Exception:
        return False, metrics


def classify_solid_scored(solid) -> Tuple[str, Dict[str, Any]]:
    """Score-based classification with explainable trace."""
    dims = _solid_bbox_sorted(solid)
    smallest, middle, longest = dims

    volume = get_solid_volume(solid)
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0

    aspect_ratio = longest / smallest if smallest > 0 else 0.0
    thickness_ratio = smallest / middle if middle > 0 else 0.0
    length_ratio = longest / middle if middle > 0 else 0.0
    cross_ratio = middle / smallest if smallest > 0 else 0.0
    top2_percent = _get_top2_face_percent(solid)
    surface_area = _get_solid_surface_area(solid)
    sa_v_ratio = surface_area / volume if volume > 0 else 0.0

    scores = {"plaat": 0.0, "profiel": 0.0, "anders": 0.0}
    reasons = {"plaat": [], "profiel": [], "anders": []}

    if top2_percent >= SCORE_PLATE_TOP2_HIGH_PCT:
        scores["plaat"] += SCORE_PLATE_PRIMARY_POINTS + 1.0
        reasons["plaat"].append(f"top2%>=high ({top2_percent:.1f})")
    elif top2_percent >= SCORE_PLATE_TOP2_MIN_PCT:
        scores["plaat"] += SCORE_PLATE_PRIMARY_POINTS
        reasons["plaat"].append(f"top2%>=min ({top2_percent:.1f})")

    if (smallest < PLATE_THICK_MAX_MM and
        thickness_ratio < PLATE_THICKNESS_RATIO_MAX and
        aspect_ratio > PLATE_ASPECT_RATIO_MIN):
        scores["plaat"] += 2.0
        reasons["plaat"].append("thin-plate-ratios")

    if (top2_percent >= SCORE_PLATE_SUPPORT_TOP2_PCT and
        thickness_ratio < SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX and
        aspect_ratio > SCORE_PLATE_SUPPORT_ASPECT_MIN):
        scores["plaat"] += 1.0
        reasons["plaat"].append("support-plate-shape")

    profile_primary = (
        smallest >= PROFILE_SMALLEST_MIN_MM and
        length_ratio >= PROFILE_LENGTH_RATIO_MIN and
        PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX
    )
    if profile_primary:
        scores["profiel"] += SCORE_PROFILE_PRIMARY_POINTS
        reasons["profiel"].append("primary-profile-ratios")

        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            scores["profiel"] += 2.0
            reasons["profiel"].append("strong-volume-fill")
        elif volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            scores["profiel"] += 1.0
            reasons["profiel"].append("weak-volume-fill")

        if 0 < sa_v_ratio < PROFILE_SA_V_RATIO_MAX:
            scores["profiel"] += 1.0
            reasons["profiel"].append("low-sa-v")

    if top2_percent < SCORE_PLATE_SUPPORT_TOP2_PCT:
        scores["anders"] += 1.5
        reasons["anders"].append("low-top2")
    if not profile_primary:
        scores["anders"] += 0.5
        reasons["anders"].append("not-profile-primary")
    if volume_ratio < PROFILE_VOLUME_RATIO_WEAK_MIN:
        scores["anders"] += 1.0
        reasons["anders"].append("low-volume-fill")

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_class, best_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    margin = best_score - second_score

    if margin < SCORE_AMBIGUOUS_MARGIN_MIN:
        best_class = "anders"
        reasons["anders"].append(f"ambiguous-margin<{SCORE_AMBIGUOUS_MARGIN_MIN}")

    trace = {
        "mode": "score",
        "features": {
            "top2_percent": round(top2_percent, 3),
            "smallest": round(smallest, 3),
            "middle": round(middle, 3),
            "longest": round(longest, 3),
            "aspect_ratio": round(aspect_ratio, 3),
            "thickness_ratio": round(thickness_ratio, 3),
            "length_ratio": round(length_ratio, 3),
            "cross_ratio": round(cross_ratio, 3),
            "volume_ratio": round(volume_ratio, 3),
            "sa_v_ratio": round(sa_v_ratio, 6),
        },
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "reasons": reasons,
        "selected": best_class,
        "margin": round(margin, 3),
    }
    return best_class, trace


def classify_solid(solid, return_trace: bool = False):
    """
    Classify a solid based on its geometry.
    
    Returns one of: "plaat", "profiel", "anders"
    
    Classification logic (v2.2):
    
    STEP 1: STANDARD PROFILE CHECK (purchased items - name-based heuristic failed)
    - Hollow tube: cylindrical ≥60%, volume_ratio <0.7 → "anders"
    - Variable thickness: face area diff >20%, elongated ≥5.0 → "anders"

    STEP 1.25: HARD PROFILE OVERRIDE (closed & constant cross-section)
    - Multi-slice section check along dominant axis
    - Closed contour ratio high + low perimeter variation → "profiel"
    
    STEP 2: PLATE DETECTION
    - PLAAT: Detected by face analysis (top 2 faces > 60% surface area) OR
             traditional thin plate criteria (thickness<25mm, thickness_ratio<0.15, aspect>5)
    
    STEP 3: PROFILE DETECTION
    - PROFIEL: smallest≥5mm, length_ratio≥5.0, cross_ratio 0.5-2.0, constant cross-section
    
    STEP 4: DEFAULT
    - ANDERS: everything else (machined parts, complex geometry)
    
    Key insight (v2.2):
    Standard profiles (tubes, UNP, I-beams) must be detected BEFORE plate check.
    Otherwise, tubes with dominant end faces (94%) and UNP with flat web (52%)
    incorrectly trigger plate classification.
    """
    mode = os.environ.get("ALES_CLASSIFICATION_MODE", "legacy").strip().lower()
    if mode == "score":
        klass, trace = classify_solid_scored(solid)
        return (klass, trace) if return_trace else klass

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
    
    trace = {
        "mode": "legacy",
        "version": "2.2",
        "features": {
            "smallest": round(smallest, 3),
            "middle": round(middle, 3),
            "longest": round(longest, 3),
            "aspect_ratio": round(aspect_ratio, 3),
            "thickness_ratio": round(thickness_ratio, 3),
            "length_ratio": round(length_ratio, 3),
            "cross_ratio": round(cross_ratio, 3),
            "volume_ratio": round(volume_ratio, 3),
            "top2_percent": round(_get_top2_face_percent(solid), 3),
        },
        "rules": [],
    }
    
    # ============================================================================
    # STEP 1: STANDARD PROFILE CHECK (v2.1)
    # Purchased items that name-based heuristics missed (STEP parser failure)
    # ============================================================================
    
    # 1a. Hollow tube detection (EN 10210-2, etc.)
    # Example: Ø88.9×4×65mm tube has cylindrical faces 94% but top2_faces also 94%
    # Must check BEFORE plate detection to avoid false positive
    if _detect_hollow_tube(solid, volume, dims):
        trace["rules"].append("standard_hollow_tube")
        return ("anders", trace) if return_trace else "anders"
    
    # 1b. Variable thickness profile detection (DIN 1026 UNP, I-beams, etc.)
    # Example: UNP160 has top2_faces 52% but variable thickness indicates standard profile
    # Must check BEFORE plate detection to avoid false positive
    if _detect_variable_thickness(solid, dims):
        trace["rules"].append("standard_variable_thickness")
        return ("anders", trace) if return_trace else "anders"

    # 1c. Hard profile signature: closed + near-constant cross-section
    # This protects long hollow/solid extrusions against bent-sheet heuristics.
    is_closed_constant_profile, section_metrics = _detect_closed_constant_cross_section(solid, dims)
    trace["features"].update(section_metrics)
    if is_closed_constant_profile:
        trace["rules"].append("closed_constant_section")
        return ("profiel", trace) if return_trace else "profiel"
    
    # ============================================================================
    # STEP 1.5: BENT SHEET DETECTION (v2.1)
    # Formed/folded sheet metal (U-profiles, channels, trays)
    # ============================================================================
    # Bent sheets have many edges and thin material, but lower top2% than flat plates
    # Must check BEFORE traditional plate detection to catch shaped sheet metal
    if _detect_bent_sheet(solid, volume, dims):
        bend_angle_sum = _estimate_bend_angle_sum(solid)
        trace["features"]["bend_angle_sum"] = round(bend_angle_sum, 3)

        # Closed loop profile rule requested by user:
        # if sum of bend angles >= 360°, classify as profile instead of bent sheet.
        if bend_angle_sum >= 360.0:
            trace["rules"].append("closed_profile_bend_sum")
            return ("profiel", trace) if return_trace else "profiel"

        trace["rules"].append("bent_sheet_metal")
        return ("plaat", trace) if return_trace else "plaat"
    
    # ============================================================================
    # STEP 2: PLATE DETECTION
    # ============================================================================
    
    # PLAAT check: Use face analysis as primary method (more reliable)
    # Lower threshold (50%) for industrial plates with holes/cutouts/weld preparations
    if _is_plate_by_face_analysis(solid, threshold=PLATE_FACE_TOP2_THRESHOLD_PCT):
        trace["rules"].append("plate_face")
        return ("plaat", trace) if return_trace else "plaat"
    
    # Fallback: traditional thin plate check for very thin plates (< 25mm)
    # thickness_ratio < 0.15 means thickness is less than 15% of width = flat
    if smallest < PLATE_THICK_MAX_MM and thickness_ratio < PLATE_THICKNESS_RATIO_MAX and aspect_ratio > PLATE_ASPECT_RATIO_MIN:
        trace["rules"].append("plate_thin")
        return ("plaat", trace) if return_trace else "plaat"
    
    # ============================================================================
    # STEP 3: PROFILE DETECTION
    # ============================================================================
    
    # PROFIEL check: solid beam/profile
    # Primary criteria: rectangular cross section (cross_ratio 0.5-2.0), elongated (length_ratio >= 5.0)
    if smallest >= PROFILE_SMALLEST_MIN_MM and length_ratio >= PROFILE_LENGTH_RATIO_MIN and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX:
        # Secondary check: must have significant volume fill
        # High volume_ratio (>0.5) = definitely solid profiel
        # Medium volume_ratio (0.15-0.5) = could be profiel with internal features OR formed plate
        
        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            # Clear case: solid rectangular beam
            trace["rules"].append("profile_primary_strong")
            return ("profiel", trace) if return_trace else "profiel"
        elif volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            # Ambiguous: could be profiel with internal features or formed plate
            # Use surface complexity as tiebreaker (lower = likely profiel)
            # Formed plates with bends have higher surface area relative to volume
            try:
                surface_area = _get_solid_surface_area(solid)
                if surface_area > 0:
                    # Surface to volume ratio: profiel should have lower SA/V than formed sheet
                    sa_v_ratio = surface_area / volume
                    # Rough threshold: constant profiel < 1.5 cm^-1, formed plate > 1.0 cm^-1
                    if sa_v_ratio < PROFILE_SA_V_RATIO_MAX:  # More surface fill = solid
                        trace["rules"].append("profile_primary_weak_sav")
                        return ("profiel", trace) if return_trace else "profiel"
            except:
                pass
    
    # ============================================================================
    # STEP 4: DEFAULT
    # ============================================================================
    
    # Default: includes formed sheet metal with bends, machined parts, etc.
    trace["rules"].append("default_anders")
    return ("anders", trace) if return_trace else "anders"


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
        
        # STEP format (varies by exporter):
        # NEXT_ASSEMBLY_USAGE_OCCURRENCE('NAUO1',' ','part_name.instance',#parent,#child,$)
        # or with blank name field. We only count non-empty explicit names.
        assembly_pattern = r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'([^']*)'"
        assembly_items = re.findall(assembly_pattern, content)
        
        if not assembly_items:
            return None
        
        # Count parts, removing instance suffixes (.1, .2, etc.)
        # Example: "10040854_1.1" -> "10040854_1"
        parts_count = defaultdict(int)
        for raw_name in assembly_items:
            full_name = (raw_name or '').strip()
            if not full_name:
                continue
            base_name = re.sub(r'\.\d+$', '', full_name)
            if base_name:
                parts_count[base_name] += 1
        
        return dict(parts_count) if parts_count else None
        
    except Exception as e:
        # Fail silently and fall back to geometric analysis
        return None


def parse_step_product_names(step_file_path: str) -> Optional[List[str]]:
    """
    Parse STEP file to extract candidate part names directly from STEP entities.

    Priority order:
    1) PRODUCT names (preferred)
    2) SHAPE_REPRESENTATION names
    3) PRODUCT_DEFINITION names (legacy fallback)

    Filters out:
    - Main assembly name (matches filename stem)
    - Frame/Skeleton helper geometry
    - Empty/'NONE' values
    - Clear material-only PRODUCT_DEFINITION labels (e.g. AISI ...)
    
    Args:
        step_file_path: Path to STEP file
        
    Returns:
        List of part names in order, or None if parsing fails
        
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
        
        # Some exporters put a secondary assembly alias in FILE_NAME header (e.g. ..._000)
        # which should not be used as part name candidates.
        header_file_stem = ''
        header_match = re.search(r"FILE_NAME\s*\(\s*'([^']+)'", content)
        if header_match:
            header_file_stem = Path((header_match.group(1) or '').strip()).stem

        def _is_candidate(name: str) -> bool:
            candidate = (name or '').strip()
            if not candidate:
                return False
            if candidate.upper() == 'NONE':
                return False
            if candidate == main_assembly_name:
                return False
            if header_file_stem and candidate.lower() == header_file_stem.lower():
                return False

            candidate_lower = candidate.lower()
            if candidate_lower.startswith('frame') or candidate_lower.startswith('skeleton'):
                return False
            if '_skeleton' in candidate_lower:
                return False

            # Avoid material labels that can appear in PRODUCT_DEFINITION
            if candidate_lower.startswith('aisi '):
                return False
            
            # Filter out generic SpaceClaim shape names
            if candidate_lower.startswith('vaste vorm'):
                return False

            return True

        def _dedupe_preserve_order(names: List[str]) -> List[str]:
            seen = set()
            result = []
            for name in names:
                key = name.strip()
                if key in seen:
                    continue
                seen.add(key)
                result.append(key)
            return result

        # 1) PRODUCT names (best source for explicit part names)
        product_pattern = r"PRODUCT\s*\(\s*'([^']+)'"
        product_names = [name.strip() for name in re.findall(product_pattern, content) if _is_candidate(name)]
        product_names = _dedupe_preserve_order(product_names)
        if product_names:
            return product_names

        # 2) SHAPE_REPRESENTATION names (fallback)
        shape_pattern = r"SHAPE_REPRESENTATION\s*\(\s*'([^']+)'"
        shape_names = [name.strip() for name in re.findall(shape_pattern, content) if _is_candidate(name)]
        shape_names = _dedupe_preserve_order(shape_names)
        if shape_names:
            return shape_names

        # 3) PRODUCT_DEFINITION names (legacy fallback)
        product_def_pattern = r"PRODUCT_DEFINITION\s*\(\s*'([^']+)'"
        product_def_names = [name.strip() for name in re.findall(product_def_pattern, content) if _is_candidate(name)]
        product_def_names = _dedupe_preserve_order(product_def_names)
        if product_def_names:
            return product_def_names

        return None
        
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
            class_trace = {}
            if part_class is None:
                class_result = classify_solid(solid, return_trace=True)
                part_class, class_trace = class_result
            
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
                classification_trace=class_trace,
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
