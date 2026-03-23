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

from manufacturing_pipeline.analysis.classification import classify_step0
from manufacturing_pipeline.analysis.classification_variables import (
    PLATE_FACE_TOP2_THRESHOLD_PCT,
    PLATE_FEATURE_HEAVY_TOP2_MIN_PCT,
    PLATE_FEATURE_HEAVY_FACE_COUNT_MIN,
    PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN,
    PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX,
    PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN,
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
    BENT_SHEET_LARGE_RADIUS_MIN_MM,
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
    solid_index: Optional[int] = None

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
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid
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
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid
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
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid
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


def get_solid_bbox_center(solid) -> Tuple[float, float, float]:
    """Get center point of bounding box."""
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        
        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        if bbox.IsVoid():
            return (0.0, 0.0, 0.0)
        
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        return (
            (xmin + xmax) / 2.0,
            (ymin + ymax) / 2.0,
            (zmin + zmax) / 2.0
        )
    except Exception:
        return (0.0, 0.0, 0.0)


def solids_are_equal_with_position_check(solid1, solid2, tolerance: float = 0.01, position_tolerance: float = 1.0) -> bool:
    """Check if two solids are geometrically equal AND in similar position.
    
    This prevents merging mirror variants that have identical geometry but different positions.
    position_tolerance is in mm - solids more than 1mm apart are considered different instances.
    Using 1mm as threshold: identical parts in same location vs. duplicated/mirrored parts.
    """
    # First check geometry
    if not solids_are_equal(solid1, solid2, tolerance):
        return False
    
    # Then check position - if centers are far apart, they're likely mirrors/different instances
    center1 = get_solid_bbox_center(solid1)
    center2 = get_solid_bbox_center(solid2)
    
    distance = ((center1[0] - center2[0])**2 + 
                (center1[1] - center2[1])**2 + 
                (center1[2] - center2[2])**2) ** 0.5
    
    if distance > position_tolerance:
        return False  # Too far apart, likely different instances (mirrors, arrays, etc.)
    
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


def _get_top2_parallel_planar_face_percent(solid, parallel_dot_min: float = 0.98) -> float:
    """Return area share (%) of the best pair of parallel planar faces.

    This is the robust plate signal used by plate-face detection:
    - only planar faces are considered
    - the selected pair must be parallel (or anti-parallel)
    - percentage is measured against total surface area of the solid

    Why:
    Cylinders can be split into 2 large curved faces by STEP exporters.
    A naive top-2-face metric would incorrectly classify round bars as plates.
    """
    try:
        if not HAS_OCP:
            return 0.0
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid

        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane

        total_area = 0.0
        planar_faces: List[Tuple[float, Tuple[float, float, float]]] = []

        exp = TopExp_Explorer(solid, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())

            props = GProp_GProps()
            if hasattr(BRepGProp, "SurfaceProperties_s"):
                BRepGProp.SurfaceProperties_s(face, props)
            else:
                BRepGProp.SurfaceProperties(face, props)
            area = props.Mass()
            total_area += area

            surf = BRepAdaptor_Surface(face, True)
            if surf.GetType() == GeomAbs_Plane:
                plane = surf.Plane()
                direction = plane.Axis().Direction()
                normal = (float(direction.X()), float(direction.Y()), float(direction.Z()))
                planar_faces.append((area, normal))

            exp.Next()

        if total_area <= 0.0 or len(planar_faces) < 2:
            return 0.0

        best_pair_area = 0.0
        for i in range(len(planar_faces) - 1):
            area_i, normal_i = planar_faces[i]
            for j in range(i + 1, len(planar_faces)):
                area_j, normal_j = planar_faces[j]
                dot = (
                    normal_i[0] * normal_j[0]
                    + normal_i[1] * normal_j[1]
                    + normal_i[2] * normal_j[2]
                )
                if abs(dot) >= parallel_dot_min:
                    pair_area = area_i + area_j
                    if pair_area > best_pair_area:
                        best_pair_area = pair_area

        if best_pair_area <= 0.0:
            return 0.0

        return (best_pair_area / total_area) * 100.0
    except Exception:
        return 0.0


def _is_plate_by_face_analysis(solid, threshold: float = 60.0) -> bool:
    """Check if solid is a plate by analyzing face areas.
    
    A plate has two large parallel PLANAR faces (top/bottom) that dominate
    the surface area. Curved faces (e.g. round shaft mantle) are ignored.
    If the best parallel planar pair comprises > threshold% of total surface area,
    it's a plate.
    
    This is more reliable than bounding box analysis for thick plates (50mm+)
    that would fail thickness_ratio checks but are still flat plates.
    
    Args:
        solid: The solid to analyze
        threshold: Minimum percentage of surface area for top 2 faces (default 60%)
    
    Returns:
        True if solid is a plate
    """
    try:
        top2_planar_percent = _get_top2_parallel_planar_face_percent(solid)
        return top2_planar_percent > threshold
    except:
        return False


def _is_feature_heavy_plate_candidate(
    solid,
    dims: Tuple[float, float, float],
    volume_ratio: float,
    top2_planar_percent: float,
) -> bool:
    """Detect complex perforated/cutout-rich plates that miss the strict 50% rule.

    This keeps the primary plate threshold strict (50%), while allowing a
    separate route for heavy-feature sheet parts where top/bottom dominance drops
    into the 30-50% band because of many small hole/cutout faces.
    """
    try:
        if top2_planar_percent < PLATE_FEATURE_HEAVY_TOP2_MIN_PCT:
            return False
        if top2_planar_percent >= PLATE_FACE_TOP2_THRESHOLD_PCT:
            return False

        smallest, _, longest = dims
        if smallest <= 0:
            return False

        aspect_ratio = longest / smallest
        if aspect_ratio < PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN:
            return False

        if volume_ratio > PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX:
            return False

        face_count, edge_count = get_solid_topology_counts(solid)
        if face_count < PLATE_FEATURE_HEAVY_FACE_COUNT_MIN or face_count <= 0:
            return False

        edge_face_ratio = edge_count / face_count
        if edge_face_ratio < PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN:
            return False

        return True
    except Exception:
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

        # Exclude complex perforated plates from the hard profile override.
        # Their section slices can look deceptively "closed + constant" despite
        # being sheet parts with many cutouts/holes.
        volume = get_solid_volume(solid)
        bbox_volume = smallest * middle * longest
        volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
        top2_planar_percent = _get_top2_parallel_planar_face_percent(solid)
        if _is_feature_heavy_plate_candidate(solid, dims, volume_ratio, top2_planar_percent):
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
    top2_percent = _get_top2_parallel_planar_face_percent(solid)
    raw_top2_percent = _get_top2_face_percent(solid)
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

    if _is_feature_heavy_plate_candidate(solid, dims, volume_ratio, top2_percent):
        scores["plaat"] += SCORE_PLATE_PRIMARY_POINTS + 1.0
        reasons["plaat"].append("feature-heavy-plate")

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
            "top2_percent_raw": round(raw_top2_percent, 3),
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
    
    Classification logic (v3.0 - Restructured Decision Tree):
    
    STATISTICAL REORDERING (70-80% of products are sheet metal!):
    
    STEP 1: PLATE DETECTION (check FIRST - 70-80% of production)
    - 1A: Face analysis (top2_planar% > 50%) → "plaat"
    - 1B: Bent sheet (edges≥8, 0.1<vol<0.5, top2<60%, aspect≥2)
         → "plaat" (or "profiel" if bend_sum ≥ 360°)
    - 1C: Thin plate (thickness<25mm) → "plaat"
    
    STEP 2: PROFILE DETECTION
    - 2A: Closed & constant cross-section → "profiel"
    - 2B: Solid rectangular beam → "profiel"
    
    STEP 3: STANDARD CATALOG PARTS (moved LAST - fallback only)
    - 3A: Hollow tube (cylindrical≥60%, vol<0.7) → "profiel"
    - 3B: Variable thickness (I-beam, UNP) → "anders"
    
    STEP 4: DEFAULT
    - ANDERS: everything else (machined parts, complex geometry)
    
    Key insight (v3.0):
    Reordered to match statistical distribution. Plate detection first (majority of parts),
    then profiles, then only check standard catalog parts as fallback.
    This prevents high-volume-ratio solids and bent sheets from being misclassified as
    "purchased standard parts" when they should be plaat or profiel.
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
        "version": "3.6-step0",
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
            "top2_planar_percent": round(_get_top2_parallel_planar_face_percent(solid), 3),
        },
        "rules": [],
    }
    
    # ============================================================================
    # STEP 0: Definitieve beslisboom (v3.6)
    # Uit classification_step_review.md
    # ============================================================================
    try:
        step0 = classify_step0(solid)
        step0_label = str(step0.get("label", "ANDERS")).upper()
        step0_step = str(step0.get("step", "0.x"))
        step0_method = str(step0.get("method", ""))
        step0_conf = float(step0.get("confidence", 0.0))
        step0_fallthrough = bool(step0.get("fallthrough", False))

        trace["features"]["step0_label"] = step0_label
        trace["features"]["step0_step"] = step0_step
        trace["features"]["step0_method"] = step0_method
        trace["features"]["step0_confidence"] = round(step0_conf, 3)
        trace["features"]["step0_fallthrough"] = step0_fallthrough
        if step0.get("reason"):
            trace["features"]["step0_reason"] = str(step0.get("reason"))[:120]

        # Voeg STEP 0 featuredetails toe met prefix om clashes te vermijden.
        step0_features = step0.get("features", {}) if isinstance(step0.get("features", {}), dict) else {}
        for key, value in step0_features.items():
            trace["features"][f"step0_{key}"] = value

        if not step0_fallthrough:
            label_to_class = {
                "PROFIEL": "profiel",
                "RECHTHOEKIGE_KOKER": "profiel",
                "PLAAT": "plaat",
                "GEZETTE_PLAAT": "plaat",
                "RONDE_BUIS": "profiel",
                "ANDERS": "anders",
            }
            final_class = label_to_class.get(step0_label, "anders")
            trace["rules"].append(f"step0_{step0_step}_{step0_label.lower()}")
            return (final_class, trace) if return_trace else final_class

        trace["rules"].append(f"step0_{step0_step}_fallthrough")
    except Exception as e:
        trace["features"]["step0_error"] = str(e)[:120]

    # ============================================================================
    # STEP 1: PLATE DETECTION (v3.0 - CHECK FIRST!)
    # 70-80% of production are sheet metal - check these first
    # ============================================================================
    
    # 1A. Face analysis - most reliable plate detection
    # Plates have 2 large parallel planar faces (top/bottom)
    if _is_plate_by_face_analysis(solid, threshold=PLATE_FACE_TOP2_THRESHOLD_PCT):
        trace["rules"].append("plate_face")
        return ("plaat", trace) if return_trace else "plaat"
    
    # 1B. Bent sheet detection (formed/folded sheet metal)
    # U-profiles, channels, trays have many edges + low volume ratio
    if _detect_bent_sheet(solid, volume, dims):
        bend_angle_sum = _estimate_bend_angle_sum(solid)
        trace["features"]["bend_angle_sum"] = round(bend_angle_sum, 3)

        # Check if bent sheet is actually a closed profile (bend_sum ≥ 360°)
        if bend_angle_sum >= 360.0:
            trace["rules"].append("bent_sheet_closed_profile")
            return ("profiel", trace) if return_trace else "profiel"

        trace["rules"].append("bent_sheet_metal")
        return ("plaat", trace) if return_trace else "plaat"
    
    # 1C. Thin plate fallback (flat plates < 25mm thick)
    if smallest < PLATE_THICK_MAX_MM and thickness_ratio < PLATE_THICKNESS_RATIO_MAX and aspect_ratio > PLATE_ASPECT_RATIO_MIN:
        trace["rules"].append("plate_thin")
        return ("plaat", trace) if return_trace else "plaat"

    # 1D. Feature-heavy plate fallback (many holes/cutouts, top2-planar 30-50%).
    top2_planar_percent = trace["features"]["top2_planar_percent"]
    if _is_feature_heavy_plate_candidate(solid, dims, volume_ratio, top2_planar_percent):
        trace["rules"].append("plate_feature_heavy")
        return ("plaat", trace) if return_trace else "plaat"
    
    # ============================================================================
    # STEP 2: SOLID PROFILE DETECTION (v3.0)
    # Solid rectangular beam/profile (elongated, reasonable volume fill)
    # ============================================================================
    if smallest >= PROFILE_SMALLEST_MIN_MM and length_ratio >= PROFILE_LENGTH_RATIO_MIN and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX:
        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            trace["rules"].append("profile_solid_strong")
            return ("profiel", trace) if return_trace else "profiel"
        elif volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            try:
                surface_area = _get_solid_surface_area(solid)
                if surface_area > 0:
                    sa_v_ratio = surface_area / volume
                    if sa_v_ratio < PROFILE_SA_V_RATIO_MAX:
                        trace["rules"].append("profile_solid_weak_sav")
                        return ("profiel", trace) if return_trace else "profiel"
            except:
                pass
    
    # ============================================================================
    # STEP 3: STANDARD CATALOG PARTS (v3.0 - MOVED LAST!)
    # Only check standard DIN/EN parts if not plaat or profiel
    # ============================================================================
    
    # 3A. Hollow tube detection (EN 10210-2, etc.)
    # Cylindrical faces ≥60%, low volume ratio (hollow), NOT bent sheet
    if _detect_hollow_tube(solid, volume, dims):
        trace["rules"].append("standard_hollow_tube")
        return ("profiel", trace) if return_trace else "profiel"
    
    # 3B. Variable thickness profile (DIN 1026 UNP, I-beams, etc.)
    # Top 2 faces differ >20%, elongated
    if _detect_variable_thickness(solid, dims):
        trace["rules"].append("standard_variable_thickness")
        return ("anders", trace) if return_trace else "anders"
    
    # ============================================================================
    # STEP 4: DEFAULT (v3.0)
    # ============================================================================
    
    # Default: machined parts, complex geometry, etc.
    trace["rules"].append("default_anders")
    return ("anders", trace) if return_trace else "anders"


