from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cadquery as cq

from manufacturing_pipeline.analysis.cut_features import (
    _detect_closed_inner_contours,
    _detect_countersunk_holes,
    _filter_profile_end_opening_shaped_holes,
    _filter_contours_for_excluded_holes,
    _infer_profile_countersink_pairs,
    _detect_standalone_countersunk_holes,
    _label_contours_from_holes,
    deduplicate_holes,
    detect_holes,
    detect_shaped_holes,
)
from manufacturing_pipeline.analysis.features.hole_detection import precompute_face_properties
from manufacturing_pipeline.analysis.io.step_file_io import load_step_file


@dataclass
class HoleRow:
    index: int
    source: str
    hole_type: str
    cut_length_mm: float
    diameter_mm: float | None = None
    note: str | None = None


def _ensure_workplane(shape_obj: Any) -> cq.Workplane:
    if isinstance(shape_obj, cq.Workplane):
        return shape_obj

    if hasattr(shape_obj, "wrapped"):
        return cq.Workplane("XY").newObject([shape_obj])

    if hasattr(shape_obj, "val"):
        val = shape_obj.val()
        return cq.Workplane("XY").newObject([val])

    return cq.Workplane(obj=shape_obj)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_criteria(criteria: Sequence[Dict[str, Any]]) -> str:
    if not criteria:
        return "-"

    parts: List[str] = []
    for criterion in criteria:
        name = str(criterion.get("name", "?")).strip() or "?"
        passed = bool(criterion.get("passed", False))
        value = criterion.get("value")
        threshold = criterion.get("threshold")
        note = criterion.get("note")

        status = "OK" if passed else "NOK"
        value_txt = f"value={value}" if value is not None else "value=-"
        threshold_txt = f"threshold={threshold}" if threshold is not None else "threshold=-"
        note_txt = f"note={note}" if note else ""
        line = f"{name}({status}; {value_txt}; {threshold_txt}"
        if note_txt:
            line += f"; {note_txt}"
        line += ")"
        parts.append(line)

    return " | ".join(parts)


def _print_rows(rows: Sequence[HoleRow]) -> None:
    if not rows:
        print("Geen gaten gerapporteerd.")
        return

    print("\nSnijlengte per gat:")
    for row in rows:
        diameter_txt = f", diameter={row.diameter_mm:.2f} mm" if row.diameter_mm is not None else ""
        note_txt = f", note={row.note}" if row.note else ""
        print(
            f"- Gat {row.index:02d}: type={row.hole_type}, source={row.source}, "
            f"snijlengte={row.cut_length_mm:.3f} mm{diameter_txt}{note_txt}"
        )


def _print_debug(title: str, items: Sequence[Dict[str, Any]]) -> None:
    print(f"\n{title} ({len(items)}):")
    if not items:
        print("- Geen regels")
        return

    for item in items:
        item_id = item.get("id")
        status = item.get("status", "unknown")
        item_type = item.get("type", "unknown")
        label = item.get("label") or item.get("size") or "-"
        reason = item.get("reason", "-")
        criteria = _format_criteria(item.get("criteria") or [])
        print(
            f"- [{status}] id={item_id}, type={item_type}, label={label}, "
            f"reason={reason}"
        )
        print(f"  criteria: {criteria}")


def _build_rows_from_closed_contours(
    closed_contours: Sequence[Dict[str, Any]],
    contour_labels: Sequence[Dict[str, Any]],
) -> List[HoleRow]:
    rows: List[HoleRow] = []
    for idx, contour in enumerate(closed_contours, start=1):
        label_info = contour_labels[idx - 1] if idx - 1 < len(contour_labels) else {}
        hole_type = str(label_info.get("label") or "hole")
        radius = label_info.get("radius")
        diameter = _safe_float(radius, 0.0) * 2.0 if radius is not None else None
        rows.append(
            HoleRow(
                index=idx,
                source="closed_contour",
                hole_type=hole_type,
                cut_length_mm=_safe_float(contour.get("perimeter"), 0.0),
                diameter_mm=diameter,
            )
        )
    return rows


