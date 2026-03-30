import math
import cadquery as cq
from dataclasses import dataclass
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Plane,
                          GeomAbs_Torus, GeomAbs_Sphere, GeomAbs_BezierSurface,
                          GeomAbs_BSplineSurface, GeomAbs_Line, GeomAbs_Circle)
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_FORWARD, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from manufacturing_pipeline.analysis import sheetmetal_analysis
from manufacturing_pipeline.analysis import assembly_analysis
from manufacturing_pipeline.analysis.features import hole_detection
from manufacturing_pipeline.analysis.features import component_reporting
from manufacturing_pipeline.analysis.features import manufacturing_orchestration
from manufacturing_pipeline.analysis.features import manufacturing_features
from manufacturing_pipeline.analysis.features import runtime_support
from manufacturing_pipeline.analysis.io import step_file_io
from manufacturing_pipeline.analysis.sheetmetal import orchestration as sheetmetal_orchestration
import os
import uuid
from collections import Counter
import tempfile

STEP_HEADER = b"ISO-10303-21;"


@dataclass
class HoleFeature:
    diameter: float
    depth: float
    position: tuple[float, float, float]
    axis: tuple[float, float, float]
    type: str = "unknown"
    id: str | None = None


_IsoThreadMatch = runtime_support._IsoThreadMatch
_IsoStandardsFallback = runtime_support._IsoStandardsFallback
_WerkvoorbereidingFallback = runtime_support._WerkvoorbereidingFallback
iso_standards = _IsoStandardsFallback()
werkvoorbereiding = _WerkvoorbereidingFallback()


def _normalize_step_file(filepath: str) -> str:
    return step_file_io._normalize_step_file(filepath)


def _load_step_via_xcaf(filepath):
    return step_file_io._load_step_via_xcaf(filepath)


def load_step_file(filepath):
    return step_file_io.load_step_file(filepath)

def tessellate_shape(cq_shape, deflection=0.5, angular_deflection=0.5):
    return step_file_io.tessellate_shape(
        cq_shape,
        deflection=deflection,
        angular_deflection=angular_deflection,
    )


def extract_display_edges(mesh_data, angle_threshold_deg=32.0, min_length_ratio=0.0025):
    return step_file_io.extract_display_edges(
        mesh_data,
        angle_threshold_deg=angle_threshold_deg,
        min_length_ratio=min_length_ratio,
    )


def analyze_sheet_metal(solid):
    return sheetmetal_orchestration.analyze_sheet_metal(solid)

def _analyze_part_manufacturing(cq_part, volume, part_holes):
    return component_reporting._analyze_part_manufacturing(
        cq_part,
        volume,
        part_holes,
        iso_provider=iso_standards,
    )


def analyze_components_detailed(cq_object, output_dir):
    return component_reporting.analyze_components_detailed(
        cq_object,
        output_dir,
        cq_module=cq,
        detect_holes_fn=detect_holes,
        detect_shaped_holes_fn=detect_shaped_holes,
        analyze_sheet_metal_fn=analyze_sheet_metal,
        analyze_part_manufacturing_fn=_analyze_part_manufacturing,
    )

def get_topology_stats(cq_object):
    return component_reporting.get_topology_stats(cq_object)

def classify_components(cq_object):
    return component_reporting.classify_components(cq_object)

def get_geometric_properties(cq_object):
    return component_reporting.get_geometric_properties(cq_object)

def analyze_faces(cq_object):
    return component_reporting.analyze_faces(cq_object)


def debug_hole_detection(cq_object):
    return component_reporting.debug_hole_detection(
        cq_object,
        detect_holes_fn=detect_holes,
    )


def precompute_face_properties(cq_object):
    return hole_detection.precompute_face_properties(cq_object)


def detect_holes(cq_object, filter_bores=True, is_flat_pattern=False, is_turned=None, face_data=None, return_debug=False):
    return hole_detection.detect_holes(
        cq_object,
        filter_bores=filter_bores,
        is_flat_pattern=is_flat_pattern,
        is_turned=is_turned,
        face_data=face_data,
        return_debug=return_debug,
        turned_part_detector=is_turned_part,
    )


