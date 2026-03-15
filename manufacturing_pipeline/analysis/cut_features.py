"""
Cut Features Extraction for Sheet Metal Parts and Profiles
===========================================================

Fase 1: Gaten en snijdata voor plaat + gezette_plaat classificaties.
Fase 2: Gaten en snijdata voor profielen (buis, koker, hoekstaal).

WANNEER wordt dit uitgevoerd?
------------------------------
- Alleen voor parts met classification = "plaat" OF "gezette_plaat"
- Wordt aangeroepen vanuit xml_exporter._process_plaat_item()
- Na unfold poging (als gezette_plaat), vóór XML field population

WAT wordt er gedetecteerd?
---------------------------
1. Gaten (cylindrisch): detect_holes() uit step_processing.py
2. Vormgaten (sleuven/rectangles): detect_shaped_holes() uit step_processing.py
3. Gatcontourlengtes: perimeter van elke hole inner wire
4. Buitencontour: outer wire perimeter van grootste planar face
5. Totale snijlengte: sum(gatcontours) + buitencontour
6. Box dimensions: X en Y van bounding box

FLAT vs 3D strategie:
---------------------
- Als unfold succesvol → analyseer flat pattern (nauwkeuriger voor gezette plaat)
- Als unfold mislukt / niet geprobeerd → analyseer 3D solid

VEILIGHEID:
-----------
- Gebruikt ALLEEN bestaande detectiefuncties (geen nieuwe algoritmes)
- Faalt gracefully: bij exceptions retourneer None i.p.v. crash
- Backwards compatible: caller kan fallback naar placeholders

Auteur: ALES Manufacturing Pipeline
Datum: 3 maart 2026
Fase: 1 (plaat + gezette_plaat)
"""

from typing import Dict, List, Optional, Any, Tuple
import logging
import math
from dataclasses import dataclass

import cadquery as cq
from OCP.TopAbs import TopAbs_FACE
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape, TopoDS_Face
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cone

# Import bestaande detectiefuncties (NIET wijzigen in step_processing.py!)
from .step_processing import detect_holes, detect_shaped_holes, deduplicate_holes
from . import iso_standards

logger = logging.getLogger(__name__)


@dataclass
class CutFeatures:
    """
    Result container voor cut features extractie.
    
    Alle lengtes in millimeters.
    """
    nr_holes: int                      # Totaal aantal gaten (cilindrisch + vorm)
    hole_contours: List[float]         # Perimeter van elk gat (mm)
    hole_radii: List[float]            # Radius/halve-breedte per gat (mm)
    outer_contour: float               # Buitencontour lengte (mm)
    total_contour: float               # Totale snijlengte (mm)
    box_x: float                       # X-dimensie bounding box (mm)
    box_y: float                       # Y-dimensie bounding box (mm)
    source: str                        # "flat" of "3d"
    hole_types: List[str] = None       # ["round", "thread", "countersunk", "slot", ...]
    threaded_holes: int = 0
    countersunk_holes: int = 0
    countersunk_angles: List[float] = None
    
    # Detail info voor debugging
    nr_cylindrical: int = 0
    nr_shaped: int = 0
    shaped_types: List[str] = None     # ["Slot", "Rect", ...]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict voor logging/debugging."""
        return {
            "nr_holes": self.nr_holes,
            "hole_contours": self.hole_contours,
            "hole_radii": self.hole_radii,
            "outer_contour": self.outer_contour,
            "total_contour": self.total_contour,
            "box_x": self.box_x,
            "box_y": self.box_y,
            "source": self.source,
            "hole_types": self.hole_types or [],
            "threaded_holes": self.threaded_holes,
            "countersunk_holes": self.countersunk_holes,
            "countersunk_angles": self.countersunk_angles or [],
            "nr_cylindrical": self.nr_cylindrical,
            "nr_shaped": self.nr_shaped,
            "shaped_types": self.shaped_types or []
        }


