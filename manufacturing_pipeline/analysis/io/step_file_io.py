from __future__ import annotations

import math
import os
import tempfile

import cadquery as cq
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


STEP_HEADER = b"ISO-10303-21;"


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
    """Try to build a CadQuery object from XCAF solids; return None on failure."""
    import subprocess
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    probe_script = f'''
import sys
try:
    sys.path.insert(0, {repr(project_root)})
    from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
    result = xcaf_match_solids_to_names({repr(filepath)})
    if result is None:
        print("0")
    else:
        solids, names = result
        print(str(len(solids)))
except Exception:
    print("0")
'''
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe_script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            detail = f": {stderr[:400]}" if stderr else ""
            print(f"  XCAF probe crashed (exit {proc.returncode}), using CadQuery fallback{detail}")
            return None
        solid_count = int(proc.stdout.strip() or "0")
        if solid_count == 0:
            return None
    except subprocess.TimeoutExpired:
        print("  XCAF probe timeout (>60s), using CadQuery fallback")
        return None
    except Exception:
        return None

    try:
        from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names

        result = xcaf_match_solids_to_names(filepath)
        if result is None:
            return None

        solids, solid_names = result
        if not solids:
            return None

        cq_solids = [cq.Shape.cast(solid) for solid in solids]

        if len(cq_solids) == 1:
            workplane = cq.Workplane(obj=cq_solids[0])
        else:
            compound = cq.Compound.makeCompound(cq_solids)
            workplane = cq.Workplane(obj=compound)

        try:
            setattr(workplane, "_xcaf_solid_names", list(solid_names))
            setattr(workplane, "_xcaf_source_step", str(filepath))
        except Exception:
            pass

        return workplane
    except Exception:
        return None


def load_step_file(filepath):
    """Load and parse a STEP file and return a CadQuery Workplane/Shape."""
    if not filepath:
        raise ValueError("STEP filepath is required")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    normalized_path = _normalize_step_file(filepath)
    xcaf_shape = _load_step_via_xcaf(normalized_path)
    if xcaf_shape is not None:
        return xcaf_shape

    return cq.importers.importStep(normalized_path)


def tessellate_shape(cq_shape, deflection=0.5, angular_deflection=0.5):
    """Tessellate a CadQuery shape into triangle mesh data for 3D rendering."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location

    if hasattr(cq_shape, "val"):
        shape = cq_shape.val()
    elif hasattr(cq_shape, "wrapped"):
        shape = cq_shape
    else:
        shape = cq_shape

    ocp_shape = shape.wrapped if hasattr(shape, "wrapped") else shape

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

            for i in range(1, nb_nodes + 1):
                point = triangulation.Node(i)
                point.Transform(transform)
                vertices.extend([point.X(), point.Y(), point.Z()])

            has_normals = triangulation.HasNormals()
            reversed_face = face.Orientation() == TopAbs_REVERSED

            if has_normals:
                for i in range(1, nb_nodes + 1):
                    normal = triangulation.Normal(i)
                    nx, ny, nz = normal.X(), normal.Y(), normal.Z()
                    if reversed_face:
                        nx, ny, nz = -nx, -ny, -nz
                    normals.extend([nx, ny, nz])
            else:
                for _ in range(nb_nodes):
                    normals.extend([0.0, 0.0, 0.0])

            for t in range(1, nb_triangles + 1):
                tri = triangulation.Triangle(t)
                v1 = tri.Value(1) - 1 + vertex_offset
                v2 = tri.Value(2) - 1 + vertex_offset
                v3 = tri.Value(3) - 1 + vertex_offset
                if reversed_face:
                    indices.extend([v1, v3, v2])
                else:
                    indices.extend([v1, v2, v3])

            vertex_offset += nb_nodes

        explorer.Next()

    return {"vertices": vertices, "indices": indices, "normals": normals}


def extract_display_edges(mesh_data, angle_threshold_deg=32.0, min_length_ratio=0.0025):
    """Extract a cleaner set of display edges from tessellated mesh data."""
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
    diagonal = math.sqrt((max_x - min_x) ** 2 + (max_y - min_y) ** 2 + (max_z - min_z) ** 2)
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
        edge_length = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2)

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
