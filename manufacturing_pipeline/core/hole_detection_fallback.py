"""
Hole detection fallback strategies and enhancement mechanisms.

This module contains advanced hole detection strategies including:
- Pre-unfold shaped hole bridging (3D → flat pattern)
- Closed inner contour detection from face boundaries
- Round contour classification (isoperimetric analysis)
- Circular wire fallback for missed cylindrical holes
- Position-based deduplication logic
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Circle
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


# =============================================================================
# Helper Functions
# =============================================================================

def normalize_string(value: Any) -> str:
    """Normalize value to lowercase string."""
    return str(value or "").strip().lower()


def is_irregular_hole(hole: Dict) -> bool:
    """Check if hole is marked as irregular."""
    return "irregular" in normalize_string(hole.get("type"))


def xy_distance(point_a: Tuple[float, float, float], 
                point_b: Tuple[float, float, float], 
                tolerance: float = 1.0) -> bool:
    """Check if two 3D points match in XY (ignoring Z)."""
    dx = float(point_a[0]) - float(point_b[0])
    dy = float(point_a[1]) - float(point_b[1])
    return math.sqrt(dx * dx + dy * dy) <= tolerance


def euclidean_distance(point_a: Tuple[float, float, float], 
                      point_b: Tuple[float, float, float]) -> float:
    """Calculate 3D Euclidean distance between two points."""
    dx = float(point_a[0]) - float(point_b[0])
    dy = float(point_a[1]) - float(point_b[1])
    dz = float(point_a[2]) - float(point_b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def is_same_detection(point_a: Tuple[float, float, float],
                     point_b: Tuple[float, float, float],
                     is_flat: bool = False) -> bool:
    """Check if two detections represent the same hole (using detection logic)."""
    dx = float(point_a[0]) - float(point_b[0])
    dy = float(point_a[1]) - float(point_b[1])
    dz = float(point_a[2]) - float(point_b[2])
    planar = math.sqrt(dx * dx + dy * dy)
    
    if is_flat:
        # Flat holes: match by XY (ignore Z offset from top/bottom surfaces)
        return planar <= 1.0
    
    # 3D holes: full 3D distance match
    return math.sqrt(dx * dx + dy * dy + dz * dz) <= 2.0


def classify_contour_roundness(contour: Dict) -> bool:
    """Classify if a contour is round using isoperimetric quotient."""
    dim_text = str(contour.get("dim") or "")
    if "x" not in dim_text.lower():
        return False
    
    try:
        dim_parts = dim_text.lower().split("x")
        dim_a = abs(float(dim_parts[0].strip()))
        dim_b = abs(float(dim_parts[1].strip()))
        
        if dim_a > 0 and dim_b > 0:
            ratio = max(dim_a, dim_b) / max(min(dim_a, dim_b), 1e-6)
            # Ratio ≤ 1.15 indicates near-round contour
            return ratio <= 1.15
    except Exception:
        pass
    
    return False


# =============================================================================
# Pre-unfold Bridge
# =============================================================================

def bridge_pre_unfold_irregular_holes(pre_unfold_holes: List[Dict], 
                                     flat_shaped_holes: List[Dict],
                                     flat_shaped_debug: List[Dict]) -> Tuple[List[Dict], List[Dict], int]:
    """Bridge irregular shaped holes from pre-unfold 3D to flat pattern.
    
    Some irregular contours detected in 3D before unfold are not recovered
    on the flat pattern (coordinate transform, topology changes). This function
    bridges those missing irregular holes.
    
    Returns: (updated_shaped_holes, updated_debug, count_added)
    """
    bridge_count = 0
    existing_flat_points = [tuple(h.get("center", (0.0, 0.0, 0.0))) 
                            for h in flat_shaped_holes]
    
    for hole in pre_unfold_holes:
        if not is_irregular_hole(hole):
            continue
        
        center = hole.get("center")
        if center is None:
            continue
        
        # Check if this hole already exists in flat pattern
        if any(xy_distance(center, p, tolerance=1.0) 
               for p in existing_flat_points):
            continue
        
        item_id = f"hole-preunfold-{len(flat_shaped_holes) + bridge_count}"
        bridge_count += 1
        
        flat_shaped_holes.append({
            "id": item_id,
            "type": hole.get("type") or "Irregular contour",
            "dim": hole.get("dim") or "",
            "center": center,
            "normal": hole.get("normal") or (1.0, 0.0, 0.0),
            "perimeter": float(hole.get("perimeter") or 0.0),
            "contour_points": hole.get("contour_points") or [],
            "method": "pre_unfold_face_boundary_bridge",
        })
        
        flat_shaped_debug.append({
            "id": item_id,
            "status": "accepted",
            "type": "irregular_contour",
            "label": hole.get("dim") or "Irregular contour",
            "reason": "Toegevoegd vanuit pre-unfold 3D face boundaries (bridge)",
            "method": "pre_unfold_face_boundary_bridge",
            "criteria": [{
                "name": "pre_unfold_bridge",
                "value": True,
                "threshold": True,
                "passed": True,
                "note": "Irregulaire contour bestond pre-unfold maar ontbrak op flat detectie",
            }],
            "position": center,
            "normal": hole.get("normal") or (1.0, 0.0, 0.0),
            "size": hole.get("dim") or "",
            "perimeter": float(hole.get("perimeter") or 0.0),
            "source": "flat",
        })
        
        existing_flat_points.append(tuple(center))
    
    return flat_shaped_holes, flat_shaped_debug, bridge_count


# =============================================================================
# Closed Inner Contour Injection
# =============================================================================

def inject_closed_contours(closed_contours: List[Dict],
                           shaped_holes: List[Dict],
                           shaped_debug: List[Dict],
                           cylindrical_holes: List[Any],
                           is_flat_pattern: bool = False) -> Tuple[List[Dict], List[Dict], int]:
    """Inject closed inner contours not found by cylindrical/shaped detection.
    
    Analyzes round contours using isoperimetric quotient and applies selective
    fallback strategies for missed detections.
    
    Returns: (updated_shaped_holes, updated_debug, count_injected)
    """
    injected_count = 0
    existing_points = []
    existing_points.extend([tuple(getattr(h, "position", (0.0, 0.0, 0.0)))
                           for h in cylindrical_holes])
    existing_points.extend([tuple(h.get("center", (0.0, 0.0, 0.0)))
                           for h in shaped_holes])
    
    cylindrical_points = [tuple(getattr(h, "position", (0.0, 0.0, 0.0)))
                         for h in cylindrical_holes]
    
    for contour in closed_contours:
        center = contour.get("center")
        if center is None:
            continue
        
        is_round_contour = classify_contour_roundness(contour)
        
        if is_round_contour:
            # Round contours usually covered by cylindrical detection
            # Only inject if not already found
            if any(is_same_detection(center, point, is_flat_pattern) 
                   for point in cylindrical_points):
                continue
            if any(euclidean_distance(center, point) <= 5.0 
                   for point in cylindrical_points):
                continue
        
        # Check if exists in any existing holes
        if any(is_same_detection(center, point, is_flat_pattern) 
               for point in existing_points):
            continue
        
        item_id = f"hole-face-boundary-{len(shaped_holes) + injected_count}"
        injected_count += 1
        
        shaped_holes.append({
            "id": item_id,
            "type": "Closed contour" if is_round_contour else "Irregular contour",
            "dim": str(contour.get("dim") or ""),
            "center": center,
            "normal": contour.get("normal") or (1.0, 0.0, 0.0),
            "perimeter": float(contour.get("perimeter") or 0.0),
            "method": ("face_boundary_round_contour_fallback" 
                      if is_round_contour else "face_boundary_primary"),
        })
        
        shaped_debug.append({
            "id": item_id,
            "status": "accepted",
            "type": "closed_contour" if is_round_contour else "irregular_contour",
            "label": str(contour.get("dim") or 
                        ("Closed contour" if is_round_contour else "Irregular contour")),
            "reason": "Toegevoegd vanuit Face Boundary als ontbrekende gesloten contour"
                     + (" (circular fallback)" if is_round_contour else ""),
            "method": ("face_boundary_round_contour_fallback"
                      if is_round_contour else "face_boundary_primary"),
            "criteria": [{
                "name": "method_order",
                "value": "primary",
                "threshold": "face_boundary_primary_first",
                "passed": True,
                "note": "Ontbrekende contour aangevuld vanuit closed inner contours",
            }],
            "position": center,
            "normal": contour.get("normal") or (1.0, 0.0, 0.0),
            "size": str(contour.get("dim") or ""),
            "perimeter": float(contour.get("perimeter") or 0.0),
            "source": "flat" if is_flat_pattern else "3d",
        })
        
        existing_points.append(tuple(center))
    
    return shaped_holes, shaped_debug, injected_count


# =============================================================================
# Circular Wire Fallback
# =============================================================================

def detect_circular_wire_fallback(wrapped_shape: Any,
                                  shaped_holes: List[Dict],
                                  shaped_debug: List[Dict],
                                  cylindrical_holes: List[Any],
                                  existing_points: List[Tuple],
                                  is_flat_pattern: bool = False,
                                  max_additions: int = 3) -> Tuple[List[Dict], List[Dict], int]:
    """Last-resort fallback: detect circular inner wires on planar faces.
    
    Some circular contours slip through detection after unfold due to
    coordinate transform or topology changes. This scans planar faces
    for circular/elliptical inner wires directly.
    
    Returns: (updated_shaped_holes, updated_debug, count_added)
    """
    if wrapped_shape is None:
        return shaped_holes, shaped_debug, 0
    
    circular_wire_added = 0
    circular_wire_seen = []
    
    face_exp = TopExp_Explorer(wrapped_shape, TopAbs_FACE)
    while face_exp.More():
        face = TopoDS.Face_s(face_exp.Current())
        face_exp.Next()
        
        # Only process planar faces
        surf = BRepAdaptor_Surface(face, True)
        if surf.GetType() != GeomAbs_Plane:
            continue
        
        outer = BRepTools.OuterWire_s(face)
        wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
        
        while wire_exp.More():
            wire = TopoDS.Wire_s(wire_exp.Current())
            wire_exp.Next()
            
            if wire.IsSame(outer):
                continue
            
            # Check if wire consists purely of circular edges
            edge_exp = TopExp_Explorer(wire, TopAbs_EDGE)
            edge_count = 0
            circle_count = 0
            
            while edge_exp.More():
                edge = TopoDS.Edge_s(edge_exp.Current())
                edge_exp.Next()
                curve = BRepAdaptor_Curve(edge)
                edge_count += 1
                if curve.GetType() == GeomAbs_Circle:
                    circle_count += 1
            
            # Pattern: single circular edge (1 circle)
            # or closed arc of circles (2+ circles forming closed wire)
            is_circular_wire = ((edge_count == 1 and circle_count == 1) or 
                               (edge_count == 2 and circle_count == 2))
            
            if not is_circular_wire:
                continue
            
            # Get center of mass
            props = GProp_GProps()
            BRepGProp.LinearProperties_s(wire, props)
            c = props.CentreOfMass()
            center = (float(c.X()), float(c.Y()), float(c.Z()))
            
            # Avoid duplicates
            if any(xy_distance(center, seen) for seen in circular_wire_seen):
                continue
            circular_wire_seen.append(center)
            
            # Skip if already detected
            if any(euclidean_distance(center, point) <= 1.0 
                   for point in existing_points):
                continue
            
            # Skip if cylindrical detection found it
            cylindrical_points = [tuple(getattr(h, "position", (0.0, 0.0, 0.0)))
                                 for h in cylindrical_holes]
            if any(xy_distance(center, point, 4.8) for point in cylindrical_points):
                continue
            
            if circular_wire_added >= max_additions:
                continue
            
            # Compute bounding box dimensions
            bbox = Bnd_Box()
            BRepBndLib.Add_s(wire, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            dx = max(0.0, float(xmax - xmin))
            dy = max(0.0, float(ymax - ymin))
            dim_a = round(max(dx, dy), 1)
            dim_b = round(min(dx, dy), 1)
            dim_text = f"{dim_a}x{dim_b}"
            
            # Add to shaped holes
            item_id = f"hole-face-circular-wire-{len(shaped_holes)}"
            shaped_holes.append({
                "id": item_id,
                "type": "Closed contour",
                "dim": dim_text,
                "center": center,
                "normal": (1.0, 0.0, 0.0),
                "perimeter": float(props.Mass() or 0.0),
                "method": "face_boundary_circular_wire_fallback",
            })
            
            shaped_debug.append({
                "id": item_id,
                "status": "accepted",
                "type": "closed_contour",
                "label": dim_text,
                "reason": "Toegevoegd vanuit circular inner wire fallback op face boundaries",
                "method": "face_boundary_circular_wire_fallback",
                "criteria": [{
                    "name": "circular_wire_fallback",
                    "value": True,
                    "threshold": True,
                    "passed": True,
                    "note": "Ronde inner wire zonder match in bestaande detecties",
                }],
                "position": center,
                "normal": (1.0, 0.0, 0.0),
                "size": dim_text,
                "perimeter": float(props.Mass() or 0.0),
                "source": "flat" if is_flat_pattern else "3d",
            })
            
            existing_points.append(tuple(center))
            circular_wire_added += 1
    
    return shaped_holes, shaped_debug, circular_wire_added


def promote_rejected_contour_candidates(
    shaped_holes: List[Dict],
    shaped_debug: List[Dict],
    cylindrical_holes: List[Any],
    is_flat_pattern: bool = False,
    min_perimeter: float = 5.0,
) -> Tuple[List[Dict], List[Dict], int]:
    """Promote rejected contour candidates that are valid closed inner loops.

    This keeps viewer, API payload and XML export aligned on the same accepted
    contour list when a contour was rejected only by strict shape heuristics.
    """
    promoted_count = 0
    existing_points: List[Tuple[float, float, float]] = []
    existing_points.extend([
        tuple(getattr(h, "position", (0.0, 0.0, 0.0)))
        for h in cylindrical_holes
    ])
    existing_points.extend([
        tuple(h.get("center", (0.0, 0.0, 0.0)))
        for h in shaped_holes
    ])

    accepted_ids = {str(h.get("id") or "") for h in shaped_holes}

    for item in shaped_debug:
        if str(item.get("status") or "").lower() != "rejected":
            continue

        item_type = normalize_string(item.get("type"))
        method = normalize_string(item.get("method"))
        perimeter = float(item.get("perimeter") or 0.0)
        contour_points = [
            p for p in (item.get("contour_points") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 3
        ]

        is_candidate_type = (
            "irregular" in item_type
            or "closed_contour" in item_type
            or "closed contour" in item_type
        )
        is_candidate_method = method in {
            "face_boundary_primary",
            "face_boundary_round_contour_fallback",
            "face_boundary_circular_wire_fallback",
            "recovery_bucket_fallback",
            "recovery_bucket_fallback_for_unclassified",
        }

        if not (is_candidate_type or is_candidate_method):
            continue
        if len(contour_points) < 3 and perimeter < min_perimeter:
            continue

        center = item.get("position")
        if not (isinstance(center, (list, tuple)) and len(center) >= 3):
            continue
        center_tuple = (float(center[0]), float(center[1]), float(center[2]))

        if any(is_same_detection(center_tuple, point, is_flat_pattern) for point in existing_points):
            continue

        item_id = str(item.get("id") or f"hole-promoted-{len(shaped_holes) + promoted_count}")
        if item_id in accepted_ids:
            item_id = f"{item_id}-promoted"

        shaped_holes.append({
            "id": item_id,
            "type": item.get("label") or item.get("type") or "Irregular contour",
            "dim": item.get("size") or item.get("label") or "",
            "center": center_tuple,
            "normal": tuple(item.get("normal") or (1.0, 0.0, 0.0)),
            "perimeter": perimeter,
            "contour_points": contour_points,
            "method": "face_boundary_rejected_promoted",
        })

        item["id"] = item_id
        item["status"] = "accepted"
        item["method"] = "face_boundary_rejected_promoted"
        item["reason"] = "Geaccepteerd als gesloten contour (single-source-of-truth promotie)"
        item["criteria"] = [
            *(item.get("criteria") or []),
            {
                "name": "promoted_closed_contour",
                "value": True,
                "threshold": True,
                "passed": True,
                "note": "Rejected contour met geldige gesloten loop is geaccepteerd",
            },
        ]

        accepted_ids.add(item_id)
        existing_points.append(center_tuple)
        promoted_count += 1

    return shaped_holes, shaped_debug, promoted_count


__all__ = [
    "normalize_string",
    "is_irregular_hole",
    "xy_distance",
    "euclidean_distance",
    "is_same_detection",
    "classify_contour_roundness",
    "bridge_pre_unfold_irregular_holes",
    "inject_closed_contours",
    "detect_circular_wire_fallback",
    "promote_rejected_contour_candidates",
]