def extract_cut_features_for_sheet(
    solid: TopoDS_Shape,
    unfold_result: Optional[Dict[str, Any]] = None,
    part_classification: str = "plaat"
) -> Optional[CutFeatures]:
    """
    Extraheer gaten, snijlengtes en box dimensions voor plaatwerk.
    
    FLOW:
    -----
    1. Bepaal analyse domain (flat pattern of 3D solid)
    2. Detect cylindrische gaten via detect_holes()
    3. Detect vormgaten via detect_shaped_holes()
    4. Dedupliceer overlappende gaten
    5. Bereken hole contours (inner wire perimeters)
    6. Bereken outer contour (grootste face outer wire)
    7. Bereken bounding box dimensions
    8. Return CutFeatures object
    
    Parameters:
    -----------
    solid : TopoDS_Shape
        De te analyseren solid (3D) of flat pattern
    unfold_result : dict, optional
        Als unfold is uitgevoerd: {"success": bool, "flat_pattern": TopoDS_Shape, ...}
    part_classification : str
        "plaat" of "gezette_plaat" (voor logging)
    
    Returns:
    --------
    CutFeatures of None bij falen
    
    VEILIGHEID:
    -----------
    - Faalt gracefully bij exceptions
    - Gebruikt alleen gevalideerde bestaande functies
    - Geen side effects op input shapes
    """
    try:
        logger.info(f"[CutFeatures] Start extractie voor {part_classification}")
        
        # STAP 1: Bepaal analyse domain
        # ==============================
        # Als unfold succesvol: gebruik flat pattern (nauwkeuriger)
        # Anders: gebruik 3D solid
        analysis_shape = solid
        source = "3d"
        
        if unfold_result and unfold_result.get("success") and unfold_result.get("flat_pattern"):
            logger.info("[CutFeatures] Gebruik flat pattern voor analyse")
            analysis_shape = unfold_result["flat_pattern"]
            source = "flat"
        else:
            logger.info("[CutFeatures] Gebruik 3D solid voor analyse (geen unfold)")
        
        # Convert naar CadQuery object voor detect_holes()
        cq_solid = cq.Solid(analysis_shape)
        cq_object = cq.Workplane("XY").newObject([cq_solid])
        
        # STAP 2: Detect cylindrische gaten
        # ==================================
        # Gebruikt detect_holes() uit step_processing.py
        # filter_bores=True: sluit draaideel boring gaten uit
        # is_flat_pattern: geeft aan of we flat of 3D analyseren
        is_flat = (source == "flat")
        logger.info(f"[CutFeatures] Detect cylindrische gaten (flat={is_flat})...")
        
        cylindrical_holes = detect_holes(
            cq_object,
            filter_bores=True,
            is_flat_pattern=is_flat
        )
        logger.info(f"[CutFeatures] Gevonden: {len(cylindrical_holes)} cylindrische gaten")
        
        # STAP 3: Detect vormgaten (sleuven, rectangles, polygonen)
        # ==========================================================
        # Gebruikt detect_shaped_holes() uit step_processing.py
        # BELANGRIJK: detect_shaped_holes verwacht CadQuery Workplane
        logger.info("[CutFeatures] Detect vormgaten (sleuven/rectangles)...")
        
        # Create Workplane object for detect_shaped_holes
        cq_workplane = cq.Workplane(obj=cq_solid)
        shaped_holes = detect_shaped_holes(cq_workplane)
        logger.info(f"[CutFeatures] Gevonden: {len(shaped_holes)} vormgaten")
        
        # STAP 4: Dedupliceer overlappende gaten
        # ========================================
        # detect_shaped_holes kan cirkels detecteren die al door detect_holes gevonden zijn
        logger.info("[CutFeatures] Dedupliceer overlappende detecties...")
        cylindrical_holes = deduplicate_holes(cylindrical_holes, shaped_holes)
        logger.info(f"[CutFeatures] Na dedup: {len(cylindrical_holes)} cylindrisch, {len(shaped_holes)} vorm")
        
        # STAP 5: Bereken hole contours (perimeters)
        # ===========================================
        hole_contours = []
        hole_radii = []
        hole_types = []
        shaped_types = []
        threaded_holes = 0
        countersunk_holes = 0
        countersunk_angles = []

        # Match conische faces op cilindrische gaten om verzonken gaten te markeren.
        countersink_matches = _detect_countersunk_holes(cq_object, cylindrical_holes)
        
        # Cylindrische gaten: contour = 2*pi*r, radius = diameter/2
        for idx, hole in enumerate(cylindrical_holes):
            radius = hole.diameter / 2.0
            perimeter = 2.0 * 3.14159265359 * radius
            hole_contours.append(perimeter)
            hole_radii.append(radius)

            hole_type = "round"
            cs_angle = countersink_matches.get(idx)
            if cs_angle is not None:
                hole_type = "countersunk"
                countersunk_holes += 1
                countersunk_angles.append(cs_angle)
            else:
                # Use a slightly wider tolerance because modeled tap-hole diameters
                # often follow drill sizes and can deviate from ideal minor diameter.
                thread_matches = iso_standards.identify_thread_from_diameter(hole.diameter, 0.20)
                tapped_matches = [m for m in thread_matches if "tapped" in m.designation.lower()]

                # Plausibility check: for sheet/plate parts, very large nominal
                # thread sizes relative to hole depth are typically clearance holes.
                hole_depth = float(getattr(hole, "depth", 0.0) or 0.0)
                if tapped_matches and hole_depth > 0:
                    plausible_matches = [
                        m for m in tapped_matches
                        if float(getattr(m, "major_diameter", 0.0) or 0.0) <= (hole_depth * 1.35)
                    ]
                    if plausible_matches:
                        tapped_matches = plausible_matches
                    else:
                        tapped_matches = []

                if tapped_matches:
                    hole_type = "thread"
                    threaded_holes += 1

            hole_types.append(hole_type)
        
        # Vormgaten: bereken perimeter uit dimensions
        for shaped in shaped_holes:
            perimeter = float(shaped.get("perimeter", 0.0) or 0.0)
            if perimeter <= 0:
                # shaped bevat "dim" string zoals "120.5x50.0" (length x width)
                # of "type" zoals "Slot", "Rect", "Poly"
                dim_str = shaped.get("dim", "")
                dimensions = _parse_dimensions_from_string(dim_str)

                if dimensions:
                    length_dim, width_dim = dimensions
                    # Perimeter approximation based on shape type
                    shape_type = shaped.get("type", "Rect")
                    if shape_type == "Slot":
                        # dim string from detect_shaped_holes stores total slot length x width.
                        # Capsule perimeter with total length L and width W: 2*(L-W) + pi*W.
                        straight_len = max(0.0, length_dim - width_dim)
                        perimeter = 2.0 * straight_len + 3.14159265359 * width_dim
                    else:
                        # Rectangle/Poly: approximate as rectangle
                        perimeter = 2.0 * (length_dim + width_dim)
                else:
                    # Fallback: geen dimensions gevonden, gebruik default
                    perimeter = 40.0  # Default small hole
            
            hole_contours.append(perimeter)

            shaped_type = shaped.get("type", "Unknown")
            shaped_types.append(shaped_type)

            shaped_type_l = (shaped_type or "").lower()
            if "slot" in shaped_type_l:
                hole_types.append("slot")
            else:
                hole_types.append("shaped")

        # Fallback: sommige STEP-modellen met tapgaten bevatten alleen conische
        # insteek/chamfer-faces en geen bruikbare cilindrische hole-face.
        # Label deze daarom niet als countersunk om false positives te vermijden.
        standalone_countersinks = _detect_standalone_countersunk_holes(
            cq_object,
            cylindrical_holes,
        )
        for cs in standalone_countersinks:
            radius = float(cs.get("inner_radius", 0.0) or 0.0)
            if radius <= 0:
                continue

            perimeter = 2.0 * 3.14159265359 * radius
            hole_contours.append(perimeter)
            hole_radii.append(radius)
            hole_types.append("thread")
            threaded_holes += 1
        
        # STAP 6: Bereken outer contour
        # ==============================
        # Vind grootste planaire face, neem outer wire perimeter
        logger.info("[CutFeatures] Bereken buitencontour...")
        outer_contour = _get_outer_contour_length(analysis_shape)
        logger.info(f"[CutFeatures] Buitencontour: {outer_contour:.2f} mm")
        
        # STAP 7: Totale snijlengte
        # ==========================
        total_contour = sum(hole_contours) + outer_contour
        logger.info(f"[CutFeatures] Totale snijlengte: {total_contour:.2f} mm")
        
        # STAP 8: Bounding box dimensions
        # ================================
        bbox = _get_bounding_box(analysis_shape)
        box_x = bbox["xlen"]
        box_y = bbox["ylen"]
        logger.info(f"[CutFeatures] Box dimensions: X={box_x:.2f} mm, Y={box_y:.2f} mm")
        
        # STAP 9: Return resultaat
        # =========================
        total_holes = len(hole_types)
        result = CutFeatures(
            nr_holes=total_holes,
            hole_contours=hole_contours,
            hole_radii=hole_radii,
            outer_contour=outer_contour,
            total_contour=total_contour,
            box_x=box_x,
            box_y=box_y,
            source=source,
            hole_types=hole_types,
            threaded_holes=threaded_holes,
            countersunk_holes=countersunk_holes,
            countersunk_angles=countersunk_angles,
            nr_cylindrical=len(cylindrical_holes),
            nr_shaped=len(shaped_holes),
            shaped_types=shaped_types
        )
        
        logger.info(f"[CutFeatures] Extractie compleet: {result.to_dict()}")
        return result
        
    except Exception as e:
        logger.error(f"[CutFeatures] FOUT tijdens extractie: {e}", exc_info=True)
        return None


