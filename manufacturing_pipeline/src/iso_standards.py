"""
ISO Standards Module for Dutch/European Manufacturing

Implements:
- ISO 2768: General tolerances for linear and angular dimensions
- ISO 286: Limits and fits (hole/shaft tolerances)
- ISO 1302: Surface roughness indication
- ISO 68-1 / ISO 261: Metric screw threads
- ISO 13715: Edge conditions (chamfers/fillets)
- Material density tables (EN standards)
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum


# =============================================================================
# ISO 2768 - General Tolerances
# =============================================================================

class ISO2768Class(Enum):
    """ISO 2768-1 tolerance classes for linear dimensions"""
    FINE = "f"
    MEDIUM = "m"
    COARSE = "c"
    VERY_COARSE = "v"


class ISO2768GeoClass(Enum):
    """ISO 2768-2 tolerance classes for geometrical tolerances"""
    H = "H"  # Most precise
    K = "K"  # Standard
    L = "L"  # Least precise


# ISO 2768-1 Linear tolerance table (mm)
# Format: (min_size, max_size): {class: tolerance}
ISO2768_LINEAR_TOLERANCES = {
    (0.5, 3): {"f": 0.05, "m": 0.1, "c": 0.2, "v": None},
    (3, 6): {"f": 0.05, "m": 0.1, "c": 0.3, "v": 0.5},
    (6, 30): {"f": 0.1, "m": 0.2, "c": 0.5, "v": 1.0},
    (30, 120): {"f": 0.15, "m": 0.3, "c": 0.8, "v": 1.5},
    (120, 400): {"f": 0.2, "m": 0.5, "c": 1.2, "v": 2.5},
    (400, 1000): {"f": 0.3, "m": 0.8, "c": 2.0, "v": 4.0},
    (1000, 2000): {"f": 0.5, "m": 1.2, "c": 3.0, "v": 6.0},
    (2000, 4000): {"f": None, "m": 2.0, "c": 4.0, "v": 8.0},
}

# ISO 2768-1 Angular tolerance table
# Format: (min_length_mm, max_length_mm): {class: (degrees, minutes)}
ISO2768_ANGULAR_TOLERANCES = {
    (0, 10): {"f": (1, 0), "m": (1, 0), "c": (1, 30), "v": (3, 0)},
    (10, 50): {"f": (0, 30), "m": (0, 30), "c": (1, 0), "v": (2, 0)},
    (50, 120): {"f": (0, 20), "m": (0, 20), "c": (0, 30), "v": (1, 0)},
    (120, 400): {"f": (0, 10), "m": (0, 10), "c": (0, 15), "v": (0, 30)},
    (400, float('inf')): {"f": (0, 5), "m": (0, 5), "c": (0, 10), "v": (0, 20)},
}

# ISO 2768-2 Geometrical tolerances (straightness, flatness) in mm
ISO2768_FLATNESS_TOLERANCES = {
    (0, 10): {"H": 0.02, "K": 0.05, "L": 0.1},
    (10, 30): {"H": 0.05, "K": 0.1, "L": 0.2},
    (30, 100): {"H": 0.1, "K": 0.2, "L": 0.4},
    (100, 300): {"H": 0.2, "K": 0.4, "L": 0.8},
    (300, 1000): {"H": 0.3, "K": 0.6, "L": 1.2},
    (1000, 3000): {"H": 0.4, "K": 0.8, "L": 1.6},
}

# ISO 2768-2 Cylindricity/Circularity tolerances
ISO2768_CYLINDRICITY_TOLERANCES = {
    (0, 30): {"H": 0.02, "K": 0.05, "L": 0.1},
    (30, 100): {"H": 0.05, "K": 0.1, "L": 0.2},
    (100, 300): {"H": 0.1, "K": 0.2, "L": 0.4},
    (300, 1000): {"H": 0.15, "K": 0.3, "L": 0.6},
}


def get_iso2768_linear_tolerance(dimension: float, tol_class: str = "m") -> Optional[float]:
    """Get ISO 2768-1 linear tolerance for a given dimension and class."""
    for (min_size, max_size), tolerances in ISO2768_LINEAR_TOLERANCES.items():
        if min_size <= dimension < max_size:
            return tolerances.get(tol_class)
    return None


def get_iso2768_angular_tolerance(shorter_leg: float, tol_class: str = "m") -> Tuple[int, int]:
    """Get ISO 2768-1 angular tolerance (degrees, minutes) for shorter leg length."""
    for (min_len, max_len), tolerances in ISO2768_ANGULAR_TOLERANCES.items():
        if min_len <= shorter_leg < max_len:
            return tolerances.get(tol_class, (1, 0))
    return (0, 5)


def get_iso2768_flatness_tolerance(length: float, geo_class: str = "K") -> Optional[float]:
    """Get ISO 2768-2 flatness/straightness tolerance."""
    for (min_len, max_len), tolerances in ISO2768_FLATNESS_TOLERANCES.items():
        if min_len <= length < max_len:
            return tolerances.get(geo_class)
    return None


def recommend_iso2768_class(part_type: str, complexity: str = "medium") -> Tuple[str, str]:
    """
    Recommend ISO 2768 class based on part type and complexity.
    Returns (linear_class, geometric_class)
    """
    recommendations = {
        ("precision", "high"): ("f", "H"),
        ("precision", "medium"): ("f", "K"),
        ("general", "high"): ("m", "H"),
        ("general", "medium"): ("m", "K"),
        ("general", "low"): ("m", "L"),
        ("rough", "medium"): ("c", "K"),
        ("rough", "low"): ("c", "L"),
        ("structural", "low"): ("v", "L"),
    }

    # Map part types to precision levels
    part_precision = {
        "Fastener (Bolt/Screw/Pin)": "precision",
        "Washer/Spacer": "general",
        "Shaft/Bar": "precision",
        "Block/Housing": "general",
        "Plate/Sheet": "general",
        "Sheet Metal": "general",
        "Sheet Metal (Bent)": "general",
        "Small Component": "precision",
        "Complex Part": "general",
    }

    precision = part_precision.get(part_type, "general")
    return recommendations.get((precision, complexity), ("m", "K"))


# =============================================================================
# ISO 286 - Limits and Fits
# =============================================================================

@dataclass
class FitRecommendation:
    """ISO 286 fit recommendation"""
    hole_tolerance: str  # e.g., "H7"
    shaft_tolerance: str  # e.g., "h6"
    fit_type: str  # "clearance", "transition", "interference"
    description: str
    application: str


# Common ISO 286 fits for hole-basis system
ISO286_COMMON_FITS = {
    "loose_running": FitRecommendation("H11", "c11", "clearance",
        "Loose running fit", "Free movement, large clearance"),
    "free_running": FitRecommendation("H9", "d9", "clearance",
        "Free running fit", "Light shafts, pulleys"),
    "easy_running": FitRecommendation("H8", "f7", "clearance",
        "Easy running fit", "Gearbox shafts, sliding fits"),
    "normal_running": FitRecommendation("H7", "g6", "clearance",
        "Normal running fit", "Precision bearings, spigots"),
    "sliding": FitRecommendation("H7", "h6", "clearance",
        "Sliding fit", "Location fits, spigots, snug fit"),
    "location_clearance": FitRecommendation("H7", "j6", "transition",
        "Location clearance fit", "Accurate location"),
    "location_transition": FitRecommendation("H7", "k6", "transition",
        "Location transition fit", "Keyed assemblies"),
    "location_interference": FitRecommendation("H7", "n6", "transition",
        "Location interference fit", "Press fit location"),
    "light_press": FitRecommendation("H7", "p6", "interference",
        "Light press fit", "Semi-permanent assembly"),
    "medium_press": FitRecommendation("H7", "s6", "interference",
        "Medium press fit", "Permanent assembly, steel parts"),
    "heavy_press": FitRecommendation("H7", "u6", "interference",
        "Heavy press fit", "Permanent shrink fits"),
}

# ISO 286 tolerance values (IT grades) in micrometers
# Simplified table for common sizes
ISO286_IT_GRADES = {
    # (min_diameter, max_diameter): {IT_grade: tolerance_um}
    (1, 3): {"IT5": 4, "IT6": 6, "IT7": 10, "IT8": 14, "IT9": 25, "IT10": 40, "IT11": 60},
    (3, 6): {"IT5": 5, "IT6": 8, "IT7": 12, "IT8": 18, "IT9": 30, "IT10": 48, "IT11": 75},
    (6, 10): {"IT5": 6, "IT6": 9, "IT7": 15, "IT8": 22, "IT9": 36, "IT10": 58, "IT11": 90},
    (10, 18): {"IT5": 8, "IT6": 11, "IT7": 18, "IT8": 27, "IT9": 43, "IT10": 70, "IT11": 110},
    (18, 30): {"IT5": 9, "IT6": 13, "IT7": 21, "IT8": 33, "IT9": 52, "IT10": 84, "IT11": 130},
    (30, 50): {"IT5": 11, "IT6": 16, "IT7": 25, "IT8": 39, "IT9": 62, "IT10": 100, "IT11": 160},
    (50, 80): {"IT5": 13, "IT6": 19, "IT7": 30, "IT8": 46, "IT9": 74, "IT10": 120, "IT11": 190},
    (80, 120): {"IT5": 15, "IT6": 22, "IT7": 35, "IT8": 54, "IT9": 87, "IT10": 140, "IT11": 220},
    (120, 180): {"IT5": 18, "IT6": 25, "IT7": 40, "IT8": 63, "IT9": 100, "IT10": 160, "IT11": 250},
}


def get_it_tolerance(diameter: float, it_grade: str) -> Optional[float]:
    """Get IT tolerance in mm for a given diameter and IT grade."""
    for (min_d, max_d), grades in ISO286_IT_GRADES.items():
        if min_d <= diameter < max_d:
            tolerance_um = grades.get(it_grade)
            if tolerance_um:
                return tolerance_um / 1000.0  # Convert to mm
    return None


def recommend_fit(application: str, diameter: float) -> FitRecommendation:
    """Recommend an ISO 286 fit based on application."""
    app_lower = application.lower()

    if "bearing" in app_lower or "precision" in app_lower:
        return ISO286_COMMON_FITS["normal_running"]
    elif "sliding" in app_lower or "location" in app_lower:
        return ISO286_COMMON_FITS["sliding"]
    elif "press" in app_lower or "permanent" in app_lower:
        return ISO286_COMMON_FITS["light_press"]
    elif "loose" in app_lower or "free" in app_lower:
        return ISO286_COMMON_FITS["free_running"]
    else:
        # Default to sliding fit for general holes
        return ISO286_COMMON_FITS["sliding"]


def analyze_hole_fit(diameter: float) -> Dict:
    """Analyze a hole and provide fit recommendations."""
    # Determine recommended fit based on diameter
    if diameter < 6:
        primary_fit = ISO286_COMMON_FITS["sliding"]
        alt_fit = ISO286_COMMON_FITS["location_clearance"]
    elif diameter < 20:
        primary_fit = ISO286_COMMON_FITS["sliding"]
        alt_fit = ISO286_COMMON_FITS["normal_running"]
    else:
        primary_fit = ISO286_COMMON_FITS["easy_running"]
        alt_fit = ISO286_COMMON_FITS["sliding"]

    h7_tolerance = get_it_tolerance(diameter, "IT7")
    h6_tolerance = get_it_tolerance(diameter, "IT6")

    return {
        "diameter": diameter,
        "primary_recommendation": {
            "fit": f"{primary_fit.hole_tolerance}/{primary_fit.shaft_tolerance}",
            "type": primary_fit.fit_type,
            "description": primary_fit.description,
            "application": primary_fit.application,
        },
        "alternative_recommendation": {
            "fit": f"{alt_fit.hole_tolerance}/{alt_fit.shaft_tolerance}",
            "type": alt_fit.fit_type,
            "description": alt_fit.description,
        },
        "tolerances": {
            "H7": f"±{h7_tolerance:.4f} mm" if h7_tolerance else "N/A",
            "h6": f"±{h6_tolerance:.4f} mm" if h6_tolerance else "N/A",
        }
    }


# =============================================================================
# ISO 1302 - Surface Roughness
# =============================================================================

@dataclass
class SurfaceFinish:
    """Surface finish specification per ISO 1302"""
    ra: float  # Arithmetic mean roughness (μm)
    rz: Optional[float] = None  # Mean roughness depth (μm)
    process: str = ""  # Manufacturing process
    symbol: str = ""  # ISO 1302 symbol description


# Typical Ra values for manufacturing processes (in μm)
SURFACE_FINISH_BY_PROCESS = {
    "rough_turning": SurfaceFinish(6.3, 25, "Rough turning", "▽"),
    "finish_turning": SurfaceFinish(1.6, 6.3, "Finish turning", "▽▽"),
    "rough_milling": SurfaceFinish(3.2, 12.5, "Rough milling", "▽"),
    "finish_milling": SurfaceFinish(1.6, 6.3, "Finish milling", "▽▽"),
    "grinding": SurfaceFinish(0.8, 3.2, "Grinding", "▽▽▽"),
    "fine_grinding": SurfaceFinish(0.4, 1.6, "Fine grinding", "▽▽▽▽"),
    "lapping": SurfaceFinish(0.1, 0.4, "Lapping", "▽▽▽▽"),
    "polishing": SurfaceFinish(0.05, 0.2, "Polishing", "▽▽▽▽"),
    "drilling": SurfaceFinish(3.2, 12.5, "Drilling", "▽"),
    "reaming": SurfaceFinish(1.6, 6.3, "Reaming", "▽▽"),
    "boring": SurfaceFinish(1.6, 6.3, "Boring", "▽▽"),
    "laser_cutting": SurfaceFinish(6.3, 25, "Laser cutting", "▽"),
    "plasma_cutting": SurfaceFinish(12.5, 50, "Plasma cutting", "~"),
    "sheet_bending": SurfaceFinish(1.6, 6.3, "Sheet bending", "▽▽"),
    "casting": SurfaceFinish(12.5, 50, "Casting (as-cast)", "~"),
    "forging": SurfaceFinish(6.3, 25, "Forging", "~"),
    "3d_printing_fdm": SurfaceFinish(12.5, 50, "3D printing (FDM)", "~"),
    "3d_printing_sla": SurfaceFinish(1.6, 6.3, "3D printing (SLA)", "▽▽"),
}

# Standard Ra values per ISO 1302 (preferred series)
ISO1302_PREFERRED_RA = [0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.3, 12.5, 25, 50]


def estimate_surface_finish_from_face_type(face_type: str, is_internal: bool = False) -> SurfaceFinish:
    """Estimate surface finish based on face geometry type."""
    if face_type == "Plane":
        return SURFACE_FINISH_BY_PROCESS["finish_milling"]
    elif face_type == "Cylinder":
        if is_internal:
            return SURFACE_FINISH_BY_PROCESS["boring"]
        else:
            return SURFACE_FINISH_BY_PROCESS["finish_turning"]
    elif face_type == "Cone":
        return SURFACE_FINISH_BY_PROCESS["finish_turning"]
    elif face_type == "Sphere":
        return SURFACE_FINISH_BY_PROCESS["finish_milling"]
    elif face_type == "Torus":
        return SURFACE_FINISH_BY_PROCESS["finish_milling"]
    elif face_type in ["Bezier", "BSpline"]:
        return SURFACE_FINISH_BY_PROCESS["finish_milling"]
    else:
        return SURFACE_FINISH_BY_PROCESS["rough_milling"]


def get_nearest_standard_ra(ra_value: float) -> float:
    """Get the nearest standard ISO 1302 Ra value."""
    return min(ISO1302_PREFERRED_RA, key=lambda x: abs(x - ra_value))


def analyze_surface_requirements(face_analysis: Dict) -> Dict:
    """Analyze surface finish requirements based on face types."""
    total_faces = sum(face_analysis.values())
    if total_faces == 0:
        return {}

    surface_requirements = []

    for face_type, count in face_analysis.items():
        if count > 0:
            finish = estimate_surface_finish_from_face_type(face_type)
            surface_requirements.append({
                "face_type": face_type,
                "count": count,
                "percentage": round(count / total_faces * 100, 1),
                "recommended_ra": finish.ra,
                "recommended_rz": finish.rz,
                "typical_process": finish.process,
            })

    # Sort by count descending
    surface_requirements.sort(key=lambda x: x["count"], reverse=True)

    # Calculate overall complexity and recommended general finish
    bspline_ratio = face_analysis.get("BSpline", 0) / total_faces if total_faces > 0 else 0

    if bspline_ratio > 0.3:
        general_recommendation = "5-axis CNC milling recommended"
        general_ra = 1.6
    elif face_analysis.get("Cylinder", 0) > face_analysis.get("Plane", 0):
        general_recommendation = "CNC turning with milling operations"
        general_ra = 1.6
    else:
        general_recommendation = "3-axis CNC milling"
        general_ra = 3.2

    return {
        "by_face_type": surface_requirements,
        "general_recommendation": general_recommendation,
        "default_ra": general_ra,
        "default_rz": general_ra * 4,  # Approximate Rz ≈ 4-7 × Ra
    }


# =============================================================================
# ISO 68-1 / ISO 261 - Metric Screw Threads
# =============================================================================

@dataclass
class MetricThread:
    """ISO metric thread specification"""
    designation: str  # e.g., "M8" or "M8x1"
    major_diameter: float  # mm
    pitch: float  # mm
    is_coarse: bool
    minor_diameter: float  # mm (approximate)
    pitch_diameter: float  # mm (approximate)


# ISO 261 Metric coarse thread series
ISO_METRIC_COARSE_THREADS = {
    # major_diameter: pitch
    1.0: 0.25, 1.2: 0.25, 1.4: 0.3, 1.6: 0.35, 1.8: 0.35,
    2.0: 0.4, 2.2: 0.45, 2.5: 0.45, 3.0: 0.5, 3.5: 0.6,
    4.0: 0.7, 4.5: 0.75, 5.0: 0.8, 6.0: 1.0, 7.0: 1.0,
    8.0: 1.25, 10.0: 1.5, 12.0: 1.75, 14.0: 2.0, 16.0: 2.0,
    18.0: 2.5, 20.0: 2.5, 22.0: 2.5, 24.0: 3.0, 27.0: 3.0,
    30.0: 3.5, 33.0: 3.5, 36.0: 4.0, 39.0: 4.0, 42.0: 4.5,
    45.0: 4.5, 48.0: 5.0, 52.0: 5.0, 56.0: 5.5, 60.0: 5.5,
    64.0: 6.0, 68.0: 6.0,
}

# ISO 261 Metric fine thread series (common sizes)
ISO_METRIC_FINE_THREADS = {
    # major_diameter: [available fine pitches]
    3.0: [0.35],
    4.0: [0.5],
    5.0: [0.5],
    6.0: [0.75, 0.5],
    8.0: [1.0, 0.75, 0.5],
    10.0: [1.25, 1.0, 0.75, 0.5],
    12.0: [1.5, 1.25, 1.0, 0.75, 0.5],
    14.0: [1.5, 1.25, 1.0],
    16.0: [1.5, 1.0],
    18.0: [2.0, 1.5, 1.0],
    20.0: [2.0, 1.5, 1.0],
    22.0: [2.0, 1.5, 1.0],
    24.0: [2.0, 1.5, 1.0],
    27.0: [2.0, 1.5, 1.0],
    30.0: [3.0, 2.0, 1.5, 1.0],
    33.0: [3.0, 2.0, 1.5],
    36.0: [3.0, 2.0, 1.5],
    39.0: [3.0, 2.0, 1.5],
    42.0: [4.0, 3.0, 2.0, 1.5],
    48.0: [4.0, 3.0, 2.0, 1.5],
}


def calculate_thread_dimensions(major_diameter: float, pitch: float) -> Dict:
    """Calculate thread dimensions per ISO 68-1."""
    # Thread height H = 0.866025 × pitch
    H = 0.866025 * pitch

    # Minor diameter (root) d3 = D - 1.0825 × pitch (internal) or d1 = D - 1.2268 × pitch (external)
    minor_diameter_internal = major_diameter - 1.0825 * pitch
    minor_diameter_external = major_diameter - 1.2268 * pitch

    # Pitch diameter d2 = D - 0.6495 × pitch
    pitch_diameter = major_diameter - 0.6495 * pitch

    return {
        "major_diameter": major_diameter,
        "pitch": pitch,
        "pitch_diameter": round(pitch_diameter, 3),
        "minor_diameter_internal": round(minor_diameter_internal, 3),
        "minor_diameter_external": round(minor_diameter_external, 3),
        "thread_height": round(H, 3),
        "thread_depth": round(0.54125 * pitch, 3),  # Actual thread depth
    }


def identify_thread_from_diameter(diameter: float, tolerance: float = 0.15) -> List[MetricThread]:
    """
    Identify possible ISO metric threads from a measured diameter.
    Returns list of possible thread matches.
    """
    matches = []

    # Check against coarse threads (major diameter)
    for major_d, pitch in ISO_METRIC_COARSE_THREADS.items():
        if abs(diameter - major_d) <= tolerance:
            dims = calculate_thread_dimensions(major_d, pitch)
            matches.append(MetricThread(
                designation=f"M{int(major_d) if major_d == int(major_d) else major_d}",
                major_diameter=major_d,
                pitch=pitch,
                is_coarse=True,
                minor_diameter=dims["minor_diameter_internal"],
                pitch_diameter=dims["pitch_diameter"],
            ))

    # Check against minor diameters (for internal threads / tapped holes)
    for major_d, pitch in ISO_METRIC_COARSE_THREADS.items():
        dims = calculate_thread_dimensions(major_d, pitch)
        if abs(diameter - dims["minor_diameter_internal"]) <= tolerance:
            matches.append(MetricThread(
                designation=f"M{int(major_d) if major_d == int(major_d) else major_d} (tapped)",
                major_diameter=major_d,
                pitch=pitch,
                is_coarse=True,
                minor_diameter=dims["minor_diameter_internal"],
                pitch_diameter=dims["pitch_diameter"],
            ))

    # Check fine threads
    for major_d, pitches in ISO_METRIC_FINE_THREADS.items():
        for pitch in pitches:
            if abs(diameter - major_d) <= tolerance:
                dims = calculate_thread_dimensions(major_d, pitch)
                matches.append(MetricThread(
                    designation=f"M{int(major_d) if major_d == int(major_d) else major_d}x{pitch}",
                    major_diameter=major_d,
                    pitch=pitch,
                    is_coarse=False,
                    minor_diameter=dims["minor_diameter_internal"],
                    pitch_diameter=dims["pitch_diameter"],
                ))

    return matches


def get_tap_drill_size(thread_designation: str) -> Optional[float]:
    """Get recommended tap drill size for a thread."""
    # Parse designation - remove annotations like "(tapped)"
    if thread_designation.startswith("M"):
        # Clean the designation - remove parenthetical notes
        clean_designation = thread_designation.split("(")[0].strip()
        parts = clean_designation[1:].replace("x", " ").split()

        try:
            major_d = float(parts[0])
        except (ValueError, IndexError):
            return None

        if len(parts) > 1:
            try:
                pitch = float(parts[1])
            except ValueError:
                # If pitch parsing fails, try to look up coarse thread
                if major_d in ISO_METRIC_COARSE_THREADS:
                    pitch = ISO_METRIC_COARSE_THREADS[major_d]
                else:
                    return None
        elif major_d in ISO_METRIC_COARSE_THREADS:
            pitch = ISO_METRIC_COARSE_THREADS[major_d]
        else:
            return None

        # Tap drill = Major diameter - pitch (approximate rule)
        # More precise: D - 1.0825 × P for 75% thread
        return round(major_d - pitch, 2)

    return None


# =============================================================================
# Material Density Tables (EN Standards)
# =============================================================================

@dataclass
class Material:
    """Material properties"""
    name: str
    density: float  # kg/m³
    standard: str  # EN standard reference
    typical_use: str
    yield_strength: Optional[float] = None  # MPa
    tensile_strength: Optional[float] = None  # MPa


# Common materials with densities (Dutch/European standards)
MATERIAL_DATABASE = {
    # Steels (EN 10027)
    "steel_s235": Material("S235JR", 7850, "EN 10025-2", "Structural steel", 235, 360),
    "steel_s275": Material("S275JR", 7850, "EN 10025-2", "Structural steel", 275, 410),
    "steel_s355": Material("S355JR", 7850, "EN 10025-2", "Structural steel", 355, 470),
    "steel_c45": Material("C45", 7850, "EN 10083-2", "Machine parts, shafts", 340, 620),
    "steel_42crmo4": Material("42CrMo4", 7850, "EN 10083-3", "High-strength parts", 750, 1000),
    "steel_304": Material("X5CrNi18-10 (304)", 7900, "EN 10088-1", "Stainless, corrosion resistant", 210, 520),
    "steel_316": Material("X2CrNiMo17-12-2 (316)", 8000, "EN 10088-1", "Marine, chemical resistant", 220, 530),

    # Aluminum alloys (EN 573 / EN 485)
    "alu_1050": Material("EN AW-1050A", 2700, "EN 573-3", "Sheet metal, general purpose", 75, 105),
    "alu_5083": Material("EN AW-5083", 2660, "EN 573-3", "Marine, pressure vessels", 240, 305),
    "alu_6061": Material("EN AW-6061", 2700, "EN 573-3", "Structural, machining", 240, 290),
    "alu_6082": Material("EN AW-6082", 2700, "EN 573-3", "Structural, high strength", 250, 300),
    "alu_7075": Material("EN AW-7075", 2810, "EN 573-3", "Aerospace, high strength", 480, 540),

    # Copper alloys
    "copper": Material("Cu-ETP", 8940, "EN 1652", "Electrical, thermal", 200, 250),
    "brass_cuzn37": Material("CuZn37", 8440, "EN 1652", "Machining, fittings", 290, 410),
    "bronze_cusn8": Material("CuSn8", 8800, "EN 1652", "Bearings, gears", 260, 450),

    # Plastics (for reference)
    "pom": Material("POM (Delrin)", 1410, "ISO 9988-1", "Gears, bearings", 65, 70),
    "pa6": Material("PA6 (Nylon)", 1130, "ISO 1874-1", "Gears, bushings", 70, 85),
    "peek": Material("PEEK", 1300, "ISO 10350-1", "High-temp applications", 95, 100),
    "abs": Material("ABS", 1050, "ISO 2580-1", "General purpose", 40, 50),

    # Cast iron
    "cast_iron_grey": Material("EN-GJL-250", 7200, "EN 1561", "Housings, bases", 250, None),
    "cast_iron_ductile": Material("EN-GJS-400-15", 7100, "EN 1563", "Structural castings", 250, 400),
}


def get_material(material_key: str) -> Optional[Material]:
    """Get material properties by key."""
    return MATERIAL_DATABASE.get(material_key)


def calculate_mass(volume_mm3: float, material_key: str) -> Optional[Dict]:
    """Calculate mass from volume and material."""
    material = MATERIAL_DATABASE.get(material_key)
    if not material:
        return None

    volume_m3 = volume_mm3 / 1e9
    mass_kg = volume_m3 * material.density

    return {
        "material": material.name,
        "standard": material.standard,
        "density_kg_m3": material.density,
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1000,
        "mass_kg": round(mass_kg, 4),
        "mass_g": round(mass_kg * 1000, 2),
    }


def estimate_material_from_density(measured_density: float, tolerance: float = 0.1) -> List[Material]:
    """Estimate material from measured/calculated density."""
    matches = []
    for key, material in MATERIAL_DATABASE.items():
        if abs(material.density - measured_density) / material.density <= tolerance:
            matches.append(material)
    return matches


def get_all_materials_by_category() -> Dict[str, List[Material]]:
    """Get all materials organized by category."""
    categories = {
        "Steel (Carbon)": [],
        "Steel (Stainless)": [],
        "Aluminum": [],
        "Copper & Alloys": [],
        "Plastics": [],
        "Cast Iron": [],
    }

    for key, material in MATERIAL_DATABASE.items():
        if key.startswith("steel_") and "304" not in key and "316" not in key:
            categories["Steel (Carbon)"].append(material)
        elif "304" in key or "316" in key:
            categories["Steel (Stainless)"].append(material)
        elif key.startswith("alu_"):
            categories["Aluminum"].append(material)
        elif key.startswith("copper") or key.startswith("brass") or key.startswith("bronze"):
            categories["Copper & Alloys"].append(material)
        elif key in ["pom", "pa6", "peek", "abs"]:
            categories["Plastics"].append(material)
        elif key.startswith("cast_iron"):
            categories["Cast Iron"].append(material)

    return categories


# =============================================================================
# ISO 13715 - Edge Conditions (Chamfers/Fillets)
# =============================================================================

@dataclass
class EdgeCondition:
    """Edge condition per ISO 13715"""
    type: str  # "chamfer", "fillet", "sharp", "broken"
    size: float  # mm (chamfer leg or fillet radius)
    angle: Optional[float] = None  # degrees (for chamfers)
    iso_symbol: str = ""


# Standard chamfer sizes (45°)
STANDARD_CHAMFER_SIZES = [0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]

# Standard fillet radii
STANDARD_FILLET_RADII = [0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]


def classify_edge_condition(size: float, is_internal: bool = False) -> EdgeCondition:
    """Classify edge condition based on size."""
    if size < 0.1:
        return EdgeCondition("sharp", size, iso_symbol="—")
    elif size < 0.5:
        return EdgeCondition("broken", size, iso_symbol="+0.3/-0")
    elif is_internal:
        return EdgeCondition("fillet", size, iso_symbol=f"R{size}")
    else:
        return EdgeCondition("chamfer", size, 45.0, iso_symbol=f"{size}×45°")


def get_nearest_standard_chamfer(size: float) -> float:
    """Get nearest standard chamfer size."""
    return min(STANDARD_CHAMFER_SIZES, key=lambda x: abs(x - size))


def get_nearest_standard_fillet(radius: float) -> float:
    """Get nearest standard fillet radius."""
    return min(STANDARD_FILLET_RADII, key=lambda x: abs(x - radius))


def analyze_edge_requirements(chamfer_count: int, fillet_count: int,
                              avg_chamfer_size: float = 1.0,
                              avg_fillet_radius: float = 2.0) -> Dict:
    """Analyze edge treatment requirements."""
    return {
        "chamfers": {
            "count": chamfer_count,
            "recommended_size": get_nearest_standard_chamfer(avg_chamfer_size),
            "iso_callout": f"{get_nearest_standard_chamfer(avg_chamfer_size)}×45°",
        },
        "fillets": {
            "count": fillet_count,
            "recommended_radius": get_nearest_standard_fillet(avg_fillet_radius),
            "iso_callout": f"R{get_nearest_standard_fillet(avg_fillet_radius)}",
        },
        "general_note": "All edges to be deburred and broken 0.2-0.5mm unless otherwise specified (ISO 13715)",
    }
