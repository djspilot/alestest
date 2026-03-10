"""DXF-based metrics extraction for sheet metal parts.

This module provides utilities to:
1. Generate DXF files from sheet metal solids (flat and unfolded)
2. Extract geometric metrics from DXF files
3. Calculate oriented bounding boxes, holes, contours, and areas
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import math

# Add manufacturing_pipeline to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import cadquery as cq
    from cadquery import Solid, Wire, Face, Edge
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

try:
    from shapely.geometry import Polygon, box, MultiPoint
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def generate_dxf_from_solid(
    solid: Any,
    output_path: Path,
    is_unfolded: bool = False
) -> bool:
    """Generate DXF from a sheet metal solid (flat or unfolded representation).
    
    Args:
        solid: CadQuery solid object OR OCP TopoDS_Solid
        output_path: Path where DXF should be written
        is_unfolded: If True, solid is already unfolded; if False, extract largest planar face
        
    Returns:
        True if DXF generation succeeded, False otherwise
    """
    if not HAS_CADQUERY or not HAS_EZDXF:
        print(f"[WARN] DXF generation requires CadQuery and ezdxf")
        return False
    
    try:
        # Convert OCP solid to CadQuery if needed
        if not hasattr(solid, 'faces') or not callable(getattr(solid, 'faces', None)):
            try:
                # Try to wrap OCP solid in CadQuery
                solid = cq.Solid(solid)
                print(f"[DEBUG] OCP solid converted to CadQuery")
            except Exception as e:
                print(f"[WARN] Solid conversion failed: {e}")
                return False
        
        if is_unfolded:
            # For unfolded solids, find largest face (usually the unfolded flat pattern)
            loops = _extract_loops_from_largest_face(solid)
        else:
            # For flat plates, extract from largest planar face using 2D projection
            loops = _extract_loops_from_largest_planar_face(solid)
        
        if not loops or not loops.get('outer_loop'):
            print(f"[WARN] No loops extracted from solid")
            return False
        
        _write_dxf(output_path, loops)
        print(f"[OK] DXF written: {output_path}")
        return True
        
    except Exception as e:
        print(f"[WARN] DXF generation failed: {str(e)[:80]}")
        import traceback
        traceback.print_exc()
        return False


def extract_metrics_from_dxf(dxf_path: Path) -> Optional[Dict[str, Any]]:
    """Extract sheet metal metrics from a DXF file.
    
    Returns dict with:
    - box_x, box_y: Oriented bounding box dimensions (OBB)
    - nr_holes: Number of holes
    - hole_contours: Comma-separated perimeter list
    - outer_contour: Outer perimeter
    - total_contour: Sum of outer + hole perimeters
    - area_no_holes: Area of flat pattern minus holes
    - top_area: Area of flat pattern (same as area_no_holes for sheets)
    
    Supports both:
    - Python-generated DXF (with LWPOLYLINE layers 'outer', 'hole_*')
    - FreeCAD-generated DXF (with ARC/LINE contours)
    """
    if not HAS_EZDXF or not HAS_SHAPELY:
        print(f"[WARN] Metrics extraction requires ezdxf and shapely")
        return None
    
    try:
        if not dxf_path.exists():
            print(f"[WARN] DXF file not found: {dxf_path}")
            return None
        
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
        
        # Try LWPOLYLINE approach first (Python-generated DXF)
        loops = _read_polylines_from_dxf(msp)
        
        # Fallback: detect holes from ARC/LINE contours (FreeCAD-generated DXF)
        if not loops or not loops.get('hole_loops') or len(loops.get('hole_loops', [])) == 0:
            print(f"[DEBUG] LWPOLYLINE holes not found, trying ARC/LINE contour detection...")
            loops_alt = _detect_hole_contours_from_arcs(msp)
            if loops_alt and loops_alt.get('outer_loop'):
                loops = loops_alt
        
        if not loops or not loops.get('outer_loop'):
            print(f"[WARN] No polylines found in DXF")
            return None
        
        metrics = _metrics_from_loops(loops)
        return metrics
        
    except Exception as e:
        print(f"[WARN] Metrics extraction failed: {str(e)[:80]}")
        return None


# ======================== INTERNAL HELPERS ========================

def _extract_loops_from_largest_planar_face(solid: Any) -> Optional[Dict[str, List]]:
    """Extract 2D loops from largest planar face via projection.
    
    For flat plates (NrBends=0), this projects the 3D face to 2D using
    the face normal and orthogonal basis vectors.
    
    Handles both CadQuery and OCP solids.
    """
    if not HAS_CADQUERY:
        return None
    
    try:
        # Convert OCP solid to CadQuery if needed
        if not hasattr(solid, 'faces') or not callable(getattr(solid, 'faces', None)):
            try:
                solid = cq.Solid(solid)
                print(f"[DEBUG] OCP→CadQuery conversion successful")
            except Exception as e:
                print(f"[DEBUG] OCP→CadQuery conversion failed: {e}")
                return None
        
        # Get all faces
        try:
            faces_selector = solid.faces()
            if hasattr(faces_selector, 'vals'):
                faces_list = faces_selector.vals()
            else:
                faces_list = list(solid.faces())
        except:
            faces_list = list(solid.faces())
        
        if not faces_list:
            print(f"[DEBUG] No faces found")
            return None
        
        # Find largest face by area
        largest_face = None
        max_area = 0
        for face in faces_list:
            try:
                # .Area() is a method that returns a Quantity; extract numeric value
                area_val = face.Area()
                if hasattr(area_val, 'value'):
                    area = float(area_val.value)
                else:
                    area = float(area_val)
                if area > max_area:
                    max_area = area
                    largest_face = face
            except:
                pass
        
        if largest_face is None:
            print(f"[DEBUG] No face with calculable area")
            return None
        
        print(f"[DEBUG] Largest face area: {max_area:.1f} mm²")
        
        # Get face normal (orthogonal to the plane)
        try:
            face_normal = largest_face.normalAt()
            # Normalize to CadQuery Vector if needed
            if hasattr(face_normal, 'x') and hasattr(face_normal, 'y') and hasattr(face_normal, 'z'):
                # OCP vector: extract coordinates
                face_normal = cq.Vector(face_normal.x, face_normal.y, face_normal.z)
            elif not isinstance(face_normal, cq.Vector):
                face_normal = cq.Vector(face_normal)
        except:
            face_normal = cq.Vector(0, 0, 1)  # Default vertical
        
        # Get orthogonal basis vectors for 2D projection
        try:
            z_component = face_normal.getZ() if hasattr(face_normal, 'getZ') else face_normal.z
            if abs(z_component) > 0.99:  # Effectively Z-aligned
                basis_u = cq.Vector(1, 0, 0)
                basis_v = cq.Vector(0, 1, 0)
            else:
                # Build orthonormal basis
                basis_u = cq.Vector(0, 0, 1).cross(face_normal).normalized()
                basis_v = face_normal.cross(basis_u).normalized()
        except Exception as e:
            print(f"[DEBUG] Basis vector calculation failed: {e}, using defaults")
            basis_u = cq.Vector(1, 0, 0)
            basis_v = cq.Vector(0, 1, 0)
        
        # Extract outer loop
        outer_wire = largest_face.outerWire()
        outer_loop = _wire_to_polyline_2d(outer_wire, basis_u, basis_v)
        
        # Extract hole loops
        hole_loops = []
        try:
            for inner_wire in largest_face.innerWires():
                hole_loop = _wire_to_polyline_2d(inner_wire, basis_u, basis_v)
                if hole_loop:
                    hole_loops.append(hole_loop)
        except:
            pass
        
        return {
            'outer_loop': outer_loop,
            'hole_loops': hole_loops,
            'face_area': max_area  # Store actual 3D face area
        }
        
    except Exception as e:
        print(f"[WARN] Face extraction failed: {str(e)[:60]}")
        return None


def _extract_loops_from_largest_face(solid: Any) -> Optional[Dict[str, List]]:
    """Extract 2D loops from largest face (for already-flat/unfolded solids).
    
    Handles both CadQuery and OCP solids.
    """
    if not HAS_CADQUERY:
        return None
    
    try:
        # Convert OCP solid to CadQuery if needed
        if not hasattr(solid, 'faces'):
            try:
                solid = cq.Solid(solid)
            except Exception as e:
                print(f"[DEBUG] Conversion to CadQuery failed: {e}")
                return None
        
        # Get all faces
        try:
            faces_selector = solid.faces()
            if hasattr(faces_selector, 'vals'):
                faces_list = faces_selector.vals()
            else:
                faces_list = list(solid.faces())
        except:
            faces_list = list(solid.faces())
        
        if not faces_list:
            return None
        
        # Find largest face by area
        largest_face = None
        max_area = 0
        for face in faces_list:
            try:
                # .Area() is a method that returns a Quantity; extract numeric value
                area_val = face.Area()
                if hasattr(area_val, 'value'):
                    area = float(area_val.value)
                else:
                    area = float(area_val)
                if area > max_area:
                    max_area = area
                    largest_face = face
            except:
                pass
        
        if largest_face is None:
            return None
        
        # For unfolded/flat, use face normal to define 2D plane
        try:
            face_normal = largest_face.normalAt()
            # Normalize to CadQuery Vector if needed
            if hasattr(face_normal, 'x') and hasattr(face_normal, 'y') and hasattr(face_normal, 'z'):
                # OCP vector: extract coordinates
                face_normal = cq.Vector(face_normal.x, face_normal.y, face_normal.z)
            elif not isinstance(face_normal, cq.Vector):
                face_normal = cq.Vector(face_normal)
        except:
            face_normal = cq.Vector(0, 0, 1)
        
        # Determine basis vectors
        try:
            z_component = face_normal.getZ() if hasattr(face_normal, 'getZ') else face_normal.z
            if abs(z_component) > 0.99:
                basis_u = cq.Vector(1, 0, 0)
                basis_v = cq.Vector(0, 1, 0)
            else:
                basis_u = cq.Vector(0, 0, 1).cross(face_normal).normalized()
                basis_v = face_normal.cross(basis_u).normalized()
        except Exception as e:
            print(f"[DEBUG] Basis vector calculation failed: {e}, using defaults")
            basis_u = cq.Vector(1, 0, 0)
            basis_v = cq.Vector(0, 1, 0)
        
        outer_wire = largest_face.outerWire()
        outer_loop = _wire_to_polyline_2d(outer_wire, basis_u, basis_v)
        
        hole_loops = []
        for inner_wire in largest_face.innerWires():
            hole_loop = _wire_to_polyline_2d(inner_wire, basis_u, basis_v)
            if hole_loop:
                hole_loops.append(hole_loop)
        
        return {
            'outer_loop': outer_loop,
            'hole_loops': hole_loops
        }
        
    except Exception as e:
        print(f"[WARN] Face extraction failed: {str(e)[:60]}")
        return None


def _wire_to_polyline_2d(wire: Any, basis_u, basis_v) -> Optional[List[Tuple[float, float]]]:
    """Convert 3D wire to 2D polyline via projection."""
    if not HAS_CADQUERY:
        return None
    
    try:
        # Get ordered points from wire via sampling
        points_3d = None
        # Try different sample method signatures
        try:
            # Try the most common signature
            result = wire.sample(n_samples=200)
            if isinstance(result, tuple):
                points_3d = result[0]
            else:
                points_3d = result
        except TypeError as te:
            try:
                # Try positional argument
                result = wire.sample(200)
                if isinstance(result, tuple):
                    points_3d = result[0]
                else:
                    points_3d = result
            except Exception as e2:
                try:
                    # Try no argument variant
                    result = wire.sample()
                    if isinstance(result, tuple):
                        points_3d = result[0]
                    else:
                        points_3d = result
                except Exception as e3:
                    print(f"[DEBUG] All wire.sample() attempts failed: {te}, {e2}, {e3}")
                    return None
        
        if not points_3d or len(points_3d) < 3:
            return None
        
        # Make sure we have a list of points, not a single array
        if hasattr(points_3d, '__iter__') and len(points_3d) > 0:
            first_item = points_3d[0]
            if not hasattr(first_item, 'dot'):  # Not a Vector
                if isinstance(first_item, (list, tuple)) and len(first_item) == 3:
                    # Convert tuples to Vectors
                    points_3d = [cq.Vector(*pt) if isinstance(pt, (list, tuple)) else pt for pt in points_3d]
        
        # Project 3D points to 2D using basis vectors
        polyline_2d = []
        for pt in points_3d:
            # Convert to Vector if needed
            if not hasattr(pt, 'dot'):
                if isinstance(pt, (list, tuple)):
                    pt = cq.Vector(*pt)
                else:
                    continue
            # Project point onto 2D plane defined by basis_u, basis_v
            x = pt.dot(basis_u)
            y = pt.dot(basis_v)
            polyline_2d.append((x, y))
        
        return polyline_2d if len(polyline_2d) >= 3 else None
        
    except Exception as e:
        import traceback
        print(f"[WARN] Wire projection failed: {str(e)[:60]}")
        traceback.print_exc()
        return None


def _write_dxf(output_path: Path, loops: Dict[str, List]) -> None:
    """Write loops to DXF file using ezdxf."""
    if not HAS_EZDXF:
        return
    
    try:
        doc = ezdxf.new()
        msp = doc.modelspace()
        
        # Write outer loop
        if loops.get('outer_loop'):
            outer_pts = loops['outer_loop']
            msp.add_lwpolyline(outer_pts, dxfattribs={'layer': 'outer'})
        
        # Write hole loops
        for i, hole_loop in enumerate(loops.get('hole_loops', [])):
            if hole_loop:
                msp.add_lwpolyline(hole_loop, dxfattribs={'layer': f'hole_{i}'})
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(output_path))
        
    except Exception as e:
        print(f"[WARN] DXF write failed: {str(e)[:60]}")


def _read_polylines_from_dxf(msp) -> Optional[Dict[str, List]]:
    """Read polylines from DXF modelspace."""
    try:
        outer_loop = None
        hole_loops = []
        
        for entity in msp.query('LWPOLYLINE'):
            pts = [(pt[0], pt[1]) for pt in entity.get_points()]
            
            if entity.dxf.layer == 'outer':
                outer_loop = pts
            elif entity.dxf.layer.startswith('hole_'):
                hole_loops.append(pts)
        
        return {
            'outer_loop': outer_loop,
            'hole_loops': hole_loops,
            'source': 'lwpolyline',
        }
        
    except Exception as e:
        print(f"[WARN] DXF reading failed: {str(e)[:60]}")
        return None


def _dot3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm3(v: Tuple[float, float, float]) -> float:
    return math.sqrt(_dot3(v, v))


def _normalize3(v: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    length = _norm3(v)
    if length <= 1e-12:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def _mat_vec_mul3(matrix: List[List[float]], vector: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )


def _power_iteration_symmetric3(
    matrix: List[List[float]],
    iterations: int = 24,
) -> Tuple[Optional[Tuple[float, float, float]], float]:
    """Approximate dominant eigenvector/eigenvalue for a symmetric 3x3 matrix."""
    seeds = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
    )
    best_vector = None
    best_eigenvalue = -1.0

    for seed in seeds:
        vector = _normalize3(seed)
        if vector is None:
            continue

        for _ in range(iterations):
            w = _mat_vec_mul3(matrix, vector)
            candidate = _normalize3(w)
            if candidate is None:
                break
            vector = candidate

        w_final = _mat_vec_mul3(matrix, vector)
        eigenvalue = _dot3(vector, w_final)
        if eigenvalue > best_eigenvalue:
            best_eigenvalue = eigenvalue
            best_vector = vector

    return best_vector, best_eigenvalue


def _orthogonal_fallback_axis(axis: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    """Build a stable axis orthogonal to the input axis."""
    references = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    ref = min(references, key=lambda candidate: abs(_dot3(axis, candidate)))
    cross = (
        axis[1] * ref[2] - axis[2] * ref[1],
        axis[2] * ref[0] - axis[0] * ref[2],
        axis[0] * ref[1] - axis[1] * ref[0],
    )
    return _normalize3(cross)


def _estimate_planar_basis_from_points(
    points_3d: List[Tuple[float, float, float]],
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Estimate a 2D projection basis from 3D points using covariance PCA."""
    if len(points_3d) < 3:
        return None

    count = float(len(points_3d))
    mean_x = sum(point[0] for point in points_3d) / count
    mean_y = sum(point[1] for point in points_3d) / count
    mean_z = sum(point[2] for point in points_3d) / count

    c_xx = c_xy = c_xz = 0.0
    c_yy = c_yz = c_zz = 0.0
    for point_x, point_y, point_z in points_3d:
        dx = point_x - mean_x
        dy = point_y - mean_y
        dz = point_z - mean_z
        c_xx += dx * dx
        c_xy += dx * dy
        c_xz += dx * dz
        c_yy += dy * dy
        c_yz += dy * dz
        c_zz += dz * dz

    divisor = max(count - 1.0, 1.0)
    covariance = [
        [c_xx / divisor, c_xy / divisor, c_xz / divisor],
        [c_xy / divisor, c_yy / divisor, c_yz / divisor],
        [c_xz / divisor, c_yz / divisor, c_zz / divisor],
    ]

    axis_u, eigen_u = _power_iteration_symmetric3(covariance)
    if axis_u is None or eigen_u <= 1e-12:
        return None

    deflated = [
        [covariance[row][col] - eigen_u * axis_u[row] * axis_u[col] for col in range(3)]
        for row in range(3)
    ]
    axis_v_raw, _ = _power_iteration_symmetric3(deflated)

    if axis_v_raw is None:
        axis_v = _orthogonal_fallback_axis(axis_u)
        if axis_v is None:
            return None
        return axis_u, axis_v

    projection = _dot3(axis_v_raw, axis_u)
    axis_v_ortho = (
        axis_v_raw[0] - projection * axis_u[0],
        axis_v_raw[1] - projection * axis_u[1],
        axis_v_raw[2] - projection * axis_u[2],
    )
    axis_v = _normalize3(axis_v_ortho)
    if axis_v is None:
        axis_v = _orthogonal_fallback_axis(axis_u)
    if axis_v is None:
        return None

    return axis_u, axis_v


