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
from manufacturing_pipeline.analysis.features import manufacturing_features
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


class _IsoThreadMatch:
    def __init__(self, designation: str = "", pitch: float = 0.0, major_diameter: float = 0.0):
        self.designation = designation
        self.pitch = pitch
        self.major_diameter = major_diameter


class _IsoStandardsFallback:
    """Minimal compatibility shim after removing analysis/iso_standards.py."""

    @staticmethod
    def analyze_hole_fit(_diameter):
        recommendation = {"fit": "N/A", "description": "ISO disabled"}
        return {
            "primary_recommendation": recommendation,
            "alternative_recommendation": recommendation,
            "tolerances": {},
        }

    @staticmethod
    def identify_thread_from_diameter(_diameter, _tolerance=0.15):
        return []

    @staticmethod
    def get_tap_drill_size(_designation):
        return None

    @staticmethod
    def get_nearest_standard_fillet(value):
        return value

    @staticmethod
    def get_nearest_standard_chamfer(value):
        return value

    @staticmethod
    def recommend_iso2768_class(_part_type, _complexity):
        return "m", "K"

    @staticmethod
    def get_iso2768_linear_tolerance(_dimension, _linear_class):
        return 0.0

    @staticmethod
    def analyze_surface_requirements(_face_analysis):
        return {
            "default_ra": 3.2,
            "general_recommendation": "ISO disabled",
            "by_face_type": [],
        }

    @staticmethod
    def calculate_mass(volume_mm3, material_key="steel_s235"):
        density = 7.85e-6 if material_key.startswith("steel") else 2.70e-6
        mass_kg = float(volume_mm3 or 0.0) * density
        return {
            "material": material_key,
            "mass_kg": mass_kg,
            "density_kg_m3": density * 1e9,
        }

    @staticmethod
    def get_all_materials_by_category():
        return {"steel": ["steel_s235"], "aluminum": ["alu_6061"]}


iso_standards = _IsoStandardsFallback()


class _WerkvoorbereidingFallback:
    @staticmethod
    def calculate_cost_estimate(*_args, **_kwargs):
        return {"estimated_total_cost": None, "currency": "EUR"}

    @staticmethod
    def generate_tool_list(*_args, **_kwargs):
        return []

    @staticmethod
    def classify_outsourcing(*_args, **_kwargs):
        return {"recommended": False, "reason": "Werkvoorbereiding disabled"}

    @staticmethod
    def recommend_surface_treatment(*_args, **_kwargs):
        return []

    @staticmethod
    def generate_purchase_spec(*_args, **_kwargs):
        return {"summary": "Werkvoorbereiding disabled"}


werkvoorbereiding = _WerkvoorbereidingFallback()


def _normalize_step_file(filepath: str) -> str:
    """Return a sanitized STEP path when the file has junk before the STEP header."""
    with open(filepath, "rb") as handle:
        data = handle.read()

    if data.startswith(STEP_HEADER):
        return filepath

    header_index = data.find(STEP_HEADER)
    if header_index <= 0:
        return filepath

    suffix = os.path.splitext(filepath)[1] or ".stp"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data[header_index:])
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def _load_step_via_xcaf(filepath):
    """Try to build a CadQuery object from XCAF solids; return None on failure.

    Runs the XCAF reader in a subprocess to guard against segfaults in the
    OCP C++ layer on complex/corrupt STEP files. The subprocess writes solid
    count to stdout; if it crashes we fall back to CadQuery import.
    """
    import subprocess
    import sys

    # Quick pre-check: run XCAF in a subprocess to see if it crashes
    probe_script = f'''
import sys
try:
    sys.path.insert(0, "{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
    from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
    result = xcaf_match_solids_to_names("{filepath}")
    if result is None:
        print("0")
    else:
        solids, names = result
        print(str(len(solids)))
except Exception as e:
    print("0")
'''
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe_script],
            capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            # Subprocess crashed (segfault = 139, etc.)
            print(f"  XCAF probe crashed (exit {proc.returncode}), using CadQuery fallback")
            return None
        solid_count = int(proc.stdout.strip() or "0")
        if solid_count == 0:
            return None
    except subprocess.TimeoutExpired:
        print("  XCAF probe timeout (>60s), using CadQuery fallback")
        return None
    except Exception:
        return None

    # Probe succeeded — safe to load in-process
    try:
        from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names

        result = xcaf_match_solids_to_names(filepath)
        if result is None:
            return None

        solids, solid_names = result
        if not solids:
            return None

        cq_solids = []
        for solid in solids:
            cq_solids.append(cq.Shape.cast(solid))

        if len(cq_solids) == 1:
            wp = cq.Workplane(obj=cq_solids[0])
        else:
            compound = cq.Compound.makeCompound(cq_solids)
            wp = cq.Workplane(obj=compound)

        try:
            setattr(wp, "_xcaf_solid_names", list(solid_names))
            setattr(wp, "_xcaf_source_step", str(filepath))
        except Exception:
            pass

        return wp
    except Exception:
        return None


def load_step_file(filepath):
    """
    Load and parse a STEP file and return a CadQuery Workplane/Shape.

    Priority:
    1) XCAF reader (with subprocess probe to catch segfaults)
    2) CadQuery importer fallback
    """
    if not filepath:
        raise ValueError("STEP filepath is required")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    normalized_path = _normalize_step_file(filepath)

    xcaf_shape = _load_step_via_xcaf(normalized_path)
    if xcaf_shape is not None:
        return xcaf_shape

    # CadQuery importer fallback (existing behavior)
    return cq.importers.importStep(normalized_path)

