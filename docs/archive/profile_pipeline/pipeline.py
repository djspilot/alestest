"""Core pipeline: STEP → solids → sections → classification."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Polygon, MultiPolygon

from manufacturing_pipeline.analysis.profile_classifier import (
    Section2D,
    SolidInstance,
    ProfileRegistry,
    read_step_solids,
    read_step_solids_flat,
    solid_vertices_np,
    find_extrusion_axis,
    section_plane_positions_from_vertices,
    slice_solid_to_section,
    dominant_section_cluster,
    normalize_section_polygon,
    section_distance,
    extract_section_features,
    classify_section,
)

from .config import PipelineConfig
from .result import SolidResult, SectionResult, ClassificationResult

logger = logging.getLogger("profile_pipeline")


# ---------------------------------------------------------------------------
# STEP reading
# ---------------------------------------------------------------------------

def _read_solids(step_path: str, strategy: str) -> list[SolidInstance]:
    """Read STEP file with configurable reader strategy."""
    readers = {
        "flat_first": [("flat", read_step_solids_flat), ("xde", read_step_solids)],
        "xde_first": [("xde", read_step_solids), ("flat", read_step_solids_flat)],
        "flat_only": [("flat", read_step_solids_flat)],
        "xde_only": [("xde", read_step_solids)],
    }

    for name, reader_fn in readers.get(strategy, readers["flat_first"]):
        try:
            logger.info("Trying %s reader for %s", name, step_path)
            solids = reader_fn(str(step_path))
            if solids:
                logger.info("%s reader found %d solid(s)", name, len(solids))
                return solids
        except Exception as e:
            logger.warning("%s reader failed: %s", name, e)

    raise RuntimeError(f"Could not read any solids from {step_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _polygon_to_dict(poly: Polygon | None) -> dict | None:
    if poly is None or poly.is_empty:
        return None
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    return {
        "outer": [[round(x, 6), round(y, 6)] for x, y in poly.exterior.coords],
        "holes": [
            [[round(x, 6), round(y, 6)] for x, y in ring.coords]
            for ring in poly.interiors
        ],
    }


def _features_to_dict(features) -> dict:
    return {
        "area": round(features.area, 6),
        "perimeter": round(features.perimeter, 6),
        "compactness": round(features.compactness, 6),
        "convexity": round(features.convexity, 6),
        "bbox_ratio": round(features.bbox_ratio, 6),
        "bbox_fill": round(features.bbox_fill, 6),
        "holes": features.holes,
        "symmetry_angles_deg": [round(a, 2) for a in features.symmetry_angles_deg],
        "symmetry_scores": [round(s, 4) for s in features.symmetry_scores],
        "reentrant_corners": features.reentrant_corners,
        "line_length_fraction": round(features.line_length_fraction, 4),
        "curve_length_fraction": round(features.curve_length_fraction, 4),
    }


# ---------------------------------------------------------------------------
# Single solid processing
# ---------------------------------------------------------------------------

def _process_solid(
    solid: SolidInstance,
    index: int,
    config: PipelineConfig,
    registry: ProfileRegistry,
) -> SolidResult | None:
    """Analyse a single solid. Returns None if analysis fails."""

    # Axis detection
    axis = find_extrusion_axis(solid.shape)
    if axis is None:
        logger.warning("Solid %d: no extrusion axis found, skipping", index)
        return None

    # Vertices & bounding box
    vertices = solid_vertices_np(solid.shape)
    bbox_min = vertices.min(axis=0).tolist()
    bbox_max = vertices.max(axis=0).tolist()

    # Section fractions
    fracs = config.section_fractions()
    positions = section_plane_positions_from_vertices(vertices, axis.direction, fracs)

    # Compute sections
    sections: list[SectionResult] = []
    valid_sections: list[Section2D] = []

    for frac, pos in zip(fracs, positions):
        plane_origin = axis.direction * pos

        try:
            sec = slice_solid_to_section(
                solid.shape,
                plane_origin=plane_origin,
                plane_normal=axis.direction,
                section_position=pos,
            )
        except Exception as e:
            logger.debug("Solid %d section at %.0f%%: %s", index, frac * 100, e)
            sec = None

        is_valid = sec is not None and not sec.polygon.is_empty and sec.polygon.area > 0

        sr = SectionResult(
            position_frac=frac,
            position_abs=round(pos, 6),
            plane_origin=[round(x, 6) for x in plane_origin.tolist()],
            plane_normal=[round(x, 6) for x in axis.direction.tolist()],
            is_valid=is_valid,
        )

        if is_valid:
            valid_sections.append(sec)
            if config.include_polygon_coords:
                sr.polygon = _polygon_to_dict(sec.polygon)
            if config.include_features:
                sr.features = _features_to_dict(extract_section_features(sec))

        sections.append(sr)

    # Enough sections?
    if len(valid_sections) < config.min_valid_sections:
        logger.warning(
            "Solid %d: only %d valid sections (need %d)",
            index, len(valid_sections), config.min_valid_sections,
        )
        return None

    # Dominant cluster + medoid
    cluster = dominant_section_cluster(valid_sections)
    stability = len(cluster) / max(len(valid_sections), 1)

    if stability < config.cluster_stability_ratio:
        logger.warning("Solid %d: cluster stability %.2f < %.2f", index, stability, config.cluster_stability_ratio)
        return None

    normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
    dsum = [
        sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
        for i, a in enumerate(normalized)
    ]
    core = cluster[int(np.argmin(dsum))]

    # Classification
    result = classify_section(core, registry=registry, template_accept_threshold=config.template_accept_threshold)

    top_matches = None
    if config.include_top_matches and "top_matches" in result:
        top_matches = [
            {"family": m.family, "variant": m.variant, "score": round(m.score, 6)}
            for m in result["top_matches"]
        ]

    classification = ClassificationResult(
        label=result["label"],
        method=result["method"],
        variant=result.get("variant"),
        top_matches=top_matches,
    )

    # Core section output
    core_section = SectionResult(
        position_frac=core.source_position,
        position_abs=round(float(core.source_position), 6),
        plane_origin=[0, 0, 0],
        plane_normal=[round(x, 6) for x in axis.direction.tolist()],
        is_valid=True,
    )
    if config.include_polygon_coords:
        core_section.polygon = _polygon_to_dict(core.polygon)
    if config.include_features:
        core_section.features = _features_to_dict(extract_section_features(core))

    # Optional 3D vertices
    verts_3d = None
    if config.include_vertices:
        if len(vertices) > config.max_vertices_export:
            idx = np.linspace(0, len(vertices) - 1, config.max_vertices_export, dtype=int)
            vertices = vertices[idx]
        verts_3d = [[round(x, 4) for x in v.tolist()] for v in vertices]

    logger.info(
        "Solid %d (%s): %s [%s]",
        index,
        solid.debug_name or solid.instance_id,
        classification.label,
        classification.method,
    )

    return SolidResult(
        name=solid.debug_name or solid.instance_id,
        instance_id=solid.instance_id,
        units=solid.units,
        axis_direction=[round(x, 6) for x in axis.direction.tolist()],
        axis_origin=[round(x, 6) for x in axis.origin.tolist()],
        axis_source=axis.source,
        axis_score=round(axis.score, 4),
        bounding_box_min=[round(x, 4) for x in bbox_min],
        bounding_box_max=[round(x, 4) for x in bbox_max],
        classification=classification,
        sections=sections,
        core_section=core_section,
        cluster_size=len(cluster),
        sections_total=len(valid_sections),
        vertices_3d=verts_3d,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_step_solids(
    solids: list[SolidInstance],
    config: PipelineConfig | None = None,
) -> list[SolidResult]:
    """Classify pre-loaded SolidInstance objects.

    Use this when you already have solids from your own STEP reader.
    """
    config = config or PipelineConfig()
    registry = ProfileRegistry().extend_generic_defaults()
    results = []

    for i, solid in enumerate(solids):
        if config.solid_filter and not config.solid_filter(solid, i):
            logger.debug("Solid %d filtered out", i)
            continue
        try:
            result = _process_solid(solid, i, config, registry)
        except Exception as e:
            logger.error("Solid %d failed: %s", i, e)
            result = None
        if result is not None:
            results.append(result)

    return results


def classify_step_file(
    step_path: str | Path,
    config: PipelineConfig | None = None,
    output_json: str | Path | None = None,
) -> list[SolidResult]:
    """End-to-end: read STEP file → classify all solids → return results.

    Args:
        step_path: Path to .stp / .step file.
        config: Pipeline configuration. Uses defaults if None.
        output_json: If set, write results to this JSON file.

    Returns:
        List of SolidResult for each successfully classified solid.

    Example:
        >>> results = classify_step_file("model.stp")
        >>> for r in results:
        ...     print(r.name, r.classification.label)

        >>> # With custom config
        >>> cfg = PipelineConfig(num_sections=3, include_vertices=True)
        >>> results = classify_step_file("model.stp", config=cfg, output_json="out.json")
    """
    config = config or PipelineConfig()
    step_path = Path(step_path)

    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    solids = _read_solids(str(step_path), config.reader_strategy)
    logger.info("Read %d solid(s) from %s", len(solids), step_path.name)

    results = classify_step_solids(solids, config)

    if output_json is not None:
        output = {
            "source_file": step_path.name,
            "total_solids": len(solids),
            "classified_solids": len(results),
            "config": {
                "num_sections": config.num_sections,
                "section_range": list(config.section_range),
                "template_accept_threshold": config.template_accept_threshold,
            },
            "solids": [r.to_dict() for r in results],
        }
        out_path = Path(output_json)
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Written to %s", out_path)

    return results