def _project_point_to_basis(
    point_3d: Tuple[float, float, float],
    basis_u: Tuple[float, float, float],
    basis_v: Tuple[float, float, float],
) -> Tuple[float, float]:
    return (_dot3(point_3d, basis_u), _dot3(point_3d, basis_v))


def _detect_hole_contours_from_arcs(msp) -> Optional[Dict[str, List]]:
    """Detect hole contours from ARC and LINE entities (FreeCAD-generated DXF).
    
    FreeCAD exports sheet metal unfolds as ARC/LINE entities forming closed loops.
    This function:
    1. Collects all ARC and LINE entities
    2. Groups them into closed contours (loops)
    3. Identifies outer loop (largest area) and inner loops (holes)
    
    Returns dict with 'outer_loop', 'hole_loops', and 'bbox_from_dxf'.
    """
    try:
        from shapely.geometry import Polygon, LineString, box as shapely_box
        from shapely.ops import unary_union
    except ImportError:
        print(f"[WARN] Shapely required for ARC/LINE detection")
        return None
    
    try:
        # Try to get DXF extents first (before parsing entities)
        # ezdxf: msp is a Modelspace, access doc via context
        try:
            doc = None
            # Try to get document from msp
            if hasattr(msp, 'doc'):
                doc = msp.doc
            elif hasattr(msp, 'dxf'):
                # Alternative: get via dxf attribute
                if hasattr(msp.dxf, 'doc'):
                    doc = msp.dxf.doc
            
            bbox_from_dxf = None
            if doc:
                extmin = doc.header.get('$EXTMIN', None)
                extmax = doc.header.get('$EXTMAX', None)
                
                if extmin and extmax:
                    bbox_from_dxf = {
                        'x_min': extmin[0],
                        'y_min': extmin[1],
                        'x_max': extmax[0],
                        'y_max': extmax[1],
                        'width': extmax[0] - extmin[0],
                        'height': extmax[1] - extmin[1]
                    }
                    print(f"[DEBUG] DXF BBox from header: X={bbox_from_dxf['width']:.2f}, Y={bbox_from_dxf['height']:.2f}")
        except Exception as e:
            print(f"[DEBUG] Could not get DXF header bbox: {e}")
            bbox_from_dxf = None
        
        entities = []
        
        # Collect all ARC and LINE entities with coordinates
        for entity in msp.query('ARC'):
            try:
                center = entity.dxf.center
                radius = entity.dxf.radius
                start_angle = entity.dxf.start_angle
                end_angle = entity.dxf.end_angle
                
                # Sample arc into line segments; handle 360° wrap robustly.
                delta = end_angle - start_angle
                if delta <= 0.0:
                    delta += 360.0
                steps = max(8, int(delta / 5.0))

                arc_pts = []
                center_z = float(getattr(center, 'z', 0.0))
                for i in range(steps + 1):
                    angle = start_angle + (delta * i / steps)
                    rad = math.radians(angle)
                    x = center.x + radius * math.cos(rad)
                    y = center.y + radius * math.sin(rad)
                    arc_pts.append((x, y, center_z))

                for i in range(len(arc_pts) - 1):
                    entities.append(('line', arc_pts[i], arc_pts[i + 1]))
            except Exception as e:
                print(f"[DEBUG] Arc error: {e}")
                pass
        
        # Collect LINE entities
        for entity in msp.query('LINE'):
            try:
                p1 = entity.dxf.start
                p2 = entity.dxf.end
                entities.append((
                    'line',
                    (float(p1.x), float(p1.y), float(getattr(p1, 'z', 0.0))),
                    (float(p2.x), float(p2.y), float(getattr(p2, 'z', 0.0))),
                ))
            except:
                pass
        
        if not entities:
            print(f"[DEBUG] No ARC/LINE entities found")
            return None
        
        print(f"[DEBUG] Found {len(entities)} ARC/LINE segments")

        all_points_3d = []
        for _, point_a, point_b in entities:
            all_points_3d.append(point_a)
            all_points_3d.append(point_b)

        basis = _estimate_planar_basis_from_points(all_points_3d)
        if basis:
            basis_u, basis_v = basis
            projected_entities = [
                (
                    etype,
                    _project_point_to_basis(point_a, basis_u, basis_v),
                    _project_point_to_basis(point_b, basis_u, basis_v),
                )
                for etype, point_a, point_b in entities
            ]
            all_points_2d = [_project_point_to_basis(point, basis_u, basis_v) for point in all_points_3d]
            print(f"[DEBUG] 3D->2D projection enabled for ARC/LINE contours")
        else:
            projected_entities = [(etype, (a[0], a[1]), (b[0], b[1])) for etype, a, b in entities]
            all_points_2d = [(point[0], point[1]) for point in all_points_3d]
            print(f"[DEBUG] Projection fallback to XY plane")

        projected_bbox_2d = None
        if all_points_2d:
            xs = [point[0] for point in all_points_2d]
            ys = [point[1] for point in all_points_2d]
            projected_bbox_2d = {
                'width': max(xs) - min(xs),
                'height': max(ys) - min(ys),
            }
        
        # Group entities into contours (closed loops)
        contours = _group_entities_into_contours(projected_entities)
        
        if not contours:
            print(f"[WARN] No closed contours detected")
            return None
        
        print(f"[DEBUG] Detected {len(contours)} contours")
        
        # Find outer loop (largest area)
        outer_idx = 0
        outer_area = 0
        hole_loops = []
        
        for i, contour in enumerate(contours):
            poly = Polygon(contour)
            area = poly.area
            
            if area > outer_area:
                # Previous outer becomes hole
                if i > 0:
                    hole_loops.append(contours[outer_idx])
                outer_area = area
                outer_idx = i
            else:
                hole_loops.append(contour)
        
        outer_loop = contours[outer_idx]
        
        print(f"[DEBUG] Outer loop: {len(outer_loop)} pts, area={outer_area:.1f}")
        print(f"[DEBUG] Holes: {len(hole_loops)} loops")
        
        result = {
            'outer_loop': outer_loop,
            'hole_loops': hole_loops,
            'all_points_2d': all_points_2d,
            'projected_bbox_2d': projected_bbox_2d,
            'source': 'arc_line',
        }
        
        # Add DXF bbox if available
        if bbox_from_dxf:
            result['bbox_from_dxf'] = bbox_from_dxf
        
        return result
        
    except Exception as e:
        print(f"[WARN] Arc detection failed: {str(e)[:60]}")
        return None


