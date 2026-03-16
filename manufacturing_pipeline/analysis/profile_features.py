"""
Profile Feature Extraction Module

Extracts geometric features from tube/profile parts for XML export:
- Circular tubes: diameter, wall thickness, inner/outer radius
- Rectangular tubes: width, height, wall thickness, corner radius

This module is designed to be easily replaceable without affecting
other parts of the codebase (sheet metal, assembly analysis, etc.).

Usage:
    features = extract_profile_features(solid, dims, volume)
    tube_type = features['tube_type']  # e.g., "C_88.9x4" or "R_100x50x3"
"""

import math
from typing import Dict, List, Optional, Tuple, Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback without NumPy
    np = None

# Try to import CAD libraries
try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX, TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


def extract_profile_features(solid, dims: Tuple[float, float, float], volume: float) -> Dict[str, Any]:
    """
    Extract tube/profile features for XML export.
    
    This is the main entry point for profile feature extraction.
    
    Args:
        solid: OCP TopoDS_Shape solid
        dims: Bounding box dimensions [smallest, middle, largest] in mm
        volume: Volume in mm³
    
    Returns:
        Dictionary with extracted features:
        {
            'tube_type': str,          # "R_100x50x3" or "C_88.9x4"
            'is_circular': bool,
            'is_rectangular': bool,
            'width': float,            # For rectangular (middle dim)
            'height': float,           # For rectangular (smallest dim)
            'diameter': float,         # For circular (outer diameter)
            'thickness': float,        # Wall thickness
            'outer_radius': float,     # Corner radius (rect) or cylinder radius (circ)
            'inner_radius': float,     # Corner radius (rect) or cylinder radius (circ)
            'length': float,           # Longest dimension
            'bbox_x': float,           # Bounding box largest
            'bbox_y': float,           # Bounding box middle
            'bbox_z': float,           # Bounding box smallest
            'success': bool,           # Extraction successful
            'method': str              # Detection method used
        }
    """
    if not HAS_OCP:
        return _create_fallback_result(dims, volume)

    try:
        # ---------------------------------------------------------------
        # Primary: cut-based cross-section extraction.
        # Uses a plane whose normal IS the PCA length axis, so cross-section
        # dims are rotation-independent and always represent true outer size.
        # ---------------------------------------------------------------
        section_result = _extract_dims_from_cross_section(solid, dims)

        if section_result:
            shape_type = section_result['shape_type']
            sec_w = section_result['width']
            sec_h = section_result['height']

            # Length = longest sorted AABB dim (dominant axis always correct
            # even for tilted profiles because length >> cross-section).
            length_dim = float(sorted(dims)[-1])

            # Build corrected 3D dims: (smallest_cross, largest_cross, length).
            # These give the right volume ratio for wall-thickness estimation.
            cross_min = min(sec_w, sec_h)
            cross_max = max(sec_w, sec_h)
            corrected_dims = (cross_min, cross_max, length_dim)

            tube_type_info = _detect_tube_type(solid, corrected_dims, volume)

            if shape_type == 'C':
                tube_type_info['is_circular'] = True
                tube_type_info['is_rectangular'] = False
                outer_d = section_result['outer_diam']
                c_dims = (outer_d, outer_d, length_dim)
                result = _extract_circular_tube_features(solid, c_dims, volume, tube_type_info)
                result['method'] = 'cross_section_circular'
                return result
            else:  # 'R'
                tube_type_info['is_circular'] = False
                tube_type_info['is_rectangular'] = True
                result = _extract_rectangular_tube_features(solid, corrected_dims, volume, tube_type_info)
                result['method'] = 'cross_section_rectangular'
                return result

        # ---------------------------------------------------------------
        # Fallback: sorted AABB dims (cross-section method failed).
        # ---------------------------------------------------------------
        sorted_dims = tuple(sorted(dims))

        # Detect tube type (circular vs rectangular)
        tube_type_info = _detect_tube_type(solid, sorted_dims, volume)

        if tube_type_info['is_circular']:
            return _extract_circular_tube_features(solid, sorted_dims, volume, tube_type_info)
        elif tube_type_info['is_rectangular']:
            return _extract_rectangular_tube_features(solid, sorted_dims, volume, tube_type_info)
        else:
            # Fallback: treat as solid profile
            return _extract_solid_profile_features(solid, sorted_dims, volume)

    except Exception as e:
        # Fallback on error
        return _create_fallback_result(dims, volume, error=str(e))


