from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import cadquery as cq


def _get_bounding_box(shape) -> Dict[str, float]:
    try:
        cq_shape = cq.Shape(shape)
        bb = cq_shape.BoundingBox()
        return {"xlen": bb.xlen, "ylen": bb.ylen, "zlen": bb.zlen}
    except Exception:
        return {"xlen": 0.0, "ylen": 0.0, "zlen": 0.0}


def _parse_dimensions_from_string(dim_str: str) -> Optional[tuple]:
    try:
        if not dim_str or "x" not in dim_str:
            return None
        parts = dim_str.lower().split("x")
        if len(parts) != 2:
            return None
        length = float(parts[0].strip())
        width = float(parts[1].strip())
        return (length, width)
    except Exception:
        return None


def _filter_profile_end_opening_shaped_holes(
    shaped_holes: List[Dict[str, Any]],
    bbox_min: Tuple[float, float, float],
    bbox_max: Tuple[float, float, float],
    *,
    normalize_vector: Callable[[Any], Any],
    as_point_tuple: Callable[[Any], Any],
    dot: Callable[[Any, Any], float],
    parse_dimensions: Callable[[str], Optional[tuple]],
) -> List[Dict[str, Any]]:
    if not shaped_holes:
        return shaped_holes

    dims = [
        float(bbox_max[0] - bbox_min[0]),
        float(bbox_max[1] - bbox_min[1]),
        float(bbox_max[2] - bbox_min[2]),
    ]
    longest_dim = max(dims)
    if longest_dim <= 0:
        return shaped_holes

    axis_idx = int(max(range(3), key=lambda i: dims[i]))
    cross_dims = sorted([dims[i] for i in range(3) if i != axis_idx])
    if len(cross_dims) != 2 or cross_dims[0] <= 0 or cross_dims[1] <= 0:
        return shaped_holes

    axis_vector = [0.0, 0.0, 0.0]
    axis_vector[axis_idx] = 1.0
    axis_min = float(bbox_min[axis_idx])
    axis_max = float(bbox_max[axis_idx])
    end_band = max(2.0, longest_dim * 0.05)

    kept: List[Dict[str, Any]] = []
    for shaped in shaped_holes:
        normal = normalize_vector(as_point_tuple(shaped.get("normal")))
        center = as_point_tuple(shaped.get("center"))
        parsed_dims = parse_dimensions(str(shaped.get("dim", "")))

        if normal is None or center is None or parsed_dims is None:
            kept.append(shaped)
            continue

        axis_alignment = abs(dot(tuple(axis_vector), normal))
        if axis_alignment < 0.95:
            kept.append(shaped)
            continue

        axis_pos = float(center[axis_idx])
        end_distance = min(abs(axis_pos - axis_min), abs(axis_pos - axis_max))
        if end_distance > end_band:
            kept.append(shaped)
            continue

        dim_a, dim_b = parsed_dims
        max_dim = max(dim_a, dim_b)
        min_dim = min(dim_a, dim_b)
        is_large_end_opening = (
            max_dim >= cross_dims[1] * 0.60 and min_dim >= cross_dims[0] * 0.50
        )
        if is_large_end_opening:
            continue

        kept.append(shaped)

    return kept


def _infer_profile_countersink_pairs(
    cylindrical_holes,
    countersink_matches: Dict[int, float],
    *,
    normalize_vector: Callable[[Any], Any],
    dot: Callable[[Any, Any], float],
    as_point_tuple: Callable[[Any], Any],
    distance_point_to_axis: Callable[[Any, Any, Any], float],
    signed_axis_distance: Callable[[Any, Any, Any], float],
) -> Tuple[set, set]:
    inferred: set = set()
    suppressed: set = set()

    if not cylindrical_holes:
        return inferred, suppressed

    for i, large in enumerate(cylindrical_holes):
        if i in countersink_matches:
            continue

        best_j = None
        best_score = None

        for j, small in enumerate(cylindrical_holes):
            if i == j or j in suppressed or j in countersink_matches:
                continue
            if float(large.diameter) <= float(small.diameter):
                continue

            ratio = float(large.diameter) / max(float(small.diameter), 1e-9)
            if ratio < 1.6 or ratio > 2.6:
                continue

            a = normalize_vector(getattr(large, "axis", None))
            b = normalize_vector(getattr(small, "axis", None))
            if a is None or b is None:
                continue
            if abs(dot(a, b)) < 0.98:
                continue

            p_large = as_point_tuple(getattr(large, "position", None))
            p_small = as_point_tuple(getattr(small, "position", None))
            if p_large is None or p_small is None:
                continue

            perp = distance_point_to_axis(p_small, p_large, a)
            if perp > 4.0:
                continue

            axial = abs(signed_axis_distance(p_small, p_large, a))
            if axial < 5.0 or axial > 30.0:
                continue

            depth_large = float(getattr(large, "depth", 0.0) or 0.0)
            depth_small = float(getattr(small, "depth", 0.0) or 0.0)
            if abs(depth_large - depth_small) > 2.0:
                continue

            score = perp + 0.05 * abs(axial - 15.0)
            if best_score is None or score < best_score:
                best_score = score
                best_j = j

        if best_j is not None:
            inferred.add(i)
            suppressed.add(best_j)

    return inferred, suppressed