def tessellate_shape(cq_shape, deflection=0.5, angular_deflection=0.5):
    """Tessellate a CadQuery shape into triangle mesh data for 3D rendering.

    Args:
        cq_shape: CadQuery Workplane or Shape object.
        deflection: Linear deflection for mesh quality (smaller = finer).
        angular_deflection: Angular deflection in radians.

    Returns:
        dict with flat arrays: {"vertices": [...], "indices": [...], "normals": [...]}
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location

    # Unwrap CadQuery object to OCP shape
    if hasattr(cq_shape, 'val'):
        shape = cq_shape.val()
    elif hasattr(cq_shape, 'wrapped'):
        shape = cq_shape
    else:
        shape = cq_shape

    ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape

    # Tessellate
    mesh = BRepMesh_IncrementalMesh(ocp_shape, deflection, False, angular_deflection, False)
    mesh.Perform()

    vertices = []
    indices = []
    normals = []
    vertex_offset = 0

    explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is not None:
            transform = location.Transformation()
            nb_nodes = triangulation.NbNodes()
            nb_triangles = triangulation.NbTriangles()

            # Extract vertices (apply location transform)
            for i in range(1, nb_nodes + 1):
                pt = triangulation.Node(i)
                pt.Transform(transform)
                vertices.extend([pt.X(), pt.Y(), pt.Z()])

            # Extract normals if available, otherwise use face normal
            has_normals = triangulation.HasNormals()
            reversed_face = (face.Orientation() == TopAbs_REVERSED)

            if has_normals:
                for i in range(1, nb_nodes + 1):
                    n = triangulation.Normal(i)
                    nx, ny, nz = n.X(), n.Y(), n.Z()
                    if reversed_face:
                        nx, ny, nz = -nx, -ny, -nz
                    normals.extend([nx, ny, nz])
            else:
                # Approximate: use (0,0,0) placeholder, will be computed client-side
                for _ in range(nb_nodes):
                    normals.extend([0.0, 0.0, 0.0])

            # Extract triangle indices (adjust for vertex offset and face orientation)
            for t in range(1, nb_triangles + 1):
                tri = triangulation.Triangle(t)
                v1 = tri.Value(1) - 1 + vertex_offset
                v2 = tri.Value(2) - 1 + vertex_offset
                v3 = tri.Value(3) - 1 + vertex_offset
                if reversed_face:
                    indices.extend([v1, v3, v2])  # Flip winding
                else:
                    indices.extend([v1, v2, v3])

            vertex_offset += nb_nodes

        explorer.Next()

    return {
        "vertices": vertices,
        "indices": indices,
        "normals": normals,
    }


def extract_display_edges(mesh_data, angle_threshold_deg=32.0, min_length_ratio=0.0025):
    """Extract a cleaner set of display edges from tessellated mesh data.

    Keeps boundary edges and sharp feature edges while dropping coplanar
    tessellation diagonals that create noisy wireframes in the viewer.
    """
    vertices = mesh_data.get("vertices") or []
    indices = mesh_data.get("indices") or []
    if len(vertices) < 6 or len(indices) < 3:
        return []

    points = [
        (float(vertices[i]), float(vertices[i + 1]), float(vertices[i + 2]))
        for i in range(0, len(vertices), 3)
    ]

    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    min_z = min(point[2] for point in points)
    max_x = max(point[0] for point in points)
    max_y = max(point[1] for point in points)
    max_z = max(point[2] for point in points)
    diagonal = math.sqrt(
        (max_x - min_x) ** 2 +
        (max_y - min_y) ** 2 +
        (max_z - min_z) ** 2
    )
    min_length = max(diagonal * min_length_ratio, 0.75)
    sharp_threshold = math.cos(math.radians(angle_threshold_deg))

    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def _cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def _normalize(v):
        length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if length <= 1e-9:
            return None
        return (v[0] / length, v[1] / length, v[2] / length)

    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    edge_faces = {}
    for tri_index in range(0, len(indices), 3):
        i0, i1, i2 = indices[tri_index:tri_index + 3]
        if i0 >= len(points) or i1 >= len(points) or i2 >= len(points):
            continue

        p0, p1, p2 = points[i0], points[i1], points[i2]
        normal = _normalize(_cross(_sub(p1, p0), _sub(p2, p0)))
        if normal is None:
            continue

        for start, end in ((i0, i1), (i1, i2), (i2, i0)):
            key = (start, end) if start < end else (end, start)
            edge_faces.setdefault(key, []).append(normal)

    display_edges = []
    for (start, end), normals_for_edge in edge_faces.items():
        p0 = points[start]
        p1 = points[end]
        edge_length = math.sqrt(
            (p1[0] - p0[0]) ** 2 +
            (p1[1] - p0[1]) ** 2 +
            (p1[2] - p0[2]) ** 2
        )

        include_edge = False
        if len(normals_for_edge) == 1:
            include_edge = edge_length >= (min_length * 0.35)
        else:
            for left_index in range(len(normals_for_edge)):
                for right_index in range(left_index + 1, len(normals_for_edge)):
                    if _dot(normals_for_edge[left_index], normals_for_edge[right_index]) < sharp_threshold:
                        include_edge = edge_length >= min_length
                        break
                if include_edge:
                    break

        if include_edge:
            display_edges.extend([*p0, *p1])

    return display_edges


def analyze_sheet_metal(solid):
    """
    Analyze a solid to determine if it's a sheet metal part.
    Returns thickness, bend count, and standard compliance.
    """
    # 1. Get all faces
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    faces = []
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()

    planar_faces = []
    cylindrical_faces = []
    
    total_area = 0.0
    
    for f in faces:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, props)
        area = props.Mass()
        total_area += area
        
        surf = BRepAdaptor_Surface(f, True)
        stype = surf.GetType()
        if stype == GeomAbs_Plane:
            planar_faces.append((f, area))
        elif stype == GeomAbs_Cylinder:
            cylindrical_faces.append((f, area, surf.Cylinder().Radius()))

    # 2. Detect Thickness (Parallel Planar Faces)
    thickness_counts = {} # thickness -> area
    
    planes = []
    for f, area in planar_faces:
        surf = BRepAdaptor_Surface(f, True)
        pln = surf.Plane()
        ax = pln.Axis().Direction()
        normal = (ax.X(), ax.Y(), ax.Z())
        loc = pln.Location()
        d_val = -(normal[0]*loc.X() + normal[1]*loc.Y() + normal[2]*loc.Z())
        planes.append({"normal": normal, "d": d_val, "area": area})

    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            p1 = planes[i]
            p2 = planes[j]
            dot = p1["normal"][0]*p2["normal"][0] + p1["normal"][1]*p2["normal"][1] + p1["normal"][2]*p2["normal"][2]
            
            if abs(dot + 1.0) < 0.01: # Opposite normals
                dist = abs(p1["d"] + p2["d"])
                if dist > 0.1: 
                    t_val = round(dist, 2)
                    if t_val not in thickness_counts: thickness_counts[t_val] = 0
                    thickness_counts[t_val] += min(p1["area"], p2["area"])
    
    # DEBUG: Print thickness counts
    # print(f"DEBUG: Thickness counts: {thickness_counts}")

    detected_thickness = 0.0
    is_sheet = False
    
    if thickness_counts:
        # Prefer reasonable sheet thicknesses (< 25mm)
        sheet_candidates = {t: area for t, area in thickness_counts.items() if t < 25.0}
        
        if sheet_candidates:
            best_t = max(sheet_candidates, key=sheet_candidates.get)
        else:
            best_t = max(thickness_counts, key=thickness_counts.get)
            
        coverage = thickness_counts[best_t] * 2 
        # Lower threshold to 0.1 to detect complex bent parts
        if coverage / total_area > 0.1: 
            detected_thickness = best_t
            is_sheet = True

    # 3. Detect Bends
    # Use the centralized logic in sheetmetal_analysis
    is_closed_profile = False
    counter_bend_count = 0
    try:
        # Pass detected_thickness only if it's valid (>0), otherwise None to let analysis detect it
        t_arg = detected_thickness if detected_thickness > 0 else None
        sm_result = sheetmetal_analysis.analyze_sheet_metal_geometry(solid, thickness=t_arg)

        # Use bend_count_for_erp for ERP/werkvoorbereiding purposes
        # This is 0 for closed profiles (koker) since they're purchased as profile
        bend_count = sm_result.get("bend_count_for_erp", sm_result.get("bend_count", 0))
        is_closed_profile = sm_result.get("is_closed_profile", False)
        counter_bend_count = sm_result.get("counter_bend_count", 0)

        # If we didn't detect thickness before, but sheetmetal analysis did:
        if detected_thickness == 0.0 and sm_result.get("thickness"):
            detected_thickness = sm_result.get("thickness")
            is_sheet = True

    except Exception as e:
        print(f"Error in sheetmetal analysis: {e}")
        bend_count = 0

    # 4. ISO Standard Check
    iso_thicknesses = [0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
    is_standard = False
    if is_sheet:
        for iso_t in iso_thicknesses:
            if abs(detected_thickness - iso_t) < 0.05:
                is_standard = True
                break

    return {
        "is_sheet_metal": is_sheet,
        "thickness": detected_thickness,
        "bend_count": bend_count,
        "counter_bend_count": counter_bend_count,
        "is_closed_profile": is_closed_profile,
        "is_standard": is_standard
    }

def _analyze_part_manufacturing(cq_part, volume, part_holes):
    """
    Analyze ISO manufacturing requirements for a single part.
    Returns per-part: holes with fits, threads, chamfers/fillets, mass estimates.
    """
    manufacturing = {
        "holes_with_fits": [],
        "threads": [],
        "chamfers_fillets": None,
        "mass_estimates": None,
    }

    # Holes with fits (ISO 286)
    if part_holes:
        diameter_groups = {}
        for hole in part_holes:
            d_rounded = round(hole.diameter, 1)
            if d_rounded not in diameter_groups:
                diameter_groups[d_rounded] = []
            diameter_groups[d_rounded].append(hole)

        for diameter, hole_list in diameter_groups.items():
            fit_analysis = iso_standards.analyze_hole_fit(diameter)
            thread_matches = iso_standards.identify_thread_from_diameter(diameter, 0.15)
            thread_info = None
            if thread_matches:
                best = thread_matches[0]
                thread_info = {
                    "designation": best.designation,
                    "pitch": best.pitch,
                    "tap_drill": iso_standards.get_tap_drill_size(best.designation),
                }
                manufacturing["threads"].append({
                    "diameter": diameter,
                    "thread_designation": best.designation,
                    "pitch": best.pitch,
                    "tap_drill": iso_standards.get_tap_drill_size(best.designation),
                    "count": len(hole_list),
                })

            manufacturing["holes_with_fits"].append({
                "diameter": diameter,
                "count": len(hole_list),
                "fit_recommendation": fit_analysis["primary_recommendation"],
                "tolerances": fit_analysis["tolerances"],
                "possible_thread": thread_info,
            })

        manufacturing["holes_with_fits"].sort(key=lambda x: x["diameter"])

    # Chamfers and fillets (ISO 13715)
    try:
        all_faces = cq_part.faces().vals()
        chamfers = []
        fillets = []

        for face in all_faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            stype = surf.GetType()

            if stype == GeomAbs_Cone:
                cone = surf.Cone()
                half_angle = cone.SemiAngle()
                angle_deg = math.degrees(half_angle)
                if 40 <= angle_deg <= 50:
                    ref_radius = cone.RefRadius()
                    chamfers.append(round(ref_radius * 0.3, 2))

            elif stype == GeomAbs_Torus:
                torus = surf.Torus()
                minor_radius = torus.MinorRadius()
                major_radius = torus.MajorRadius()
                if minor_radius < major_radius * 0.5 and minor_radius < 20:
                    fillets.append(round(minor_radius, 2))

        avg_chamfer = sum(chamfers) / len(chamfers) if chamfers else 0
        avg_fillet = sum(fillets) / len(fillets) if fillets else 0

        manufacturing["chamfers_fillets"] = {
            "chamfer_count": len(chamfers),
            "chamfer_avg": round(avg_chamfer, 2),
            "fillet_count": len(fillets),
            "fillet_avg": round(avg_fillet, 2),
        }
    except Exception:
        manufacturing["chamfers_fillets"] = {
            "chamfer_count": 0, "chamfer_avg": 0,
            "fillet_count": 0, "fillet_avg": 0
        }

    # Mass estimates (EN 10025/573)
    volume_m3 = volume / 1e9  # mm³ to m³
    manufacturing["mass_estimates"] = {
        "steel_s235": round(volume_m3 * 7850, 3),  # kg
        "alu_6061": round(volume_m3 * 2700, 3),    # kg
    }

    return manufacturing


def analyze_components_detailed(cq_object, output_dir):
    """
    Analyze components, group identical parts, and generate 2D thumbnails.
    Returns a list of unique parts with counts and properties.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    shape = cq_object.val().wrapped
    unique_parts = {}
    
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solid = exp.Current()
        
        # Calculate properties for identification
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        volume = props.Mass()
        
        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        
        # Create a signature for grouping (rounded to 2 decimals)
        sig = (round(volume, 2), round(dims[0], 2), round(dims[1], 2), round(dims[2], 2))
        
        if sig not in unique_parts:
            # New unique part found
            part_id = str(uuid.uuid4())[:8]
            image_filename = f"part_{part_id}.svg"
            image_path = os.path.join(output_dir, image_filename)
            
            # Convert back to CQ object for export
            cq_solid = cq.Shape.cast(solid)
            
            # Detect holes for this part
            cq_wp = cq.Workplane(obj=cq_solid)
            part_holes = detect_holes(cq_wp)
            hole_summary = "None"
            if part_holes:
                from collections import Counter
                diams = [round(h.diameter, 1) for h in part_holes]
                counts = Counter(diams)
                summary_parts = []
                for d, c in counts.items():
                    summary_parts.append(f"{c}x Ø{d}mm")
                hole_summary = ", ".join(summary_parts)
            
            # Sheet Metal Analysis
            sm_data = analyze_sheet_metal(solid)
            
            # Export SVG (Isometric view)
            try:
                cq.exporters.export(
                    cq_wp,
                    image_path,
                    opt={
                        "width": 200,
                        "height": 200,
                        "marginLeft": 5,
                        "marginTop": 5,
                        "showAxes": False,
                        "projectionDir": (1, 1, 1),
                        "strokeWidth": 0.5,
                        "strokeColor": (0, 0, 0),
                        "hiddenColor": (100, 100, 100),
                        "showHidden": True
                    }
                )
            except Exception as e:
                print(f"Error exporting image for part {part_id}: {e}")
                image_path = None

            # Classify
            classification = "Unknown"
            bbox_vol = dims[0] * dims[1] * dims[2] if dims[0] > 0 else 1.0
            
            if sm_data["is_sheet_metal"]:
                classification = "Sheet Metal"
                if sm_data["bend_count"] > 0:
                    classification += " (Bent)"
            elif volume < 1000:
                if dims[2] / dims[1] > 3: classification = "Fastener (Bolt/Screw/Pin)"
                elif dims[0] < dims[1] * 0.2: classification = "Washer/Spacer"
                else: classification = "Small Component"
            else:
                aspect_ratio = dims[2] / dims[1]
                flatness = dims[0] / dims[1]
                if flatness < 0.1: classification = "Plate/Sheet"
                elif aspect_ratio > 5: classification = "Shaft/Bar"
                elif volume / bbox_vol > 0.5: classification = "Block/Housing"
                else: classification = "Complex Part"

            # Per-part ISO manufacturing analysis
            part_holes = detect_holes(cq_wp)
            shaped_holes = detect_shaped_holes(cq_wp)
            
            part_manufacturing = _analyze_part_manufacturing(cq_wp, volume, part_holes)

            # Production Data (Dutch format as requested)
            # dims is sorted ascending: [min, mid, max]
            length = dims[2]
            width = dims[1]
            thickness = dims[0]
            
            # Refine thickness for sheet metal
            if sm_data["is_sheet_metal"]:
                thickness = sm_data["thickness"]
                form = "Plaat"
            elif "Shaft" in classification or "Bar" in classification:
                form = "Profiel"
            else:
                form = "Overig"

            production_data = {
                "CalcID": part_id,
                "ArtikelNr": f"ART-{part_id}", 
                "Aantal": 1, 
                "Vorm": form,
                "Lengte": round(length, 2),
                "Breedte": round(width, 2),
                "Dikte": round(thickness, 2),
                "Hoogte": round(dims[0], 2), 
                "Snijgaten": len(part_holes) + len(shaped_holes),
                "DiaSnijgat": sorted([round(h.diameter, 1) for h in part_holes] + [h["dim"] for h in shaped_holes], key=lambda x: str(x)),
                "ZetAantal": sm_data["bend_count"],
                "Aantaltegenzet": sm_data.get("counter_bend_count", 0)
            }

            unique_parts[sig] = {
                "id": part_id,
                "count": 1,
                "volume": volume,
                "dimensions": dims,
                "classification": classification,
                "image_path": image_path,
                "hole_summary": hole_summary,
                "holes": [{"diameter": h.diameter, "depth": h.depth} for h in part_holes],  # Add actual hole data
                "sheet_metal": sm_data,
                "manufacturing": part_manufacturing,
                "production_data": production_data
            }
        else:
            # Increment count for existing part
            unique_parts[sig]["count"] += 1
            unique_parts[sig]["production_data"]["Aantal"] += 1
            
        exp.Next()
        
    return list(unique_parts.values())

