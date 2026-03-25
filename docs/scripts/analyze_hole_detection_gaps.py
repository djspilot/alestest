#!/usr/bin/env python3
"""Analyze where holes are lost in the detection pipeline.

This script focuses on a single standalone STEP part and compares:
1) Raw cylindrical hole detection
2) Raw shaped-hole detection
3) Cylindrical holes after dedup against shaped holes
4) Wrapper output (extract_cut_features_for_sheet)
5) Optional comparison against a reference XML entry

Usage example:
  python docs/scripts/analyze_hole_detection_gaps.py \
    --step data/stepfile/features/10001073529_Rev_00.stp \
    --reference-xml ../3D_visualisatie/Results_10001073426_Rev_00-aangepast20260316133910.xml \
    --reference-sheet-name "10001073529_Rev_00 Geometry"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path.cwd()))

import cadquery as cq
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Line, GeomAbs_Circle
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_EDGE

from manufacturing_pipeline.analysis.step_processing import (
    detect_holes,
    detect_shaped_holes,
    deduplicate_holes,
)
from manufacturing_pipeline.analysis.cut_features import extract_cut_features_for_sheet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze hole-detection gaps for a single part")
    parser.add_argument("--step", required=True, help="Path to standalone STEP file")
    parser.add_argument("--reference-xml", default="", help="Optional reference XML path")
    parser.add_argument(
        "--reference-sheet-name",
        default="",
        help="Sheet_Name in reference XML for the same part",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.35,
        help="Contour matching tolerance in mm (default: 0.35)",
    )
    parser.add_argument(
        "--top-shaped",
        type=int,
        default=20,
        help="Maximum number of shaped-hole rows to print (default: 20)",
    )
    return parser.parse_args()


def _extract_solids(step_doc: Any) -> List[Any]:
    shape = (
        step_doc.val().wrapped
        if hasattr(step_doc, "val")
        else step_doc.wrapped if hasattr(step_doc, "wrapped") else step_doc
    )
    solids: List[Any] = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()
    return solids


def _parse_contours(text: str) -> List[float]:
    txt = (text or "").strip()
    if not txt:
        return []
    vals: List[float] = []
    for part in txt.split("_"):
        token = part.strip().replace(",", ".")
        if not token:
            continue
        try:
            vals.append(float(token))
        except ValueError:
            continue
    return vals


def _match_multiset_with_tolerance(
    ref_vals: List[float],
    gen_vals: List[float],
    tol: float,
) -> Tuple[List[float], List[float]]:
    remaining = list(gen_vals)
    missing: List[float] = []

    for rv in ref_vals:
        best_idx = -1
        best_err = 1e9
        for i, gv in enumerate(remaining):
            err = abs(rv - gv)
            if err < best_err:
                best_err = err
                best_idx = i
        if best_idx >= 0 and best_err <= tol:
            remaining.pop(best_idx)
        else:
            missing.append(rv)

    extra = remaining
    return missing, extra


def _load_reference_part(reference_xml: Path, sheet_name: str) -> Optional[ET.Element]:
    if not reference_xml.exists():
        return None
    root = ET.parse(reference_xml).getroot()
    for node in root.findall(".//CalculationResult"):
        if (node.findtext("Sheet_Name") or "").strip() == sheet_name:
            return node
    return None


def _shape_row(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": item.get("type", ""),
        "dim": item.get("dim", ""),
        "center": tuple(round(float(v), 2) for v in item.get("center", (0.0, 0.0, 0.0))),
        "normal": tuple(round(float(v), 3) for v in item.get("normal", (0.0, 0.0, 1.0))),
    }


def _scan_inner_wires(cq_solid: Any) -> List[Dict[str, Any]]:
    """Collect inner-wire signatures from all planar faces for shaped-hole audit."""
    rows: List[Dict[str, Any]] = []
    faces = cq.Workplane(obj=cq_solid).faces().vals()

    for face_idx, face in enumerate(faces):
        surf = BRepAdaptor_Surface(face.wrapped, True)
        if surf.GetType() != GeomAbs_Plane:
            continue

        sorted_wires: List[Tuple[Any, float]] = []
        for wire in face.Wires():
            box = Bnd_Box()
            BRepBndLib.Add_s(wire.wrapped, box)
            xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
            diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
            sorted_wires.append((wire, diag))

        sorted_wires.sort(key=lambda x: x[1], reverse=True)
        if len(sorted_wires) <= 1:
            continue

        for wire, diag in sorted_wires[1:]:
            edges_count = 0
            lines = 0
            circles = 0
            perimeter = 0.0

            exp = TopExp_Explorer(wire.wrapped, TopAbs_EDGE)
            while exp.More():
                edge = TopoDS.Edge_s(exp.Current())
                curve = BRepAdaptor_Curve(edge)
                c_type = curve.GetType()

                edges_count += 1
                if c_type == GeomAbs_Line:
                    lines += 1
                    p1 = curve.Value(curve.FirstParameter())
                    p2 = curve.Value(curve.LastParameter())
                    perimeter += p1.Distance(p2)
                elif c_type == GeomAbs_Circle:
                    circles += 1
                    perimeter += curve.Circle().Radius() * abs(curve.LastParameter() - curve.FirstParameter())

                exp.Next()

            w_props = GProp_GProps()
            BRepGProp.LinearProperties_s(wire.wrapped, w_props)
            c = w_props.CentreOfMass()
            center = (float(c.X()), float(c.Y()), float(c.Z()))

            wire_class = "unknown"
            if (edges_count == 1 and circles == 1) or (edges_count == 2 and circles == 2):
                wire_class = "circle-skip"
            elif lines == 2 and circles == 2:
                wire_class = "slot"
            elif lines >= 4 and circles >= 4:
                wire_class = "rectR"
            elif lines >= 3 and circles == 0:
                wire_class = "rect/poly"

            rows.append(
                {
                    "class": wire_class,
                    "perimeter": perimeter,
                    "diag": diag,
                    "center": center,
                    "lines": lines,
                    "circles": circles,
                    "edges": edges_count,
                    "face_idx": face_idx,
                }
            )

    return rows


def _unique_xy(rows: List[Dict[str, Any]], xy_tol: float = 0.2, per_tol: float = 0.25) -> List[Dict[str, Any]]:
    """Collapse top/bottom duplicate wires by XY center and perimeter similarity."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        x, y, _z = row["center"]
        p = float(row["perimeter"])
        is_dup = False
        for prev in out:
            px, py, _pz = prev["center"]
            pp = float(prev["perimeter"])
            if abs(pp - p) <= per_tol and ((x - px) ** 2 + (y - py) ** 2) <= (xy_tol ** 2):
                is_dup = True
                break
        if not is_dup:
            out.append(row)
    return out


