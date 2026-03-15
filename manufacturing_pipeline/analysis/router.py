"""
Profile Router — pre-classifies STEP solids into manufacturing categories.

Runs the cross-section profile classifier and maps its labels to four
routing categories: PLAAT, PROFIEL, ROND, OVERIG. The manufacturing
pipeline uses this to decide which analysis path to follow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manufacturing_pipeline.core.models import RouteCategory

logger = logging.getLogger("profile_router")

# Label → RouteCategory mapping
_LABEL_MAP: dict[str, RouteCategory] = {
    "PLAT_STAAL": RouteCategory.PLAAT,
    "I_FAMILY": RouteCategory.PROFIEL,
    "U_FAMILY": RouteCategory.PROFIEL,
    "L_FAMILY": RouteCategory.PROFIEL,
    "T_FAMILY": RouteCategory.PROFIEL,
    "RECHTHOEKIGE_KOKER": RouteCategory.PROFIEL,
    "ROND_STAAL": RouteCategory.ROND,
    "RONDE_BUIS": RouteCategory.ROND,
    "ANDERS": RouteCategory.OVERIG,
}


@dataclass
class RouteResult:
    """Result of the pre-routing classification."""
    category: RouteCategory
    profile_label: str       # Original label from profile classifier
    confidence: float        # 0..1
    reasoning: str           # Why this route was chosen
    variant: str | None = None  # Template variant (e.g. "i-b0.55-tw0.08-tf0.14")
    method: str = ""         # "rule", "template", "template-fallback"


def map_profile_label(label: str, confidence: float, variant: str | None = None, method: str = "") -> RouteResult:
    """Map a profile classifier label to a RouteResult."""
    category = _LABEL_MAP.get(label, RouteCategory.OVERIG)

    reasoning_map = {
        RouteCategory.PLAAT: f"Profiel '{label}' is plat staal \u2192 PLAAT route",
        RouteCategory.PROFIEL: f"Profiel '{label}' is een stalen profiel \u2192 PROFIEL route",
        RouteCategory.ROND: f"Profiel '{label}' is rond/buisvormig \u2192 ROND route",
        RouteCategory.OVERIG: f"Profiel '{label}' niet herkend als standaard \u2192 OVERIG route",
    }

    return RouteResult(
        category=category,
        profile_label=label,
        confidence=confidence,
        reasoning=reasoning_map[category],
        variant=variant,
        method=method,
    )


def route_solid(solid_shape: Any) -> RouteResult:
    """Classify a single OCC solid and return a RouteResult.

    Uses the profile classifier's cross-section analysis to determine
    the solid's profile type, then maps to a routing category.
    """
    from manufacturing_pipeline.analysis.profile_classifier import (
        classify_solid_profile,
        ProfileRegistry,
    )

    registry = ProfileRegistry().extend_generic_defaults()
    result = classify_solid_profile(solid_shape, registry=registry)

    return map_profile_label(
        label=result.get("label", "ANDERS"),
        confidence=result.get("confidence", 0.0),
        variant=result.get("variant"),
        method=result.get("method", ""),
    )


def route_step_file(step_path: str | Path) -> RouteResult:
    """Classify a STEP file and return a RouteResult.

    For multi-solid files, classifies the largest solid (by bounding box volume).
    """
    from manufacturing_pipeline.analysis.profile_classifier import (
        read_step_solids,
        read_step_solids_flat,
        classify_solid_profile,
        ProfileRegistry,
        solid_vertices_np,
    )
    import numpy as np

    step_path = str(step_path)

    # Try flat reader first (consistent with manufacturing pipeline)
    solids = []
    for reader in [read_step_solids_flat, read_step_solids]:
        try:
            solids = reader(step_path)
            if solids:
                break
        except Exception as e:
            logger.debug("Reader failed: %s", e)

    if not solids:
        logger.warning("No solids found in %s, routing as OVERIG", step_path)
        return RouteResult(
            category=RouteCategory.OVERIG,
            profile_label="ANDERS",
            confidence=0.0,
            reasoning="Geen solids gevonden in STEP bestand",
        )

    # Pick largest solid by bounding box volume
    best_solid = solids[0]
    best_vol = 0.0
    for s in solids:
        try:
            verts = solid_vertices_np(s.shape)
            dims = verts.max(axis=0) - verts.min(axis=0)
            vol = float(np.prod(dims))
            if vol > best_vol:
                best_vol = vol
                best_solid = s
        except Exception:
            pass

    registry = ProfileRegistry().extend_generic_defaults()
    result = classify_solid_profile(best_solid.shape, registry=registry)

    route = map_profile_label(
        label=result.get("label", "ANDERS"),
        confidence=result.get("confidence", 0.0),
        variant=result.get("variant"),
        method=result.get("method", ""),
    )

    logger.info(
        "Routed %s → %s (%s, confidence=%.2f)",
        Path(step_path).name,
        route.category.value,
        route.profile_label,
        route.confidence,
    )
    return route