def get_topology_stats(cq_object):
    """
    Count topological entities (Solids, Shells, Faces, Edges, Vertices).
    """
    shape = cq_object.val().wrapped
    stats = {
        "solids": 0,
        "shells": 0,
        "faces": 0,
        "edges": 0,
        "vertices": 0
    }
    
    for entity_type, key in [
        (TopAbs_SOLID, "solids"),
        (TopAbs_SHELL, "shells"),
        (TopAbs_FACE, "faces"),
        (TopAbs_EDGE, "edges"),
        (TopAbs_VERTEX, "vertices")
    ]:
        exp = TopExp_Explorer(shape, entity_type)
        while exp.More():
            stats[key] += 1
            exp.Next()
            
    return stats

def classify_components(cq_object):
    """
    Iterate through solids and classify them based on geometric heuristics.
    """
    shape = cq_object.val().wrapped
    classification = {
        "Fastener (Bolt/Screw/Pin)": 0,
        "Washer/Spacer": 0,
        "Plate/Sheet": 0,
        "Shaft/Bar": 0,
        "Block/Housing": 0,
        "Complex/Other": 0
    }
    
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solid = exp.Current()
        
        # Calculate properties for this solid
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        volume = props.Mass()
        
        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        bbox_vol = dims[0] * dims[1] * dims[2] if dims[0] > 0 else 1.0
        
        # Heuristics
        if volume < 1000: # Small volume (mm^3) -> likely fastener/washer
            if dims[2] / dims[1] > 3: # Long and thin -> Pin/Screw
                classification["Fastener (Bolt/Screw/Pin)"] += 1
            elif dims[0] < dims[1] * 0.2: # Very flat -> Washer
                classification["Washer/Spacer"] += 1
            else:
                classification["Fastener (Bolt/Screw/Pin)"] += 1
        else:
            # Larger parts
            aspect_ratio = dims[2] / dims[1]
            flatness = dims[0] / dims[1]
            
            if flatness < 0.1: # Very flat -> Plate
                classification["Plate/Sheet"] += 1
            elif aspect_ratio > 5: # Long -> Shaft
                classification["Shaft/Bar"] += 1
            elif volume / bbox_vol > 0.5: # Boxy -> Block
                classification["Block/Housing"] += 1
            else:
                classification["Complex/Other"] += 1
                
        exp.Next()
        
    return classification

def get_geometric_properties(cq_object):
    """
    Calculate basic geometric properties: Bounding Box, Volume, Surface Area.
    """
    shape = cq_object.val().wrapped
    
    # Mass Properties (Volume, Area, Center of Mass)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume = props.Mass()
    center_of_mass = props.CentreOfMass()
    
    BRepGProp.SurfaceProperties_s(shape, props)
    surface_area = props.Mass()
    
    # Bounding Box
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    
    return {
        "volume": volume,
        "surface_area": surface_area,
        "center_of_mass": (center_of_mass.X(), center_of_mass.Y(), center_of_mass.Z()),
        "bounding_box": {
            "min": (xmin, ymin, zmin),
            "max": (xmax, ymax, zmax),
            "dimensions": (xmax - xmin, ymax - ymin, zmax - zmin)
        }
    }

def analyze_faces(cq_object):
    """
    Classify faces by geometry type to estimate manufacturing complexity.
    """
    counts = {
        "Plane": 0,
        "Cylinder": 0,
        "Cone": 0,
        "Sphere": 0,
        "Torus": 0,
        "Bezier": 0,
        "BSpline": 0,
        "Other": 0
    }
    
    all_faces = cq_object.faces().vals()
    
    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()
        
        if stype == GeomAbs_Plane:
            counts["Plane"] += 1
        elif stype == GeomAbs_Cylinder:
            counts["Cylinder"] += 1
        elif stype == GeomAbs_Cone:
            counts["Cone"] += 1
        elif stype == GeomAbs_Sphere:
            counts["Sphere"] += 1
        elif stype == GeomAbs_Torus:
            counts["Torus"] += 1
        elif stype == GeomAbs_BezierSurface:
            counts["Bezier"] += 1
        elif stype == GeomAbs_BSplineSurface:
            counts["BSpline"] += 1
        else:
            counts["Other"] += 1
            
    return counts


