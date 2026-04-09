"""Compatibility shim for environments where FreeCAD's new unfolder is absent.

This module exposes a subset of the SheetMetalNewUnfolder API used by the
pipeline. It delegates to the vendored legacy SheetMetalUnfolder implementation
so callers can keep using the same import path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import Part  # type: ignore

import SheetMetalUnfolder  # type: ignore


_DEFAULT_K_BUCKETS = (
    0.5,
    0.75,
    1.0,
    1.5,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
    8.0,
    10.0,
    12.0,
    15.0,
    20.0,
)


@dataclass
class BendAllowanceCalculator:
    """Minimal compatibility with the API expected by runtime_unfold/worker."""

    k_factor: float
    standard: str = "ansi"

    @classmethod
    def from_single_value(cls, value: float, standard: str = "ansi") -> "BendAllowanceCalculator":
        return cls(k_factor=float(value), standard=str(standard))


def _face_from_facename(shape: Any, facename: str):
    token = str(facename or "")
    if not token.startswith("Face"):
        raise ValueError(f"Invalid face token: {facename!r}")
    idx = int(token[4:]) - 1
    faces = getattr(shape, "Faces", None) or []
    if idx < 0 or idx >= len(faces):
        raise IndexError(f"Face index out of range for {facename!r}")
    return idx, faces[idx]


def _k_lookup_from_bac(bac: BendAllowanceCalculator | None) -> dict[float, float]:
    k_value = float(getattr(bac, "k_factor", 0.44) or 0.44)
    return {float(bucket): k_value for bucket in _DEFAULT_K_BUCKETS}


def getUnfold(
    bac: BendAllowanceCalculator,
    obj: Any,
    facename: str,
):
    """Shim signature that mirrors SheetMetalNewUnfolder.getUnfold().

    Returns:
    - selected_face
    - unfolded_shape
    - bend_lines_compound
    - root_normal
    - bend_infos (best-effort empty list in shim mode)
    """

    shape = getattr(obj, "Shape", None)
    if shape is None:
        raise RuntimeError("Object has no Shape for unfolding")

    _face_idx, selected_face = _face_from_facename(shape, facename)
    k_lookup = _k_lookup_from_bac(bac)

    unfolded_shape, fold_compound, root_normal, _name, err_code, _face_sel, _obj_name = SheetMetalUnfolder.getUnfold(
        k_lookup,
        obj,
        selected_face,
        facename,
    )

    if err_code:
        raise RuntimeError(f"Legacy unfold returned error code {err_code}")
    if unfolded_shape is None:
        raise RuntimeError("Legacy unfold returned no unfolded shape")

    # Keep return contract compatible with the new unfolder API.
    bend_lines_compound = fold_compound if fold_compound is not None else Part.Compound([])
    bend_infos = []
    return selected_face, unfolded_shape, bend_lines_compound, root_normal, bend_infos