def _group_entities_into_contours(entities: List) -> List[List]:
    """Group line/arc segments into closed loops.
    
    Args:
        entities: List of ('line', p1, p2) tuples
        
    Returns:
        List of contours, where each contour is a list of (x, y) points.
        Filters out tiny/incomplete contours.
    """
    if not entities:
        return []
    
    contours = []
    remaining = list(entities)
    
    # Group segments into potential contours
    raw_contours = []
    
    while remaining:
        current_contour = [remaining[0][1], remaining[0][2]]
        remaining.pop(0)
        
        # Grow this contour by finding connected segments
        max_iterations = len(remaining) + 100  # Safety limit
        iterations = 0
        
        while iterations < max_iterations:
            iterations += 1
            last_pt = current_contour[-1]
            found = False
            
            for i, (etype, p1, p2) in enumerate(remaining):
                tolerance = 1.0  # Distance tolerance 1mm for endpoint matching
                
                # Check if p1 connects to last point
                dist1 = math.sqrt((p1[0] - last_pt[0])**2 + (p1[1] - last_pt[1])**2)
                if dist1 < tolerance:
                    current_contour.append(p2)
                    remaining.pop(i)
                    found = True
                    break
                
                # Check if p2 connects to last point
                dist2 = math.sqrt((p2[0] - last_pt[0])**2 + (p2[1] - last_pt[1])**2)
                if dist2 < tolerance:
                    current_contour.append(p1)
                    remaining.pop(i)
                    found = True
                    break
            
            if not found:
                break
        
        # Check if contour is closed
        if len(current_contour) > 2:
            first_pt = current_contour[0]
            last_pt = current_contour[-1]
            closure_dist = math.sqrt((first_pt[0] - last_pt[0])**2 + (first_pt[1] - last_pt[1])**2)
            
            if closure_dist < 2.0:  # Reasonably closed
                # Remove duplicate closing point
                contour_clean = current_contour[:-1]
                raw_contours.append(contour_clean)
    
    # Filter contours by size: keep only significant ones
    # - Minimum 10 points (avoid fragments)
    # - Minimum 50mm perimeter (avoid tiny loops)
    for contour in raw_contours:
        if len(contour) < 10:
            continue
        
        # Calculate perimeter
        perim = 0
        for i in range(len(contour)):
            p1 = contour[i]
            p2 = contour[(i+1) % len(contour)]
            dist = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            perim += dist
        
        if perim < 50:  # Skip tiny contours
            continue
        
        contours.append(contour)
    
    return contours