def _detect_tube_type(solid, dims: Tuple[float, float, float], volume: float) -> Dict[str, Any]:
    """
    Detect whether profile is circular, rectangular, or solid.
    
    Detection strategy:
    - Circular: High cylindrical face % (≥60%), low volume ratio (<0.7)
    - Rectangular: High planar face % (≥80%), low volume ratio (<0.7)
    - Solid: High volume ratio (≥0.5)
    
    Returns:
        {
            'is_circular': bool,
            'is_rectangular': bool,
            'is_hollow': bool,
            'cylindrical_pct': float,
            'planar_pct': float,
            'volume_ratio': float
        }
    """
    smallest, middle, largest = sorted(dims)
    bbox_volume = smallest * middle * largest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
    
    # Analyze face types
    total_area = 0.0
    cylindrical_area = 0.0
    planar_area = 0.0
    
    face_exp = TopExp_Explorer(solid, TopAbs_FACE)
    while face_exp.More():
        face = TopoDS.Face_s(face_exp.Current())
        surf_adapter = BRepAdaptor_Surface(face, True)
        
        # Calculate face area
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()
        total_area += area
        
        # Check surface type
        surf_type = surf_adapter.GetType()
        if surf_type == GeomAbs_Cylinder:
            cylindrical_area += area
        elif surf_type == GeomAbs_Plane:
            planar_area += area
        
        face_exp.Next()
    
    # Calculate percentages
    cylindrical_pct = (cylindrical_area / total_area * 100) if total_area > 0 else 0
    planar_pct = (planar_area / total_area * 100) if total_area > 0 else 0
    
    # Determine type
    is_hollow = volume_ratio < 0.7
    is_circular = cylindrical_pct >= 60.0 and is_hollow
    is_rectangular = planar_pct >= 80.0 and is_hollow and not is_circular
    
    return {
        'is_circular': is_circular,
        'is_rectangular': is_rectangular,
        'is_hollow': is_hollow,
        'cylindrical_pct': cylindrical_pct,
        'planar_pct': planar_pct,
        'volume_ratio': volume_ratio
    }


def _extract_circular_tube_features(solid, dims: Tuple[float, float, float], 
                                    volume: float, type_info: Dict) -> Dict[str, Any]:
    """
    Extract features for circular/cylindrical tubes.
    
    Strategy:
    1. Extract all cylindrical face radii
    2. Outer radius = max(radii), Inner radius = min(radii)
    3. Wall thickness = outer_radius - inner_radius
    4. Create type string: "C_{diameter}x{thickness}"
    
    Args:
        solid: OCP TopoDS_Shape
        dims: [smallest, middle, largest]
        volume: Volume in mm³
        type_info: Output from _detect_tube_type()
    
    Returns:
        Feature dictionary
    """
    smallest, middle, largest = sorted(dims)
    
    # Extract cylinder radii
    cylinder_radii = _extract_cylinder_radii(solid)
    
    if not cylinder_radii:
        # Fallback: estimate from bounding box
        # Assume circular cross-section: diameter ≈ middle dimension
        estimated_outer_radius = middle / 2.0
        estimated_inner_radius = estimated_outer_radius * 0.8  # Guess 20% wall
        cylinder_radii = [estimated_outer_radius, estimated_inner_radius]
    
    # Sort radii to get outer/inner
    cylinder_radii_sorted = sorted(cylinder_radii, reverse=True)
    outer_radius = cylinder_radii_sorted[0]
    inner_radius = cylinder_radii_sorted[-1] if len(cylinder_radii_sorted) > 1 else outer_radius * 0.8
    
    # Calculate dimensions
    outer_diameter = outer_radius * 2.0
    wall_thickness = outer_radius - inner_radius
    
    # Create type string: "C_88.9x4"
    tube_type = f"C_{outer_diameter:.1f}x{wall_thickness:.0f}"
    
    return {
        'tube_type': tube_type,
        'is_circular': True,
        'is_rectangular': False,
        'width': outer_diameter,  # Alias for diameter
        'height': outer_diameter,  # Alias for diameter
        'diameter': outer_diameter,
        'thickness': wall_thickness,
        'outer_radius': outer_radius,
        'inner_radius': inner_radius,
        'length': largest,
        'bbox_x': largest,
        'bbox_y': middle,
        'bbox_z': smallest,
        'success': True,
        'method': 'circular_cylinder_extraction',
        'cylindrical_pct': type_info.get('cylindrical_pct', 0),
        'volume_ratio': type_info.get('volume_ratio', 0)
    }


