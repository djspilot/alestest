from __future__ import annotations

import math


def _vector_components(value):
    """Extract numeric XYZ components from FreeCAD/OCP point-like objects."""
    for names in (("x", "y", "z"), ("X", "Y", "Z")):
        if all(hasattr(value, name) for name in names):
            return tuple(float(getattr(value, name)) for name in names)

    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])

    raise TypeError(f"Unsupported vector type: {type(value)!r}")


def _normalize_components(x_value, y_value, z_value):
    length = math.sqrt(x_value * x_value + y_value * y_value + z_value * z_value)
    if length <= 1e-9:
        raise ValueError("Zero-length vector")
    return x_value / length, y_value / length, z_value / length


def _find_largest_planar_face(shape):
    """Return the largest planar face of a FreeCAD shape, if any."""
    largest_face = None
    largest_area = -1.0

    for face in getattr(shape, "Faces", []):
        try:
            surface = getattr(face, "Surface", None)
            if surface is None or "Plane" not in getattr(surface, "TypeId", ""):
                continue

            area = float(face.Area)
            if area > largest_area:
                largest_face = face
                largest_area = area
        except Exception:
            continue

    return largest_face


def _choose_plane_basis(normal):
    """Build a stable in-plane basis from a face normal."""
    nx_value, ny_value, nz_value = _normalize_components(*_vector_components(normal))

    best_projection = None
    best_axis = None
    best_length = -1.0
    for axis in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        dot = axis[0] * nx_value + axis[1] * ny_value + axis[2] * nz_value
        proj_x = axis[0] - dot * nx_value
        proj_y = axis[1] - dot * ny_value
        proj_z = axis[2] - dot * nz_value
        proj_len = math.sqrt(proj_x * proj_x + proj_y * proj_y + proj_z * proj_z)

        if proj_len > best_length:
            best_length = proj_len
            best_projection = (proj_x, proj_y, proj_z)
            best_axis = axis

    if best_projection is None or best_length <= 1e-9:
        raise ValueError("Could not derive plane basis")

    ux_value, uy_value, uz_value = _normalize_components(*best_projection)
    vx_value = ny_value * uz_value - nz_value * uy_value
    vy_value = nz_value * ux_value - nx_value * uz_value
    vz_value = nx_value * uy_value - ny_value * ux_value
    vx_value, vy_value, vz_value = _normalize_components(vx_value, vy_value, vz_value)

    return {
        "u": (ux_value, uy_value, uz_value),
        "v": (vx_value, vy_value, vz_value),
        "normal": (nx_value, ny_value, nz_value),
        "reference_axis": best_axis,
    }


def _sample_edge_points(shape, samples_per_edge=33):
    """Sample a shape's edges densely enough to capture arc extents."""
    sample_points = []
    for edge in getattr(shape, "Edges", []):
        points = None
        try:
            points = edge.discretize(samples_per_edge)
        except Exception:
            try:
                points = edge.discretize(Number=samples_per_edge)
            except Exception:
                points = None

        if not points:
            try:
                points = [edge.firstVertex().Point, edge.lastVertex().Point]
            except Exception:
                points = None

        if points:
            for point in points:
                try:
                    sample_points.append(_vector_components(point))
                except Exception:
                    continue

    if sample_points:
        return sample_points

    for vertex in getattr(shape, "Vertexes", []):
        try:
            sample_points.append(_vector_components(vertex.Point))
        except Exception:
            continue

    return sample_points


def _measure_flat_pattern_dimensions(flat_shape):
    """Measure a flat pattern in its own plane instead of global XYZ."""
    bbox = flat_shape.BoundBox
    raw_bbox = (
        float(bbox.XLength),
        float(bbox.YLength),
        float(bbox.ZLength),
    )
    raw_sorted = sorted(raw_bbox, reverse=True)

    dims = {
        "flat_length": raw_sorted[0],
        "flat_width": raw_sorted[1],
        "raw_bbox": raw_bbox,
        "projection_used": False,
        "reference_axis": None,
    }

    planar_face = _find_largest_planar_face(flat_shape)
    if planar_face is None:
        return dims

    try:
        basis = _choose_plane_basis(planar_face.normalAt(0, 0))
        sample_points = _sample_edge_points(flat_shape)
        if len(sample_points) < 2:
            return dims

        projected = []
        ux_value, uy_value, uz_value = basis["u"]
        vx_value, vy_value, vz_value = basis["v"]
        for point in sample_points:
            px_value, py_value, pz_value = point
            u_coord = px_value * ux_value + py_value * uy_value + pz_value * uz_value
            v_coord = px_value * vx_value + py_value * vy_value + pz_value * vz_value
            projected.append((u_coord, v_coord))

        u_values = [value[0] for value in projected]
        v_values = [value[1] for value in projected]
        length = max(u_values) - min(u_values)
        width = max(v_values) - min(v_values)
        if width > length:
            length, width = width, length

        if length > 0 and width > 0:
            dims.update(
                {
                    "flat_length": float(length),
                    "flat_width": float(width),
                    "projection_used": True,
                    "reference_axis": basis["reference_axis"],
                }
            )
    except Exception:
        pass

    return dims