def _classify_shaped_inner_wire(edge_count, lines, circles, radii, lengths, bbox_dims):
    dims = sorted(abs(value) for value in bbox_dims)
    dim_str = f"{dims[2]:.1f}x{dims[1]:.1f}"

    if lines == 2 and circles == 2:
        radius = sum(radii) / len(radii) if radii else 0
        line_length = max(lengths) if lengths else 0
        width = 2 * radius
        total_length = line_length + (2 * radius)
        return "Slot", f"{total_length:.1f}x{width:.1f}", "slot_like"

    if lines >= 4 and circles >= 4:
        return "Rect (R)", dim_str, "rounded_rect_like"

    if lines >= 3 and circles == 0:
        return ("Rect" if lines == 4 else "Poly"), dim_str, "polygonal"

    if edge_count >= 2:
        return "Closed contour", dim_str, "closed_contour"

    return "unknown", dim_str, "unknown"


def _sample_edge_points(edge, reverse=False):
    """Sample edge geometry into 3D points for viewer contour rendering."""
    try:
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
        c_type = curve.GetType()
        if c_type == GeomAbs_Circle:
            segments = 18
        elif c_type == GeomAbs_Line:
            segments = 2
        else:
            segments = 8

        u_start = curve.FirstParameter()
        u_end = curve.LastParameter()
        if reverse:
            u_start, u_end = u_end, u_start

        points = []
        for idx in range(segments):
            if segments == 1:
                t = u_start
            else:
                t = u_start + (u_end - u_start) * (idx / (segments - 1))
            point = curve.Value(t)
            points.append((point.X(), point.Y(), point.Z()))
        return points
    except Exception:
        return []


def _edge_end_keys(edge, tolerance):
    """Return endpoint keys/coords for edge adjacency reconstruction."""
    exp = TopExp_Explorer(edge, TopAbs_VERTEX)
    vertices = []
    while exp.More():
        vertices.append(TopoDS.Vertex_s(exp.Current()))
        exp.Next()

    if len(vertices) < 2:
        return None

    start = BRep_Tool.Pnt_s(vertices[0])
    end = BRep_Tool.Pnt_s(vertices[-1])

    start_point = (float(start.X()), float(start.Y()), float(start.Z()))
    end_point = (float(end.X()), float(end.Y()), float(end.Z()))

    def _key(point):
        return (
            round(point[0] / tolerance),
            round(point[1] / tolerance),
            round(point[2] / tolerance),
        )

    return _key(start_point), _key(end_point), start_point, end_point