def _extract_rectangular_tube_features(solid, dims: Tuple[float, float, float],
                                       volume: float, type_info: Dict) -> Dict[str, Any]:
    """
    Extract features for rectangular/square tubes.
    
    Strategy:
    1. Width = middle dimension, Height = smallest dimension
    2. Extract torus radii (corner radii) if present
    3. Estimate wall thickness from volume ratio or torus analysis
    4. Create type string: "R_{width}x{height}x{thickness}"
    
    Args:
        solid: OCP TopoDS_Shape
        dims: [smallest, middle, largest]
        volume: Volume in mm³
        type_info: Output from _detect_tube_type()
    
    Returns:
        Feature dictionary
    """
    smallest, middle, largest = sorted(dims)
    
    # Cross-section dimensions
    width = middle
    height = smallest
    
    # Extract corner radii (torus faces)
    torus_radii = _extract_torus_radii(solid)
    
    if torus_radii:
        # Outer radius = max (outer corner), Inner radius = min (inner corner)
        outer_radius = max(torus_radii)
        inner_radius = min(torus_radii)
    else:
        # No torus faces found - sharp corners or estimation failed
        outer_radius = 0.0
        inner_radius = 0.0
    
    # Estimate wall thickness
    volume_ratio = type_info.get('volume_ratio', 0)
    thickness = _estimate_wall_thickness(smallest, middle, volume_ratio, torus_radii)
    
    # Create type string: "R_100x50x3"
    tube_type = f"R_{width:.0f}x{height:.0f}x{thickness:.0f}"
    
    return {
        'tube_type': tube_type,
        'is_circular': False,
        'is_rectangular': True,
        'width': width,
        'height': height,
        'diameter': 0.0,  # N/A for rectangular
        'thickness': thickness,
        'outer_radius': outer_radius,  # Corner radius
        'inner_radius': inner_radius,  # Corner radius
        'length': largest,
        'bbox_x': largest,
        'bbox_y': middle,
        'bbox_z': smallest,
        'success': True,
        'method': 'rectangular_torus_extraction',
        'planar_pct': type_info.get('planar_pct', 0),
        'volume_ratio': volume_ratio
    }


def _extract_solid_profile_features(solid, dims: Tuple[float, float, float], 
                                    volume: float) -> Dict[str, Any]:
    """
    Fallback for solid profiles (not hollow tubes).
    
    Returns basic bounding box dimensions.
    """
    smallest, middle, largest = sorted(dims)
    
    return {
        'tube_type': f"Profile_{largest:.0f}x{middle:.0f}x{smallest:.0f}",
        'is_circular': False,
        'is_rectangular': False,
        'width': middle,
        'height': smallest,
        'diameter': 0.0,
        'thickness': smallest,  # Treat as solid thickness
        'outer_radius': 0.0,
        'inner_radius': 0.0,
        'length': largest,
        'bbox_x': largest,
        'bbox_y': middle,
        'bbox_z': smallest,
        'success': True,
        'method': 'solid_profile_fallback',
        'volume_ratio': volume / (smallest * middle * largest) if (smallest * middle * largest) > 0 else 0
    }


# =============================================================================
# HELPER FUNCTIONS - GEOMETRY EXTRACTION
# =============================================================================

def _extract_cylinder_radii(solid) -> List[float]:
    """
    Extract all cylindrical face radii from a solid.
    
    Returns:
        List of radii in mm, sorted descending (largest first)
    """
    radii = []
    
    face_exp = TopExp_Explorer(solid, TopAbs_FACE)
    while face_exp.More():
        face = TopoDS.Face_s(face_exp.Current())
        surf_adapter = BRepAdaptor_Surface(face, True)
        
        if surf_adapter.GetType() == GeomAbs_Cylinder:
            try:
                cylinder = surf_adapter.Cylinder()
                radius = cylinder.Radius()
                if radius > 0.1:  # Filter noise
                    radii.append(radius)
            except:
                pass
        
        face_exp.Next()
    
    # Remove duplicates (tolerance 0.1mm)
    unique_radii = []
    for r in sorted(radii, reverse=True):
        if not any(abs(r - ur) < 0.1 for ur in unique_radii):
            unique_radii.append(r)
    
    return unique_radii


def _extract_torus_radii(solid) -> List[float]:
    """
    Extract torus face minor radii (corner radii) from a solid.
    
    For rectangular tubes:
    - Outer corners: larger torus minor radius
    - Inner corners: smaller torus minor radius
    
    Returns:
        List of minor radii in mm, sorted descending
    """
    radii = []
    
    face_exp = TopExp_Explorer(solid, TopAbs_FACE)
    while face_exp.More():
        face = TopoDS.Face_s(face_exp.Current())
        surf_adapter = BRepAdaptor_Surface(face, True)
        
        if surf_adapter.GetType() == GeomAbs_Torus:
            try:
                torus = surf_adapter.Torus()
                minor_radius = torus.MinorRadius()
                major_radius = torus.MajorRadius()
                
                # Filter: minor radius should be reasonable for corner radius
                if 0.5 < minor_radius < 50 and minor_radius < major_radius * 0.5:
                    radii.append(minor_radius)
            except:
                pass
        
        face_exp.Next()
    
    # Remove duplicates (tolerance 0.1mm)
    unique_radii = []
    for r in sorted(radii, reverse=True):
        if not any(abs(r - ur) < 0.1 for ur in unique_radii):
            unique_radii.append(r)
    
    return unique_radii


