from __future__ import annotations

import math
from typing import Any, Dict, Optional


def extract_cut_features_for_sheet(
    solid,
    *,
    CutFeaturesCls,
    cq_module,
    detect_holes_fn,
    detect_shaped_holes_fn,
    deduplicate_holes_fn,
    iso_standards,
    logger,
    detect_closed_inner_contours,
    detect_countersunk_holes,
    detect_standalone_countersunk_holes,
    label_contours_from_holes,
    get_outer_contour_length,
    get_bounding_box,
    parse_dimensions_from_string,
    unfold_result: Optional[Dict[str, Any]] = None,
    part_classification: str = "plaat",
):
    try:
        logger.info(f"[CutFeatures] Start extractie voor {part_classification}")

        analysis_shape = solid
        source = "3d"
        if unfold_result and unfold_result.get("success") and unfold_result.get("flat_pattern"):
            logger.info("[CutFeatures] Gebruik flat pattern voor analyse")
            analysis_shape = unfold_result["flat_pattern"]
            source = "flat"
        else:
            logger.info("[CutFeatures] Gebruik 3D solid voor analyse (geen unfold)")

        cq_solid = cq_module.Solid(analysis_shape)
        cq_object = cq_module.Workplane("XY").newObject([cq_solid])
        closed_contours = detect_closed_inner_contours(analysis_shape) if analysis_shape else []
        logger.info(f"[CutFeatures] Gesloten binnencontouren: {len(closed_contours)}")

        is_flat = source == "flat"
        logger.info(f"[CutFeatures] Detect cylindrische gaten (flat={is_flat})...")
        cylindrical_holes = detect_holes_fn(cq_object, filter_bores=True, is_flat_pattern=is_flat)
        logger.info(f"[CutFeatures] Gevonden: {len(cylindrical_holes)} cylindrische gaten")

        logger.info("[CutFeatures] Detect vormgaten (sleuven/rectangles)...")
        cq_workplane = cq_module.Workplane(obj=cq_solid)
        shaped_holes = detect_shaped_holes_fn(cq_workplane)
        logger.info(f"[CutFeatures] Gevonden: {len(shaped_holes)} vormgaten")

        logger.info("[CutFeatures] Dedupliceer overlappende detecties...")
        cylindrical_holes = deduplicate_holes_fn(cylindrical_holes, shaped_holes)
        logger.info(f"[CutFeatures] Na dedup: {len(cylindrical_holes)} cylindrisch, {len(shaped_holes)} vorm")

        hole_contours = []
        hole_radii = []
        hole_types = []
        shaped_types = []
        threaded_holes = 0
        countersunk_holes = 0
        countersunk_angles = []

        countersink_matches = detect_countersunk_holes(cq_object, cylindrical_holes)

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
                thread_matches = iso_standards.identify_thread_from_diameter(hole.diameter, 0.20)
                tapped_matches = [m for m in thread_matches if "tapped" in m.designation.lower()]
                major_matches = [m for m in thread_matches if "tapped" not in m.designation.lower()]
                if tapped_matches and major_matches:
                    tapped_matches = []

                hole_depth = float(getattr(hole, "depth", 0.0) or 0.0)
                if tapped_matches and hole_depth > 0:
                    plausible_matches = [
                        m
                        for m in tapped_matches
                        if float(getattr(m, "major_diameter", 0.0) or 0.0) <= (hole_depth * 1.35)
                    ]
                    tapped_matches = plausible_matches if plausible_matches else []

                if tapped_matches:
                    hole_type = "thread"
                    threaded_holes += 1

            hole_types.append(hole_type)

        for shaped in shaped_holes:
            perimeter = float(shaped.get("perimeter", 0.0) or 0.0)
            if perimeter <= 0:
                dimensions = parse_dimensions_from_string(shaped.get("dim", ""))
                if dimensions:
                    length_dim, width_dim = dimensions
                    if shaped.get("type", "Rect") == "Slot":
                        straight_len = max(0.0, length_dim - width_dim)
                        perimeter = 2.0 * straight_len + math.pi * width_dim
                    else:
                        perimeter = 2.0 * (length_dim + width_dim)
                else:
                    perimeter = 40.0

            hole_contours.append(perimeter)
            shaped_types.append(shaped.get("type", "Unknown"))
            hole_types.append("hole")

        standalone_countersinks = detect_standalone_countersunk_holes(cq_object, cylindrical_holes)
        for cs in standalone_countersinks:
            radius = float(cs.get("inner_radius", 0.0) or 0.0)
            if radius <= 0:
                continue
            hole_contours.append(2.0 * math.pi * radius)
            hole_radii.append(radius)
            hole_types.append("thread")
            threaded_holes += 1

        logger.info("[CutFeatures] Bereken buitencontour...")
        outer_contour = get_outer_contour_length(analysis_shape)
        logger.info(f"[CutFeatures] Buitencontour: {outer_contour:.2f} mm")

        if closed_contours:
            hole_contours = [float(item["perimeter"]) for item in closed_contours]
            label_results = label_contours_from_holes(
                closed_contours,
                cylindrical_holes,
                countersink_matches,
            )
            hole_types = [r["label"] for r in label_results]
            hole_radii = [r["radius"] for r in label_results if r["radius"] is not None]
            threaded_holes = sum(1 for r in label_results if r["label"] == "thread")
            countersunk_holes = sum(1 for r in label_results if r["label"] == "countersunk")
            countersunk_angles = [r["cs_angle"] for r in label_results if r.get("cs_angle") is not None]

        total_contour = sum(hole_contours) + outer_contour
        logger.info(f"[CutFeatures] Totale snijlengte: {total_contour:.2f} mm")

        bbox = get_bounding_box(analysis_shape)
        box_x = bbox["xlen"]
        box_y = bbox["ylen"]
        logger.info(f"[CutFeatures] Box dimensions: X={box_x:.2f} mm, Y={box_y:.2f} mm")

        total_holes = len(closed_contours) if closed_contours else len(hole_types)
        result = CutFeaturesCls(
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
            shaped_types=shaped_types,
        )
        logger.info(f"[CutFeatures] Extractie compleet: {result.to_dict()}")
        return result
    except Exception as exc:
        logger.error(f"[CutFeatures] FOUT tijdens extractie: {exc}", exc_info=True)
        return None