def _recover_contours_from_bucket(bucket_entries, tolerance=0.05):
    """Reconstruct closed mixed contours from rejected edge fragments."""
    if not bucket_entries:
        return [], []

    from collections import defaultdict

    edge_records = []
    adjacency = defaultdict(list)

    for entry in bucket_entries:
        for edge in entry.get("edges") or []:
            end_info = _edge_end_keys(edge, tolerance)
            if end_info is None:
                continue
            start_key, end_key, start_point, end_point = end_info
            rec = {
                "edge": edge,
                "start_key": start_key,
                "end_key": end_key,
                "start_point": start_point,
                "end_point": end_point,
                "normal": entry.get("normal"),
                "source": entry.get("source", "3d"),
            }
            edge_index = len(edge_records)
            edge_records.append(rec)
            adjacency[start_key].append((edge_index, False))
            adjacency[end_key].append((edge_index, True))

    if not edge_records:
        return [], []

    used_edges = set()
    recovered = []
    debug_items = []

    for edge_index, edge_record in enumerate(edge_records):
        if edge_index in used_edges:
            continue

        chain = [(edge_index, False)]
        used_edges.add(edge_index)
        start_key = edge_record["start_key"]
        current_key = edge_record["end_key"]

        max_steps = max(32, len(edge_records) * 2)
        closed = False

        while max_steps > 0:
            max_steps -= 1
            if current_key == start_key and len(chain) >= 3:
                closed = True
                break

            next_choice = None
            for candidate_index, reverse in adjacency.get(current_key, []):
                if candidate_index in used_edges:
                    continue
                next_choice = (candidate_index, reverse)
                break

            if next_choice is None:
                break

            candidate_index, reverse = next_choice
            chain.append((candidate_index, reverse))
            used_edges.add(candidate_index)

            candidate = edge_records[candidate_index]
            current_key = candidate["start_key"] if reverse else candidate["end_key"]

        if not closed:
            continue

        contour_points = []
        edge_lengths = []
        lines = 0
        circles = 0
        radii = []
        line_lengths = []

        for chain_index, (candidate_index, reverse) in enumerate(chain):
            rec = edge_records[candidate_index]
            edge = rec["edge"]

            sampled = _sample_edge_points(edge, reverse=reverse)
            if not sampled:
                continue

            if chain_index > 0 and contour_points:
                sampled = sampled[1:]
            contour_points.extend(sampled)

            edge_props = GProp_GProps()
            BRepGProp.LinearProperties_s(edge, edge_props)
            edge_length = float(edge_props.Mass())
            edge_lengths.append(edge_length)

            curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
            c_type = curve.GetType()
            if c_type == GeomAbs_Line:
                lines += 1
                line_lengths.append(edge_length)
            elif c_type == GeomAbs_Circle:
                circles += 1
                try:
                    radii.append(float(curve.Circle().Radius()))
                except Exception:
                    pass

        if len(contour_points) < 4:
            continue

        first_point = contour_points[0]
        last_point = contour_points[-1]
        close_dist = math.sqrt(
            (first_point[0] - last_point[0]) ** 2
            + (first_point[1] - last_point[1]) ** 2
            + (first_point[2] - last_point[2]) ** 2
        )
        if close_dist > max(0.25, tolerance * 6.0):
            continue

        if edge_lengths and sum(edge_lengths) <= 1e-3:
            continue

        xs = [pt[0] for pt in contour_points]
        ys = [pt[1] for pt in contour_points]
        zs = [pt[2] for pt in contour_points]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)

        shape_type, dim_str, shape_family = _classify_shaped_inner_wire(
            len(chain), lines, circles, radii, line_lengths, (dx, dy, dz)
        )
        if shape_type == "unknown":
            shape_type = "Recovered contour"
            shape_family = "recovered_mixed"

        center = (
            sum(xs) / len(xs),
            sum(ys) / len(ys),
            sum(zs) / len(zs),
        )
        perimeter = float(sum(edge_lengths))
        normal = next((edge_records[idx]["normal"] for idx, _ in chain if edge_records[idx].get("normal") is not None), (0.0, 0.0, 1.0))
        source = next((edge_records[idx]["source"] for idx, _ in chain if edge_records[idx].get("source") is not None), "3d")

        item_id = f"hole-recovered-{len(recovered)}"
        recovered.append({
            "id": item_id,
            "type": shape_type,
            "dim": dim_str,
            "center": center,
            "normal": normal,
            "perimeter": perimeter,
            "contour_points": contour_points,
            "method": "recovery_bucket_fallback",
        })
        debug_items.append({
            "id": item_id,
            "status": "accepted",
            "type": str(shape_type).lower().replace(" ", "_"),
            "label": dim_str or shape_type,
            "reason": "Geaccepteerd via recovery bucket (gemengde contour line/arc)",
            "method": "recovery_bucket_fallback",
            "criteria": [
                {
                    "name": "method_order",
                    "value": "fallback",
                    "threshold": "face_boundary_primary_first",
                    "passed": True,
                    "note": "Pas gebruikt nadat Face Boundary geen herkenbare vorm gaf",
                },
                {
                    "name": "recovery_bucket",
                    "value": True,
                    "threshold": True,
                    "passed": True,
                    "note": "Wire walking op afgewezen contour-fragmenten",
                },
                {
                    "name": "edge_count",
                    "value": len(chain),
                    "threshold": 3,
                    "passed": len(chain) >= 3,
                    "note": "Minimale gesloten lus",
                },
                {
                    "name": "closed_loop",
                    "value": round(close_dist, 4),
                    "threshold": round(max(0.25, tolerance * 6.0), 4),
                    "passed": True,
                    "note": "Begin/eind binnen closure tolerance",
                },
                {
                    "name": "shape_family",
                    "value": shape_family,
                    "threshold": "slot/rect/poly/recovered_mixed",
                    "passed": True,
                    "note": "Recovered contour classificatie",
                },
            ],
            "position": center,
            "normal": normal,
            "size": dim_str,
            "perimeter": perimeter,
            "contour_points": contour_points,
            "source": source,
        })

    return recovered, debug_items


def detect_shaped_holes(shape, face_data=None, is_flat_pattern=False, return_debug=False):
    return hole_detection.detect_shaped_holes(
        shape,
        face_data=face_data,
        is_flat_pattern=is_flat_pattern,
        return_debug=return_debug,
    )