def _build_rows_from_fallback(
    cylindrical_holes: Sequence[Any],
    countersink_matches: Dict[int, float],
    shaped_holes: Sequence[Dict[str, Any]],
) -> List[HoleRow]:
    rows: List[HoleRow] = []
    next_index = 1

    for idx, hole in enumerate(cylindrical_holes):
        diameter = _safe_float(getattr(hole, "diameter", 0.0), 0.0)
        radius = diameter / 2.0
        perimeter = 2.0 * math.pi * radius
        hole_type = "countersunk" if idx in countersink_matches else "round"
        rows.append(
            HoleRow(
                index=next_index,
                source="cylindrical_fallback",
                hole_type=hole_type,
                cut_length_mm=perimeter,
                diameter_mm=diameter,
            )
        )
        next_index += 1

    for shaped in shaped_holes:
        rows.append(
            HoleRow(
                index=next_index,
                source="shaped_fallback",
                hole_type="hole",
                cut_length_mm=_safe_float(shaped.get("perimeter"), 0.0),
                diameter_mm=None,
                note=str(shaped.get("type") or "Unknown"),
            )
        )
        next_index += 1

    return rows


def _build_open_contour_note(criteria_items: Sequence[Dict[str, Any]]) -> str | None:
    open_like_ids: List[str] = []
    for item in criteria_items:
        if str(item.get("status") or "").lower() != "rejected":
            continue
        item_id = str(item.get("id") or "")
        for criterion in item.get("criteria") or []:
            name = str(criterion.get("name") or "").strip().lower()
            passed = bool(criterion.get("passed", True))
            if name == "angle_coverage" and not passed:
                if item_id:
                    open_like_ids.append(item_id)
                break

    if not open_like_ids:
        return None

    unique_ids = list(dict.fromkeys(open_like_ids))
    sample = ", ".join(unique_ids[:5])
    return (
        "open_contour_candidate_not_counted: "
        f"{len(unique_ids)} kandidaat(en) afgewezen (onvoldoende angle coverage; vermoedelijk niet-gesloten/open contour). "
        f"Voorbeelden: {sample}"
    )