def _detect_countersunk_holes(cq_object, cylindrical_holes) -> Dict[int, float]:
    """
    Detecteer verzonken gaten door conische faces te matchen op gat-as en positie.

    Returns:
    --------
    Dict met key = hole-index, value = countersink included angle in graden.
    """
    if not cylindrical_holes:
        return {}

    conical_faces = _collect_conical_faces(cq_object)
    if not conical_faces:
        return {}

    matches: Dict[int, float] = {}

    for idx, hole in enumerate(cylindrical_holes):
        hole_axis = _normalize_vector(hole.axis)
        if hole_axis is None:
            continue

        hole_radius = max(float(hole.diameter) * 0.5, 0.0)
        hole_pos = hole.position
        hole_axis_origin = _as_point_tuple(getattr(hole, "axis_origin", None)) or _as_point_tuple(hole_pos)
        if hole_axis_origin is None:
            continue

        best_angle: Optional[float] = None
        best_score: Optional[float] = None

        for cone in conical_faces:
            axis_dot = abs(_dot(hole_axis, cone["axis"]))
            if axis_dot < 0.97:
                continue

            radial_dist = _distance_point_to_axis(hole_axis_origin, cone["origin"], cone["axis"])
            if radial_dist > max(1.0, hole_radius * 1.25):
                continue

            axial_dist = abs(_signed_axis_distance(hole_axis_origin, cone["origin"], cone["axis"]))
            if axial_dist > max(25.0, hole_radius * 6.0):
                continue

            included_angle = cone["included_angle"]
            if included_angle < 55.0 or included_angle > 150.0:
                continue

            score = radial_dist + (1.0 - axis_dot) * 10.0 + axial_dist * 0.05
            if best_score is None or score < best_score:
                best_score = score
                best_angle = included_angle

        if best_angle is not None:
            matches[idx] = round(best_angle, 2)

    return matches


