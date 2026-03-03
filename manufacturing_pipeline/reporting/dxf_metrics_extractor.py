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
    from shapely.geometry import Polygon, box
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
        
        loops = _read_polylines_from_dxf(msp)
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
            'hole_loops': hole_loops
        }
        
    except Exception as e:
        print(f"[WARN] DXF reading failed: {str(e)[:60]}")
        return None


def _metrics_from_loops(loops: Dict[str, List]) -> Dict[str, Any]:
    """Calculate metrics from loop data using shapely."""
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
        
        if not outer_loop or len(outer_loop) < 3:
            return metrics
        
        # Create outer polygon
        outer_poly = Polygon(outer_loop)
        
        # Oriented Bounding Box (OBB)
        obb = outer_poly.minimum_rotated_rectangle
        edge_lengths = []
        for i in range(4):
            p1 = obb.exterior.coords[i]
            p2 = obb.exterior.coords[(i + 1) % 4]
            dist = math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
            edge_lengths.append(dist)
        
        edge_lengths.sort()
        metrics['box_x'] = edge_lengths[2]  # Second-longest edge
        metrics['box_y'] = edge_lengths[1]  # Shorter edge (not diagonal)
        
        # Outer contour (perimeter)
        metrics['outer_contour'] = outer_poly.length
        
        # Holes
        hole_areas = []
        hole_perimeters = []
        total_hole_area = 0.0
        
        for hole_loop in hole_loops:
            if len(hole_loop) >= 3:
                hole_poly = Polygon(hole_loop)
                hole_perimeters.append(hole_poly.length)
                hole_areas.append(hole_poly.area)
                total_hole_area += hole_poly.area
        
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
        return {}
