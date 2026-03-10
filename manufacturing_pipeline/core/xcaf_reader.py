"""
XCAF-based STEP reader for reliable solid-to-name mapping.

This module reads the STEP product tree directly via OpenCASCADE XCAF.
It provides direct (solid, name) pairs and avoids regex or volume-only guessing.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    HAS_XCAF = True
except ImportError:
    HAS_XCAF = False


def _get_label_name(label: "TDF_Label") -> str:
    """Extract label name if present."""
    name_attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), name_attr):
        return name_attr.Get().ToExtString()
    return ""


def _get_solid_volume(solid: Any) -> float:
    """Compute solid volume safely."""
    try:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        return abs(float(props.Mass()))
    except Exception:
        return 0.0


def _traverse_label(
    shape_tool: Any,
    label: "TDF_Label",
    parent_name: Optional[str] = None,
    results: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Recursively traverse XCAF tree and collect named solids."""
    if results is None:
        results = []

    name = _get_label_name(label)

    if shape_tool.IsAssembly_s(label):
        components = TDF_LabelSequence()
        shape_tool.GetComponents_s(label, components)

        for i in range(components.Length()):
            comp_label = components.Value(i + 1)
            referred = TDF_Label()

            if shape_tool.GetReferredShape_s(comp_label, referred):
                comp_name = _get_label_name(comp_label)
                ref_name = _get_label_name(referred)
                effective_name = ref_name or comp_name

                before_count = len(results)
                _traverse_label(
                    shape_tool,
                    referred,
                    parent_name=name or parent_name,
                    results=results,
                )

                # Fill empty names from the best available instance/definition name.
                if effective_name and len(results) > before_count:
                    for item in results[before_count:]:
                        if not item["name"]:
                            item["name"] = effective_name
            else:
                _traverse_label(
                    shape_tool,
                    comp_label,
                    parent_name=name or parent_name,
                    results=results,
                )

        return results

    shape = shape_tool.GetShape_s(label)
    if shape is None or shape.IsNull():
        return results

    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    found = 0
    while explorer.More():
        solid = TopoDS.Solid_s(explorer.Current())
        results.append(
            {
                "name": name or "",
                "solid": solid,
                "parent_assembly": parent_name,
                "volume": _get_solid_volume(solid),
            }
        )
        found += 1
        explorer.Next()

    if found == 0:
        try:
            solid = TopoDS.Solid_s(shape)
            if not solid.IsNull():
                results.append(
                    {
                        "name": name or "",
                        "solid": solid,
                        "parent_assembly": parent_name,
                        "volume": _get_solid_volume(solid),
                    }
                )
        except Exception:
            pass

    return results


def _add_occurrence_counts(results: List[Dict[str, Any]]) -> None:
    """Annotate each row with occurrence_count by part name."""
    counts = Counter(row["name"] for row in results if row["name"])
    for row in results:
        row["occurrence_count"] = counts.get(row["name"], 1) if row["name"] else 1


def _assign_fallback_names(results: List[Dict[str, Any]]) -> None:
    """Assign deterministic fallback names when STEP names are empty."""
    idx = 1
    for row in results:
        if not row["name"]:
            row["name"] = f"Part_{idx:03d}"
            idx += 1


def read_step_with_names(step_path: str) -> List[Dict[str, Any]]:
    """
    Read STEP file through XCAF and return rows with `name` and `solid`.

    Returns an empty list on failure.
    """
    if not HAS_XCAF:
        logger.warning("XCAF bindings are not available")
        return []

    path = Path(step_path).resolve()
    if not path.exists():
        logger.error("STEP file does not exist: %s", path)
        return []

    app = None
    doc = None
    try:
        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString(""))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetColorMode(False)
        reader.SetLayerMode(False)

        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            logger.error("STEPCAF read failed: %s (status=%s)", path.name, status)
            return []

        if not reader.Transfer(doc):
            logger.error("STEPCAF transfer failed: %s", path.name)
            return []

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

        roots = TDF_LabelSequence()
        shape_tool.GetFreeShapes(roots)
        if roots.Length() == 0:
            logger.warning("No root labels found in %s", path.name)
            return []

        results: List[Dict[str, Any]] = []
        for i in range(roots.Length()):
            root = roots.Value(i + 1)
            _traverse_label(shape_tool, root, results=results)

        _add_occurrence_counts(results)
        _assign_fallback_names(results)

        return results
    except Exception as exc:
        logger.error("XCAF parsing failed for %s: %s", path.name, exc, exc_info=True)
        return []
    finally:
        if app is not None and doc is not None:
            try:
                app.Close(doc)
            except Exception:
                # Some OCP builds throw here; safe to ignore.
                pass


def xcaf_get_name_counts(step_path: str) -> Optional[Dict[str, int]]:
    """Return ordered name -> count mapping from XCAF, or None on failure."""
    rows = read_step_with_names(step_path)
    if not rows:
        return None

    counts = Counter(row["name"] for row in rows)
    ordered: Dict[str, int] = {}
    for row in rows:
        name = row["name"]
        if name not in ordered:
            ordered[name] = int(counts[name])
    return ordered if ordered else None


def xcaf_match_solids_to_names(step_path: str) -> Optional[Tuple[List[Any], List[str]]]:
    """Return aligned (solids, names) lists from XCAF, or None on failure."""
    rows = read_step_with_names(step_path)
    if not rows:
        return None

    solids = [row["solid"] for row in rows]
    names = [row["name"] for row in rows]
    return solids, names