def _extract_dims_from_cross_section(
    solid,
    fallback_dims: Tuple[float, float, float],
) -> Optional[Dict[str, Any]]:
    """
    Determine profile cross-section shape (R or C) and outer dimensions by
    cutting the solid with a plane perpendicular to its PCA-derived length axis.

    This is more reliable than both AABB and PCA-extent tricks because:
    - The cutting plane normal IS the true length axis (from PCA eigenvector),
      so the section is always truly perpendicular regardless of assembly rotation.
    - Vertex bbox in the section plane gives actual outer cross-section dims.
    - Edge curve types (GeomAbs_Line vs GeomAbs_Circle) directly identify R vs C.

    Returns:
        {'shape_type': 'R'|'C', 'width': float, 'height': float,
         'outer_diam': float, 'method': 'cross_section'}
        or None when extraction fails.
    """
    if np is None or not HAS_OCP:
        return None

    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        # ------------------------------------------------------------------
        # Step 1: Collect vertices and run PCA to find the length axis.
        # ------------------------------------------------------------------
        points: List[Tuple[float, float, float]] = []
        vexp = TopExp_Explorer(solid, TopAbs_VERTEX)
        while vexp.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vexp.Current()))
            points.append((p.X(), p.Y(), p.Z()))
            vexp.Next()

        if len(points) < 6:
            return None

        pts = np.unique(np.round(np.array(points, dtype=float), 4), axis=0)
        if len(pts) < 6:
            return None

        centroid = pts.mean(axis=0)
        centered = pts - centroid
        cov = np.cov(centered.T)
        evals, evecs = np.linalg.eigh(cov)

        # Dominant eigenvector (largest eigenvalue) = profile length direction.
        # The two smaller eigenvectors span the cross-section plane.
        length_idx = int(np.argmax(evals))
        cross_idxs = [i for i in range(3) if i != length_idx]
        length_axis = evecs[:, length_idx]
        sec_u = evecs[:, cross_idxs[0]]
        sec_v = evecs[:, cross_idxs[1]]

        # ------------------------------------------------------------------
        # Step 2: Cut solid at centroid with plane perpendicular to length axis.
        # ------------------------------------------------------------------
        nx, ny, nz = float(length_axis[0]), float(length_axis[1]), float(length_axis[2])
        cx, cy, cz = float(centroid[0]), float(centroid[1]), float(centroid[2])
        plane = gp_Pln(gp_Pnt(cx, cy, cz), gp_Dir(nx, ny, nz))

        try:
            sec_op = BRepAlgoAPI_Section(solid, plane, False)
        except TypeError:
            sec_op = BRepAlgoAPI_Section(solid, plane)

        sec_op.Build()
        if hasattr(sec_op, 'IsDone') and not sec_op.IsDone():
            return None

        section_shape = sec_op.Shape()

        # ------------------------------------------------------------------
        # Step 3: Project section vertices onto the section plane (sec_u, sec_v).
        # ------------------------------------------------------------------
        sec_2d: List[Tuple[float, float]] = []
        svert_exp = TopExp_Explorer(section_shape, TopAbs_VERTEX)
        while svert_exp.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(svert_exp.Current()))
            v = np.array([p.X(), p.Y(), p.Z()]) - centroid
            sec_2d.append((float(v @ sec_u), float(v @ sec_v)))
            svert_exp.Next()

        if len(sec_2d) < 4:
            return None

        # ------------------------------------------------------------------
        # Step 4: 2D bounding box = outer cross-section dimensions.
        # Outer vertices always bound inner ones, so all-vertex bbox = outer box.
        # ------------------------------------------------------------------
        u_vals = [s[0] for s in sec_2d]
        v_vals = [s[1] for s in sec_2d]
        sec_width  = max(u_vals) - min(u_vals)
        sec_height = max(v_vals) - min(v_vals)

        if sec_width < 1.0 or sec_height < 1.0:
            return None

        # ------------------------------------------------------------------
        # Step 5: Determine shape type from edge curve lengths.
        # ------------------------------------------------------------------
        line_len = 0.0
        arc_len  = 0.0
        circle_radii: List[float] = []

        eexp = TopExp_Explorer(section_shape, TopAbs_EDGE)
        while eexp.More():
            edge = TopoDS.Edge_s(eexp.Current())
            try:
                props = GProp_GProps()
                if hasattr(BRepGProp, 'LinearProperties_s'):
                    BRepGProp.LinearProperties_s(edge, props)
                else:
                    BRepGProp.LinearProperties(edge, props)
                elen = props.Mass()
                if elen > 1e-3:
                    adaptor = BRepAdaptor_Curve(edge)
                    ct = adaptor.GetType()
                    if ct == GeomAbs_Line:
                        line_len += elen
                    elif ct == GeomAbs_Circle:
                        arc_len += elen
                        circle_radii.append(adaptor.Circle().Radius())
            except Exception:
                pass
            eexp.Next()

        total_len = line_len + arc_len
        is_circ = (total_len > 0) and (arc_len / total_len > 0.85)

        if is_circ:
            outer_d = (max(circle_radii) * 2.0) if circle_radii else max(sec_width, sec_height)
            outer_d = round(outer_d, 1)
            return {
                'shape_type': 'C',
                'width': outer_d,
                'height': outer_d,
                'outer_diam': outer_d,
                'method': 'cross_section',
            }

        # Rectangular: width >= height
        w = round(max(sec_width, sec_height), 1)
        h = round(min(sec_width, sec_height), 1)
        return {
            'shape_type': 'R',
            'width': w,
            'height': h,
            'outer_diam': 0.0,
            'method': 'cross_section',
        }

    except Exception:
        return None