def debug_hole_detection(cq_object):
    """
    Debug function to analyze why holes may not be detected.
    Returns detailed info about all cylindrical faces.
    """
    debug_info = {
        "total_faces": 0,
        "cylindrical_faces": [],
        "rejected_faces": [],
        "candidates": [],
        "final_holes": []
    }

    all_faces = cq_object.faces().vals()
    debug_info["total_faces"] = len(all_faces)

    for i, face in enumerate(all_faces):
        surf = BRepAdaptor_Surface(face.wrapped, True)
        surf_type = surf.GetType()

        if surf_type == GeomAbs_Cylinder:
            cylinder = surf.Cylinder()
            radius = cylinder.Radius()
            orientation = face.wrapped.Orientation()

            # Get angular span
            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            face_info = {
                "face_index": i,
                "diameter": round(radius * 2, 2),
                "orientation": "REVERSED" if orientation == TopAbs_REVERSED else "FORWARD",
                "angle_deg": round(angle_deg, 1),
                "is_internal": orientation == TopAbs_REVERSED
            }

            debug_info["cylindrical_faces"].append(face_info)

            if orientation != TopAbs_REVERSED:
                debug_info["rejected_faces"].append({
                    **face_info,
                    "reason": "Not REVERSED orientation (external cylinder/boss)"
                })
            else:
                debug_info["candidates"].append(face_info)

    # Run actual detection
    holes = detect_holes(cq_object)
    debug_info["final_holes"] = [
        {"diameter": h.diameter, "depth": h.depth, "position": h.position}
        for h in holes
    ]

    return debug_info


def precompute_face_properties(cq_object):
    """
    Pre-compute face properties in a single pass over all faces.
    Extracts primitive values (floats/tuples) to avoid OCP object lifetime issues.

    Returns:
        list of dicts, each with:
        - face: the OCP face object (for operations that need it)
        - type: str ('cylinder', 'plane', 'cone', 'sphere', 'torus', 'other')
        - area: float
        - center: (x, y, z) tuple
        - orientation: TopAbs orientation enum value
        For cylinders:
        - radius: float
        - axis: (dx, dy, dz) tuple
        - axis_origin: (x, y, z) tuple
        - u_min, u_max: float (parameter range)
        For planes:
        - normal: (nx, ny, nz) tuple
        - plane_d: float (plane equation constant)
        - plane_location: (x, y, z) tuple
    """
    all_faces = cq_object.faces().vals()
    face_data = []

    type_map = {
        GeomAbs_Cylinder: 'cylinder',
        GeomAbs_Plane: 'plane',
        GeomAbs_Cone: 'cone',
        GeomAbs_Sphere: 'sphere',
        GeomAbs_Torus: 'torus',
    }

    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        area = props.Mass()
        center = props.CentreOfMass()

        entry = {
            'face': face,
            'type': type_map.get(stype, 'other'),
            'area': area,
            'center': (center.X(), center.Y(), center.Z()),
            'orientation': face.wrapped.Orientation(),
        }

        if stype == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            loc = cyl.Location()
            axis = cyl.Axis().Direction()
            entry['radius'] = cyl.Radius()
            entry['axis'] = (axis.X(), axis.Y(), axis.Z())
            entry['axis_origin'] = (loc.X(), loc.Y(), loc.Z())
            entry['u_min'] = surf.FirstUParameter()
            entry['u_max'] = surf.LastUParameter()

        elif stype == GeomAbs_Plane:
            pln = surf.Plane()
            axis = pln.Axis().Direction()
            loc = pln.Location()
            entry['normal'] = (axis.X(), axis.Y(), axis.Z())
            entry['plane_location'] = (loc.X(), loc.Y(), loc.Z())
            entry['plane_d'] = -(axis.X()*loc.X() + axis.Y()*loc.Y() + axis.Z()*loc.Z())

        face_data.append(entry)

    return face_data