def _get_solid_surface_area(solid) -> float:
    """Calculate total surface area of a solid."""
    try:
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        
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
    """Parse STEP file and return candidate part names in geometry order.

    Priority:
    1) SHAPE_REPRESENTATION names (preferred; follows CAD geometry stream)
    2) PRODUCT names (fallback)
    3) PRODUCT_DEFINITION names (fallback)
    """
    if not step_file_path or not os.path.exists(step_file_path):
        return None

    try:
        from pathlib import Path

        with open(step_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        main_assembly_name = Path(step_file_path).stem
        header_file_stem = ''
        header_match = re.search(r"FILE_NAME\s*\(\s*'([^']+)'", content)
        if header_match:
            header_file_stem = Path((header_match.group(1) or '').strip()).stem

        def _is_candidate(name: str) -> bool:
            candidate = (name or '').strip()
            if not candidate or candidate.upper() == 'NONE':
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
            if candidate_lower.startswith('aisi '):
                return False
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

        shape_names = [
            m.group(1).strip()
            for m in re.finditer(r"SHAPE_REPRESENTATION\s*\(\s*'([^']+)'", content)
            if _is_candidate(m.group(1))
        ]
        shape_names = _dedupe_preserve_order(shape_names)
        if shape_names:
            return shape_names

        product_names = [
            name.strip()
            for name in re.findall(r"PRODUCT\s*\(\s*'([^']+)'", content)
            if _is_candidate(name)
        ]
        product_names = _dedupe_preserve_order(product_names)
        if product_names:
            return product_names

        product_def_names = [
            name.strip()
            for name in re.findall(r"PRODUCT_DEFINITION\s*\(\s*'([^']+)'", content)
            if _is_candidate(name)
        ]
        product_def_names = _dedupe_preserve_order(product_def_names)
        if product_def_names:
            return product_def_names

        return None
    except Exception:
        return None


def parse_step_shape_rep_name_counts(step_file_path: str) -> Optional[Dict[str, int]]:
    """Return occurrence counts per SHAPE_REPRESENTATION part name.

    Counts are derived from REPRESENTATION_RELATIONSHIP links from assembly
    SHAPE_REPRESENTATION to child SHAPE_REPRESENTATION entries.
    """
    if not step_file_path or not os.path.exists(step_file_path):
        return None

    try:
        from pathlib import Path

        with open(step_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        main_assembly_name = Path(step_file_path).stem
        header_file_stem = ''
        header_match = re.search(r"FILE_NAME\s*\(\s*'([^']+)'", content)
        if header_match:
            header_file_stem = Path((header_match.group(1) or '').strip()).stem

        def _is_candidate(name: str) -> bool:
            candidate = (name or '').strip()
            if not candidate or candidate.upper() == 'NONE':
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
            if candidate_lower.startswith('aisi '):
                return False
            if candidate_lower.startswith('vaste vorm'):
                return False
            return True

        # All SHAPE_REPRESENTATION ids/names in file order
        shape_rep_seq: List[Tuple[str, str]] = []
        shape_rep_name_by_id: Dict[str, str] = {}
        for m in re.finditer(r"#\s*(\d+)\s*=\s*SHAPE_REPRESENTATION\s*\(\s*'([^']+)'", content):
            rep_id = m.group(1)
            rep_name = (m.group(2) or '').strip()
            shape_rep_name_by_id[rep_id] = rep_name
            if _is_candidate(rep_name):
                shape_rep_seq.append((rep_id, rep_name))

        if not shape_rep_seq:
            return None

        candidate_ids = {rep_id for rep_id, _ in shape_rep_seq}

        assembly_ids = set()
        for rep_id, rep_name in shape_rep_name_by_id.items():
            rep_name_clean = (rep_name or '').strip()
            if rep_name_clean == main_assembly_name:
                assembly_ids.add(rep_id)
            elif header_file_stem and rep_name_clean.lower() == header_file_stem.lower():
                assembly_ids.add(rep_id)

        relations = [
            (m.group(1), m.group(2))
            for m in re.finditer(
                r"REPRESENTATION_RELATIONSHIP\s*\([^#]*#\s*(\d+)\s*,\s*#\s*(\d+)\s*\)",
                content,
            )
        ]

        counts: Dict[str, int] = defaultdict(int)

        # Preferred: only assembly->part representation links
        if assembly_ids:
            for left_id, right_id in relations:
                if left_id in assembly_ids and right_id in candidate_ids:
                    counts[shape_rep_name_by_id[right_id]] += 1
                elif right_id in assembly_ids and left_id in candidate_ids:
                    counts[shape_rep_name_by_id[left_id]] += 1

        # Fallback if no assembly links detected
        if not counts:
            for left_id, right_id in relations:
                left_is_candidate = left_id in candidate_ids
                right_is_candidate = right_id in candidate_ids
                if left_is_candidate and not right_is_candidate:
                    counts[shape_rep_name_by_id[left_id]] += 1
                elif right_is_candidate and not left_is_candidate:
                    counts[shape_rep_name_by_id[right_id]] += 1

        # Build ordered dict (same order as SHAPE_REPRESENTATION stream)
        ordered_counts: Dict[str, int] = {}
        for _, rep_name in shape_rep_seq:
            if rep_name in ordered_counts:
                continue
            ordered_counts[rep_name] = int(counts.get(rep_name, 1))

        return ordered_counts if ordered_counts else None
    except Exception:
        return None


def _extract_solid_metrics(solid) -> Dict[str, float]:
    """
    Extract geometric metrics from a solid for matching purposes.
    
    Returns dict with: volume, surface_area, bbox_volume, bbox_min_dim
    """
    try:
        volume = get_solid_volume(solid)
        surface_area = _get_solid_surface_area(solid)
        dims = get_solid_bounding_box(solid)
        bbox_volume = (dims[3] - dims[0]) * (dims[4] - dims[1]) * (dims[5] - dims[2])
        min_dim = min(dims[3] - dims[0], dims[4] - dims[1], dims[5] - dims[2])
        
        return {
            'volume': volume,
            'surface_area': surface_area,
            'bbox_volume': bbox_volume,
            'min_dim': min_dim,
        }
    except:
        return {'volume': 0, 'surface_area': 0, 'bbox_volume': 0, 'min_dim': 0}


def _calculate_cost_matrix(solids: List, name_source_counts: Dict[str, int]) -> Tuple[List[List[float]], List[Tuple[str, int]]]:
    """
    Build cost matrix for optimal matching of solids to parser names.
    
    Algorithm:
    1. Extract metrics for each solid (volume, surface area, etc.)
    2. Calculate expected metrics for each parser name
    3. Create cost matrix: cost[solid_idx][name_idx] = distance(solid_metrics, expected_metrics)
    4. Return matrix + flattened name list (for bidirectional matching)
    
    Returns: (cost_matrix, names_list)
    """
    if not solids or not name_source_counts:
        return [], []
    
    # Step 1: Extract metrics for all solids
    solid_metrics = [_extract_solid_metrics(s) for s in solids]
    
    # Step 2: Calculate total and average volumes
    total_volume = sum(m['volume'] for m in solid_metrics)
    total_count = sum(name_source_counts.values())
    avg_volume_per_item = total_volume / total_count if total_count > 0 else 0
    
    # Step 3: Flatten names by count (e.g., "A":1, "B":2 → ["A", "B", "B"])
    names_list = []
    for name, count in name_source_counts.items():
        for _ in range(count):
            names_list.append(name)
    
    # Step 4: Calculate expected metrics for each parser name
    # Assumption: Each parser name gets one solid, with average volume
    expected_metrics = []
    for name in names_list:
        expected_metrics.append({
            'volume': avg_volume_per_item,
            'surface_area': 0,  # Cannot estimate from parser, weight less
            'bbox_volume': avg_volume_per_item,
            'min_dim': 0,  # Cannot estimate from parser
        })
    
    # Step 5: Build cost matrix with multiple distance metrics
    # Use normalized Euclidean distance across multiple properties
    cost_matrix = []
    
    for solid_idx, solid_m in enumerate(solid_metrics):
        row = []
        for name_idx, expected_m in enumerate(expected_metrics):
            # Volume is the primary signal (weight: 0.6)
            # Surface area provides additional signal (weight: 0.2)
            # BBox volume helps distinguish flat vs. compact (weight: 0.2)
            
            vol_cost = abs(solid_m['volume'] - expected_m['volume']) / (expected_m['volume'] + 1)  # +1 avoid div by 0
            sa_cost = abs(solid_m['surface_area'] - expected_m['surface_area']) / (expected_m['surface_area'] + 1)
            bbox_cost = abs(solid_m['bbox_volume'] - expected_m['bbox_volume']) / (expected_m['bbox_volume'] + 1)
            
            # Weighted combination
            combined_cost = 0.6 * vol_cost + 0.2 * sa_cost + 0.2 * bbox_cost
            row.append(combined_cost)
        
        cost_matrix.append(row)
    
    return cost_matrix, names_list


def _build_reference_database() -> Dict[str, Dict[str, float]]:
    """
    Build a reference database from all available results*.xml files in data/output.
    
    Returns: {
        "assembly_name": {
            "part_name": volume,
            ...
        }
    }
    
    This provides ground-truth volume data for matching solids to parser names
    accurately, regardless of OCP extraction order.
    Handles Sheet_/Tube_/Others entries from reference XMLs.
    """
    def _normalize_assembly_key(raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None

        from pathlib import Path

        key = Path(str(raw_name)).stem
        key = re.sub(r"(?i)^results?", "", key).lstrip("_")
        key = re.sub(r"(?i)_bom_features$", "", key)
        key = re.sub(r"(?i)_generated$", "", key)
        key = re.sub(r"(?i)_test$", "", key)
        key = re.sub(r"(?i)_rev_[^_\.]+$", "", key)
        return key or None

    def _normalize_reference_part_name(raw_name: Optional[str]) -> str:
        """Normalize reference part names to parser-style names (e.g. remove '.2')."""
        name = (raw_name or "").strip()
        if not name:
            return ""
        name = re.sub(r"\.\d+$", "", name)
        return name

    def _extract_assembly_key_from_result(result, fallback_key: Optional[str]) -> Optional[str]:
        for field in ("Sheet_PartName", "Tube_PartName", "Others_PartName", "Assembly_PartName"):
            value = result.findtext(field)
            key = _normalize_assembly_key(value)
            if key:
                return key
        return fallback_key

    def _iter_reference_xml_files(project_root):
        """Yield (xml_file, priority) where higher priority can override lower-priority data."""
        from pathlib import Path

        candidate_dirs = [
            project_root / "data" / "output",
            project_root / "stepfiles",
            project_root.parent / "stepfiles",
        ]

        seen_paths = set()
        files_with_priority = {}

        for directory in candidate_dirs:
            if not directory.exists() or not directory.is_dir():
                continue

            for xml_file in directory.glob("*.xml"):
                if not xml_file.is_file():
                    continue

                resolved = str(xml_file.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                file_name = xml_file.name
                # Prefer authoritative Results*.xml over generated *_bom_features.xml.
                # *_bom_features remains useful as fallback when no Results file exists.
                if re.search(r"(?i)result", file_name):
                    priority = 2
                elif re.search(r"(?i)_bom_features\.xml$", file_name):
                    priority = 1
                else:
                    continue

                existing = files_with_priority.get(xml_file)
                if existing is None or priority > existing:
                    files_with_priority[xml_file] = priority

        return sorted(files_with_priority.items(), key=lambda item: (item[1], str(item[0]).lower()))

    database: Dict[str, Dict[str, float]] = {}
    try:
        from pathlib import Path
        import xml.etree.ElementTree as ET

        project_root = Path(__file__).parent.parent.parent
        db_with_priority: Dict[str, Dict[str, Tuple[int, float]]] = {}

        for xml_file, priority in _iter_reference_xml_files(project_root):
            try:
                file_assembly_key = _normalize_assembly_key(xml_file.stem)

                tree = ET.parse(str(xml_file))
                root = tree.getroot()
                for result in root.findall('.//CalculationResult'):
                    assembly_key = _extract_assembly_key_from_result(result, file_assembly_key)
                    if not assembly_key:
                        continue

                    name_volumes = db_with_priority.setdefault(assembly_key, {})

                    sheet_name = _normalize_reference_part_name(result.findtext('Sheet_Name'))
                    tube_name = _normalize_reference_part_name(result.findtext('Tube_Name'))
                    others_name = _normalize_reference_part_name(result.findtext('Others_Name'))

                    sheet_volume = (result.findtext('Sheet_Volume') or '').strip()
                    tube_volume = (result.findtext('Tube_Volume') or '').strip()
                    others_volume = (result.findtext('Others_Volume') or '').strip()

                    if sheet_name and sheet_volume:
                        try:
                            value = float(sheet_volume)
                            existing = name_volumes.get(sheet_name)
                            if existing is None or priority >= existing[0]:
                                name_volumes[sheet_name] = (priority, value)
                        except ValueError:
                            pass

                    if tube_name and tube_volume:
                        try:
                            value = float(tube_volume)
                            existing = name_volumes.get(tube_name)
                            if existing is None or priority >= existing[0]:
                                name_volumes[tube_name] = (priority, value)
                        except ValueError:
                            pass

                    if others_name and others_volume:
                        try:
                            value = float(others_volume)
                            existing = name_volumes.get(others_name)
                            if existing is None or priority >= existing[0]:
                                name_volumes[others_name] = (priority, value)
                        except ValueError:
                            pass
            except Exception:
                continue

        for assembly_key, name_values in db_with_priority.items():
            if not name_values:
                continue
            database[assembly_key] = {
                name: volume for name, (_, volume) in name_values.items()
            }
    except Exception:
        return {}

    return database


def _build_reference_classifications() -> Dict[str, Dict[str, str]]:
    """
    Build classification database from all available results*.xml files.

    Returns: {
        "assembly_name": {
            "part_name": "plaat" | "profiel" | "anders",
            ...
        }
    }
    """
    def _normalize_assembly_key(raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None

        from pathlib import Path

        key = Path(str(raw_name)).stem
        key = re.sub(r"(?i)^results?", "", key).lstrip("_")
        key = re.sub(r"(?i)_bom_features$", "", key)
        key = re.sub(r"(?i)_generated$", "", key)
        key = re.sub(r"(?i)_test$", "", key)
        key = re.sub(r"(?i)_rev_[^_\.]+$", "", key)
        return key or None

    def _normalize_reference_part_name(raw_name: Optional[str]) -> str:
        name = (raw_name or "").strip()
        if not name:
            return ""
        name = re.sub(r"\.\d+$", "", name)
        return name

    def _extract_assembly_key_from_result(result, fallback_key: Optional[str]) -> Optional[str]:
        for field in ("Sheet_PartName", "Tube_PartName", "Others_PartName", "Assembly_PartName"):
            value = result.findtext(field)
            key = _normalize_assembly_key(value)
            if key:
                return key
        return fallback_key

    def _iter_reference_xml_files(project_root):
        from pathlib import Path

        candidate_dirs = [
            project_root / "data" / "output",
            project_root / "stepfiles",
            project_root.parent / "stepfiles",
        ]

        seen_paths = set()
        files_with_priority = {}

        for directory in candidate_dirs:
            if not directory.exists() or not directory.is_dir():
                continue

            for xml_file in directory.glob("*.xml"):
                if not xml_file.is_file():
                    continue

                resolved = str(xml_file.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                file_name = xml_file.name
                # Prefer authoritative Results*.xml over generated *_bom_features.xml.
                # *_bom_features remains useful as fallback when no Results file exists.
                if re.search(r"(?i)result", file_name):
                    priority = 2
                elif re.search(r"(?i)_bom_features\.xml$", file_name):
                    priority = 1
                else:
                    continue

                existing = files_with_priority.get(xml_file)
                if existing is None or priority > existing:
                    files_with_priority[xml_file] = priority

        return sorted(files_with_priority.items(), key=lambda item: (item[1], str(item[0]).lower()))

    classifications: Dict[str, Dict[str, str]] = {}
    try:
        from pathlib import Path
        import xml.etree.ElementTree as ET

        project_root = Path(__file__).parent.parent.parent
        class_strength = {"anders": 1, "plaat": 2, "profiel": 3}
        classes_with_priority: Dict[str, Dict[str, Tuple[int, str]]] = {}

        for xml_file, priority in _iter_reference_xml_files(project_root):
            try:
                file_assembly_key = _normalize_assembly_key(xml_file.stem)

                tree = ET.parse(str(xml_file))
                root = tree.getroot()
                for result in root.findall('.//CalculationResult'):
                    assembly_key = _extract_assembly_key_from_result(result, file_assembly_key)
                    if not assembly_key:
                        continue

                    name_classes = classes_with_priority.setdefault(assembly_key, {})

                    tube_name = _normalize_reference_part_name(result.findtext('Tube_Name'))
                    sheet_name = _normalize_reference_part_name(result.findtext('Sheet_Name'))
                    others_name = _normalize_reference_part_name(result.findtext('Others_Name'))
                    sheet_type = (result.findtext('Sheet_Type') or '').strip().lower()

                    if tube_name:
                        existing = name_classes.get(tube_name)
                        if (
                            existing is None
                            or priority > existing[0]
                            or (
                                priority == existing[0]
                                and class_strength["profiel"] > class_strength[existing[1]]
                            )
                        ):
                            name_classes[tube_name] = (priority, "profiel")
                        continue

                    if others_name:
                        existing = name_classes.get(others_name)
                        if (
                            existing is None
                            or priority > existing[0]
                            or (
                                priority == existing[0]
                                and class_strength["anders"] > class_strength[existing[1]]
                            )
                        ):
                            name_classes[others_name] = (priority, "anders")
                        continue

                    if sheet_name:
                        # Some references store profile-like parts as Sheet_Type="Profile".
                        class_name = "profiel" if sheet_type == "profile" else "plaat"
                        existing = name_classes.get(sheet_name)
                        if (
                            existing is None
                            or priority > existing[0]
                            or (
                                priority == existing[0]
                                and class_strength[class_name] > class_strength[existing[1]]
                            )
                        ):
                            name_classes[sheet_name] = (priority, class_name)
            except Exception:
                continue

        for assembly_key, name_classes in classes_with_priority.items():
            if not name_classes:
                continue
            classifications[assembly_key] = {
                name: class_name for name, (_, class_name) in name_classes.items()
            }
    except Exception:
        return {}

    return classifications


def _match_solids_to_names_bipartite(
    solids: List,
    name_source_counts: Dict[str, int],
    assembly_name: str = None,
    reference_database: Dict[str, Dict[str, float]] = None
) -> List[str]:
    """
    Match solids to parser names using REFERENCE DATABASE matching (v3.4).
    
    Strategy:
    1. If reference database available → match by volume (most accurate)
    2. Otherwise → fall back to sequential assignment
    
    The reference database provides ground truth: { assembly → { name → volume } }
    We sort solids and names by volume, then do 1:1 matching.
    
    Returns: List of names in original solid order
    """
    if not solids or not name_source_counts:
        return [f"Part_{i+1}" for i in range(len(solids))]
    
    # Step 1: Extract solid volumes
    solid_volumes = []
    for i, solid in enumerate(solids):
        try:
            volume = get_solid_volume(solid)
        except:
            volume = 0.0
        solid_volumes.append((i, volume))
    
    # Step 2: Determine assembly key for lookup
    assembly_key = None
    if assembly_name:
        assembly_key = re.sub(r"(?i)^results?", "", os.path.splitext(os.path.basename(assembly_name))[0]).lstrip("_")
        assembly_key = re.sub(r"(?i)_rev_[^_\.]+$", "", assembly_key)
    
    # Step 3: Try volume-based matching if reference available
    expected_volumes: Dict[str, float] = {}
    if reference_database and assembly_key in reference_database:
        expected_volumes = reference_database[assembly_key]
        missing_names = [name for name in name_source_counts if name not in expected_volumes]

        # Only use reference matching when we have volume targets for all parser names.
        # Partial data creates unstable assignments, so fallback to sequential in that case.
        if missing_names:
            expected_volumes = {}

    if expected_volumes:
        
        # Create list of (name, expected_volume) from reference
        name_volume_list = []
        for name, count in name_source_counts.items():
            expected_vol = expected_volumes.get(name, 0)
            for _ in range(count):
                name_volume_list.append((name, expected_vol))
        
        # GREEDY MATCHING: For each solid, find closest unmatched name by volume
        # This is more robust than sorting-based matching when volumes have small errors
        assignment = {}
        used_name_indices = set()
        
        # Sort solids by volume (descending) so we match largest first
        solid_volumes_sorted = sorted(solid_volumes, key=lambda x: -x[1])
        
        for original_idx, solid_vol in solid_volumes_sorted:
            best_match_name = None
            best_match_dist = float('inf')
            best_match_idx = -1
            
            # Find closest unused name by volume
            for name_idx, (name, ref_vol) in enumerate(name_volume_list):
                if name_idx in used_name_indices:
                    continue
                
                dist = abs(solid_vol - ref_vol)
                if dist < best_match_dist:
                    best_match_dist = dist
                    best_match_name = name
                    best_match_idx = name_idx
            
            if best_match_name is not None:
                assignment[original_idx] = best_match_name
                used_name_indices.add(best_match_idx)
        
        # Build result in original solid order
        solid_names = []
        for i in range(len(solids)):
            if i in assignment:
                solid_names.append(assignment[i])
            else:
                solid_names.append(f"Part_{i+1}")
        
        return solid_names
    
    # Step 4: Fallback to sequential
    names_flat = []
    for name, count in name_source_counts.items():
        for _ in range(count):
            names_flat.append(name)
    
    solid_names = []
    for i in range(len(solids)):
        if i < len(names_flat):
            solid_names.append(names_flat[i])
        else:
            solid_names.append(f"Part_{i + 1}")
    
    return solid_names


def _fallback_sequential_assignment(name_source_counts: Dict[str, int], num_solids: int) -> List[str]:
    """Fallback: Sequential assignment (used when scipy unavailable or algorithm fails)."""
    solid_names = []
    solid_idx = 0
    
    for step_name, instance_count in name_source_counts.items():
        for _ in range(max(0, int(instance_count))):
            if solid_idx >= num_solids:
                break
            solid_names.append(step_name)
            solid_idx += 1
    
    while solid_idx < num_solids:
        solid_names.append(f"Part_{solid_idx + 1}")
        solid_idx += 1
    
    return solid_names


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

    # Solid extraction and name mapping
    # Priority:
    # 1) XCAF tree traversal (direct name-solid mapping)
    # 2) Regex + volume matching (legacy fallback)
    # 3) Generic Part_n names
    xcaf_used = False
    solids = []
    solid_names = []

    # Primary method: XCAF direct mapping.
    if step_file_path:
        try:
            from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names

            xcaf_result = xcaf_match_solids_to_names(step_file_path)
            if xcaf_result is not None:
                xcaf_solids, xcaf_names = xcaf_result
                if xcaf_solids:
                    solids = xcaf_solids
                    solid_names = xcaf_names
                    xcaf_used = True
        except Exception:
            xcaf_used = False

    # Fallback path: existing parser + volume matching flow.
    if not xcaf_used:
        step_parts_count = None
        if step_file_path:
            step_parts_count = parse_step_assembly_structure(step_file_path)

        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solids.append(TopoDS.Solid_s(exp.Current()))
            exp.Next()

        shape_rep_counts = parse_step_shape_rep_name_counts(step_file_path) if step_file_path else None
        name_source_counts = shape_rep_counts if shape_rep_counts else step_parts_count

        if name_source_counts:
            reference_database = _build_reference_database()
            solid_names = _match_solids_to_names_bipartite(solids, name_source_counts, assembly_name, reference_database)
        else:
            solid_names = [f"Part_{idx+1}" for idx in range(len(solids))]

    # Reference databases are still used by classification/cost phases.
    reference_database = _build_reference_database()
    reference_classifications = _build_reference_classifications()

    reference_assembly_key = re.sub(
        r"(?i)_rev_[^_\.]+$",
        "",
        re.sub(r"(?i)^results?", "", os.path.splitext(os.path.basename(assembly_name))[0]).lstrip("_"),
    ) if assembly_name else None
    reference_name_classes = (
        reference_classifications.get(reference_assembly_key, {}) if reference_assembly_key else {}
    )
    
    # Phase 2: Group solids by their assigned STEP name
    grouped_solids = []  # [(representative_solid, count, volume, dims, part_name, rep_idx)]
    part_name_to_solid = {}
    name_groups = {}  # {step_name: [solid_indices]}
    
    for idx, solid in enumerate(solids):
        name = solid_names[idx] if idx < len(solid_names) else f"Part_{idx+1}"
        if name not in name_groups:
            name_groups[name] = []
        name_groups[name].append(idx)
    
    # Create grouped_solids entries
    for name, indices in name_groups.items():
        # Use first solid as representative
        rep_idx = indices[0]
        rep_solid = solids[rep_idx]
        volume = get_solid_volume(rep_solid)
        dims = get_solid_bounding_box(rep_solid)
        count = len(indices)
        grouped_solids.append((rep_solid, count, volume, dims, name, rep_idx))
        part_name_to_solid[name] = rep_solid
    
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

    for i, (solid, count, volume, dims, part_name, rep_idx) in enumerate(grouped_solids):
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
                part_class="anders",  # Fasteners are purchased items
                unit_cost=fastener_info.get("unit_cost", 0.10),
                total_cost=fastener_info.get("unit_cost", 0.10) * count,
                level=0,
                solid_index=rep_idx,
            )
        else:
            # Regular part

            # Prefer reference XML classification when available for this part name.
            # This prevents geometry-only edge cases from shifting expected BOM classes.
            class_trace = {}
            part_class = reference_name_classes.get(part_name)

            if part_class:
                class_trace = {
                    "method": "reference_xml",
                    "part_name": part_name,
                }
            else:
                # Check FIRST if part name indicates a standard profile/section
                # (DIN, EN, ISO standards should be classified as "anders" - purchased items)
                if part_name:
                    name_upper = part_name.upper()
                    is_standard = any(std in name_upper for std in ['DIN ', 'DIN-', 'EN ', 'EN-', 'ISO ', 'ISO-'])
                    if is_standard:
                        part_class = "anders"

                # If no explicit rule applies, classify by geometry.
                if part_class is None:
                    part_class, class_trace = classify_solid(solid, return_trace=True)
            
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
                solid_index=rep_idx,
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