def extract_cut_features_for_profile(
    solid,
    *,
    CutFeaturesCls,
    cq_module,
    detect_holes_fn,
    detect_shaped_holes_fn,
    deduplicate_holes_fn,
    iso_standards,
    logger,
    detect_closed_inner_contours,
    filter_profile_end_opening_shaped_holes,
    infer_profile_countersink_pairs,
    detect_countersunk_holes,
    detect_standalone_countersunk_holes,
    label_contours_from_holes,
    parse_dimensions_from_string,
    part_classification: str = "profiel",
):
    try:
        logger.info(f"[CutFeatures] Start profiel extractie voor {part_classification}")
        source = "3d"

        cq_solid = cq_module.Solid(solid)
        cq_object = cq_module.Workplane("XY").newObject([cq_solid])
        closed_contours = detect_closed_inner_contours(solid) if solid else []

        logger.info("[CutFeatures] Profiel: detect cylindrische gaten...")
        cylindrical_holes = detect_holes_fn(cq_object, filter_bores=False, is_flat_pattern=False)
        logger.info(f"[CutFeatures] Profiel vóór bore-filter: {len(cylindrical_holes)} cylindrische gaten")

        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        longest_dim = max(xmax - xmin, ymax - ymin, zmax - zmin)
        if longest_dim > 0:
            before_count = len(cylindrical_holes)
            cylindrical_holes = [hole for hole in cylindrical_holes if hole.depth <= longest_dim * 0.3]
            filtered_count = before_count - len(cylindrical_holes)
            if filtered_count > 0:
                logger.info(
                    f"[CutFeatures] Profiel bore-filter: {filtered_count} gaten verwijderd "
                    f"(depth > {longest_dim * 0.3:.1f}mm)"
                )

        logger.info(f"[CutFeatures] Profiel: {len(cylindrical_holes)} cylindrische gaten")
        logger.info("[CutFeatures] Profiel: detect vormgaten...")
        cq_workplane = cq_module.Workplane(obj=cq_solid)
        shaped_holes = detect_shaped_holes_fn(cq_workplane)
        shaped_holes = filter_profile_end_opening_shaped_holes(shaped_holes, (xmin, ymin, zmin), (xmax, ymax, zmax))
        closed_contours = filter_profile_end_opening_shaped_holes(
            closed_contours,
            (xmin, ymin, zmin),
            (xmax, ymax, zmax),
        )
        logger.info(f"[CutFeatures] Profiel: {len(closed_contours)} gesloten binnencontouren")
        logger.info(f"[CutFeatures] Profiel: {len(shaped_holes)} vormgaten")

        logger.info("[CutFeatures] Profiel: dedupliceer...")
        cylindrical_holes = deduplicate_holes_fn(cylindrical_holes, shaped_holes)
        logger.info(f"[CutFeatures] Profiel na dedup: {len(cylindrical_holes)} cylindrisch, {len(shaped_holes)} vorm")

        hole_contours = []
        hole_radii = []
        hole_types = []
        shaped_types = []
        threaded_holes = 0
        countersunk_holes = 0
        countersunk_angles = []

        countersink_matches = detect_countersunk_holes(cq_object, cylindrical_holes)
        inferred_countersunk, suppressed_subholes = infer_profile_countersink_pairs(
            cylindrical_holes,
            countersink_matches,
        )

        for idx, hole in enumerate(cylindrical_holes):
            if idx in suppressed_subholes:
                continue

            radius = hole.diameter / 2.0
            hole_contours.append(2.0 * math.pi * radius)
            hole_radii.append(radius)

            hole_type = "round"
            cs_angle = countersink_matches.get(idx)
            if cs_angle is not None or idx in inferred_countersunk:
                hole_type = "countersunk"
                countersunk_holes += 1
                if cs_angle is not None:
                    countersunk_angles.append(cs_angle)
            else:
                thread_matches = iso_standards.identify_thread_from_diameter(hole.diameter, 0.20)
                tapped_matches = [m for m in thread_matches if "tapped" in m.designation.lower()]
                major_matches = [m for m in thread_matches if "tapped" not in m.designation.lower()]

                if tapped_matches and not major_matches:
                    hole_type = "thread"
                    threaded_holes += 1
                elif tapped_matches and major_matches:
                    hole_depth = float(getattr(hole, "depth", 0.0) or 0.0)
                    if hole.diameter <= 6.0 and hole_depth <= max(6.0, hole.diameter * 1.5):
                        for match in tapped_matches:
                            delta = float(match.major_diameter) - float(hole.diameter)
                            if 0.8 <= delta <= 1.4:
                                hole_type = "thread"
                                threaded_holes += 1
                                break

            hole_types.append(hole_type)

        for shaped in shaped_holes:
            perimeter = float(shaped.get("perimeter", 0.0) or 0.0)
            if perimeter <= 0:
                dimensions = parse_dimensions_from_string(shaped.get("dim", ""))
                if dimensions:
                    length_dim, width_dim = dimensions
                    if shaped.get("type", "Rect") == "Slot":
                        straight_len = max(0.0, length_dim - width_dim)
                        perimeter = 2.0 * straight_len + math.pi * width_dim
                    else:
                        perimeter = 2.0 * (length_dim + width_dim)
                else:
                    perimeter = 40.0

            hole_contours.append(perimeter)
            shaped_types.append(shaped.get("type", "Unknown"))
            hole_types.append("hole")

        standalone_countersinks = detect_standalone_countersunk_holes(cq_object, cylindrical_holes)
        for cs in standalone_countersinks:
            radius = float(cs.get("inner_radius", 0.0) or 0.0)
            if radius <= 0:
                continue
            hole_contours.append(2.0 * math.pi * radius)
            hole_radii.append(radius)
            hole_types.append("thread")
            threaded_holes += 1

        outer_contour = 0.0
        if closed_contours:
            hole_contours = [float(item["perimeter"]) for item in closed_contours]
            label_results = label_contours_from_holes(
                closed_contours,
                cylindrical_holes,
                countersink_matches,
                inferred_countersunk=inferred_countersunk,
                is_profile=True,
            )
            hole_types = [r["label"] for r in label_results]
            hole_radii = [r["radius"] for r in label_results if r["radius"] is not None]
            threaded_holes = sum(1 for r in label_results if r["label"] == "thread")
            countersunk_holes = sum(1 for r in label_results if r["label"] == "countersunk")
            countersunk_angles = [r["cs_angle"] for r in label_results if r.get("cs_angle") is not None]
        total_contour = sum(hole_contours)

        total_holes = len(closed_contours) if closed_contours else len(hole_types)
        logger.info(f"[CutFeatures] Profiel: {total_holes} gaten, snijlengte={total_contour:.2f} mm")

        result = CutFeaturesCls(
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
            shaped_types=shaped_types,
        )

        logger.info(f"[CutFeatures] Profiel extractie compleet: {result.to_dict()}")
        return result
    except Exception as exc:
        logger.error(f"[CutFeatures] FOUT tijdens profiel extractie: {exc}", exc_info=True)
        return None