def _extract_obb_dimensions(shape_geometry) -> Optional[Tuple[float, float]]:
    """Return (long_side, short_side) from minimum rotated rectangle."""
    try:
        if shape_geometry is None or shape_geometry.is_empty:
            return None

        obb = shape_geometry.minimum_rotated_rectangle
        if not hasattr(obb, 'exterior'):
            min_x, min_y, max_x, max_y = shape_geometry.bounds
            span_x = max_x - min_x
            span_y = max_y - min_y
            if span_x <= 1e-9 or span_y <= 1e-9:
                return None
            return max(span_x, span_y), min(span_x, span_y)

        coords = list(obb.exterior.coords)
        if len(coords) < 5:
            return None

        edge_lengths = []
        for i in range(4):
            p1 = coords[i]
            p2 = coords[i + 1]
            edge_lengths.append(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2))

        edge_lengths = sorted(length for length in edge_lengths if length > 1e-9)
        if len(edge_lengths) < 2:
            return None

        return edge_lengths[-1], edge_lengths[-2]
    except Exception:
        return None


def _metrics_from_loops(loops: Dict[str, List]) -> Dict[str, Any]:
    """Calculate metrics from loop data using shapely.
    
    Prefers DXF header bounding box if available (more reliable for FreeCAD exports).
    Falls back to OBB calculation from contours if needed.
    """
    if not HAS_SHAPELY:
        return {}
    
    try:
        metrics = {
            'box_x': 0.0,
            'box_y': 0.0,
            'nr_holes': 0,
            'hole_contours': '',
            'outer_contour': 0.0,
            'total_contour': 0.0,
            'area_no_holes': 0.0,
            'top_area': 0.0,
        }
        
        outer_loop = loops.get('outer_loop', [])
        hole_loops = loops.get('hole_loops', [])
        face_area_3d = loops.get('face_area')  # Get original 3D face area if available
        bbox_dxf = loops.get('bbox_from_dxf')  # DXF header bounding box
        all_points_2d = loops.get('all_points_2d', [])
        projected_bbox_2d = loops.get('projected_bbox_2d')
        loops_source = loops.get('source', '')
        
        if not outer_loop or len(outer_loop) < 3:
            return metrics
        
        # Use DXF header bbox if available (more reliable than OBB of contours)
        if bbox_dxf:
            metrics['box_x'] = bbox_dxf['width']
            metrics['box_y'] = bbox_dxf['height']
            print(f"[DEBUG] Using DXF bbox: {metrics['box_x']:.2f} x {metrics['box_y']:.2f}")
        elif projected_bbox_2d:
            width = float(projected_bbox_2d.get('width', 0.0))
            height = float(projected_bbox_2d.get('height', 0.0))
            metrics['box_x'] = max(width, height)
            metrics['box_y'] = min(width, height)
            print(f"[DEBUG] Using projected bbox: {metrics['box_x']:.2f} x {metrics['box_y']:.2f}")
        else:
            obb_dims = None

            if all_points_2d and len(all_points_2d) >= 3:
                obb_dims = _extract_obb_dimensions(MultiPoint(all_points_2d))
                if obb_dims:
                    print(f"[DEBUG] Using projected point-cloud OBB: {obb_dims[0]:.2f} x {obb_dims[1]:.2f}")

            if obb_dims is None:
                outer_for_obb = Polygon(outer_loop)
                if not outer_for_obb.is_valid:
                    outer_for_obb = MultiPoint(outer_loop).convex_hull
                obb_dims = _extract_obb_dimensions(outer_for_obb)
                if obb_dims:
                    print(f"[DEBUG] Using outer-loop OBB: {obb_dims[0]:.2f} x {obb_dims[1]:.2f}")

            if obb_dims:
                metrics['box_x'] = obb_dims[0]
                metrics['box_y'] = obb_dims[1]
        
        # Create outer polygon for other metrics
        outer_poly = Polygon(outer_loop)
        if not outer_poly.is_valid:
            repaired = outer_poly.buffer(0)
            if not repaired.is_empty:
                if repaired.geom_type == 'MultiPolygon':
                    outer_poly = max(repaired.geoms, key=lambda geom: geom.area)
                else:
                    outer_poly = repaired
        
        # Outer contour (perimeter)
        metrics['outer_contour'] = outer_poly.length
        
        # Holes
        hole_areas = []
        hole_perimeters = []
        total_hole_area = 0.0
        outer_area_reference = abs(outer_poly.area)
        outer_perimeter_reference = max(outer_poly.length, 1e-9)
        
        for hole_loop in hole_loops:
            if len(hole_loop) >= 3:
                hole_poly = Polygon(hole_loop)
                hole_area = abs(hole_poly.area)
                hole_perimeter = hole_poly.length

                # ARC/LINE-derived contours can include duplicate shell loops from 3D DXF exports.
                # Reject implausibly large "holes" in that mode.
                if loops_source == 'arc_line':
                    if hole_area >= outer_area_reference * 0.8 or hole_perimeter >= outer_perimeter_reference * 0.9:
                        continue

                hole_perimeters.append(hole_perimeter)
                hole_areas.append(hole_area)
                total_hole_area += hole_area
        
        metrics['nr_holes'] = len(hole_perimeters)
        metrics['hole_contours'] = '_'.join(f"{p:.2f}" for p in hole_perimeters)
        
        # Total contour
        metrics['total_contour'] = metrics['outer_contour'] + sum(hole_perimeters)
        
        # Areas: reference convention expects TopArea as net area (with holes removed)
        # and AreaNoHoles as gross outer area.
        # Use original 3D face area (net) when available for higher accuracy.
        if face_area_3d is not None and face_area_3d > 0:
            metrics['top_area'] = face_area_3d
            # Estimate gross area by adding scaled hole areas back to net area
            projection_outer_area = outer_poly.area
            if projection_outer_area > 0 and total_hole_area > 0:
                hole_area_scaled = total_hole_area * (face_area_3d / projection_outer_area)
                metrics['area_no_holes'] = face_area_3d + hole_area_scaled
            else:
                metrics['area_no_holes'] = face_area_3d
        else:
            # Fallback: projected net/gross areas
            metrics['top_area'] = outer_poly.area - total_hole_area
            metrics['area_no_holes'] = outer_poly.area
        
        return metrics
        
    except Exception as e:
        print(f"[WARN] Metrics calculation failed: {str(e)[:60]}")
        import traceback
        traceback.print_exc()
        return {}