def deduplicate_holes(circular_holes, shaped_holes, return_debug=False):
    return hole_detection.deduplicate_holes(
        circular_holes,
        shaped_holes,
        return_debug=return_debug,
    )

def is_turned_part(cq_object):
    """
    Identify if part is lathe-machinable based on axisymmetry.
    Uses surface AREA (not face count) for accurate classification.
    """
    try:
        all_faces = cq_object.faces().vals()
        if not all_faces:
            return False

        cylindrical_area = 0.0
        planar_area = 0.0
        other_area = 0.0

        axes = []  # Collect cylinder/cone axes

        for face in all_faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            stype = surf.GetType()

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face.wrapped, props)
            area = props.Mass()

            if stype == GeomAbs_Cylinder:
                cylindrical_area += area
                axis = surf.Cylinder().Axis().Direction()
                axes.append((axis.X(), axis.Y(), axis.Z()))
            elif stype == GeomAbs_Cone:
                cylindrical_area += area  # Cones are typical of turned parts
                axis = surf.Cone().Axis().Direction()
                axes.append((axis.X(), axis.Y(), axis.Z()))
            elif stype == GeomAbs_Plane:
                planar_area += area
            else:
                other_area += area

        total_area = cylindrical_area + planar_area + other_area
        if total_area == 0:
            return False

        # Check if cylindrical/conical surfaces dominate (> 40% of surface area)
        cyl_ratio = cylindrical_area / total_area
        if cyl_ratio < 0.40:
            return False

        # Check if cylinder axes are mostly aligned (common lathe axis)
        if len(axes) < 2:
            return cyl_ratio > 0.5  # If mostly cylindrical, probably turned

        # Check axis alignment
        ref_axis = axes[0]
        aligned_count = 0
        for axis in axes:
            dot = abs(ref_axis[0]*axis[0] + ref_axis[1]*axis[1] + ref_axis[2]*axis[2])
            if dot > 0.95:  # Nearly parallel
                aligned_count += 1

        # If most cylinders are aligned, it's a turned part
        alignment_ratio = aligned_count / len(axes)
        return alignment_ratio > 0.7

    except Exception:
        return False


# =============================================================================
# Advanced Manufacturing Analysis Functions
# =============================================================================

def detect_threads(cq_object, tolerance=0.15):
    return manufacturing_features.detect_threads(
        cq_object,
        detect_holes_fn=detect_holes,
        iso_provider=iso_standards,
        tolerance=tolerance,
    )


def detect_shafts(cq_object):
    return manufacturing_features.detect_shafts(
        cq_object,
        iso_provider=iso_standards,
    )


def analyze_chamfers_and_fillets(cq_object):
    return manufacturing_features.analyze_chamfers_and_fillets(
        cq_object,
        iso_provider=iso_standards,
    )


def analyze_manufacturing_requirements(cq_object, face_analysis=None):
    return manufacturing_orchestration.analyze_manufacturing_requirements(
        cq_object,
        analyze_faces_fn=analyze_faces,
        get_geometric_properties_fn=get_geometric_properties,
        is_turned_part_fn=is_turned_part,
        iso_provider=iso_standards,
        face_analysis=face_analysis,
    )


def calculate_mass_properties(cq_object, material_key="steel_s235"):
    return manufacturing_orchestration.calculate_mass_properties(
        cq_object,
        get_geometric_properties_fn=get_geometric_properties,
        iso_provider=iso_standards,
        material_key=material_key,
    )


def analyze_holes_with_fits(cq_object):
    return manufacturing_orchestration.analyze_holes_with_fits(
        cq_object,
        detect_holes_fn=detect_holes,
        iso_provider=iso_standards,
    )


def generate_manufacturing_summary(cq_object, output_dir=None):
    return manufacturing_orchestration.generate_manufacturing_summary(
        cq_object,
        analyze_faces_fn=analyze_faces,
        get_geometric_properties_fn=get_geometric_properties,
        get_topology_stats_fn=get_topology_stats,
        analyze_manufacturing_requirements_fn=analyze_manufacturing_requirements,
        analyze_holes_with_fits_fn=analyze_holes_with_fits,
        detect_threads_fn=detect_threads,
        analyze_chamfers_and_fillets_fn=analyze_chamfers_and_fillets,
        calculate_mass_properties_fn=calculate_mass_properties,
        output_dir=output_dir,
    )


