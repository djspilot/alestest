#!/usr/bin/env python3
"""Validate and snapshot generated XML exports.

Goal:
- Guard important status fields (DocumentControl + sheet X/Y dimensions)
- Keep timestamped snapshots so generated XML files are never lost
- Record git metadata for traceability

Usage examples:
    python docs/scripts/preserve_xml_status.py --xml ..\\stepfiles\\10040878_1_generated_latest.xml
    python docs/scripts/preserve_xml_status.py --xml data\\output\\run.xml --tag test-run --fail-on-warning
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ValidationSummary:
    total_sheet_rows: int
    missing_xy_names: list[str]
    bends_without_unfold: list[str]
    doc_status: str
    doc_control_found: bool

    @property
    def has_errors(self) -> bool:
        return len(self.missing_xy_names) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.bends_without_unfold) > 0 or not self.doc_control_found or not self.doc_status


def _find_repo_root(start_path: Path) -> Path:
    current = start_path.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start_path.resolve()


def _run_git(repo_root: Path, args: list[str]) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return ""


def _git_metadata(repo_root: Path) -> dict[str, str | bool]:
    return {
        "branch": _run_git(repo_root, ["branch", "--show-current"]),
        "commit": _run_git(repo_root, ["rev-parse", "--short", "HEAD"]),
        "dirty": bool(_run_git(repo_root, ["status", "--porcelain"])),
    }


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(float((value or "").strip() or default))
    except Exception:
        return default


def validate_xml_status(xml_path: Path) -> ValidationSummary:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    doc_control = root.find("DocumentControl")
    doc_control_found = doc_control is not None
    doc_status = ""
    if doc_control is not None:
        doc_status = (doc_control.findtext("Status", "") or "").strip()

    sheet_rows = []
    for row in root.findall("CalculationResult"):
        sheet_name = (row.findtext("Sheet_Name", "") or "").strip()
        if sheet_name:
            sheet_rows.append(row)

    missing_xy_names: list[str] = []
    bends_without_unfold: list[str] = []

    for row in sheet_rows:
        sheet_name = (row.findtext("Sheet_Name", "") or "").strip() or "<unknown>"
        box_x = (row.findtext("Sheet_BoxX", "") or "").strip()
        box_y = (row.findtext("Sheet_BoxY", "") or "").strip()

        if not box_x or not box_y:
            missing_xy_names.append(sheet_name)

        nr_bends = _safe_int(row.findtext("Sheet_NrBends", "0"), default=0)
        unfold_success = (row.findtext("Sheet_UnfoldSuccess", "False") or "False").strip().lower() == "true"
        if nr_bends > 0 and not unfold_success:
            bends_without_unfold.append(sheet_name)

    return ValidationSummary(
        total_sheet_rows=len(sheet_rows),
        missing_xy_names=missing_xy_names,
        bends_without_unfold=bends_without_unfold,
        doc_status=doc_status,
        doc_control_found=doc_control_found,
    )


def _snapshot_xml(
    xml_path: Path,
    snapshot_root: Path,
    repo_root: Path,
    tag: str,
    summary: ValidationSummary,
    git_info: dict[str, str | bool],
) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = snapshot_root / xml_path.stem / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    snapshot_xml_path = snapshot_dir / xml_path.name
    shutil.copy2(xml_path, snapshot_xml_path)

    source_abs = xml_path.resolve()
    snapshot_abs = snapshot_xml_path.resolve()

    source_rel = str(source_abs)
    snapshot_rel = str(snapshot_abs)
    try:
        source_rel = str(source_abs.relative_to(repo_root.resolve()))
    except Exception:
        pass
    try:
        snapshot_rel = str(snapshot_abs.relative_to(repo_root.resolve()))
    except Exception:
        pass

    meta = {
        "timestamp": timestamp,
        "tag": tag,
        "source_xml": source_rel,
        "source_xml_abs": str(source_abs),
        "snapshot_xml": snapshot_rel,
        "snapshot_xml_abs": str(snapshot_abs),
        "git": git_info,
        "validation": {
            "document_control_found": summary.doc_control_found,
            "document_status": summary.doc_status,
            "total_sheet_rows": summary.total_sheet_rows,
            "missing_xy_count": len(summary.missing_xy_names),
            "missing_xy_names": summary.missing_xy_names,
            "bends_without_unfold_count": len(summary.bends_without_unfold),
            "bends_without_unfold_names": summary.bends_without_unfold,
        },
    }

    meta_path = snapshot_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")

    latest_pointer = snapshot_root / f"LATEST_{xml_path.stem}.txt"
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(str(snapshot_xml_path.resolve()), encoding="utf-8")

    return snapshot_xml_path, meta_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate XML status fields and create a protected snapshot.")
    parser.add_argument("--xml", required=True, help="Path to generated XML file")
    parser.add_argument(
        "--snapshot-root",
        default="data/snapshots/xml_status",
        help="Snapshot root directory (relative to repo root by default)",
    )
    parser.add_argument("--tag", default="", help="Optional label for this snapshot")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 1 on warnings as well",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    xml_path = Path(args.xml).expanduser()
    if not xml_path.is_absolute():
        xml_path = (Path.cwd() / xml_path).resolve()

    if not xml_path.exists():
        print(f"[ERROR] XML not found: {xml_path}")
        return 2

    repo_root = _find_repo_root(Path(__file__).parent)

    snapshot_root = Path(args.snapshot_root).expanduser()
    if not snapshot_root.is_absolute():
        snapshot_root = (repo_root / snapshot_root).resolve()

    print("=== XML Status Guard ===")
    print(f"XML:           {xml_path}")
    print(f"Snapshot root: {snapshot_root}")

    try:
        summary = validate_xml_status(xml_path)
    except Exception as exc:
        print(f"[ERROR] Failed to parse/validate XML: {exc}")
        return 2

    print("\nValidation summary:")
    print(f"- DocumentControl found: {summary.doc_control_found}")
    print(f"- DocumentControl Status: {summary.doc_status or '<empty>'}")
    print(f"- Sheet rows: {summary.total_sheet_rows}")
    print(f"- Missing Sheet_BoxX/Sheet_BoxY rows: {len(summary.missing_xy_names)}")
    if summary.missing_xy_names:
        print("  Names: " + ", ".join(summary.missing_xy_names))
    print(f"- Bent rows without unfold success: {len(summary.bends_without_unfold)}")
    if summary.bends_without_unfold:
        print("  Names: " + ", ".join(summary.bends_without_unfold))

    tag = args.tag.strip() or f"xml-status-{datetime.now().strftime('%Y%m%d')}"
    git_info = _git_metadata(repo_root)

    try:
        snapshot_xml_path, meta_path = _snapshot_xml(xml_path, snapshot_root, repo_root, tag, summary, git_info)
    except Exception as exc:
        print(f"[ERROR] Failed to create snapshot: {exc}")
        return 2

    print("\nSnapshot created:")
    print(f"- XML:  {snapshot_xml_path}")
    print(f"- Meta: {meta_path}")
    print(f"- Git:  {git_info.get('branch', '')}@{git_info.get('commit', '')} (dirty={git_info.get('dirty', False)})")

    if summary.has_errors:
        print("\n[FAIL] Hard validation failed (missing X/Y on at least one sheet row).")
        return 1

    if args.fail_on_warning and summary.has_warnings:
        print("\n[FAIL] Warnings present and --fail-on-warning is enabled.")
        return 1

    if summary.has_warnings:
        print("\n[OK with warnings] Snapshot saved; review warnings above.")
    else:
        print("\n[OK] Validation passed and snapshot saved.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
