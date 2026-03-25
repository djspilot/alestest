#!/usr/bin/env python3
"""
STEP 0 Classification Detailed Report Generator

Test en report gegeneratie voor de classification.py STEP 0 beslisboom.
Per solid een gedetailleerde trace met alle criteria per stap (0.1-0.5).

Criteria bronnen: classification_step_review.md + classification.py

Gebruik:
    python test_step0_detailed_report.py <stepfile.stp>
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logging.basicConfig(level=logging.WARNING, format="%(name)s - %(levelname)s - %(message)s")

# ============================================================================
# OCP Imports (nieuw pythonocc-core: OCP.*)
# ============================================================================
try:
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False
    print("ERROR: OCP (pythonocc-core) nodig voor STEP-file reader")
    sys.exit(1)

# ============================================================================
# Lokale Imports
# ============================================================================
from manufacturing_pipeline.analysis.classification import (
    classify_step0,
    _get_volume,
    _get_bbox_sorted,
    _is_bent_sheet_geometry,
    _is_constant_thickness,
)
from manufacturing_pipeline.analysis.classification_variables import (
    PLATE_THICK_MAX_MM,
    PROFILE_LENGTH_RATIO_MIN,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_CROSS_RATIO_MAX,
    PROFILE_SMALLEST_MIN_MM,
    PROFILE_VOLUME_RATIO_STRONG_MIN,
    PROFILE_VOLUME_RATIO_WEAK_MIN,
)


# ============================================================================
# Detectie: OCC.Core vs OCP conflict
#
# profile_classifier.py is geschreven voor OCC.Core.* (oud pythonocc-core).
# Onze omgeving heeft OCP.* (nieuw). Stap 0.1, 0.2, 0.3, 0.4a vereisen
# profile_classifier en kunnen daardoor NIET draaien in deze omgeving.
# Stap 0.4b en 0.5 gebruiken classification.py helpers die OCP direct aanroepen
# en werken WEL.
# ============================================================================
def _check_profile_classifier() -> tuple[bool, str]:
    try:
        import OCC  # noqa: F401
        return True, ""
    except ModuleNotFoundError:
        pass
    return False, (
        "profile_classifier.py vereist 'OCC.Core.*' (oud pythonocc-core).\n"
        "     Deze omgeving heeft 'OCP.*' (nieuw pythonocc-core).\n"
        "     Stap 0.1 t/m 0.4a zijn NIET uitvoerbaar in deze omgeving.\n"
        "     Stap 0.4b en 0.5 werken WEL (gebruiken OCP direct)."
    )


_PC_AVAILABLE, _PC_BLOCKER = _check_profile_classifier()


def _skip(label: str = "") -> str:
    return f"⚠ SKIP — OCC.Core niet beschikbaar{(' (' + label + ')') if label else ''}"


# ============================================================================
# Step0Evaluator
# ============================================================================

class Step0Evaluator:
    """Evalueer alle criteria per stap, geef gedetailleerd report."""

    def __init__(self, solid):
        self.solid = solid
        self.dims = _get_bbox_sorted(solid)
        self.volume = _get_volume(solid)
        self.smallest, self.middle, self.longest = self.dims

    # ------------------------------------------------------------------
    # Stap 0.1
    # ------------------------------------------------------------------
    def evaluate_step_0_1(self) -> Dict[str, Any]:
        """Stap 0.1: Slice-validatie (poort).
        Bronnen: classification_step_review.md §0.1
        """
        result = {
            "step": "0.1",
            "name": "Slice-validatie (stabiele extrusie-as, poort)",
            "criteria": {
                "stabiele_extrusie_as":     _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "min_3_geldige_sections":   _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "dominant_cluster >= 0.60": _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
            },
            "exit_on_fail": "ANDERS",
            "passed": True,   # geen blocker = poort overgeslagen, doorlopen
            "reason": "",
        }

        if not _PC_AVAILABLE:
            result["reason"] = f"BLOCKER:\n     {_PC_BLOCKER}"
            return result

        try:
            from manufacturing_pipeline.analysis.profile_classifier import (
                find_extrusion_axis,
                solid_vertices_np,
                section_plane_positions_from_vertices,
                slice_solid_to_section,
                dominant_section_cluster,
            )
        except Exception as e:
            result["reason"] = f"ImportError: {e}"
            return result

        try:
            axis = find_extrusion_axis(self.solid)
            result["criteria"]["stabiele_extrusie_as"] = axis is not None
            if axis is None:
                result["passed"] = False
                result["reason"] = "geen stabiele extrusie-as → EXIT: ANDERS"
                return result

            vertices = solid_vertices_np(self.solid)
            positions = section_plane_positions_from_vertices(
                vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
            )
            sections = []
            for s in positions:
                sec = slice_solid_to_section(
                    self.solid,
                    plane_origin=axis.direction * s,
                    plane_normal=axis.direction,
                    section_position=s,
                )
                if sec is not None and sec.polygon.area > 0:
                    sections.append(sec)

            ok_sections = len(sections) >= 3
            result["criteria"]["min_3_geldige_sections"] = (len(sections), 3, ok_sections)
            if not ok_sections:
                result["passed"] = False
                result["reason"] = f"te weinig doorsneden: {len(sections)} < 3 → EXIT: ANDERS"
                return result

            cluster = dominant_section_cluster(sections)
            ratio = len(cluster) / max(len(sections), 1)
            ok_cluster = ratio >= 0.60
            result["criteria"]["dominant_cluster >= 0.60"] = (ratio, 0.60, ok_cluster)
            if not ok_cluster:
                result["passed"] = False
                result["reason"] = f"doorsneden niet stabiel: ratio={ratio:.2f} < 0.60 → EXIT: ANDERS"
                return result

            result["passed"] = True
            result["reason"] = "alle criteria OK → doorloopt naar 0.2"

        except Exception as e:
            result["reason"] = f"exception: {e}"

        return result

    # ------------------------------------------------------------------
    # Stap 0.2
    # ------------------------------------------------------------------
    def evaluate_step_0_2(self) -> Dict[str, Any]:
        """Stap 0.2: Gesloten-hol → RONDE_BUIS / RECHTHOEKIGE_KOKER.
        Bronnen: classification_step_review.md §0.2
        """
        result = {
            "step": "0.2",
            "name": "Gesloten-hol (BUIS / KOKER)",
            "criteria": {
                "holes == 1":                   _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "outer + inner near-circle":    _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "outer + inner near-rectangle": _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
            },
            "exit_on_match": "RONDE_BUIS / RECHTHOEKIGE_KOKER",
            "matched": False,
            "label": None,
            "reason": "",
        }

        if not _PC_AVAILABLE:
            result["reason"] = f"BLOCKER: OCC.Core niet beschikbaar"
            return result

        try:
            from manufacturing_pipeline.analysis.profile_classifier import (
                find_extrusion_axis, solid_vertices_np,
                section_plane_positions_from_vertices, slice_solid_to_section,
                dominant_section_cluster, normalize_section_polygon,
                extract_section_features, section_distance,
                _is_nearly_circle, _is_nearly_rectangle,
            )
            import numpy as np
            from shapely.geometry import Polygon as ShapelyPolygon
        except Exception as e:
            result["reason"] = f"ImportError: {e}"
            return result

        try:
            axis = find_extrusion_axis(self.solid)
            if axis is None:
                result["reason"] = "geen extrusie-as"
                return result

            vertices = solid_vertices_np(self.solid)
            positions = section_plane_positions_from_vertices(
                vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
            )
            sections = []
            for s in positions:
                sec = slice_solid_to_section(
                    self.solid,
                    plane_origin=axis.direction * s,
                    plane_normal=axis.direction,
                    section_position=s,
                )
                if sec is not None and sec.polygon.area > 0:
                    sections.append(sec)

            cluster = dominant_section_cluster(sections) if sections else []
            if not cluster:
                result["reason"] = "geen dominant cluster"
                return result

            normalized = [normalize_section_polygon(s.polygon) for s in cluster]
            dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
                    for i, a in enumerate(normalized)]
            core_sec = cluster[int(np.argmin(dsum))]
            features = extract_section_features(core_sec)
            core_poly = core_sec.polygon

            has_one_hole = features.holes == 1
            result["criteria"]["holes == 1"] = (features.holes, 1, has_one_hole)
            if not has_one_hole:
                result["reason"] = f"doorsnede heeft {features.holes} holes → geen buis/koker"
                return result

            outer = ShapelyPolygon(core_poly.exterior.coords)
            inner = ShapelyPolygon(list(core_poly.interiors[0].coords))

            is_round = _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94)
            is_rect  = _is_nearly_rectangle(outer, 0.85, 0.95) and _is_nearly_rectangle(inner, 0.85, 0.95)

            result["criteria"]["outer + inner near-circle"]    = is_round
            result["criteria"]["outer + inner near-rectangle"] = is_rect

            if is_round:
                result["matched"] = True
                result["label"]   = "RONDE_BUIS"
                result["reason"]  = "outer en inner beide cirkelrond → EXIT"
            elif is_rect:
                result["matched"] = True
                result["label"]   = "RECHTHOEKIGE_KOKER"
                result["reason"]  = "outer en inner beide rechthoekig → EXIT"
            else:
                result["reason"] = "holes==1 maar vorm niet cirkel/rechthoek → doorloopt naar 0.3"

        except Exception as e:
            result["reason"] = f"exception: {e}"

        return result

    # ------------------------------------------------------------------
    # Stap 0.3
    # ------------------------------------------------------------------
    def evaluate_step_0_3(self) -> Dict[str, Any]:
        """Stap 0.3: Open profiel (L/U/I/T).
        Bronnen: classification_step_review.md §0.3
        """
        return {
            "step": "0.3",
            "name": "Open profiel (L / U / I / T)",
            "criteria": {
                "holes == 0":                          _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "reentrant_corners > 0":               _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "dikteConstant == false":              _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "template match score <= 0.12":        _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "bent-sheet veto (niet gezette plaat)":_skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
            },
            "exit_on_match": "PROFIEL",
            "matched": False,
            "label": None,
            "reason": "BLOCKER: OCC.Core niet beschikbaar" if not _PC_AVAILABLE else "",
        }

    # ------------------------------------------------------------------
    # Stap 0.4a
    # ------------------------------------------------------------------
    def evaluate_step_0_4a(self) -> Dict[str, Any]:
        """Stap 0.4a: Vlakke plaat (high confidence).
        Bronnen: classification_step_review.md §0.4a

        Criteria:
          holes == 0
          reentrant_corners == 0
          dikteConstant == true
          near-rectangle == true
          bbox_ratio <= 0.30  →  high confidence, EXIT
          bbox_ratio >  0.30  →  lage confidence, fallthrough naar Step 1
        """
        result = {
            "step":  "0.4a",
            "name":  "Vlakke plaat (holes==0, reentrant==0, dikteConstant, near-rect, bbox_ratio)",
            "criteria": {
                "holes == 0":             _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "reentrant_corners == 0": _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "dikteConstant == true":  _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "near_rectangle":         _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
                "bbox_ratio <= 0.30":     _skip() if not _PC_AVAILABLE else "[niet geëvalueerd]",
            },
            "exit_on_match": "PLAAT (of fallthrough bij lage confidence)",
            "matched": False,
            "label": None,
            "reason": "BLOCKER: OCC.Core niet beschikbaar" if not _PC_AVAILABLE else "",
        }

        if not _PC_AVAILABLE:
            return result

        try:
            from manufacturing_pipeline.analysis.profile_classifier import (
                find_extrusion_axis, solid_vertices_np,
                section_plane_positions_from_vertices, slice_solid_to_section,
                dominant_section_cluster, normalize_section_polygon,
                extract_section_features, section_distance, _is_nearly_rectangle,
            )
            import numpy as np
        except Exception as e:
            result["reason"] = f"ImportError: {e}"
            return result

        try:
            axis = find_extrusion_axis(self.solid)
            if axis is None:
                result["reason"] = "geen extrusie-as"
                return result

            vertices = solid_vertices_np(self.solid)
            positions = section_plane_positions_from_vertices(
                vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
            )
            sections = []
            for s in positions:
                sec = slice_solid_to_section(
                    self.solid,
                    plane_origin=axis.direction * s,
                    plane_normal=axis.direction,
                    section_position=s,
                )
                if sec is not None and sec.polygon.area > 0:
                    sections.append(sec)

            cluster = dominant_section_cluster(sections) if sections else []
            if not cluster:
                result["reason"] = "geen dominant cluster"
                return result

            normalized = [normalize_section_polygon(s.polygon) for s in cluster]
            dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
                    for i, a in enumerate(normalized)]
            core_sec  = cluster[int(np.argmin(dsum))]
            features  = extract_section_features(core_sec)

            holes_ok = features.holes == 0
            result["criteria"]["holes == 0"] = (features.holes, 0, holes_ok)
            if not holes_ok:
                result["reason"] = f"doorsnede heeft {features.holes} hole(s) → geen vlakke plaat"
                return result

            rc = features.reentrant_corners
            reentrant_ok = rc == 0
            result["criteria"]["reentrant_corners == 0"] = (rc, 0, reentrant_ok)
            if not reentrant_ok:
                result["reason"] = f"{rc} reentrant corner(s) → niet vlakke plaat (→ 0.4b)"
                return result

            const_ok = _is_constant_thickness(self.solid)
            result["criteria"]["dikteConstant == true"] = const_ok
            if not const_ok:
                result["reason"] = "variabele wanddikte → geen vlakke plaat"
                return result

            rect_ok = _is_nearly_rectangle(core_sec.polygon)
            result["criteria"]["near_rectangle"] = rect_ok
            if not rect_ok:
                result["reason"] = "sectie niet rechthoekig → lage confidence, fallthrough"
                return result

            bbox_ratio = features.bbox_ratio
            high_conf  = bbox_ratio <= 0.30
            result["criteria"]["bbox_ratio <= 0.30"] = (bbox_ratio, 0.30, high_conf)
            result["matched"] = True
            if high_conf:
                result["label"]  = "PLAAT"
                result["reason"] = f"HIGH confidence (bbox_ratio={bbox_ratio:.3f}) → EXIT"
            else:
                result["label"]  = "PLAAT (fallthrough)"
                result["reason"] = (
                    f"LAGE confidence (bbox_ratio={bbox_ratio:.3f}) → fallthrough naar Step 1"
                )

        except Exception as e:
            result["reason"] = f"exception: {e}"

        return result

    # ------------------------------------------------------------------
    # Stap 0.4b
    # ------------------------------------------------------------------
    def evaluate_step_0_4b(self) -> Dict[str, Any]:
        """Stap 0.4b: Constant-dikte open sectie → GEZETTE_PLAAT of PROFIEL.
        Bronnen: classification_step_review.md §0.4b

        Criteria:
          holes == 0                 (vereist profile_classifier)
          reentrant_corners > 0      (vereist profile_classifier)
          dikteConstant == true      (proxy via OCP face areas — werkt hier WEL)
          _detect_bent_sheet == true → GEZETTE_PLAAT
          _detect_bent_sheet == false → PROFIEL
        """
        result = {
            "step":  "0.4b",
            "name":  "Constant-dikte open sectie (GEZETTE_PLAAT of PROFIEL)",
            "criteria": {},
            "exit_on_match": "GEZETTE_PLAAT of PROFIEL",
            "matched": False,
            "label": None,
            "reason": "",
        }

        # holes en reentrant_corners komen uit profile_classifier
        result["criteria"]["holes == 0 (sectie)"] = (
            _skip("reentrant via profile_classifier") if not _PC_AVAILABLE else "[niet geëvalueerd]"
        )
        result["criteria"]["reentrant_corners > 0 (sectie)"] = (
            _skip("reentrant via profile_classifier") if not _PC_AVAILABLE else "[niet geëvalueerd]"
        )

        # dikteConstant proxy werkt WEL met OCP
        is_const = _is_constant_thickness(self.solid)
        result["criteria"]["dikteConstant == true (proxy)"] = is_const

        # _detect_bent_sheet werkt WEL met OCP
        is_bent = _is_bent_sheet_geometry(self.solid, self.volume, self.dims)
        result["criteria"]["_detect_bent_sheet == true"] = is_bent

        # Extra info voor diagnose
        result["criteria"]["dikte (smallest dim)"] = (
            self.smallest, PLATE_THICK_MAX_MM, self.smallest <= PLATE_THICK_MAX_MM
        )

        if not is_const:
            result["reason"] = "variabele wanddikte → stap 0.4b niet van toepassing"
            return result

        if self.smallest > PLATE_THICK_MAX_MM:
            result["reason"] = (
                f"dikte {self.smallest:.1f}mm > {PLATE_THICK_MAX_MM}mm → te dik voor gezette plaat/dunprofiel"
            )
            return result

        if is_bent:
            result["matched"] = True
            result["label"]   = "GEZETTE_PLAAT"
            result["reason"]  = "bent_sheet detectie positief → GEZETTE_PLAAT, EXIT"
        else:
            # Aanname: constant dik + niet bent = open profiel
            result["matched"] = True
            result["label"]   = "PROFIEL"
            result["reason"]  = "dikteConstant + niet bent → open PROFIEL, EXIT"

        return result

    # ------------------------------------------------------------------
    # Stap 0.5
    # ------------------------------------------------------------------
    def evaluate_step_0_5(self) -> Dict[str, Any]:
        """Stap 0.5: Massief profiel fallback via dimensies.
        Bronnen: classification.py _step_0_5_solid_profile_fallback()
        """
        result = {
            "step":  "0.5",
            "name":  "Massief profiel fallback (dimensies)",
            "criteria": {},
            "exit_on_match": "PROFIEL of ANDERS",
            "matched": True,   # deze stap geeft altijd een antwoord
            "label": None,
            "reason": "",
        }

        length_ratio = self.longest / self.middle if self.middle > 0 else 0.0
        cross_ratio  = self.middle / self.smallest if self.smallest > 0 else 0.0
        bbox_vol     = self.smallest * self.middle * self.longest
        vol_ratio    = self.volume / bbox_vol if bbox_vol > 0 else 0.0

        result["criteria"]["smallest >= 5mm (PROFILE_SMALLEST_MIN_MM)"] = (
            self.smallest, PROFILE_SMALLEST_MIN_MM, self.smallest >= PROFILE_SMALLEST_MIN_MM
        )
        result["criteria"]["length_ratio >= 3.0 (PROFILE_LENGTH_RATIO_MIN)"] = (
            length_ratio, PROFILE_LENGTH_RATIO_MIN, length_ratio >= PROFILE_LENGTH_RATIO_MIN
        )
        result["criteria"]["cross_ratio in [0.5, 3.5]"] = (
            cross_ratio,
            f"[{PROFILE_CROSS_RATIO_MIN}, {PROFILE_CROSS_RATIO_MAX}]",
            PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX,
        )

        geom_ok = (
            self.smallest >= PROFILE_SMALLEST_MIN_MM
            and length_ratio >= PROFILE_LENGTH_RATIO_MIN
            and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX
        )

        if geom_ok:
            result["criteria"]["volume_ratio > 0.5 (STRONG)"] = (
                vol_ratio, PROFILE_VOLUME_RATIO_STRONG_MIN, vol_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN
            )
            if vol_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
                result["label"]  = "PROFIEL"
                result["reason"] = f"massief profiel STRONG (vol_ratio={vol_ratio:.3f}) → EXIT"
                return result

            if vol_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
                result["criteria"]["SA/V tiebreaker"] = "niet berekend (weak path)"
                result["label"]  = "PROFIEL (weak)"
                result["reason"] = f"massief profiel WEAK via SA/V (vol_ratio={vol_ratio:.3f})"
                return result

        result["label"]  = "ANDERS"
        result["reason"] = "geen enkel profiel criterium gehaald → ANDERS (fallback)"
        return result

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    def generate_report(self) -> str:
        bbox_vol = self.smallest * self.middle * self.longest
        lines = []
        lines.append("=" * 80)
        lines.append("STEP 0 CLASSIFICATION DETAILED TRACE REPORT")
        lines.append("=" * 80)
        lines.append(f"\nBounding Box : {self.smallest:.1f} × {self.middle:.1f} × {self.longest:.1f} mm")
        lines.append(f"Volume       : {self.volume:.1f} mm³")
        lines.append(f"BBox Volume  : {bbox_vol:.1f} mm³")
        lines.append(f"Volume Ratio : {self.volume / bbox_vol if bbox_vol > 0 else 0:.4f}")

        if not _PC_AVAILABLE:
            lines.append(f"\n⚠ OMGEVINGSWAARSCHUWING:")
            lines.append(f"  {_PC_BLOCKER}")

        lines.append("\n" + "-" * 80)

        evaluators = [
            self.evaluate_step_0_1,
            self.evaluate_step_0_2,
            self.evaluate_step_0_3,
            self.evaluate_step_0_4a,
            self.evaluate_step_0_4b,
            self.evaluate_step_0_5,
        ]

        for fn in evaluators:
            step = fn()
            step_num  = step["step"]
            step_name = step["name"]

            lines.append(f"\nSTAP {step_num}: {step_name}")
            lines.append("-" * 80)

            for key, val in step["criteria"].items():
                if isinstance(val, tuple) and len(val) == 3:
                    actual, required, ok = val
                    mark = "✓" if ok else "✗"
                    lines.append(f"  {mark} {key}: {actual!r} (required: {required})")
                elif isinstance(val, bool):
                    mark = "✓" if val else "✗"
                    lines.append(f"  {mark} {key}: {val}")
                else:
                    lines.append(f"  · {key}: {val}")

            # Samenvatting van deze stap
            matched = step.get("matched", None)
            passed  = step.get("passed",  None)
            label   = step.get("label",   None)
            reason  = step.get("reason",  "")

            if matched is True and label:
                lines.append(f"\n  ➜ MATCH: {label}")
                lines.append(f"     {reason}")
                lines.append(f"     → STAP {step_num} EXIT\n")
            elif passed is False:
                lines.append(f"\n  ➜ GEFAALD: {reason}\n")
            elif matched is False:
                if reason:
                    lines.append(f"\n  ➜ Geen match → {reason}\n")
                else:
                    lines.append(f"\n  ➜ Geen match → doorloopt naar volgende stap\n")
            else:
                if reason:
                    lines.append(f"\n  · {reason}\n")

        lines.append("-" * 80)

        # Werkelijk resultaat van classify_step0()
        actual = classify_step0(self.solid)
        lines.append(f"\nACTUEEL RESULTAAT van classify_step0():")
        lines.append(f"  label      : {actual.get('label', '?')}")
        lines.append(f"  step       : {actual.get('step', '?')}")
        lines.append(f"  method     : {actual.get('method', '?')}")
        lines.append(f"  confidence : {actual.get('confidence', 0):.2f}")
        lines.append(f"  fallthrough: {actual.get('fallthrough', '?')}")
        lines.append(f"  reason     : {actual.get('reason', '?')}")
        lines.append("\n" + "=" * 80 + "\n")

        return "\n".join(lines)


# ============================================================================
# STEP-file reader
# ============================================================================

def read_step_file(step_path: str) -> list:
    if not os.path.exists(step_path):
        print(f"ERROR: bestand niet gevonden: {step_path}")
        return []
    try:
        reader = STEPControl_Reader()
        reader.ReadFile(step_path)
        reader.TransferRoots()
        shape = reader.OneShape()

        solids = []
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solids.append(TopoDS.Solid_s(exp.Current()))
            exp.Next()

        print(f"✓ {len(solids)} solid(s) geladen uit {step_path}")
        return solids
    except Exception as e:
        import traceback
        print(f"ERROR bij inlezen STEP-file: {e}")
        traceback.print_exc()
        return []


# ============================================================================
# Main
# ============================================================================

def main():
    if len(sys.argv) > 1:
        step_file = sys.argv[1]
    else:
        test_dir = Path(__file__).parent / "snapshots"
        files    = list(test_dir.glob("*.step")) + list(test_dir.glob("*.stp"))
        if not files:
            print("Gebruik: python test_step0_detailed_report.py <stepfile.stp>")
            return
        step_file = str(files[0])

    print(f"Inlezen: {step_file}\n")
    solids = read_step_file(step_file)
    if not solids:
        return

    for i, solid in enumerate(solids):
        print(f"\n{'='*80}\nSOLID #{i}\n{'='*80}\n")
        evaluator = Step0Evaluator(solid)
        print(evaluator.generate_report())


if __name__ == "__main__":
    main()