def detect_holes(cq_object, filter_bores=True, is_flat_pattern=False, is_turned=None, face_data=None, return_debug=False):
    """
    Extract all holes from geometry using CadQuery selectors.
    Filters out external features (bosses) and groups split faces.

    Args:
        cq_object: CadQuery object to analyze
        filter_bores: If True, filters out bores in turned parts (holes that
                     span the full length of the part, which are machined bores
                     not laser-cut holes)
        is_flat_pattern: If True, relaxes orientation checks for flat patterns
                        where hole orientation may be inconsistent after unfolding
        is_turned: If provided, skip redundant is_turned_part() call
        face_data: If provided, use precomputed face properties instead of
                  calling BRepAdaptor_Surface per face
    """
    candidates = []
    debug_items = []
    candidate_counter = 0

    def make_criterion(name, value=None, threshold=None, passed=True, note=None):
        return {
            "name": name,
            "value": value,
            "threshold": threshold,
            "passed": bool(passed),
            "note": note,
        }

    def make_hole_debug_item(item_id, status, reason, criteria, payload):
        return {
            "id": item_id,
            "status": status,
            "type": "cylindrical",
            "label": f"Ø{float(payload.get('diameter') or 0.0):.1f} mm",
            "reason": reason,
            "criteria": criteria,
            **payload,
        }

    # Get bounding box for bore filtering
    part_dims = None
    if filter_bores:
        try:
            shape = cq_object.val().wrapped
            bbox = Bnd_Box()
            BRepBndLib.Add_s(shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            part_dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        except Exception:
            part_dims = None

    # For flat patterns, the smallest bbox dimension is a practical thickness proxy.
    # This is used to reject bend/artefact cylinders without hard-limiting real large holes.
    thickness_ref = part_dims[0] if part_dims and part_dims[0] > 0 else None

    # Check if this is a turned part (axisymmetric)
    if is_turned is None:
        is_turned = is_turned_part(cq_object) if filter_bores else False

    # Iterate over all faces - use precomputed data if available
    if face_data is not None:
        for fd in face_data:
            if fd['type'] != 'cylinder':
                continue
            if not is_flat_pattern and fd['orientation'] != TopAbs_REVERSED:
                continue

            radius = fd['radius']

            u_min = fd['u_min']
            u_max = fd['u_max']
            angle_deg = math.degrees(abs(u_max - u_min))

            arc_length = radius * abs(u_max - u_min)
            depth = fd['area'] / arc_length if arc_length > 0 else 0

            # Large flat-pattern cylinders can be real cut-outs, but bend artefacts
            # typically show very large depth compared to sheet thickness.
            if is_flat_pattern and radius * 2 > 100 and thickness_ref is not None:
                threshold = max(20.0, thickness_ref * 3.0)
                if depth > threshold:
                    item_id = f"hole-cyl-{candidate_counter}"
                    candidate_counter += 1
                    debug_items.append(make_hole_debug_item(
                        item_id,
                        "rejected",
                        "Afgewezen als flat-pattern buigartefact",
                        [
                            make_criterion("flat_artifact_filter", round(depth, 3), round(threshold, 3), False, "Diepte te groot voor uitslaggat"),
                            make_criterion("flat_pattern_source", "flat", None, True, None),
                        ],
                        {
                            "diameter": radius * 2,
                            "depth": depth,
                            "position": fd['center'],
                            "axis": fd['axis'],
                            "source": "flat" if is_flat_pattern else "3d",
                        }
                    ))
                    continue

            candidates.append({
                "id": f"hole-cyl-{candidate_counter}",
                "diameter": radius * 2,
                "depth": depth,
                "position": fd['center'],
                "axis_origin": fd['axis_origin'],
                "axis": fd['axis'],
                "angle": angle_deg
            })
            candidate_counter += 1
    else:
        all_faces = cq_object.faces().vals()

        for face in all_faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            if surf.GetType() == GeomAbs_Cylinder:
                # Check orientation: Must be REVERSED (internal hole)
                # For flat patterns, accept both orientations as unfold can flip them
                if not is_flat_pattern and face.wrapped.Orientation() != TopAbs_REVERSED:
                    continue

                cylinder = surf.Cylinder()
                radius = cylinder.Radius()

                location = cylinder.Location()
                axis = cylinder.Axis().Direction()

                u_min = surf.FirstUParameter()
                u_max = surf.LastUParameter()
                angle_deg = math.degrees(abs(u_max - u_min))

                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face.wrapped, props)
                area = props.Mass()
                center = props.CentreOfMass()

                arc_length = radius * abs(u_max - u_min)
                depth = area / arc_length if arc_length > 0 else 0

                # Large flat-pattern cylinders can be real cut-outs, but bend artefacts
                # typically show very large depth compared to sheet thickness.
                if is_flat_pattern and radius * 2 > 100 and thickness_ref is not None:
                    threshold = max(20.0, thickness_ref * 3.0)
                    if depth > threshold:
                        item_id = f"hole-cyl-{candidate_counter}"
                        candidate_counter += 1
                        debug_items.append(make_hole_debug_item(
                            item_id,
                            "rejected",
                            "Afgewezen als flat-pattern buigartefact",
                            [
                                make_criterion("flat_artifact_filter", round(depth, 3), round(threshold, 3), False, "Diepte te groot voor uitslaggat"),
                                make_criterion("flat_pattern_source", "flat", None, True, None),
                            ],
                            {
                                "diameter": radius * 2,
                                "depth": depth,
                                "position": (center.X(), center.Y(), center.Z()),
                                "axis": (axis.X(), axis.Y(), axis.Z()),
                                "source": "flat" if is_flat_pattern else "3d",
                            }
                        ))
                        continue

                candidates.append({
                    "id": f"hole-cyl-{candidate_counter}",
                    "diameter": radius * 2,
                    "depth": depth,
                    "position": (center.X(), center.Y(), center.Z()),
                    "axis_origin": (location.X(), location.Y(), location.Z()),
                    "axis": (axis.X(), axis.Y(), axis.Z()),
                    "angle": angle_deg
                })
                candidate_counter += 1
            
    # Group candidates by Axis and Diameter
    # Pre-bucket by diameter to avoid O(n²) comparisons
    from collections import defaultdict
    diameter_buckets = defaultdict(list)
    for idx, c in enumerate(candidates):
        bucket_key = round(c["diameter"], 2)
        diameter_buckets[bucket_key].append((idx, c))

    grouped_holes = []
    processed_indices = set()

    for bucket_key in diameter_buckets:
        # Check this bucket + adjacent buckets (±0.01) for edge cases
        nearby = []
        for adj_key in [bucket_key - 0.01, bucket_key, bucket_key + 0.01]:
            if adj_key in diameter_buckets:
                nearby.extend(diameter_buckets[adj_key])

        for i, c1 in nearby:
            if i in processed_indices:
                continue

            current_group = [c1]
            processed_indices.add(i)

            for j, c2 in nearby:
                if j in processed_indices:
                    continue

                # Check diameter match
                if abs(c1["diameter"] - c2["diameter"]) > 0.01:
                    continue

                # Check axis direction match (parallel)
                dot = (c1["axis"][0]*c2["axis"][0] +
                       c1["axis"][1]*c2["axis"][1] +
                       c1["axis"][2]*c2["axis"][2])
                if abs(abs(dot) - 1.0) > 0.01:
                    continue

                # Check if axes are collinear (distance between lines)
                dx = c2["axis_origin"][0] - c1["axis_origin"][0]
                dy = c2["axis_origin"][1] - c1["axis_origin"][1]
                dz = c2["axis_origin"][2] - c1["axis_origin"][2]

                cx = dy*c1["axis"][2] - dz*c1["axis"][1]
                cy = dz*c1["axis"][0] - dx*c1["axis"][2]
                cz = dx*c1["axis"][1] - dy*c1["axis"][0]
                dist_sq = cx*cx + cy*cy + cz*cz

                if dist_sq < 0.01:  # Collinear axes (0.1² = 0.01)
                    t1 = (c1["position"][0]*c1["axis"][0] + c1["position"][1]*c1["axis"][1] +
                          c1["position"][2]*c1["axis"][2])
                    t2 = (c2["position"][0]*c1["axis"][0] + c2["position"][1]*c1["axis"][1] +
                          c2["position"][2]*c1["axis"][2])

                    if abs(t1 - t2) < 5.0:
                        current_group.append(c2)
                        processed_indices.add(j)

            grouped_holes.append(current_group)


    # Convert groups to HoleFeatures
    holes = []
    for group in grouped_holes:
        # Sum angles
        total_angle = sum(c["angle"] for c in group)

        # Filter out fillets (usually 90 degrees or less per face).
        # A hole should be close to 360 degrees. Flat patterns use a lower
        # threshold for regular holes, but large-diameter cylinders require
        # near-full coverage to avoid bend artefacts.
        min_angle = 160 if is_flat_pattern else 270
        group_diameter = group[0]["diameter"] if group else 0.0
        if is_flat_pattern and group_diameter > 100:
            min_angle = 300
        if total_angle > min_angle:
            # Use properties of the first face (or average)
            # Depth is usually the same for all faces in a split hole
            # Or if they are stacked, we should sum depths?
            # For split faces (180+180), depth is same.
            # For stacked faces, depth adds up.
            # But here we assume split faces (common in STEP).
            
            # Take max depth of the group as the hole depth
            max_depth = max(c["depth"] for c in group)

            first = group[0]
            diameter = first["diameter"]
            hole_axis = first["axis"]

            # Filter out bores in turned parts
            skip_hole = False
            if filter_bores and is_turned and part_dims:
                # For turned parts, any internal cylinder aligned with the part's
                # long axis is likely a machined bore, not a laser-cut hole.
                # Turned parts (axisymmetric) have their lathe axis along the longest dimension.

                # Determine the longest dimension direction
                # Typically for turned parts, the long axis is well-defined
                # If the hole depth is significant (> 5mm) compared to smallest dimension,
                # it's likely a bore
                min_dim = part_dims[0]  # Smallest dimension (often wall thickness for tubes)

                # Bores typically have depth > the smallest cross-section dimension
                if max_depth > min_dim * 0.5:
                    skip_hole = True

            criteria = [
                make_criterion("angle_coverage", round(total_angle, 3), round(min_angle, 3), total_angle > min_angle, "Totale cilindrische dekking"),
                make_criterion("bore_filter", round(max_depth, 3), round(min_dim * 0.5, 3) if filter_bores and is_turned and part_dims else None, not skip_hole, "Bore-filter voor draaistukken"),
            ]

            if not skip_hole:
                holes.append(HoleFeature(
                    diameter=diameter,
                    depth=max_depth,
                    position=first["position"],
                    axis=hole_axis,
                    id=first["id"],
                ))
                debug_items.append(make_hole_debug_item(
                    first["id"],
                    "accepted",
                    "Geaccepteerd als cilindrisch gat",
                    criteria,
                    {
                        "diameter": diameter,
                        "depth": max_depth,
                        "position": first["position"],
                        "axis": hole_axis,
                        "source": "flat" if is_flat_pattern else "3d",
                    },
                ))
            else:
                debug_items.append(make_hole_debug_item(
                    first["id"],
                    "rejected",
                    "Afgewezen als boring in draaideel",
                    criteria,
                    {
                        "diameter": diameter,
                        "depth": max_depth,
                        "position": first["position"],
                        "axis": hole_axis,
                        "source": "flat" if is_flat_pattern else "3d",
                    },
                ))
        else:
            first = group[0]
            debug_items.append(make_hole_debug_item(
                first["id"],
                "rejected",
                "Afgewezen op onvoldoende cilindrische dekking",
                [
                    make_criterion("angle_coverage", round(total_angle, 3), round(min_angle, 3), False, "Totale cilindrische dekking te laag"),
                ],
                {
                    "diameter": first["diameter"],
                    "depth": max(c["depth"] for c in group),
                    "position": first["position"],
                    "axis": first["axis"],
                    "source": "flat" if is_flat_pattern else "3d",
                },
            ))

    if return_debug:
        return holes, debug_items
    return holes


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
    """
    Detect non-circular holes (slots, rectangles) by analyzing planar face contours.
    Returns a list of dicts describing the holes.

    Args:
        shape: CadQuery object to analyze
        face_data: If provided, use precomputed face properties for planar face filtering
    """
    all_shaped_holes = []
    debug_items = []
    recovery_bucket = []
    candidate_counter = 0

    def make_criterion(name, value=None, threshold=None, passed=True, note=None):
        return {
            "name": name,
            "value": value,
            "threshold": threshold,
            "passed": bool(passed),
            "note": note,
        }

    # Find planar faces - use precomputed data if available
    if face_data is not None:
        planar_faces = [(fd['face'], fd['normal']) for fd in face_data if fd['type'] == 'plane']
    else:
        faces = shape.faces().vals()
        planar_faces = []
        for face in faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            if surf.GetType() == GeomAbs_Plane:
                pln = surf.Plane()
                axis = pln.Axis().Direction()
                planar_faces.append((face, (axis.X(), axis.Y(), axis.Z())))

    source = "flat" if is_flat_pattern else "3d"

    if not planar_faces:
        if return_debug:
            return [], []
        return []

    for face, normal in planar_faces:
        
        wires = face.Wires()
        
        sorted_wires = []
        for wire in wires:
            b = Bnd_Box()
            BRepBndLib.Add_s(wire.wrapped, b)
            xmin, ymin, zmin, xmax, ymax, zmax = b.Get()
            diag = math.sqrt((xmax-xmin)**2 + (ymax-ymin)**2 + (zmax-zmin)**2)
            sorted_wires.append((wire, diag))
            
        sorted_wires.sort(key=lambda x: x[1], reverse=True)
        
        # If there are wires, the first one is likely the outline. The rest are holes.
        if len(sorted_wires) > 1:
            inner_wires = [w[0] for w in sorted_wires[1:]]
            
            for wire in inner_wires:
                # Analyze shape
                edges = []
                iterator = TopExp_Explorer(wire.wrapped, TopAbs_EDGE)
                while iterator.More():
                    edges.append(iterator.Current())
                    iterator.Next()
                    
                if not edges: continue
                
                # Check for circle (already handled by detect_holes)
                is_circle = False
                if len(edges) == 1:
                    curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges[0]))
                    if curve.GetType() == GeomAbs_Circle:
                        is_circle = True
                elif len(edges) == 2:
                     # Check if both are arcs forming a circle
                     c1 = BRepAdaptor_Curve(TopoDS.Edge_s(edges[0]))
                     c2 = BRepAdaptor_Curve(TopoDS.Edge_s(edges[1]))
                     if c1.GetType() == GeomAbs_Circle and c2.GetType() == GeomAbs_Circle:
                         is_circle = True
                
                if is_circle:
                    continue
                    
                # Analyze complex shape
                lines = 0
                circles = 0
                radii = []
                lengths = []
                
                for edge in edges:
                    curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
                    c_type = curve.GetType()
                    if c_type == GeomAbs_Line:
                        lines += 1
                        p1 = curve.Value(curve.FirstParameter())
                        p2 = curve.Value(curve.LastParameter())
                        lengths.append(p1.Distance(p2))
                    elif c_type == GeomAbs_Circle:
                        circles += 1
                        radii.append(curve.Circle().Radius())
                
                b = Bnd_Box()
                BRepBndLib.Add_s(wire.wrapped, b)
                xmin, ymin, zmin, xmax, ymax, zmax = b.Get()
                dx = xmax - xmin
                dy = ymax - ymin
                dz = zmax - zmin
                shape_type, dim_str, shape_family = _classify_shaped_inner_wire(
                    len(edges),
                    lines,
                    circles,
                    radii,
                    lengths,
                    (dx, dy, dz),
                )
                
                if shape_type != "unknown":
                    # Calculate center
                    w_props = GProp_GProps()
                    BRepGProp.LinearProperties_s(wire.wrapped, w_props)
                    c = w_props.CentreOfMass()
                    center = (c.X(), c.Y(), c.Z())
                    perimeter = float(w_props.Mass())
                    contour_points = []
                    for edge in edges:
                        contour_points.extend(_sample_edge_points(edge))
                    if contour_points and contour_points[0] != contour_points[-1]:
                        contour_points.append(contour_points[0])
                    
                    item_id = f"hole-shaped-{candidate_counter}"
                    candidate_counter += 1
                    candidate = {
                        "id": item_id,
                        "type": shape_type,
                        "dim": dim_str,
                        "center": center,
                        "normal": normal,
                        "perimeter": perimeter,
                        "contour_points": contour_points,
                        "method": "face_boundary_primary",
                    }
                    all_shaped_holes.append(candidate)
                    debug_items.append({
                        "id": item_id,
                        "status": "accepted",
                        "type": str(shape_type).lower().replace(" ", "_"),
                        "label": dim_str or shape_type,
                        "reason": (
                            "Geaccepteerd als generieke gesloten contour"
                            if shape_type == "Closed contour"
                            else f"Geaccepteerd als {shape_type}"
                        ),
                        "method": "face_boundary_primary",
                        "criteria": [
                            make_criterion("method_order", "primary", "face_boundary_primary_first", True, "Eerst geprobeerd via inner wires van face"),
                            make_criterion("face_boundary", True, True, True, "Outer wire uitgesloten; inner wires als hole-kandidaten"),
                            make_criterion("recognized_shape", shape_type, "known", True, f"{lines} lijnen / {circles} bogen"),
                            make_criterion("shape_family", shape_family, "slot/rect/poly/closed_contour", True, "Inner wire op planar face"),
                            make_criterion("closed_inner_wire", True, True, True, "Inner wire van planar face wordt als gesloten contour behandeld"),
                            make_criterion("is_circle", False, False, True, "Niet door de cilindrische detector afgehandeld"),
                        ],
                        "position": center,
                        "normal": normal,
                        "size": dim_str,
                        "perimeter": perimeter,
                        "contour_points": contour_points,
                        "source": source,
                    })
                else:
                    w_props = GProp_GProps()
                    BRepGProp.LinearProperties_s(wire.wrapped, w_props)
                    c = w_props.CentreOfMass()
                    center = (c.X(), c.Y(), c.Z())
                    perimeter = float(w_props.Mass())
                    contour_points = []
                    for edge in edges:
                        contour_points.extend(_sample_edge_points(edge))
                    if contour_points and contour_points[0] != contour_points[-1]:
                        contour_points.append(contour_points[0])

                    item_id = f"hole-shaped-{candidate_counter}"
                    candidate_counter += 1
                    candidate = {
                        "id": item_id,
                        "type": "Irregular contour",
                        "dim": dim_str,
                        "center": center,
                        "normal": normal,
                        "perimeter": perimeter,
                        "contour_points": contour_points,
                        "method": "face_boundary_primary",
                    }
                    all_shaped_holes.append(candidate)
                    debug_items.append({
                        "id": item_id,
                        "status": "accepted",
                        "type": "irregular_contour",
                        "label": dim_str or "Irregular contour",
                        "reason": "Geaccepteerd als irregulaire gesloten contour via Face Boundary",
                        "method": "face_boundary_primary",
                        "criteria": [
                            make_criterion("method_order", "primary", "face_boundary_primary_first", True, "Eerst geprobeerd via inner wires van face"),
                            make_criterion("face_boundary", True, True, True, "Inner wire kandidaat vanuit face boundaries"),
                            make_criterion("recognized_shape", "unknown", "known", True, f"{lines} lijnen / {circles} bogen"),
                            make_criterion("irregular_contour_policy", True, True, True, "Onbekende gesloten contour toch als gat teruggeven"),
                        ],
                        "position": center,
                        "normal": normal,
                        "size": dim_str,
                        "perimeter": perimeter,
                        "contour_points": contour_points,
                        "source": source,
                    })

    recovered_holes, recovered_debug = _recover_contours_from_bucket(recovery_bucket)
    if recovered_holes:
        all_shaped_holes.extend(recovered_holes)
        debug_items.extend(recovered_debug)
                    
    # Deduplicate - pre-group by (type, dim) to avoid O(n²)
    from collections import defaultdict
    type_dim_buckets = defaultdict(list)
    for idx, h in enumerate(all_shaped_holes):
        type_dim_buckets[(h["type"], h["dim"])].append((idx, h))

    unique_holes = []
    processed_indices = set()

    for bucket in type_dim_buckets.values():
        for i, h1 in bucket:
            if i in processed_indices:
                continue

            for j, h2 in bucket:
                if i == j or j in processed_indices:
                    continue

                dx = h2["center"][0] - h1["center"][0]
                dy = h2["center"][1] - h1["center"][1]
                dz = h2["center"][2] - h1["center"][2]
                dist_sq = dx*dx + dy*dy + dz*dz

                if dist_sq < 0.01:  # 0.1² = 0.01
                    processed_indices.add(j)
                    rejected_id = h2.get("id")
                    for item in debug_items:
                        if item.get("id") == rejected_id:
                            item["status"] = "rejected"
                            item["reason"] = "Afgewezen als duplicaat van een shaped hole op hetzelfde vlak"
                            item["criteria"].append(
                                make_criterion("deduplicate", True, False, False, "Duplicaat op zelfde vlak")
                            )
                else:
                    dist = math.sqrt(dist_sq)
                    if dist > 0:
                        vx, vy, vz = dx / dist, dy / dist, dz / dist
                        nx, ny, nz = h1["normal"]
                        dot = abs(vx * nx + vy * ny + vz * nz)
                        if dot > 0.9:  # Parallel
                            processed_indices.add(j)
                            rejected_id = h2.get("id")
                            for item in debug_items:
                                if item.get("id") == rejected_id:
                                    item["status"] = "rejected"
                                    item["reason"] = "Afgewezen als duplicaat van een shaped hole op hetzelfde vlak"
                                    item["criteria"].append(
                                        make_criterion("deduplicate", True, False, False, "Duplicaat op zelfde vlak")
                                    )

            unique_holes.append(h1)
            processed_indices.add(i)

    if return_debug:
        return unique_holes, debug_items
    return unique_holes