def _estimate_wall_thickness(smallest_dim: float, middle_dim: float,
                             volume_ratio: float, torus_radii: List[float]) -> float:
    """
    Estimate wall thickness for hollow rectangular tubes.
    
    Estimation strategies (in priority order):
    1. From volume ratio: analytical hollow-box wall solve (preferred)
    2. From torus radii: fallback estimate from detected corner radii
    3. Default: 3mm (common thin-walled tube)
    
    Args:
        smallest_dim: Smallest bbox dimension (height)
        middle_dim: Middle bbox dimension (width)
        volume_ratio: actual_volume / bbox_volume
        torus_radii: List of corner radii
    
    Returns:
        Estimated wall thickness in mm
    """
    # Strategy 1: Analytical area-balance solve from volume ratio.
    # For a constant rectangular hollow section:
    #   fill_ratio f = A_material / (W*H) = volume_ratio
    #   A_material = W*H - (W-2t)(H-2t)
    # -> 4t² - 2(W+H)t + fWH = 0
    if 0.01 < volume_ratio < 0.98 and smallest_dim > 0 and middle_dim > 0:
        width = float(middle_dim)
        height = float(smallest_dim)
        fill_ratio = float(volume_ratio)

        discriminant = ((width + height) ** 2) - (4.0 * fill_ratio * width * height)
        if discriminant >= 0:
            thickness = ((width + height) - math.sqrt(discriminant)) / 4.0
            if 0.5 <= thickness <= (height / 2.0):
                return round(thickness, 1)

    # Strategy 2: Torus-based fallback (only when area-balance is inconclusive)
    if torus_radii:
        inner_radius = min(torus_radii)
        thickness = inner_radius * 1.5
        if 0.5 <= thickness <= smallest_dim / 2.0:
            return round(thickness, 1)

    # Strategy 3: Default fallback
    # Common thin-walled tube thicknesses: 2, 3, 4, 5mm
    return 3.0


# =============================================================================
# FALLBACK FUNCTIONS
# =============================================================================

def _create_fallback_result(dims: Tuple[float, float, float], 
                            volume: float, error: str = None) -> Dict[str, Any]:
    """
    Create fallback result when extraction fails or OCP unavailable.
    """
    smallest, middle, largest = sorted(dims)
    
    return {
        'tube_type': f"Profile_{largest:.0f}mm",
        'is_circular': False,
        'is_rectangular': False,
        'width': middle,
        'height': smallest,
        'diameter': 0.0,
        'thickness': 0.0,
        'outer_radius': 0.0,
        'inner_radius': 0.0,
        'length': largest,
        'bbox_x': largest,
        'bbox_y': middle,
        'bbox_z': smallest,
        'success': False,
        'method': 'fallback',
        'error': error
    }


# =============================================================================
# BENT PLATE CROSS-SECTION ANALYSIS
# =============================================================================

