from __future__ import annotations

from typing import Optional, Tuple

from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result

try:
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False


def _get_surface_area(solid) -> Optional[float]:
    if not _HAS_OCP:
        return None
    try:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(solid, props)
        surface_area = float(props.Mass())
        return surface_area if surface_area > 0 else None
    except Exception:
        return None


def _step_0_5_solid_profile_fallback(
    solid, dims: Tuple[float, float, float], volume: float
) -> Step0Result:
    from manufacturing_pipeline.analysis.classification_variables import (
        PROFILE_CROSS_RATIO_MAX,
        PROFILE_CROSS_RATIO_MIN,
        PROFILE_LENGTH_RATIO_MIN,
        PROFILE_SA_V_RATIO_MAX,
        PROFILE_SMALLEST_MIN_MM,
        PROFILE_VOLUME_RATIO_STRONG_MIN,
        PROFILE_VOLUME_RATIO_WEAK_MIN,
    )

    smallest, middle, longest = dims
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
    length_ratio = longest / middle if middle > 0 else 0.0
    cross_ratio = middle / smallest if smallest > 0 else 0.0

    if (
        smallest >= PROFILE_SMALLEST_MIN_MM
        and length_ratio >= PROFILE_LENGTH_RATIO_MIN
        and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX
    ):
        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            return _result(
                label="PROFIEL",
                step="0.5",
                method="fallback",
                confidence=0.78,
                fallthrough=False,
                reason=f"massief profiel fallback (vol_ratio={volume_ratio:.3f} sterk)",
            )

        if volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            surface_area = _get_surface_area(solid)
            if surface_area is not None and volume > 0:
                sa_v_ratio = surface_area / volume
                if sa_v_ratio < PROFILE_SA_V_RATIO_MAX:
                    return _result(
                        label="PROFIEL",
                        step="0.5",
                        method="fallback",
                        confidence=0.70,
                        fallthrough=False,
                        reason=f"massief profiel SA/V tiebreaker ({sa_v_ratio:.3f})",
                        features={
                            "volume_ratio": volume_ratio,
                            "sa_v_ratio": sa_v_ratio,
                        },
                    )

    return _result(
        label="ANDERS",
        step="0.5",
        method="fallback",
        confidence=0.55,
        fallthrough=True,
        reason="geen classificatie gevonden in STEP 0; doorval naar Step 1",
        features={
            "volume_ratio": volume_ratio,
            "length_ratio": length_ratio,
            "cross_ratio": cross_ratio,
        },
    )