def deduplicate_holes(circular_holes, shaped_holes, return_debug=False):
    """
    Remove circular holes that are part of a shaped hole (e.g. rounded corners of a rect).
    Returns filtered list of circular_holes.
    """
    if not shaped_holes:
        if return_debug:
            return circular_holes, []
        return circular_holes
        
    filtered_circular = []
    rejected = []
    
    for circ in circular_holes:
        is_duplicate = False
        c_pos = circ.position
        
        for shaped in shaped_holes:
            s_pos = shaped["center"]

            # Fallback contour candidates are diagnostics/augmentation from face boundaries;
            # they should not suppress cylindrical holes in final counting.
            if shaped.get("method") in {
                "face_boundary_round_contour_fallback",
                "face_boundary_circular_wire_fallback",
            }:
                continue

            # Check of gat en shaped hole op zelfde vlak zitten (parallelle assen)
            # Niet-parallelle assen → ander vlak → nooit duplicaat
            shaped_normal = shaped.get("normal")
            if shaped_normal and hasattr(circ, 'axis') and circ.axis:
                dot = abs(circ.axis[0]*shaped_normal[0] +
                          circ.axis[1]*shaped_normal[1] +
                          circ.axis[2]*shaped_normal[2])
                if dot < 0.7:
                    continue

            # Calculate distance
            dx = c_pos[0] - s_pos[0]
            dy = c_pos[1] - s_pos[1]
            dz = c_pos[2] - s_pos[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)

            # Parse dimensions of shaped hole to get a "radius of influence"
            # dim string is like "20.2x19.5"
            try:
                dims = [float(x) for x in shaped["dim"].split('x')]
                max_dim = max(dims)
            except:
                max_dim = 20.0 # Fallback
                
            # If the circular hole is within the shaped hole's bounding area
            # we assume it's part of the shape (e.g. a corner radius).
            # Size check: the circular hole diameter must be comparable to the
            # shaped hole's smallest dimension (e.g. corner radius ≈ min_dim/2).
            # A small drill hole near a large opening is NOT a duplicate.
            min_dim = min(dims) if len(dims) >= 2 else max_dim
            circ_diam = circ.diameter
            if circ_diam < min_dim * 0.25:
                # Circle is much smaller than the shape — independent hole
                continue

            if dist < (max_dim * 0.8):
                is_duplicate = True
                rejected.append({
                    "id": getattr(circ, "id", None),
                    "reason": "Afgewezen als onderdeel van een shaped hole",
                    "criteria": [
                        {
                            "name": "duplicate_of_shaped_hole",
                            "value": round(dist, 3),
                            "threshold": round(max_dim * 0.8, 3),
                            "passed": False,
                            "note": f"Nabij shaped hole {shaped.get('dim', shaped.get('type', 'unknown'))}",
                        }
                    ],
                })
                break
        
        if not is_duplicate:
            filtered_circular.append(circ)
            
    if return_debug:
        return filtered_circular, rejected
    return filtered_circular

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
    """
    Detect potential threaded features by analyzing cylindrical holes
    and matching to ISO metric thread standards.
    """
    holes = detect_holes(cq_object)
    thread_candidates = []

    for hole in holes:
        diameter = hole.diameter
        matches = iso_standards.identify_thread_from_diameter(diameter, tolerance)

        if matches:
            # Prefer coarse thread match
            coarse_matches = [m for m in matches if m.is_coarse]
            best_match = coarse_matches[0] if coarse_matches else matches[0]

            thread_candidates.append({
                "diameter": diameter,
                "depth": hole.depth,
                "position": hole.position,
                "thread_designation": best_match.designation,
                "pitch": best_match.pitch,
                "is_coarse": best_match.is_coarse,
                "minor_diameter": best_match.minor_diameter,
                "tap_drill": iso_standards.get_tap_drill_size(best_match.designation),
                "all_matches": [m.designation for m in matches[:3]],  # Top 3 matches
            })

    return thread_candidates