def extract_bent_plate_cross_section(solid) -> Optional[Dict[str, Any]]:
    """
    Extract bent-plate geometry via cross-section analysis.

    Designed for sheet-metal parts that are prismatic (near-constant cross-section
    along an extrusion axis), such as C-channels, U-profiles, Z-sections, etc.

    Algorithm:
        1. PCA on solid vertices → dominant axis = extrusion direction.
        2. Sample sections at 5 fractions along the extrusion axis to verify
           topology is consistent (prismatic guard).
        3. Analyse the middle section (centroid):
           - Arc edges  → bends (cylindrical faces whose axis is parallel to the
                          extrusion direction appear as circles/arcs in the section).
           - Line edges → flat plate segments.
        4. Group concentric arc pairs (inner + outer face of same bend) by centre
           proximity.  From each pair: inner_radius, thickness, bend_angle.
        5. Compute flat developed width = sum of straight segments + neutral-line
           arc lengths for each bend.

    Guard conditions (returns None if):
        - Fewer than 8 unique vertices (too simple / degenerate)
        - Extrusion length < 50 mm (too short; bbox methods are sufficient)
        - Section edge-count CV > 0.40 (non-prismatic geometry)
        - No arc segments found in middle section (flat plate, no bends)
        - No concentric arc pairs or single arcs with angle > 350° (hollow tube)
        - Thickness estimate < 0.3 mm or > 40 mm (implausible)

    Returns:
        Dict with keys:
            thickness        (mm, float)
            nr_bends         (int)
            bend_angles      (list[float], degrees, unsigned magnitude)
            inner_radii      (list[float], mm)
            bend_line_length (mm, float — extrusion length)
            flat_width       (mm, float — neutral-line developed width)
            method           ('cross_section_bent_plate')
        or None when the solid is not a valid bent prismatic plate.
    """
    if np is None or not HAS_OCP:
        return None

    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp

        # ------------------------------------------------------------------
        # Step 1: PCA to find the extrusion (length) axis.
        # ------------------------------------------------------------------
        points: List[Tuple[float, float, float]] = []
        vexp = TopExp_Explorer(solid, TopAbs_VERTEX)
        while vexp.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vexp.Current()))
            points.append((p.X(), p.Y(), p.Z()))
            vexp.Next()

        if len(points) < 8:
            return None

        pts = np.unique(np.round(np.array(points, dtype=float), 4), axis=0)
        if len(pts) < 8:
            return None

        centroid = pts.mean(axis=0)
        centered = pts - centroid
        cov = np.cov(centered.T)
        evals, evecs = np.linalg.eigh(cov)

        # Dominant eigenvector (largest eigenvalue) = extrusion direction.
        length_idx = int(np.argmax(evals))
        cross_idxs = [i for i in range(3) if i != length_idx]
        length_axis = evecs[:, length_idx]
        sec_u = evecs[:, cross_idxs[0]]
        sec_v = evecs[:, cross_idxs[1]]

        # Snap to the nearest cardinal axis when nearly axis-aligned (|dot| > 0.97).
        # This is critical: a cylinder with axis exactly along Y cut by a plane
        # whose normal is *slightly* tilted from Y produces an ELLIPSE, not a circle.
        # Snapping ensures a true perpendicular cut → clean circular arcs.
        _CARDINALS = [
            (np.array([1., 0., 0.]), np.array([0., 1., 0.]), np.array([0., 0., 1.])),
            (np.array([0., 1., 0.]), np.array([1., 0., 0.]), np.array([0., 0., 1.])),
            (np.array([0., 0., 1.]), np.array([1., 0., 0.]), np.array([0., 1., 0.])),
        ]
        _SNAP_THRESHOLD = 0.97
        for _lax, _su, _sv in _CARDINALS:
            if abs(float(length_axis @ _lax)) > _SNAP_THRESHOLD:
                _sign = 1.0 if float(length_axis @ _lax) > 0 else -1.0
                length_axis = _lax * _sign
                sec_u = _su
                sec_v = _sv
                break

        # Extrusion extent from vertex projections.
        projections = centered @ length_axis
        extrusion_length = float(projections.max() - projections.min())

        if extrusion_length < 50.0:
            return None

        nx = float(length_axis[0])
        ny = float(length_axis[1])
        nz = float(length_axis[2])

        # ------------------------------------------------------------------
        # Step 2: Consistency sampling — 5 cross-sections along the extrusion.
        # Fracs [0.2, 0.8] are "end" sections  (~20% from each tip).
        # Fracs [0.4, 0.5, 0.6] are "middle" sections.
        # We track which fracs succeed so we can later compare end vs middle
        # edge counts to detect a lip or extra bend only at the extremities.
        # ------------------------------------------------------------------
        sample_fracs = [0.2, 0.4, 0.5, 0.6, 0.8]
        _END_FRACS   = {0.2, 0.8}
        section_edge_counts: List[int] = []
        section_perimeters: List[float] = []
        # Per-zone edge counts for lip detection.
        _end_ec:    List[int] = []
        _middle_ec: List[int] = []

        for frac in sample_fracs:
            offset = (frac - 0.5) * extrusion_length
            cx = float(centroid[0]) + nx * offset
            cy = float(centroid[1]) + ny * offset
            cz = float(centroid[2]) + nz * offset
            plane = gp_Pln(gp_Pnt(cx, cy, cz), gp_Dir(nx, ny, nz))

            try:
                sec_op = BRepAlgoAPI_Section(solid, plane, False)
            except TypeError:
                sec_op = BRepAlgoAPI_Section(solid, plane)

            sec_op.Build()
            if hasattr(sec_op, 'IsDone') and not sec_op.IsDone():
                continue

            shape = sec_op.Shape()
            edge_exp = TopExp_Explorer(shape, TopAbs_EDGE)
            ec = 0
            perim = 0.0
            while edge_exp.More():
                edge = TopoDS.Edge_s(edge_exp.Current())
                props = GProp_GProps()
                if hasattr(BRepGProp, 'LinearProperties_s'):
                    BRepGProp.LinearProperties_s(edge, props)
                else:
                    BRepGProp.LinearProperties(edge, props)
                elen = props.Mass()
                if elen > 0.5:
                    ec += 1
                    perim += elen
                edge_exp.Next()

            if ec > 0:
                section_edge_counts.append(ec)
                section_perimeters.append(perim)
                if frac in _END_FRACS:
                    _end_ec.append(ec)
                else:
                    _middle_ec.append(ec)

        if len(section_edge_counts) < 3:
            return None  # Not enough valid sections

        # ------------------------------------------------------------------
        # Step 3: Topology consistency check.
        # ------------------------------------------------------------------
        ec_arr = np.array(section_edge_counts, dtype=float)
        ec_mean = float(ec_arr.mean())
        ec_cv = float(ec_arr.std() / ec_mean) if ec_mean > 0 else 1.0

        if ec_cv > 0.40:
            return None  # Non-prismatic geometry

        # Lip detection: if any end section has MORE edges than the median of
        # the middle sections, a lip or extra bend is localised at an extremity
        # and will be invisible to this cross-section method.
        _middle_median = float(np.median(_middle_ec)) if _middle_ec else ec_mean
        has_end_complexity = bool(_end_ec and max(_end_ec) > _middle_median)

        # ------------------------------------------------------------------
        # Step 4: Detailed analysis of the middle cross-section (at centroid).
        # ------------------------------------------------------------------
        cx = float(centroid[0])
        cy = float(centroid[1])
        cz = float(centroid[2])
        plane = gp_Pln(gp_Pnt(cx, cy, cz), gp_Dir(nx, ny, nz))

        try:
            sec_op = BRepAlgoAPI_Section(solid, plane, False)
        except TypeError:
            sec_op = BRepAlgoAPI_Section(solid, plane)

        sec_op.Build()
        if hasattr(sec_op, 'IsDone') and not sec_op.IsDone():
            return None

        mid_shape = sec_op.Shape()

        # ------------------------------------------------------------------
        # Step 5: Extract arc and line edges from the middle section.
        # Arc edges correspond to bends (cylindrical faces whose axis is
        # parallel to the extrusion direction).
        # Line edges correspond to flat plate portions.
        # ------------------------------------------------------------------
        arcs: List[Dict[str, Any]] = []
        lines: List[Dict[str, float]] = []

        edge_exp = TopExp_Explorer(mid_shape, TopAbs_EDGE)
        while edge_exp.More():
            edge = TopoDS.Edge_s(edge_exp.Current())
            try:
                props = GProp_GProps()
                if hasattr(BRepGProp, 'LinearProperties_s'):
                    BRepGProp.LinearProperties_s(edge, props)
                else:
                    BRepGProp.LinearProperties(edge, props)
                elen = props.Mass()

                if elen < 0.3:
                    edge_exp.Next()
                    continue

                adaptor = BRepAdaptor_Curve(edge)
                ct = adaptor.GetType()

                if ct == GeomAbs_Circle:
                    circ = adaptor.Circle()
                    center = circ.Location()
                    radius = circ.Radius()

                    # Project centre onto section-plane (2D) coordinates.
                    v = np.array([center.X(), center.Y(), center.Z()]) - centroid
                    center_u = float(v @ sec_u)
                    center_v = float(v @ sec_v)

                    # Arc angle from parameter range.
                    t1 = adaptor.FirstParameter()
                    t2 = adaptor.LastParameter()
                    angle_rad = abs(t2 - t1)
                    angle_deg = math.degrees(angle_rad)

                    arcs.append({
                        'center_u': center_u,
                        'center_v': center_v,
                        'radius': radius,
                        'angle_deg': angle_deg,
                        'arc_length': elen,
                    })

                elif ct == GeomAbs_Line:
                    lines.append({'length': elen})

            except Exception:
                pass
            edge_exp.Next()

        if not arcs:
            return None  # No bends detected

        # ------------------------------------------------------------------
        # Step 6: Group concentric arcs by centre proximity.
        # Same bend → inner face (r_small) + outer face (r_large) are concentric.
        # Grouping tolerance: 3 mm (much less than typical bend locations).
        # ------------------------------------------------------------------
        center_tol = 3.0
        groups: List[List[Dict[str, Any]]] = []

        for arc in arcs:
            placed = False
            for group in groups:
                gc_u = float(np.mean([a['center_u'] for a in group]))
                gc_v = float(np.mean([a['center_v'] for a in group]))
                dist = math.sqrt((arc['center_u'] - gc_u) ** 2 + (arc['center_v'] - gc_v) ** 2)
                if dist < center_tol:
                    group.append(arc)
                    placed = True
                    break
            if not placed:
                groups.append([arc])

        # Keep only real bends:
        # - Paired concentric arcs (inner + outer) with angle > 20°, < 350°
        # - Full circles (angle ≈ 360°) are hollow-tube cross-sections → exclude.
        bend_groups: List[List[Dict[str, Any]]] = []
        for group in groups:
            max_angle = max(a['angle_deg'] for a in group)
            if max_angle > 350.0:
                # Full circle(s) → hollow tube, not bent plate → reject entire solid
                return None
            if max_angle > 20.0:
                if len(group) >= 2:
                    bend_groups.append(group)

        if not bend_groups:
            return None  # No real bends found with concentric pairs

        # ------------------------------------------------------------------
        # Step 7: Extract per-bend parameters.
        # ------------------------------------------------------------------
        bend_angles_deg: List[float] = []
        inner_radii_mm: List[float] = []
        thickness_estimates: List[float] = []

        # Sort bend groups by position along the section (left-to-right in 2D).
        bend_groups.sort(key=lambda g: float(np.mean([a['center_u'] for a in g])))

        for group in bend_groups:
            radii = sorted(a['radius'] for a in group)
            r_inner = radii[0]
            r_outer = radii[-1]
            t_est = r_outer - r_inner

            if t_est < 0.3 or t_est > 40.0:
                continue

            thickness_estimates.append(t_est)
            inner_radii_mm.append(round(r_inner, 2))

            # Bend angle = subtended angle of the inner arc.
            inner_arc = min(group, key=lambda a: abs(a['radius'] - r_inner))
            bend_angles_deg.append(round(inner_arc['angle_deg'], 1))

        if not bend_angles_deg:
            return None

        # ------------------------------------------------------------------
        # Step 8: Compute plate thickness (median of per-bend estimates).
        # ------------------------------------------------------------------
        t_arr = np.array(thickness_estimates, dtype=float)
        if len(t_arr) == 0:
            return None

        if len(t_arr) > 1:
            t_cv = float(t_arr.std() / t_arr.mean()) if t_arr.mean() > 0 else 1.0
            if t_cv > 0.40:
                return None  # Inconsistent thickness estimates

        plate_thickness = float(np.median(t_arr))

        if plate_thickness < 0.3 or plate_thickness > 40.0:
            return None

        # ------------------------------------------------------------------
        # Step 9: Flat developed width = straight segments + neutral arcs.
        # ------------------------------------------------------------------
        flat_width = sum(l['length'] for l in lines)
        for i, group in enumerate(bend_groups):
            if i >= len(inner_radii_mm):
                continue
            r_inner = inner_radii_mm[i]
            angle_rad = math.radians(bend_angles_deg[i])
            neutral_r = r_inner + plate_thickness / 2.0
            flat_width += neutral_r * abs(angle_rad)

        flat_width = round(flat_width, 1)

        return {
            'thickness': round(plate_thickness, 2),
            'nr_bends': len(bend_angles_deg),
            'bend_angles': bend_angles_deg,
            'inner_radii': inner_radii_mm,
            'bend_line_length': round(extrusion_length, 1),
            'flat_width': flat_width,
            'method': 'cross_section_bent_plate',
            # True when an end section (first/last 20%) has more edges than the
            # middle sections → a lip or extra bend at the extremity is possible,
            # which this cross-section method cannot see.  The caller may trigger
            # FreeCAD unfold as a complementary check.
            'has_end_complexity': has_end_complexity,
        }

    except Exception:
        return None