def analyze_step_holes(step_path: Path, part_mode: str) -> Dict[str, Any]:
    loaded = load_step_file(str(step_path))
    workplane = _ensure_workplane(loaded)

    solids = workplane.solids().vals()
    if not solids:
        solids = [workplane.val()]

    all_rows: List[HoleRow] = []
    all_debug: List[Dict[str, Any]] = []

    for solid_index, solid in enumerate(solids, start=1):
        wp = cq.Workplane("XY").newObject([solid])
        face_data = precompute_face_properties(wp)

        cylindrical_holes, cyl_debug = detect_holes(
            wp,
            filter_bores=(part_mode != "profile"),
            is_flat_pattern=(part_mode == "plate"),
            face_data=face_data,
            return_debug=True,
        )
        shaped_holes, shaped_debug = detect_shaped_holes(
            wp,
            face_data=face_data,
            is_flat_pattern=(part_mode == "plate"),
            return_debug=True,
        )

        closed_contours = _detect_closed_inner_contours(solid.wrapped)

        if part_mode == "profile":
            # Keep validation aligned with profile production logic:
            # profile end openings should not count as closed hole contours.
            try:
                from OCP.Bnd import Bnd_Box
                from OCP.BRepBndLib import BRepBndLib

                bbox = Bnd_Box()
                BRepBndLib.Add_s(solid.wrapped if hasattr(solid, "wrapped") else solid, bbox)
                xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
                bbox_min = (xmin, ymin, zmin)
                bbox_max = (xmax, ymax, zmax)
                shaped_holes = _filter_profile_end_opening_shaped_holes(shaped_holes, bbox_min, bbox_max)
                closed_contours = _filter_profile_end_opening_shaped_holes(closed_contours, bbox_min, bbox_max)
            except Exception:
                pass

        cylindrical_holes, dedup_debug = deduplicate_holes(
            cylindrical_holes,
            shaped_holes,
            return_debug=True,
        )

        countersink_matches = _detect_countersunk_holes(wp, cylindrical_holes)
        standalone_cs = _detect_standalone_countersunk_holes(wp, cylindrical_holes)
        inferred_countersunk = set()
        suppressed_subholes = set()

        if part_mode == "profile":
            inferred_countersunk, suppressed_subholes = _infer_profile_countersink_pairs(
                cylindrical_holes,
                countersink_matches,
            )
            if suppressed_subholes and closed_contours:
                closed_contours = _filter_contours_for_excluded_holes(
                    closed_contours,
                    cylindrical_holes,
                    suppressed_subholes,
                )

        contour_labels = _label_contours_from_holes(
            closed_contours,
            cylindrical_holes,
            countersink_matches,
            inferred_countersunk=inferred_countersunk,
            is_profile=(part_mode == "profile"),
        )

        if closed_contours:
            rows = _build_rows_from_closed_contours(closed_contours, contour_labels)
        else:
            rows = _build_rows_from_fallback(cylindrical_holes, countersink_matches, shaped_holes)

        for row in rows:
            row.note = f"solid_{solid_index}" if not row.note else f"{row.note}, solid_{solid_index}"
        all_rows.extend(rows)

        if standalone_cs:
            for cs in standalone_cs:
                radius = _safe_float(cs.get("inner_radius"), 0.0)
                if radius > 0:
                    all_rows.append(
                        HoleRow(
                            index=len(all_rows) + 1,
                            source="standalone_countersink",
                            hole_type="countersunk",
                            cut_length_mm=2.0 * math.pi * radius,
                            diameter_mm=2.0 * radius,
                            note=f"solid_{solid_index}",
                        )
                    )

        all_debug.extend(cyl_debug)
        all_debug.extend(shaped_debug)
        all_debug.extend(dedup_debug)

    rows_sorted = list(all_rows)
    for idx, row in enumerate(rows_sorted, start=1):
        row.index = idx

    total_holes = len(rows_sorted)
    threaded = sum(1 for row in rows_sorted if row.hole_type == "thread")
    countersunk = sum(1 for row in rows_sorted if "countersunk" in row.hole_type)

    total_cut_length = sum(row.cut_length_mm for row in rows_sorted)

    notes = [
        "Aantal gaten + snijlengte per gat volgen closed inner contours als die gevonden zijn.",
        "Draadgat-herkenning gebruikt de actieve ISO-threadtabellen (M3 t/m M24 met tap- en major-diameters).",
        "Criteria en afwijsredenen komen direct uit detect_holes, detect_shaped_holes en deduplicate_holes debug-output.",
    ]
    open_note = _build_open_contour_note(all_debug)
    if open_note:
        notes.append(open_note)

    return {
        "step_path": str(step_path),
        "part_mode": part_mode,
        "summary": {
            "aantal_gaten": total_holes,
            "aantal_draadgaten": threaded,
            "aantal_verzonken_gaten": countersunk,
            "totale_snijlengte_mm": total_cut_length,
        },
        "holes": [
            {
                "index": row.index,
                "source": row.source,
                "type": row.hole_type,
                "snijlengte_mm": row.cut_length_mm,
                "diameter_mm": row.diameter_mm,
                "note": row.note,
            }
            for row in rows_sorted
        ],
        "criteria": all_debug,
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valideer gatdetectie op een STEP-file met criteria/afwijsredenen.",
    )
    parser.add_argument("--step", required=True, help="Pad naar STEP-file")
    parser.add_argument(
        "--part-mode",
        choices=["plate", "profile"],
        default="plate",
        help="Kies plate (plaat) of profile (profiel) voor gating/labels.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print volledige output als JSON in plaats van tekst.",
    )
    args = parser.parse_args()

    step_path = Path(args.step).expanduser().resolve()
    if not step_path.exists():
        print(f"STEP-file niet gevonden: {step_path}")
        return 2

    result = analyze_step_holes(step_path, args.part_mode)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    summary = result["summary"]
    print("Hole Detection Validatie")
    print(f"STEP: {result['step_path']}")
    print(f"Mode: {result['part_mode']}")
    print(f"Aantal gaten: {summary['aantal_gaten']}")
    print(f"Aantal draadgaten: {summary['aantal_draadgaten']}")
    print(f"Aantal verzonken gaten: {summary['aantal_verzonken_gaten']}")
    print(f"Totale snijlengte: {summary['totale_snijlengte_mm']:.3f} mm")

    rows = [
        HoleRow(
            index=item["index"],
            source=item["source"],
            hole_type=item["type"],
            cut_length_mm=_safe_float(item["snijlengte_mm"], 0.0),
            diameter_mm=item.get("diameter_mm"),
            note=item.get("note"),
        )
        for item in result["holes"]
    ]
    _print_rows(rows)

    accepted = [item for item in result["criteria"] if str(item.get("status")) == "accepted"]
    rejected = [item for item in result["criteria"] if str(item.get("status")) == "rejected"]
    _print_debug("Criteria - Geaccepteerd", accepted)
    _print_debug("Criteria - Afgewezen", rejected)

    print("\nNotities:")
    for note in result.get("notes") or []:
        print(f"- {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