def detect_shafts(cq_object):
    """
    Detect external cylindrical features (shafts) for fit analysis.
    """
    shafts = []
    all_faces = cq_object.faces().vals()

    # Group cylindrical faces by axis and analyze
    cylinder_data = []

    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        if surf.GetType() == GeomAbs_Cylinder:
            cylinder = surf.Cylinder()
            radius = cylinder.Radius()
            location = cylinder.Location()
            axis = cylinder.Axis().Direction()

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face.wrapped, props)
            area = props.Mass()
            circumference = 2 * math.pi * radius
            length = area / circumference

            # Check if this is likely an external surface (shaft) vs internal (hole)
            # by checking face orientation
            cylinder_data.append({
                "diameter": radius * 2,
                "length": length,
                "position": (location.X(), location.Y(), location.Z()),
                "axis": (axis.X(), axis.Y(), axis.Z()),
            })

    # Group by similar diameters and analyze
    if cylinder_data:
        # Sort by diameter
        cylinder_data.sort(key=lambda x: x["diameter"], reverse=True)

        # Take unique diameters (potential shafts are typically larger)
        seen_diameters = set()
        for cyl in cylinder_data:
            d = round(cyl["diameter"], 1)
            if d not in seen_diameters and d > 3.0:  # Min 3mm for shaft
                seen_diameters.add(d)
                fit_analysis = iso_standards.analyze_hole_fit(cyl["diameter"])
                shafts.append({
                    "diameter": cyl["diameter"],
                    "length": cyl["length"],
                    "position": cyl["position"],
                    "fit_recommendation": fit_analysis["primary_recommendation"],
                })

    return shafts


def analyze_chamfers_and_fillets(cq_object):
    """
    Detect chamfers (conical faces) and fillets (torus faces) in the geometry.
    """
    chamfers = []
    fillets = []

    all_faces = cq_object.faces().vals()

    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        area = props.Mass()

        if stype == GeomAbs_Cone:
            cone = surf.Cone()
            half_angle = cone.SemiAngle()
            angle_deg = math.degrees(half_angle)

            # Chamfers typically have 45° angle
            if 40 <= angle_deg <= 50:
                # Estimate chamfer size from area
                ref_radius = cone.RefRadius()
                chamfers.append({
                    "angle": round(angle_deg, 1),
                    "estimated_size": round(ref_radius * 0.3, 2),  # Approximate
                    "area": area,
                })

        elif stype == GeomAbs_Torus:
            torus = surf.Torus()
            minor_radius = torus.MinorRadius()
            major_radius = torus.MajorRadius()

            # Fillets have small minor radius relative to major
            if minor_radius < major_radius * 0.5 and minor_radius < 20:
                fillets.append({
                    "radius": round(minor_radius, 2),
                    "area": area,
                    "standard_radius": iso_standards.get_nearest_standard_fillet(minor_radius),
                })

    # Summarize
    chamfer_sizes = [c["estimated_size"] for c in chamfers]
    fillet_radii = [f["radius"] for f in fillets]

    avg_chamfer = sum(chamfer_sizes) / len(chamfer_sizes) if chamfer_sizes else 1.0
    avg_fillet = sum(fillet_radii) / len(fillet_radii) if fillet_radii else 2.0

    return {
        "chamfers": {
            "count": len(chamfers),
            "sizes": list(set(round(s, 1) for s in chamfer_sizes)),
            "average_size": round(avg_chamfer, 2),
            "recommended_standard": iso_standards.get_nearest_standard_chamfer(avg_chamfer),
        },
        "fillets": {
            "count": len(fillets),
            "radii": list(set(round(r, 1) for r in fillet_radii)),
            "average_radius": round(avg_fillet, 2),
            "recommended_standard": iso_standards.get_nearest_standard_fillet(avg_fillet),
        },
        "edge_note": "All edges to be deburred and broken 0.2-0.5mm unless otherwise specified (ISO 13715)",
    }


def analyze_manufacturing_requirements(cq_object, face_analysis=None):
    """
    Comprehensive manufacturing analysis including tolerances, surface finish,
    and process recommendations per ISO standards.
    """
    if face_analysis is None:
        face_analysis = analyze_faces(cq_object)

    geom_props = get_geometric_properties(cq_object)
    is_turned = is_turned_part(cq_object)

    # Get bounding box dimensions
    dims = geom_props["bounding_box"]["dimensions"]
    max_dim = max(dims)
    min_dim = min(dims)

    # Determine complexity
    total_faces = sum(face_analysis.values())
    bspline_ratio = face_analysis.get("BSpline", 0) / total_faces if total_faces > 0 else 0
    torus_count = face_analysis.get("Torus", 0)

    if bspline_ratio > 0.3:
        complexity = "high"
    elif torus_count > 10 or total_faces > 500:
        complexity = "medium"
    else:
        complexity = "low"

    # Determine part type for tolerance recommendation
    if is_turned:
        part_type = "Shaft/Bar"
    elif min_dim < max_dim * 0.1:
        part_type = "Plate/Sheet"
    else:
        part_type = "Block/Housing"

    # Get ISO 2768 recommendations
    linear_class, geo_class = iso_standards.recommend_iso2768_class(part_type, complexity)

    # Calculate tolerances for key dimensions
    tolerance_table = []
    for dim in dims:
        tol = iso_standards.get_iso2768_linear_tolerance(dim, linear_class)
        if tol:
            tolerance_table.append({
                "dimension": round(dim, 2),
                "tolerance": f"±{tol}",
                "class": linear_class,
            })

    # Surface finish analysis
    surface_analysis = iso_standards.analyze_surface_requirements(face_analysis)

    # Manufacturing process recommendation
    if is_turned:
        primary_process = "CNC Turning"
        secondary_processes = ["Milling (for features)", "Grinding (if Ra < 0.8)"]
    elif bspline_ratio > 0.2:
        primary_process = "5-Axis CNC Milling"
        secondary_processes = ["3-Axis roughing", "Finishing passes"]
    elif min_dim < max_dim * 0.05:
        primary_process = "Sheet Metal (Laser/Plasma + Bending)"
        secondary_processes = ["Deburring", "Surface treatment"]
    else:
        primary_process = "3-Axis CNC Milling"
        secondary_processes = ["Drilling", "Tapping", "Deburring"]

    return {
        "iso2768_recommendation": {
            "linear_class": linear_class,
            "geometric_class": geo_class,
            "designation": f"ISO 2768-{linear_class}{geo_class}",
            "tolerance_table": tolerance_table,
        },
        "surface_finish": surface_analysis,
        "manufacturing_process": {
            "primary": primary_process,
            "secondary": secondary_processes,
            "complexity": complexity,
        },
        "part_characteristics": {
            "is_turned_part": is_turned,
            "part_type": part_type,
            "max_dimension": round(max_dim, 2),
            "volume": round(geom_props["volume"], 2),
        },
    }


