"""Regression tests for STEP naming/grouping fallback behavior."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    import cadquery as cq
except ImportError:  # pragma: no cover - environment dependent
    cq = None

from manufacturing_pipeline.analysis.assembly_analysis import (
    analyze_assembly_complete,
    parse_step_assembly_structure,
    parse_step_shape_rep_name_counts,
)

GENERIC_PREFIXES = (
    "Part_",
    "Plaatdeel",
    "Profieldeel",
    "Verspaamd deel",
    "Vaste vorm",
)


def is_generic_name(name: str) -> bool:
    normalized = (name or "").strip()
    return not normalized or normalized.startswith(GENERIC_PREFIXES)


def evaluate_naming(step_path: Path) -> dict:
    shape_rep_counts = parse_step_shape_rep_name_counts(str(step_path))
    assembly_counts = parse_step_assembly_structure(str(step_path))

    doc = cq.importers.importStep(str(step_path))
    result = analyze_assembly_complete(
        doc,
        assembly_name=step_path.stem,
        material="steel_s235",
        step_file_path=str(step_path),
    )

    bom_items = result.get("flat_bom", [])
    names = [str(item.get("part_name", "")).strip() for item in bom_items]

    generic_names = [name for name in names if is_generic_name(name)]
    explicit_names = [name for name in names if not is_generic_name(name)]

    return {
        "shape_rep_name_count": len(shape_rep_counts or {}),
        "assembly_name_count": len(assembly_counts or {}),
        "total_items": len(names),
        "generic_count": len(generic_names),
        "explicit_count": len(explicit_names),
        "explicit_names": explicit_names,
        "generic_names": generic_names,
    }


@unittest.skipIf(cq is None, "cadquery is not installed")
class TestStepNamingFallbackRegression(unittest.TestCase):
    def _skip_if_missing(self, file_path: Path) -> None:
        if not file_path.exists():
            self.skipTest(f"STEP file not found: {file_path}")

    def test_shape_rep_primary_keeps_explicit_names(self):
        step_path = ROOT_DIR / "data/output/10001091875_Rev_00.step"
        self._skip_if_missing(step_path)

        stats = evaluate_naming(step_path)

        self.assertGreater(
            stats["shape_rep_name_count"],
            0,
            "Expected SHAPE_REP parser to be available for primary target",
        )
        self.assertEqual(
            stats["generic_count"],
            0,
            f"Unexpected generic names: {stats['generic_names']}",
        )
        self.assertGreater(stats["explicit_count"], 0)

    def test_assembly_fallback_handles_missing_shape_rep(self):
        step_path = WORKSPACE_DIR / "stepfiles/10040878_1.stp"
        self._skip_if_missing(step_path)

        stats = evaluate_naming(step_path)

        self.assertEqual(
            stats["shape_rep_name_count"],
            0,
            "Expected SHAPE_REP parser to be unavailable for fallback target",
        )
        self.assertGreater(
            stats["assembly_name_count"],
            0,
            "Expected assembly parser fallback to provide names",
        )
        self.assertEqual(
            stats["generic_count"],
            0,
            f"Unexpected generic names: {stats['generic_names']}",
        )
        self.assertGreater(stats["explicit_count"], 0)


if __name__ == "__main__":
    unittest.main()