def main() -> int:
    args = parse_args()

    step_path = Path(args.step).resolve()
    if not step_path.exists():
        print(f"[ERROR] STEP not found: {step_path}")
        return 1

    print("=== Hole Detection Gap Analysis ===")
    print(f"STEP: {step_path}")

    doc = cq.importers.importStep(str(step_path))
    solids = _extract_solids(doc)
    if not solids:
        print("[ERROR] No solids found in STEP")
        return 1
    if len(solids) > 1:
        print(f"[WARN] STEP contains {len(solids)} solids; using first solid for standalone diagnosis")

    solid = solids[0]
    cq_solid = cq.Solid(solid)
    cq_obj = cq.Workplane("XY").newObject([cq_solid])

    circular_raw = detect_holes(cq_obj, filter_bores=True, is_flat_pattern=False)
    shaped_raw = detect_shaped_holes(cq.Workplane(obj=cq_solid))
    circular_after = deduplicate_holes(circular_raw, shaped_raw)

    cut = extract_cut_features_for_sheet(solid=solid, unfold_result=None, part_classification="plaat")
    if cut is None:
        print("[ERROR] extract_cut_features_for_sheet returned None")
        return 1

    print("\n--- Pipeline counts ---")
    print(f"cylindrical_raw          : {len(circular_raw)}")
    print(f"shaped_raw               : {len(shaped_raw)}")
    print(f"cylindrical_after_dedup  : {len(circular_after)}")
    print(f"wrapper_total_holes      : {cut.nr_holes}")
    print(f"wrapper_nr_cylindrical   : {cut.nr_cylindrical}")
    print(f"wrapper_nr_shaped        : {cut.nr_shaped}")
    print(f"wrapper_threaded         : {cut.threaded_holes}")
    print(f"wrapper_countersunk      : {cut.countersunk_holes}")

    print("\n--- Wrapper hole types ---")
    type_counts: Dict[str, int] = {}
    for t in cut.hole_types:
        type_counts[t] = type_counts.get(t, 0) + 1
    print(json.dumps(type_counts, indent=2, sort_keys=True))

    print("\n--- Raw shaped holes (sample) ---")
    sample = [_shape_row(h) for h in shaped_raw[: max(0, args.top_shaped)]]
    print(json.dumps(sample, indent=2))

    # Explain why potential shaped wires are skipped.
    wire_rows = _scan_inner_wires(cq_solid)
    unknown_rows = [r for r in wire_rows if r["class"] == "unknown"]
    unknown_unique = _unique_xy(unknown_rows)

    print("\n--- Inner-wire audit (planar faces) ---")
    print(f"inner_wires_total         : {len(wire_rows)}")
    print(f"inner_wires_unknown       : {len(unknown_rows)}")
    print(f"unknown_unique_xy         : {len(unknown_unique)}")

    if unknown_unique:
        print("unknown_unique_samples:")
        unknown_payload = [
            {
                "perimeter": round(float(r["perimeter"]), 2),
                "diag": round(float(r["diag"]), 2),
                "center": tuple(round(float(v), 2) for v in r["center"]),
                "lines": int(r["lines"]),
                "circles": int(r["circles"]),
                "edges": int(r["edges"]),
            }
            for r in unknown_unique[: max(0, args.top_shaped)]
        ]
        print(json.dumps(unknown_payload, indent=2))

    # Optional XML comparison.
    if args.reference_xml and args.reference_sheet_name:
        ref_xml = Path(args.reference_xml).resolve()
        ref_part = _load_reference_part(ref_xml, args.reference_sheet_name)

        print("\n--- Reference comparison ---")
        print(f"reference_xml: {ref_xml}")
        print(f"reference_sheet_name: {args.reference_sheet_name}")

        if ref_part is None:
            print("[ERROR] Reference part not found in XML")
            return 2

        ref_holes = int((ref_part.findtext("Sheet_NrHoles") or "0").strip() or 0)
        ref_cs = int((ref_part.findtext("Sheet_NrHolesCS") or "0").strip() or 0)
        ref_contours = _parse_contours(ref_part.findtext("Sheet_HoleContours") or "")

        gen_contours = [float(v) for v in cut.hole_contours]
        missing, extra = _match_multiset_with_tolerance(ref_contours, gen_contours, args.tolerance)

        print(f"reference_holes          : {ref_holes}")
        print(f"generated_holes          : {cut.nr_holes}")
        print(f"delta_holes              : {cut.nr_holes - ref_holes}")
        print(f"reference_countersunk    : {ref_cs}")
        print(f"generated_countersunk    : {cut.countersunk_holes}")
        print(f"delta_countersunk        : {cut.countersunk_holes - ref_cs}")
        print(f"reference_contours_count : {len(ref_contours)}")
        print(f"generated_contours_count : {len(gen_contours)}")
        print(f"missing_contours_count   : {len(missing)}")
        print(f"extra_contours_count     : {len(extra)}")

        print("\nmissing_contours_ref_values:")
        print(json.dumps([round(v, 2) for v in missing], indent=2))

        print("\nextra_contours_generated_values:")
        print(json.dumps([round(v, 2) for v in extra], indent=2))

        ref_cs_raw = (ref_part.findtext("Sheet_HolesCS") or "").strip()
        print(f"\nreference_Sheet_HolesCS: {ref_cs_raw}")
        print(f"generated_countersunk_angles: {cut.countersunk_angles}")

        # Check circle-skip wires that are not represented by detected cylindrical holes.
        circle_skip_unique = _unique_xy([r for r in wire_rows if r["class"] == "circle-skip"])
        cyl_signatures = []
        for h in circular_after:
            x, y, _z = h.position
            cyl_signatures.append((float(x), float(y), float(math.pi * h.diameter)))

        unmatched_circle_skip = []
        for row in circle_skip_unique:
            x, y, _z = row["center"]
            p = float(row["perimeter"])
            matched = False
            for cx, cy, cp in cyl_signatures:
                if ((x - cx) ** 2 + (y - cy) ** 2) <= (1.0 ** 2) and abs(cp - p) <= 0.6:
                    matched = True
                    break
            if not matched:
                unmatched_circle_skip.append(row)

        print(f"unmatched_circle_skip_xy  : {len(unmatched_circle_skip)}")
        if unmatched_circle_skip:
            payload = [
                {
                    "perimeter": round(float(r["perimeter"]), 2),
                    "center": tuple(round(float(v), 2) for v in r["center"]),
                    "lines": int(r["lines"]),
                    "circles": int(r["circles"]),
                }
                for r in unmatched_circle_skip[: max(0, args.top_shaped)]
            ]
            print("unmatched_circle_skip_samples:")
            print(json.dumps(payload, indent=2))

        # Heuristic diagnosis
        print("\n--- Diagnosis hints ---")
        if len(shaped_raw) == 0 and (ref_holes - cut.nr_holes) > 0:
            print("- No shaped holes detected while holes are missing: shaped-hole detection is likely a primary suspect.")
        if len(circular_raw) > len(circular_after):
            print("- Circular holes were removed in deduplicate_holes: check false-positive shaped holes causing over-dedup.")
        if unknown_unique:
            print("- Unknown inner-wire classes exist: broaden shaped-hole classification rules (edge-pattern coverage).")
        if unmatched_circle_skip:
            print("- Some circle-skip wires have no cylindrical match: investigate detect_holes criteria or cone-only handling.")
        if cut.countersunk_holes < ref_cs:
            print("- Countersinks lower than reference: inspect cone matching and STEP cone topology for this part.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