def calculate_mass_properties(cq_object, material_key="steel_s235"):
    """
    Calculate mass properties for different materials.
    """
    geom_props = get_geometric_properties(cq_object)
    volume = geom_props["volume"]

    # Calculate for specified material
    mass_data = iso_standards.calculate_mass(volume, material_key)

    if not mass_data:
        return None

    # Calculate for common alternative materials
    alternatives = {}
    for alt_key in ["steel_s355", "steel_304", "alu_6061", "alu_7075"]:
        if alt_key != material_key:
            alt_mass = iso_standards.calculate_mass(volume, alt_key)
            if alt_mass:
                alternatives[alt_key] = {
                    "material": alt_mass["material"],
                    "mass_kg": alt_mass["mass_kg"],
                }

    return {
        "primary": mass_data,
        "alternatives": alternatives,
        "volume_mm3": volume,
        "volume_cm3": volume / 1000,
    }


def analyze_holes_with_fits(cq_object):
    """
    Analyze all holes and provide ISO 286 fit recommendations.
    """
    holes = detect_holes(cq_object)
    analyzed_holes = []

    # Group holes by diameter
    diameter_groups = {}
    for hole in holes:
        d_rounded = round(hole.diameter, 1)
        if d_rounded not in diameter_groups:
            diameter_groups[d_rounded] = []
        diameter_groups[d_rounded].append(hole)

    for diameter, hole_list in diameter_groups.items():
        fit_analysis = iso_standards.analyze_hole_fit(diameter)

        # Check for thread match
        thread_matches = iso_standards.identify_thread_from_diameter(diameter, 0.15)
        thread_info = None
        if thread_matches:
            best = thread_matches[0]
            thread_info = {
                "designation": best.designation,
                "pitch": best.pitch,
                "tap_drill": iso_standards.get_tap_drill_size(best.designation),
            }

        analyzed_holes.append({
            "diameter": diameter,
            "count": len(hole_list),
            "depths": [round(h.depth, 2) for h in hole_list],
            "fit_recommendation": fit_analysis["primary_recommendation"],
            "alternative_fit": fit_analysis["alternative_recommendation"],
            "tolerances": fit_analysis["tolerances"],
            "possible_thread": thread_info,
        })

    # Sort by diameter
    analyzed_holes.sort(key=lambda x: x["diameter"])

    return analyzed_holes


def generate_manufacturing_summary(cq_object, output_dir=None):
    """
    Generate a complete manufacturing summary for the assembly/part.
    """
    # Basic analysis
    face_analysis = analyze_faces(cq_object)
    geom_props = get_geometric_properties(cq_object)
    topology = get_topology_stats(cq_object)

    # Manufacturing analysis
    mfg_requirements = analyze_manufacturing_requirements(cq_object, face_analysis)
    holes_analysis = analyze_holes_with_fits(cq_object)
    threads = detect_threads(cq_object)
    chamfers_fillets = analyze_chamfers_and_fillets(cq_object)

    # Mass calculations for common materials
    mass_steel = calculate_mass_properties(cq_object, "steel_s235")
    mass_alu = calculate_mass_properties(cq_object, "alu_6061")

    return {
        "geometry": {
            "volume_mm3": geom_props["volume"],
            "surface_area_mm2": geom_props["surface_area"],
            "bounding_box": geom_props["bounding_box"],
            "center_of_mass": geom_props["center_of_mass"],
        },
        "topology": topology,
        "face_analysis": face_analysis,
        "manufacturing": mfg_requirements,
        "holes": {
            "summary": holes_analysis,
            "total_count": sum(h["count"] for h in holes_analysis),
        },
        "threads": {
            "detected": threads,
            "count": len(threads),
        },
        "edges": chamfers_fillets,
        "mass_estimates": {
            "steel_s235": mass_steel["primary"] if mass_steel else None,
            "alu_6061": mass_alu["primary"] if mass_alu else None,
        },
    }


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
    """
    Generate complete werkvoorbereiding (manufacturing preparation) data.

    Includes:
    - Cost estimation (bewerkingstijd + kostprijs)
    - Tool list (gereedschapslijst)
    - Outsourcing classification (uitbesteding)
    - Surface treatment recommendations
    - Purchase specifications (inkoop)

    Args:
        cq_object: CadQuery workplane or shape
        material: Material code for cost calculation
        quantity: Number of pieces
        surface_treatment: Optional surface treatment code
        hourly_rates_config: Optional custom hourly rates (from pipeline_config.json)
        material_prices_config: Optional custom material prices (from pipeline_config.json)
    """
    # Get basic properties
    geom_props = get_geometric_properties(cq_object)
    face_analysis = analyze_faces(cq_object)
    holes = detect_holes(cq_object)
    threads = detect_threads(cq_object)
    chamfers_fillets = analyze_chamfers_and_fillets(cq_object)
    is_turned = is_turned_part(cq_object)

    # Determine complexity
    total_faces = sum(face_analysis.values())
    bspline_ratio = face_analysis.get("BSpline", 0) / total_faces if total_faces > 0 else 0

    if bspline_ratio > 0.3:
        complexity = "high"
    elif face_analysis.get("Torus", 0) > 10 or total_faces > 500:
        complexity = "medium"
    else:
        complexity = "low"

    # Determine process type
    dims = geom_props["bounding_box"]["dimensions"]
    min_dim = min(dims)
    max_dim = max(dims)

    if is_turned:
        process_type = "cnc_draaien"
    elif min_dim < max_dim * 0.05:
        process_type = "plaatwerk"
    elif bspline_ratio > 0.2 or complexity == "high":
        process_type = "cnc_frezen_5as"
    else:
        process_type = "cnc_frezen_3as"

    # Calculate mass
    volume = geom_props["volume"]
    density = 7850 if "steel" in material else 2700 if "alu" in material else 7850
    mass_kg = (volume / 1e9) * density

    # Prepare holes data for werkvoorbereiding
    holes_data = []
    for hole in holes:
        holes_data.append({
            "diameter": hole.diameter,
            "depth": hole.depth,
        })

    threads_data = []
    for t in threads:
        threads_data.append({
            "thread_designation": t["thread_designation"],
            "tap_drill": t.get("tap_drill"),
        })

    # Generate werkvoorbereiding data
    cost_estimate = werkvoorbereiding.calculate_cost_estimate(
        volume_mm3=volume,
        surface_area_mm2=geom_props["surface_area"],
        mass_kg=mass_kg,
        hole_count=len(holes),
        thread_count=len(threads),
        complexity=complexity,
        process_type=process_type,
        material=material,
        quantity=quantity,
        surface_treatment=surface_treatment,
        hourly_rates_config=hourly_rates_config,
        material_prices_config=material_prices_config,
    )

    tool_list = werkvoorbereiding.generate_tool_list(
        holes=holes_data,
        threads=threads_data,
        chamfers_fillets=chamfers_fillets,
        is_turned=is_turned,
        material=material,
    )

    outsourcing = werkvoorbereiding.classify_outsourcing(
        classification=process_type,
        complexity=complexity,
        is_turned=is_turned,
        is_sheet_metal=(process_type == "plaatwerk"),
        volume_mm3=volume,
        has_5axis_features=(process_type == "cnc_frezen_5as"),
        needs_surface_treatment=(surface_treatment is not None),
    )

    surface_recommendations = werkvoorbereiding.recommend_surface_treatment(
        material=material,
        corrosion_resistance="normal",
    )

    purchase_spec = werkvoorbereiding.generate_purchase_spec(
        part_id="PART-001",
        material=material,
        mass_kg=mass_kg,
        dimensions=dims,
        quantity=quantity,
    )

    return {
        "cost_estimate": cost_estimate,
        "tool_list": tool_list,
        "outsourcing": outsourcing,
        "surface_treatment_options": surface_recommendations,
        "purchase_specification": purchase_spec,
        "process_info": {
            "process_type": process_type,
            "complexity": complexity,
            "is_turned": is_turned,
            "material": material,
            "quantity": quantity,
        },
    }


def analyze_sheetmetal(cq_object, thickness: float = None, material: str = "steel_s235"):
    """
    Complete sheet metal / plaatwerk analysis.

    Analyzes:
    - Bend detection (zettingen)
    - Bend angles, radii, K-factor
    - Kantbank tooling recommendations
    - Flat pattern calculation
    - Buigkracht berekening

    Args:
        cq_object: CadQuery workplane or shape
        thickness: Known plate thickness (mm), or None to auto-detect
        material: Material code for K-factor and strength

    Returns:
        Dict with complete sheet metal analysis
    """
    # Get the underlying solid
    try:
        if hasattr(cq_object, 'val'):
            solid = cq_object.val().wrapped
        elif hasattr(cq_object, 'wrapped'):
            solid = cq_object.wrapped
        else:
            solid = cq_object
    except Exception:
        return {"error": "Could not access geometry"}

    # Auto-detect thickness if not provided
    if thickness is None:
        # Use existing sheet metal detection
        exp = TopExp_Explorer(solid, TopAbs_SOLID)
        if exp.More():
            first_solid = exp.Current()
            sm_data = analyze_sheet_metal(first_solid)
            if sm_data.get("is_sheet_metal"):
                thickness = sm_data.get("thickness", 2.0)
            else:
                thickness = 2.0  # Default

    # Run complete analysis
    result = sheetmetal_analysis.analyze_sheetmetal_complete(
        solid, thickness, material
    )

    return result


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
    return assembly_analysis.analyze_assembly_complete(
        cq_object,
        assembly_name=assembly_name,
        material=material,
        step_file_path=step_file_path
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


analyze_sheet_metal = sheetmetal_orchestration.analyze_sheet_metal


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