# =============================================================================
# WERKVOORBEREIDING FUNCTIONS
# =============================================================================

def generate_werkvoorbereiding(
    cq_object,
    material: str = "steel_s235",
    quantity: int = 1,
    surface_treatment: str = None,
    hourly_rates_config: dict = None,
    material_prices_config: dict = None
):
    return manufacturing_orchestration.generate_werkvoorbereiding(
        cq_object,
        get_geometric_properties_fn=get_geometric_properties,
        analyze_faces_fn=analyze_faces,
        detect_holes_fn=detect_holes,
        detect_threads_fn=detect_threads,
        analyze_chamfers_and_fillets_fn=analyze_chamfers_and_fillets,
        is_turned_part_fn=is_turned_part,
        werkvoorbereiding_provider=werkvoorbereiding,
        material=material,
        quantity=quantity,
        surface_treatment=surface_treatment,
        hourly_rates_config=hourly_rates_config,
        material_prices_config=material_prices_config,
    )


def analyze_sheetmetal(cq_object, thickness: float = None, material: str = "steel_s235"):
    return manufacturing_orchestration.analyze_sheetmetal(
        cq_object,
        analyze_sheet_metal_fn=analyze_sheet_metal,
        sheetmetal_analysis_module=sheetmetal_analysis,
        thickness=thickness,
        material=material,
    )


# =============================================================================
# ASSEMBLY ANALYSIS FUNCTIONS
# =============================================================================

def analyze_assembly_bom(cq_object, assembly_name: str = "Assembly", material: str = "steel_s235", step_file_path: str = None):
    """
    Analyze a STEP assembly and generate Bill of Materials (BOM).

    Includes:
    - Hierarchical BOM with part counting
    - Fastener identification (bolts, nuts, washers)
    - Mass calculation per material
    - Cost estimation
    - Sub-assembly detection

    Args:
        cq_object: CadQuery workplane or compound
        assembly_name: Name for the assembly
        material: Default material for cost calculation
        step_file_path: Path to STEP file for accurate assembly structure parsing

    Returns:
        Dict with complete assembly/BOM analysis
    """
    return manufacturing_orchestration.analyze_assembly_bom(
        cq_object,
        assembly_analysis_module=assembly_analysis,
        assembly_name=assembly_name,
        material=material,
        step_file_path=step_file_path,
    )


# Canonical ownership for STEP loading and display-mesh helpers now lives in
# analysis.io.step_file_io. Keep legacy names here for compatibility while
# later refactors remove the duplicated local implementations above.
STEP_HEADER = step_file_io.STEP_HEADER
_normalize_step_file = step_file_io._normalize_step_file
_load_step_via_xcaf = step_file_io._load_step_via_xcaf
load_step_file = step_file_io.load_step_file
tessellate_shape = step_file_io.tessellate_shape
extract_display_edges = step_file_io.extract_display_edges

# Canonical ownership for hole and shaped-contour detection now lives in
# analysis.features.hole_detection. Keep legacy names here for compatibility.
HoleFeature = hole_detection.HoleFeature
precompute_face_properties = hole_detection.precompute_face_properties
_classify_shaped_inner_wire = hole_detection._classify_shaped_inner_wire
_sample_edge_points = hole_detection._sample_edge_points
_edge_end_keys = hole_detection._edge_end_keys
_recover_contours_from_bucket = hole_detection._recover_contours_from_bucket


def detect_holes(cq_object, filter_bores=True, is_flat_pattern=False, is_turned=None, face_data=None, return_debug=False):
    return hole_detection.detect_holes(
        cq_object,
        filter_bores=filter_bores,
        is_flat_pattern=is_flat_pattern,
        is_turned=is_turned,
        face_data=face_data,
        return_debug=return_debug,
        turned_part_detector=is_turned_part,
    )


def detect_shaped_holes(shape, face_data=None, is_flat_pattern=False, return_debug=False):
    return hole_detection.detect_shaped_holes(
        shape,
        face_data=face_data,
        is_flat_pattern=is_flat_pattern,
        return_debug=return_debug,
    )


def deduplicate_holes(circular_holes, shaped_holes, return_debug=False):
    return hole_detection.deduplicate_holes(
        circular_holes,
        shaped_holes,
        return_debug=return_debug,
    )
