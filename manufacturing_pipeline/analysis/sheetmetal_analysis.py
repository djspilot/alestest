"""
Sheet Metal / Plaatwerk Analyse Module

Analyzes sheet metal parts for:
- Bend detection (zettingen)
- Bend angles, radii, bend lines
- K-factor calculation
- Flat pattern / ontwikkeling
- Kantbank tooling recommendations
- DIN 6935 bend allowance

Based on Dutch/European sheet metal manufacturing standards.
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

# Try to import CAD libraries
try:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Vec, gp_Dir, gp_Pnt
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


# =============================================================================
# STANDAARD PLAATDIKTES (ISO / DIN / NEN)
# =============================================================================

# Standaard plaatdiktes in mm (EN 10051 / EN 10131)
STANDARD_THICKNESSES = [
    0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
    1.2, 1.5, 1.8, 2.0, 2.5, 3.0,
    4.0, 5.0, 6.0, 8.0, 10.0, 12.0,
    15.0, 20.0, 25.0, 30.0
]

# Standaard buighoeken
STANDARD_BEND_ANGLES = [30, 45, 60, 90, 120, 135, 150, 180]


# =============================================================================
# KANTBANK GEREEDSCHAP DATABASE
# =============================================================================

@dataclass
class BendTool:
    """Kantbank gereedschap (matrijs + stempel)"""
    name: str
    v_opening: float      # V-opening matrijs (mm)
    punch_radius: float   # Stempel radius (mm)
    max_thickness: float  # Max plaatdikte (mm)
    min_flange: float     # Min flenslengte (mm)
    tonnage_per_m: float  # Tonnage per meter buiglengte


# Standaard V-matrijzen (DIN / Trumpf / Amada compatible)
STANDARD_V_DIES = {
    # V-opening: (name, punch_radius, max_thickness, min_flens, tonnage/m)
    4: BendTool("V4", 4, 0.5, 0.5, 4, 8),
    6: BendTool("V6", 6, 0.8, 0.8, 5, 12),
    8: BendTool("V8", 8, 1.0, 1.0, 6, 18),
    10: BendTool("V10", 10, 1.2, 1.5, 8, 25),
    12: BendTool("V12", 12, 1.5, 2.0, 10, 35),
    16: BendTool("V16", 16, 2.0, 2.5, 12, 50),
    20: BendTool("V20", 20, 2.5, 3.0, 15, 70),
    24: BendTool("V24", 24, 3.0, 4.0, 18, 90),
    32: BendTool("V32", 32, 4.0, 5.0, 24, 130),
    40: BendTool("V40", 40, 5.0, 6.0, 30, 180),
    50: BendTool("V50", 50, 6.0, 8.0, 38, 250),
    63: BendTool("V63", 63, 8.0, 10.0, 48, 350),
    80: BendTool("V80", 80, 10.0, 12.0, 60, 500),
}


# =============================================================================
# K-FACTOR EN BEND ALLOWANCE (DIN 6935)
# =============================================================================

# K-factor per materiaal en buigmethode
# K = neutrale lijn positie / plaatdikte
K_FACTORS = {
    # Materiaal: {buigmethode: k-factor}
    "steel": {
        "air_bend": 0.44,      # Luchtbuigen (meest voorkomend)
        "bottom_bend": 0.33,   # Bodembuigen
        "coining": 0.25,       # Munten/stansen
    },
    "stainless": {
        "air_bend": 0.45,
        "bottom_bend": 0.34,
        "coining": 0.26,
    },
    "aluminum": {
        "air_bend": 0.40,
        "bottom_bend": 0.30,
        "coining": 0.22,
    },
    "copper": {
        "air_bend": 0.38,
        "bottom_bend": 0.28,
        "coining": 0.20,
    },
}


def calculate_bend_allowance(
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44
) -> float:
    """
    Bereken de buigtoeslag (bend allowance) volgens DIN 6935.

    BA = π × (R + K × T) × A / 180

    Args:
        thickness: Plaatdikte (mm)
        bend_angle: Buighoek (graden, 90° = haakse hoek)
        inner_radius: Binnenradius buiging (mm)
        k_factor: K-factor (default 0.44 voor luchtbuigen staal)

    Returns:
        Bend allowance in mm
    """
    angle_rad = math.radians(bend_angle)
    ba = math.pi * (inner_radius + k_factor * thickness) * bend_angle / 180
    return ba


def calculate_bend_deduction(
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44
) -> float:
    """
    Bereken de buigaftrek (bend deduction).

    BD = 2 × (R + T) × tan(A/2) - BA

    Dit is wat je van de totale lengte aftrekt om de flat length te krijgen.
    """
    ba = calculate_bend_allowance(thickness, bend_angle, inner_radius, k_factor)
    setback = (inner_radius + thickness) * math.tan(math.radians(bend_angle / 2))
    bd = 2 * setback - ba
    return bd


def calculate_flat_length(
    flange1: float,
    flange2: float,
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44
) -> float:
    """
    Bereken de uitslag (flat pattern length) voor een enkele buiging.

    Flat = Flens1 + Flens2 - Bend Deduction
    """
    bd = calculate_bend_deduction(thickness, bend_angle, inner_radius, k_factor)
    return flange1 + flange2 - bd


def get_minimum_bend_radius(thickness: float, material: str = "steel") -> float:
    """
    Minimale binnenradius voor buigen zonder scheuren.

    Vuistregel: Ri_min = 0.5 × t (zacht staal) tot 2 × t (hard materiaal)
    """
    factors = {
        "steel": 0.5,
        "stainless": 0.8,
        "aluminum_soft": 0.3,
        "aluminum_hard": 1.0,
        "copper": 0.3,
        "brass": 0.5,
    }
    factor = factors.get(material, 0.5)
    return thickness * factor


def recommend_v_opening(thickness: float) -> Tuple[int, BendTool]:
    """
    Aanbevolen V-opening voor gegeven plaatdikte.

    Vuistregel: V = 6 × t (dunne plaat) tot 8 × t (dikke plaat)
    """
    target_v = thickness * 8  # Standaard vuistregel

    # Vind dichtstbijzijnde standaard V-matrijs
    best_v = None
    for v_size, tool in STANDARD_V_DIES.items():
        if tool.max_thickness >= thickness:
            if best_v is None or abs(v_size - target_v) < abs(best_v - target_v):
                best_v = v_size

    if best_v is None:
        best_v = max(STANDARD_V_DIES.keys())

    return best_v, STANDARD_V_DIES[best_v]


def calculate_bend_force(
    thickness: float,
    bend_length: float,
    v_opening: float,
    tensile_strength: float = 400  # N/mm² (staal)
) -> float:
    """
    Bereken benodigde buigkracht in kN.

    F = (1.33 × Rm × t² × L) / V

    Args:
        thickness: Plaatdikte (mm)
        bend_length: Buiglengte (mm)
        v_opening: V-opening matrijs (mm)
        tensile_strength: Treksterkte materiaal (N/mm²)

    Returns:
        Buigkracht in kN
    """
    force_n = (1.33 * tensile_strength * thickness**2 * bend_length) / v_opening
    return force_n / 1000  # Convert to kN


# =============================================================================
# MATERIAAL EIGENSCHAPPEN VOOR BUIGEN
# =============================================================================

MATERIAL_BEND_PROPERTIES = {
    "steel_s235": {
        "name": "S235JR",
        "tensile_strength": 360,  # N/mm² (Rm)
        "yield_strength": 235,    # N/mm² (Re)
        "k_factor": 0.44,
        "min_radius_factor": 0.5,
        "springback_factor": 1.02,  # 2% terugvering
    },
    "steel_s355": {
        "name": "S355J2",
        "tensile_strength": 510,
        "yield_strength": 355,
        "k_factor": 0.44,
        "min_radius_factor": 0.6,
        "springback_factor": 1.03,
    },
    "steel_304": {
        "name": "RVS 304",
        "tensile_strength": 520,
        "yield_strength": 210,
        "k_factor": 0.45,
        "min_radius_factor": 0.8,
        "springback_factor": 1.04,
    },
    "steel_316": {
        "name": "RVS 316",
        "tensile_strength": 530,
        "yield_strength": 220,
        "k_factor": 0.45,
        "min_radius_factor": 0.8,
        "springback_factor": 1.04,
    },
    "alu_5083": {
        "name": "Aluminium 5083-H111",
        "tensile_strength": 275,
        "yield_strength": 125,
        "k_factor": 0.40,
        "min_radius_factor": 1.0,
        "springback_factor": 1.05,
    },
    "alu_6082": {
        "name": "Aluminium 6082-T6",
        "tensile_strength": 310,
        "yield_strength": 260,
        "k_factor": 0.40,
        "min_radius_factor": 1.5,
        "springback_factor": 1.06,
    },
}


# =============================================================================
# BUIGVOLGORDE OPTIMALISATIE
# =============================================================================

class BendSequenceOptimizer:
    """
    Optimaliseer buigvolgorde voor kantbank.

    Regels:
    1. Binnenste buigingen eerst
    2. Korte flenzen voor lange
    3. Vermijd botsingen met eerder gezette flenzen
    4. Minimaliseer draaiingen
    """

    @staticmethod
    def suggest_sequence(bends: List[Dict]) -> List[Dict]:
        """
        Suggereer optimale buigvolgorde.

        Args:
            bends: Lijst van buigingen met positie, hoek, lengte

        Returns:
            Gesorteerde lijst met volgorde en aanbevelingen
        """
        if not bends:
            return []

        # Sorteer op complexiteit (korte flenzen eerst, dan op positie)
        sorted_bends = sorted(bends, key=lambda b: (
            b.get('min_flange', 0),  # Kortste flens eerst
            -b.get('angle', 90),     # Grotere hoeken eerst
            b.get('position_index', 0)
        ))

        # Voeg volgorde toe
        for i, bend in enumerate(sorted_bends):
            bend['sequence'] = i + 1
            bend['notes'] = []

            # Waarschuwingen
            if bend.get('min_flange', 100) < 8:
                bend['notes'].append("Let op: korte flens, gebruik precisie-aanslag")
            if bend.get('angle', 90) > 120:
                bend['notes'].append("Scherpe hoek: mogelijk 2 buigingen nodig")

        return sorted_bends


# =============================================================================
# GEOMETRY ANALYSE (indien OCP beschikbaar)
# =============================================================================

@dataclass
class DetectedBend:
    """Gedetecteerde buiging in geometrie"""
    bend_id: int
    angle: float              # Buighoek in graden
    inner_radius: float       # Binnenradius (mm)
    bend_length: float        # Lengte buiglijn (mm)
    flange1_length: float     # Lengte flens 1 (mm)
    flange2_length: float     # Lengte flens 2 (mm)
    position: Tuple[float, float, float]  # Positie centrum buiging
    bend_axis: Tuple[float, float, float]  # Richting buigas
    is_standard_angle: bool   # Is het een standaard hoek?
    is_standard_radius: bool  # Is het een standaard radius?


def analyze_sheet_metal_geometry(solid, thickness: float = None) -> Dict[str, Any]:
    """
    Analyseer sheet metal geometrie voor buigingen.

    Detecteert:
    - Cilindrische vlakken (= buigingen)
    - Buighoeken en radii
    - Flenslengtes
    - Buiglijnen

    Args:
        solid: OCP/TopoDS solid
        thickness: Bekende plaatdikte (optioneel, anders gedetecteerd)

    Returns:
        Dict met buiganalyse resultaten
    """
    if not HAS_OCP:
        return {"error": "OCP library not available"}

    result = {
        "is_sheet_metal": False,
        "thickness": thickness,
        "bends": [],
        "bend_count": 0,
        "total_bend_length": 0,
        "flat_pattern": None,
        "tooling_recommendations": [],
    }

    # Verzamel alle vlakken
    faces = []
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()

    cylindrical_faces = []
    planar_faces = []

    for face in faces:
        surf = BRepAdaptor_Surface(face, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()

        if stype == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            radius = cyl.Radius()
            axis = cyl.Axis()
            location = cyl.Location()
            
            # Calculate angle
            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            # Bereken buiglengte uit oppervlakte
            # circumference = 2 * math.pi * radius
            # bend_length = area / circumference if circumference > 0 else 0
            
            # Better bend length calculation: Area / ArcLength
            arc_length = radius * abs(u_max - u_min)
            bend_length = area / arc_length if arc_length > 0 else 0

            cylindrical_faces.append({
                "face": face,
                "radius": radius,
                "axis": (axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()),
                "location": (location.X(), location.Y(), location.Z()),
                "area": area,
                "bend_length": bend_length,
                "angle": angle_deg
            })

        elif stype == GeomAbs_Plane:
            pln = surf.Plane()
            normal = pln.Axis().Direction()
            planar_faces.append({
                "face": face,
                "normal": (normal.X(), normal.Y(), normal.Z()),
                "area": area,
            })

    # Find reference face (largest planar face)
    reference_normal = None
    reference_center = None
    if planar_faces:
        largest_face = max(planar_faces, key=lambda x: x["area"])
        reference_normal = largest_face["normal"]
        
        # Get center of reference face
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(largest_face["face"], props)
        cm = props.CentreOfMass()
        reference_center = (cm.X(), cm.Y(), cm.Z())

    # Detecteer buigingen uit cilindrische vlakken
    # Group concentric faces
    grouped_bends = []
    processed_indices = set()
    
    for i, c1 in enumerate(cylindrical_faces):
        if i in processed_indices: continue
        
        # Filter out full cylinders (holes)
        if c1["angle"] > 270:
            continue
            
        current_group = [c1]
        processed_indices.add(i)
        
        for j, c2 in enumerate(cylindrical_faces):
            if j in processed_indices: continue
            if c2["angle"] > 270: continue
            
            # Check if concentric (same axis, same location)
            # Axis check
            dot = (c1["axis"][0]*c2["axis"][0] + c1["axis"][1]*c2["axis"][1] + c1["axis"][2]*c2["axis"][2])
            if abs(abs(dot) - 1.0) > 0.01: continue
            
            # Location check (project onto axis to ignore axial shift, but for bends they should be aligned?)
            # Actually, for a bend, the axis location is the center of curvature.
            # If they are concentric, they share the same axis line.
            
            # Distance between axis origins
            dx = c2["location"][0] - c1["location"][0]
            dy = c2["location"][1] - c1["location"][1]
            dz = c2["location"][2] - c1["location"][2]
            
            # Cross product with axis to get distance from line
            cx = dy*c1["axis"][2] - dz*c1["axis"][1]
            cy = dz*c1["axis"][0] - dx*c1["axis"][2]
            cz = dx*c1["axis"][1] - dy*c1["axis"][0]
            dist = math.sqrt(cx*cx + cy*cy + cz*cz)
            
            if dist < 0.1:
                current_group.append(c2)
                processed_indices.add(j)
        
        grouped_bends.append(current_group)

    bends = []
    detected_thicknesses = []

    for i, group in enumerate(grouped_bends):
        # Check total angle coverage for this radius
        # If we have multiple faces with same radius, sum their angles
        # If we have inner and outer faces, they have different radii.
        
        # Group by radius first
        by_radius = {}
        for face in group:
            r = round(face["radius"], 2)
            if r not in by_radius:
                by_radius[r] = []
            by_radius[r].append(face)
            
        # Check if any radius forms a full circle (hole)
        is_hole = False
        for r, faces in by_radius.items():
            total_angle = sum(f["angle"] for f in faces)
            if total_angle > 270:
                is_hole = True
                break
        
        if is_hole:
            continue

        # A bend usually has an inner face and an outer face.
        # The inner face has the smaller radius.
        # Sometimes there are multiple split faces for the same bend.
        
        # Sort by radius
        group.sort(key=lambda x: x["radius"])
        
        # Detect thickness from concentric radii
        radii = sorted(list(by_radius.keys()))
        if len(radii) >= 2:
            # Assuming the smallest is inner and largest is outer
            t = radii[-1] - radii[0]
            if 0.1 < t < 25.0:
                detected_thicknesses.append(t)
        
        # Use the inner face for properties
        inner = group[0]
        
        # Calculate total angle for the inner radius
        inner_radius = round(inner["radius"], 2)
        inner_faces = by_radius.get(inner_radius, [inner])
        total_angle = sum(f["angle"] for f in inner_faces)
        
        # Filter: alleen relevante buigingen voor werkvoorbereiding
        # ERP systemen tellen alleen "echte kantbank zettingen":
        # 1. Bend length > 20mm (korter = gat-rand of kleine feature)
        # 2. Angle tussen 45-135° (typische kantbank hoeken)
        # 3. Radius tussen 0.5-15mm (standaard kantbank radii)
        # 4. Niet een gesloten profiel (koker)

        is_valid_bend = True
        bend_length = inner["bend_length"]

        # Filter 1: Minimale buiglengte (< 20mm is waarschijnlijk een gat-rand)
        if bend_length < 20.0:
            is_valid_bend = False

        # Filter 2: Radius check (> 15mm is walsen, niet kanten)
        if inner["radius"] > 15.0:
            is_valid_bend = False

        # Filter 3: Hoek check (< 30° is geen echte zetting)
        if total_angle < 30.0:
            is_valid_bend = False

        if 0.5 <= inner["radius"] <= 50 and is_valid_bend:
            # Determine bend direction relative to reference face
            direction = 0
            if reference_normal and reference_center:
                try:
                    # Use Axis Location relative to Reference Plane
                    # h = (AxisLoc - RefCenter) . RefNormal
                    ax_loc = inner["location"]
                    dx = ax_loc[0] - reference_center[0]
                    dy = ax_loc[1] - reference_center[1]
                    dz = ax_loc[2] - reference_center[2]
                    
                    h = dx * reference_normal[0] + dy * reference_normal[1] + dz * reference_normal[2]
                    
                    # If h > 0, axis is on the side of the normal
                    # If h < 0, axis is on the opposite side
                    # Use a threshold to avoid noise
                    if h > 0.1: direction = 1
                    elif h < -0.1: direction = -1
                    
                    # Fallback to face normal check if axis check is ambiguous (e.g. h ~ 0)
                    if direction == 0:
                         surf = BRepAdaptor_Surface(inner["face"], True)
                         u_mid = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
                         v_mid = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0
                         p = gp_Pnt()
                         d1u = gp_Vec()
                         d1v = gp_Vec()
                         surf.D1(u_mid, v_mid, p, d1u, d1v)
                         normal = d1u.Crossed(d1v)
                         normal.Normalize()
                         dot = normal.X() * reference_normal[0] + normal.Y() * reference_normal[1] + normal.Z() * reference_normal[2]
                         if dot > 0.1: direction = 1
                         elif dot < -0.1: direction = -1

                except Exception:
                    pass

            bend = DetectedBend(
                bend_id=i + 1,
                angle=round(total_angle, 1),
                inner_radius=inner["radius"],
                bend_length=inner["bend_length"],
                flange1_length=0,  # Zou berekend moeten worden
                flange2_length=0,
                position=inner["location"],
                bend_axis=inner["axis"],
                is_standard_angle=any(abs(total_angle - a) < 5 for a in STANDARD_BEND_ANGLES),
                is_standard_radius=any(abs(inner["radius"] - r) < 0.1 for r in [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]),
            )
            # Add direction attribute dynamically (not in dataclass yet, but we can use it for counting)
            bend.direction = direction
            bends.append(bend)

    if thickness is None and detected_thicknesses:
        # Use the most common thickness
        from collections import Counter
        c = Counter(detected_thicknesses)
        thickness = c.most_common(1)[0][0]
        result["thickness"] = thickness

    # Calculate counter bends
    up_bends = sum(1 for b in bends if getattr(b, 'direction', 0) == 1)
    down_bends = sum(1 for b in bends if getattr(b, 'direction', 0) == -1)

    # The minority direction is the "counter" direction
    counter_bend_count = min(up_bends, down_bends) if (up_bends + down_bends) > 0 else 0

    # Detect if this is a stock profile (purchased)
    # 1. Closed profile (koker/buis): 4 bends forming ~360°
    # 2. Open standard profile (L, U, C): simple bends over full length
    is_closed_profile = False
    is_stock_profile = False

    if len(bends) >= 4:
        total_bend_angle = sum(b.angle for b in bends)
        if 350 <= total_bend_angle <= 370:
            is_closed_profile = True
            is_stock_profile = True

    # Check for open stock profiles (L, U, C)
    if not is_stock_profile and 1 <= len(bends) <= 3:
        # Heuristic: If all bends have the same length and that length is significant
        if bends:
            lengths = [b.bend_length for b in bends]
            avg_len = sum(lengths) / len(lengths)
            # All bends same length and > 100mm? Likely a stock profile
            if all(abs(l - avg_len) < avg_len * 0.1 for l in lengths) and avg_len > 100:
                # We could also check aspect ratio if we had bbox here, 
                # but bend_length is a good proxy for profile length.
                is_stock_profile = True

    result["bends"] = bends
    result["bend_count"] = len(bends)
    result["counter_bend_count"] = counter_bend_count
    result["is_sheet_metal"] = len(bends) > 0
    result["is_closed_profile"] = is_closed_profile
    result["is_stock_profile"] = is_stock_profile
    result["total_bend_length"] = sum(b.bend_length for b in bends)

    # For stock profiles, set bend_count to 0 (purchased as profile)
    if is_stock_profile:
        result["bend_count_for_erp"] = 0
    else:
        result["bend_count_for_erp"] = len(bends)

    return result


# =============================================================================
# HOOFDFUNCTIE: COMPLETE PLAATWERK ANALYSE
# =============================================================================

def analyze_sheetmetal_complete(
    solid,
    thickness: float,
    material: str = "steel_s235",
    quantity: int = 1
) -> Dict[str, Any]:
    """
    Complete plaatwerk analyse voor werkvoorbereiding.

    Args:
        solid: OCP/TopoDS solid of CadQuery object
        thickness: Plaatdikte in mm
        material: Materiaalcode
        quantity: Aantal stuks

    Returns:
        Complete analyse dict
    """
    # Haal materiaal eigenschappen op
    mat_props = MATERIAL_BEND_PROPERTIES.get(
        material,
        MATERIAL_BEND_PROPERTIES["steel_s235"]
    )

    # Basis geometrie analyse
    if HAS_OCP:
        try:
            # Krijg underlying solid
            if hasattr(solid, 'val'):
                actual_solid = solid.val().wrapped
            elif hasattr(solid, 'wrapped'):
                actual_solid = solid.wrapped
            else:
                actual_solid = solid

            geom_analysis = analyze_sheet_metal_geometry(actual_solid, thickness)
        except Exception as e:
            geom_analysis = {"error": str(e), "bends": [], "bend_count": 0}
    else:
        geom_analysis = {"error": "OCP not available", "bends": [], "bend_count": 0}

    # Tooling aanbevelingen
    v_size, v_tool = recommend_v_opening(thickness)
    min_radius = get_minimum_bend_radius(thickness, material.split("_")[0])

    # K-factor en bend allowance
    k_factor = mat_props.get("k_factor", 0.44)
    sample_ba = calculate_bend_allowance(thickness, 90, min_radius, k_factor)

    # Buigkracht berekening (voor 1 meter buiglengte)
    bend_force_per_m = calculate_bend_force(
        thickness, 1000, v_size,
        mat_props.get("tensile_strength", 400)
    )

    # Standaard dikte check
    is_standard_thickness = any(
        abs(thickness - std) < 0.05
        for std in STANDARD_THICKNESSES
    )

    # Bouw resultaat
    result = {
        "is_sheet_metal": True,
        "thickness": {
            "value": thickness,
            "is_standard": is_standard_thickness,
            "nearest_standard": min(STANDARD_THICKNESSES, key=lambda x: abs(x - thickness)),
            "standard": "EN 10131" if is_standard_thickness else None,
        },
        "material": {
            "code": material,
            "name": mat_props.get("name", material),
            "tensile_strength": mat_props.get("tensile_strength"),
            "yield_strength": mat_props.get("yield_strength"),
            "k_factor": k_factor,
            "springback": f"{(mat_props.get('springback_factor', 1.0) - 1) * 100:.1f}%",
        },
        "bending": {
            "bend_count": geom_analysis.get("bend_count", 0),
            "total_bend_length_mm": geom_analysis.get("total_bend_length", 0),
            "min_inner_radius": min_radius,
            "bend_allowance_90deg": round(sample_ba, 2),
            "bends": [
                {
                    "id": b.bend_id,
                    "angle": b.angle,
                    "radius": b.inner_radius,
                    "length": round(b.bend_length, 1),
                    "standard_angle": b.is_standard_angle,
                    "standard_radius": b.is_standard_radius,
                }
                for b in geom_analysis.get("bends", [])
            ] if geom_analysis.get("bends") else [],
        },
        "tooling": {
            "recommended_v_die": f"V{v_size}",
            "v_opening_mm": v_size,
            "punch_radius_mm": v_tool.punch_radius,
            "min_flange_mm": v_tool.min_flange,
            "max_thickness_mm": v_tool.max_thickness,
            "bend_force_kN_per_m": round(bend_force_per_m, 1),
            "tonnage_per_m": v_tool.tonnage_per_m,
        },
        "flat_pattern": {
            "note": "Uitslag berekening beschikbaar per buiging",
            "k_factor_used": k_factor,
            "calculation_method": "DIN 6935",
        },
        "production": {
            "quantity": quantity,
            "estimated_bends_total": geom_analysis.get("bend_count", 0) * quantity,
            "machine_requirement": _recommend_machine(thickness, geom_analysis.get("total_bend_length", 0)),
        },
        "warnings": [],
    }

    # Waarschuwingen genereren
    if not is_standard_thickness:
        result["warnings"].append(
            f"Niet-standaard plaatdikte ({thickness}mm). "
            f"Overweeg {result['thickness']['nearest_standard']}mm"
        )

    for bend in geom_analysis.get("bends", []):
        if bend.inner_radius < min_radius:
            result["warnings"].append(
                f"Buiging {bend.bend_id}: radius {bend.inner_radius}mm < minimum {min_radius}mm - risico op scheuren"
            )

    return result


def _recommend_machine(thickness: float, total_bend_length: float) -> str:
    """Aanbeveling voor type kantbank."""
    if thickness <= 3 and total_bend_length < 2000:
        return "Kleine kantbank (≤50 ton)"
    elif thickness <= 6 and total_bend_length < 3000:
        return "Middelgrote kantbank (50-150 ton)"
    elif thickness <= 10:
        return "Grote kantbank (150-300 ton)"
    else:
        return "Zware kantbank (>300 ton)"


# =============================================================================
# HELPER: FLAT PATTERN CALCULATOR
# =============================================================================

def calculate_complete_flat_pattern(
    flanges: List[float],
    bend_angles: List[float],
    bend_radii: List[float],
    thickness: float,
    k_factor: float = 0.44
) -> Dict[str, Any]:
    """
    Bereken complete uitslag voor meerdere buigingen.

    Args:
        flanges: Lijst van flenslengtes [f1, f2, f3, ...]
        bend_angles: Lijst van buighoeken tussen flenzen [a1, a2, ...]
        bend_radii: Lijst van binnenradii [r1, r2, ...]
        thickness: Plaatdikte
        k_factor: K-factor

    Returns:
        Dict met flat length en details
    """
    if len(flanges) < 2 or len(bend_angles) != len(flanges) - 1:
        return {"error": "Invalid input: need at least 2 flanges and matching bend angles"}

    total_flat = sum(flanges)
    total_deduction = 0
    bend_details = []

    for i, (angle, radius) in enumerate(zip(bend_angles, bend_radii)):
        ba = calculate_bend_allowance(thickness, angle, radius, k_factor)
        bd = calculate_bend_deduction(thickness, angle, radius, k_factor)
        total_deduction += bd

        bend_details.append({
            "bend_number": i + 1,
            "angle": angle,
            "radius": radius,
            "bend_allowance": round(ba, 2),
            "bend_deduction": round(bd, 2),
        })

    flat_length = total_flat - total_deduction

    return {
        "flanges": flanges,
        "total_flange_length": round(sum(flanges), 2),
        "total_bend_deduction": round(total_deduction, 2),
        "flat_pattern_length": round(flat_length, 2),
        "thickness": thickness,
        "k_factor": k_factor,
        "bend_details": bend_details,
        "formula": "Flat = ΣFlanges - ΣBend_Deductions (DIN 6935)",
    }