def _detect_standalone_countersunk_holes(cq_object, cylindrical_holes) -> List[Dict[str, float]]:
    """
    Detecteer countersinks die niet gekoppeld konden worden aan detect_holes().

    Dit vangt STEP-varianten waar alleen conische countersink-faces beschikbaar
    zijn en de cilindrische kern niet als aparte face terugkomt.
    """
    conical_faces = _collect_conical_faces(cq_object)
    if not conical_faces:
        return []

    grouped = _group_conical_countersink_faces(conical_faces)
    standalone: List[Dict[str, float]] = []

    for candidate in grouped:
        inner_radius = float(candidate.get("inner_radius", 0.0) or 0.0)
        included_angle = float(candidate.get("included_angle", 0.0) or 0.0)

        if inner_radius <= 0:
            continue

        # Typical countersink included angles are around 82/90/100/110/120.
        if included_angle < 55.0 or included_angle > 150.0:
            continue

        if _candidate_matches_cylindrical_hole(candidate, cylindrical_holes):
            continue

        standalone.append({
            "inner_radius": inner_radius,
            "included_angle": included_angle,
            "origin": candidate["origin"],
        })

    return standalone


def _group_conical_countersink_faces(conical_faces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupliceer conische faces die dezelfde countersink representeren."""
    groups: List[Dict[str, Any]] = []

    for cone in conical_faces:
        placed = False
        for group in groups:
            axis_dot = abs(_dot(group["axis"], cone["axis"]))
            if axis_dot < 0.999:
                continue

            radial_dist = _distance_point_to_axis(cone["origin"], group["origin"], group["axis"])
            axial_dist = abs(_signed_axis_distance(cone["origin"], group["origin"], group["axis"]))
            if radial_dist > 0.2 or axial_dist > 1.0:
                continue

            if abs(float(group["included_angle"]) - float(cone["included_angle"])) > 1.0:
                continue

            if abs(float(group["inner_radius"]) - float(cone.get("inner_radius", 0.0))) > 0.3:
                continue

            group["count"] += 1
            placed = True
            break

        if not placed:
            groups.append({
                "axis": cone["axis"],
                "origin": cone["origin"],
                "included_angle": float(cone["included_angle"]),
                "inner_radius": float(cone.get("inner_radius", 0.0) or 0.0),
                "outer_radius": float(cone.get("outer_radius", 0.0) or 0.0),
                "count": 1,
            })

    return groups


def _candidate_matches_cylindrical_hole(candidate: Dict[str, Any], cylindrical_holes) -> bool:
    """Return True when a countersink candidate aligns with an already-detected cylindrical hole."""
    candidate_axis = _normalize_vector(candidate.get("axis"))
    candidate_origin = _as_point_tuple(candidate.get("origin"))
    candidate_inner_radius = float(candidate.get("inner_radius", 0.0) or 0.0)

    if candidate_axis is None or candidate_origin is None:
        return False

    for hole in cylindrical_holes:
        hole_axis = _normalize_vector(hole.axis)
        if hole_axis is None:
            continue

        axis_dot = abs(_dot(hole_axis, candidate_axis))
        if axis_dot < 0.97:
            continue

        hole_axis_origin = _as_point_tuple(getattr(hole, "axis_origin", None)) or _as_point_tuple(hole.position)
        if hole_axis_origin is None:
            continue

        radial_dist = _distance_point_to_axis(hole_axis_origin, candidate_origin, candidate_axis)
        hole_radius = max(float(hole.diameter) * 0.5, 0.0)
        radial_limit = max(1.0, min(candidate_inner_radius, hole_radius) * 0.8)
        if radial_dist > radial_limit:
            continue

        axial_dist = abs(_signed_axis_distance(hole_axis_origin, candidate_origin, candidate_axis))
        if axial_dist > max(40.0, hole_radius * 8.0):
            continue

        return True

    return False


def _collect_conical_faces(cq_object) -> List[Dict[str, Any]]:
    """Collect conische face-asdata voor countersink matching."""
    conical_faces: List[Dict[str, Any]] = []

    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle

        for face in cq_object.faces().vals():
            surf = BRepAdaptor_Surface(face.wrapped, True)
            if surf.GetType() != GeomAbs_Cone:
                continue

            cone = surf.Cone()
            axis_dir = cone.Axis().Direction()
            axis = _normalize_vector((axis_dir.X(), axis_dir.Y(), axis_dir.Z()))
            if axis is None:
                continue

            origin = cone.Location()
            included_angle = abs(math.degrees(float(cone.SemiAngle()))) * 2.0
            if included_angle <= 0:
                continue

            circle_radii: List[float] = []
            exp = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
            while exp.More():
                edge = TopoDS.Edge_s(exp.Current())
                curve = BRepAdaptor_Curve(edge)
                if curve.GetType() == GeomAbs_Circle:
                    try:
                        radius = float(curve.Circle().Radius())
                        if radius > 0:
                            circle_radii.append(radius)
                    except Exception:
                        pass
                exp.Next()

            if circle_radii:
                inner_radius = min(circle_radii)
                outer_radius = max(circle_radii)
            else:
                ref_radius = float(cone.RefRadius())
                inner_radius = 0.0
                outer_radius = ref_radius if ref_radius > 0 else 0.0

            conical_faces.append({
                "axis": axis,
                "origin": (origin.X(), origin.Y(), origin.Z()),
                "included_angle": included_angle,
                "inner_radius": inner_radius,
                "outer_radius": outer_radius,
            })
    except Exception as e:
        logger.debug(f"[CutFeatures] Conical face scan failed: {e}")

    return conical_faces


def _normalize_vector(vector: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    """Return unit vector or None for invalid vectors."""
    try:
        x, y, z = float(vector[0]), float(vector[1]), float(vector[2])
        norm = math.sqrt(x * x + y * y + z * z)
        if norm <= 1e-9:
            return None
        return (x / norm, y / norm, z / norm)
    except Exception:
        return None


def _as_point_tuple(value: Any) -> Optional[Tuple[float, float, float]]:
    """Return a numeric 3D point tuple when possible."""
    try:
        if value is None:
            return None
        return (float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return None


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance_point_to_axis(
    point: Tuple[float, float, float],
    axis_origin: Tuple[float, float, float],
    axis_dir: Tuple[float, float, float],
) -> float:
    """Shortest distance between point and infinite axis line."""
    vx = point[0] - axis_origin[0]
    vy = point[1] - axis_origin[1]
    vz = point[2] - axis_origin[2]

    cx = vy * axis_dir[2] - vz * axis_dir[1]
    cy = vz * axis_dir[0] - vx * axis_dir[2]
    cz = vx * axis_dir[1] - vy * axis_dir[0]

    return math.sqrt(cx * cx + cy * cy + cz * cz)


def _signed_axis_distance(
    point: Tuple[float, float, float],
    axis_origin: Tuple[float, float, float],
    axis_dir: Tuple[float, float, float],
) -> float:
    """Projected signed distance from axis origin to point along axis direction."""
    return (
        (point[0] - axis_origin[0]) * axis_dir[0]
        + (point[1] - axis_origin[1]) * axis_dir[1]
        + (point[2] - axis_origin[2]) * axis_dir[2]
    )


def _get_outer_contour_length(shape: TopoDS_Shape) -> float:
    """
    Bereken outer contour lengte van grootste planaire face.
    
    Strategie:
    ----------
    1. Vind alle planaire faces (GeomAbs_Plane)
    2. Sorteer op oppervlakte (grootste = skin face)
    3. Neem outer wire van grootste face
    4. Bereken perimeter
    
    Returns:
    --------
    Perimeter in mm, of 0.0 bij falen
    """
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.TopoDS import TopoDS, TopoDS_Face
        from OCP.BRepTools import BRepTools
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        
        # Collect planaire faces met oppervlakte
        planar_faces = []
        
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            
            # Check if planar
            surf = BRepAdaptor_Surface(face)
            if surf.GetType() == GeomAbs_Plane:
                # Bereken oppervlakte
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()
                planar_faces.append((face, area))
            
            exp.Next()
        
        if not planar_faces:
            logger.warning("[CutFeatures] Geen planaire faces gevonden voor outer contour")
            return 0.0
        
        # Sorteer op oppervlakte (grootste eerst)
        planar_faces.sort(key=lambda x: x[1], reverse=True)
        largest_face = planar_faces[0][0]
        
        # Haal outer wire
        outer_wire = BRepTools.OuterWire_s(largest_face)
        
        # Bereken perimeter
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(outer_wire, props)
        perimeter = props.Mass()
        
        return perimeter
        
    except Exception as e:
        logger.error(f"[CutFeatures] Fout bij outer contour berekening: {e}")
        return 0.0


def _get_bounding_box(shape: TopoDS_Shape) -> Dict[str, float]:
    """
    Bereken bounding box dimensions.
    
    Returns:
    --------
    Dict met xlen, ylen, zlen in mm
    """
    try:
        cq_shape = cq.Shape(shape)
        bb = cq_shape.BoundingBox()
        
        return {
            "xlen": bb.xlen,
            "ylen": bb.ylen,
            "zlen": bb.zlen
        }
        
    except Exception as e:
        logger.error(f"[CutFeatures] Fout bij bounding box: {e}")
        return {"xlen": 0.0, "ylen": 0.0, "zlen": 0.0}


def _parse_dimensions_from_string(dim_str: str) -> Optional[tuple]:
    """
    Parse dimensions from string like "120.5x50.0" -> (120.5, 50.0).
    
    Returns:
    --------
    Tuple (length, width) or None if parse fails
    """
    try:
        if not dim_str or 'x' not in dim_str:
            return None
        
        parts = dim_str.lower().split('x')
        if len(parts) != 2:
            return None
        
        length = float(parts[0].strip())
        width = float(parts[1].strip())
        
        return (length, width)
        
    except Exception as e:
        logger.debug(f"[CutFeatures] Could not parse dimensions from '{dim_str}': {e}")
        return None


# ============================================================================
# TOEKOMSTIGE UITBREIDINGEN (Fase 2: profiel)
# ============================================================================

def extract_cut_features_for_profile(
    solid: TopoDS_Shape,
    part_classification: str = "profiel"
) -> Optional[CutFeatures]:
    """
    Fase 2: Gaten en snijdata voor profielen (buis, koker, hoekstaal).

    Altijd 3D analyse (geen unfold). outer_contour = 0 (profiel is ingekocht,
    geen lasersnij-buitencontour). total_contour = sum(hole contours).

    Parameters:
    -----------
    solid : TopoDS_Shape
        De te analyseren profiel solid
    part_classification : str
        "profiel" (voor logging)

    Returns:
    --------
    CutFeatures of None bij falen
    """
    try:
        logger.info(f"[CutFeatures] Start profiel extractie voor {part_classification}")

        # Altijd 3D analyse (profielen worden niet ontvouwen)
        source = "3d"

        # Convert naar CadQuery object
        cq_solid = cq.Solid(solid)
        cq_object = cq.Workplane("XY").newObject([cq_solid])

        # STAP 1: Detect cylindrische gaten
        # filter_bores=True filtert binnenboring van buis weg (diepte >> wanddikte)
        logger.info("[CutFeatures] Profiel: detect cylindrische gaten...")
        cylindrical_holes = detect_holes(
            cq_object,
            filter_bores=True,
            is_flat_pattern=False
        )
        logger.info(f"[CutFeatures] Profiel: {len(cylindrical_holes)} cylindrische gaten")

        # STAP 2: Detect vormgaten (sleuven, rectangles) op planaire vlakken
        logger.info("[CutFeatures] Profiel: detect vormgaten...")
        cq_workplane = cq.Workplane(obj=cq_solid)
        shaped_holes = detect_shaped_holes(cq_workplane)
        logger.info(f"[CutFeatures] Profiel: {len(shaped_holes)} vormgaten")

        # STAP 3: Dedupliceer
        logger.info("[CutFeatures] Profiel: dedupliceer...")
        cylindrical_holes = deduplicate_holes(cylindrical_holes, shaped_holes)
        logger.info(f"[CutFeatures] Profiel na dedup: {len(cylindrical_holes)} cylindrisch, {len(shaped_holes)} vorm")

        # STAP 4: Bereken hole contours en classificeer
        hole_contours = []
        hole_radii = []
        hole_types = []
        shaped_types = []
        threaded_holes = 0
        countersunk_holes = 0
        countersunk_angles = []

        # Match conische faces op cilindrische gaten (verzonken gaten)
        countersink_matches = _detect_countersunk_holes(cq_object, cylindrical_holes)

        for idx, hole in enumerate(cylindrical_holes):
            radius = hole.diameter / 2.0
            perimeter = 2.0 * math.pi * radius
            hole_contours.append(perimeter)
            hole_radii.append(radius)

            hole_type = "round"
            cs_angle = countersink_matches.get(idx)
            if cs_angle is not None:
                hole_type = "countersunk"
                countersunk_holes += 1
                countersunk_angles.append(cs_angle)
            else:
                # Tapgat detectie — geen diepte-plausibiliteitscheck voor profielen
                # (profielgaten gaan door de wand, diepte = wanddikte < major diameter)
                thread_matches = iso_standards.identify_thread_from_diameter(hole.diameter, 0.20)
                tapped_matches = [m for m in thread_matches if "tapped" in m.designation.lower()]
                if tapped_matches:
                    hole_type = "thread"
                    threaded_holes += 1

            hole_types.append(hole_type)

        # Vormgaten: bereken perimeter uit dimensions
        for shaped in shaped_holes:
            perimeter = float(shaped.get("perimeter", 0.0) or 0.0)
            if perimeter <= 0:
                dim_str = shaped.get("dim", "")
                dimensions = _parse_dimensions_from_string(dim_str)
                if dimensions:
                    length_dim, width_dim = dimensions
                    shape_type = shaped.get("type", "Rect")
                    if shape_type == "Slot":
                        straight_len = max(0.0, length_dim - width_dim)
                        perimeter = 2.0 * straight_len + math.pi * width_dim
                    else:
                        perimeter = 2.0 * (length_dim + width_dim)
                else:
                    perimeter = 40.0

            hole_contours.append(perimeter)
            shaped_type = shaped.get("type", "Unknown")
            shaped_types.append(shaped_type)

            if "slot" in (shaped_type or "").lower():
                hole_types.append("slot")
            else:
                hole_types.append("shaped")

        # Standalone countersinks (conische faces zonder cilindrische hole-face)
        standalone_countersinks = _detect_standalone_countersunk_holes(
            cq_object, cylindrical_holes,
        )
        for cs in standalone_countersinks:
            radius = float(cs.get("inner_radius", 0.0) or 0.0)
            if radius <= 0:
                continue
            perimeter = 2.0 * math.pi * radius
            hole_contours.append(perimeter)
            hole_radii.append(radius)
            hole_types.append("thread")
            threaded_holes += 1

        # Profiel: geen buitencontour (ingekocht profiel)
        outer_contour = 0.0
        total_contour = sum(hole_contours)

        total_holes = len(hole_types)
        logger.info(f"[CutFeatures] Profiel: {total_holes} gaten, snijlengte={total_contour:.2f} mm")

        result = CutFeatures(
            nr_holes=total_holes,
            hole_contours=hole_contours,
            hole_radii=hole_radii,
            outer_contour=outer_contour,
            total_contour=total_contour,
            box_x=0.0,
            box_y=0.0,
            source=source,
            hole_types=hole_types,
            threaded_holes=threaded_holes,
            countersunk_holes=countersunk_holes,
            countersunk_angles=countersunk_angles,
            nr_cylindrical=len(cylindrical_holes),
            nr_shaped=len(shaped_holes),
            shaped_types=shaped_types
        )

        logger.info(f"[CutFeatures] Profiel extractie compleet: {result.to_dict()}")
        return result

    except Exception as e:
        logger.error(f"[CutFeatures] FOUT tijdens profiel extractie: {e}", exc_info=True)
        return None
