from __future__ import annotations

from typing import Tuple

from manufacturing_pipeline.analysis.classification_variables import BENT_SHEET_LARGE_RADIUS_MIN_MM

try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False


def _get_volume(solid) -> float:
    """Volume in mm³ via OCP mass properties."""
    if not _HAS_OCP:
        return 0.0
    try:
        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(ocp_solid, props)
        return float(props.Mass())
    except Exception:
        return 0.0


def _get_bbox_sorted(solid) -> Tuple[float, float, float]:
    """Gesorteerde bounding box [kleinste, midden, grootste] in mm."""
    if not _HAS_OCP:
        return (0.0, 0.0, 0.0)
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        box = Bnd_Box()
        BRepBndLib.Add_s(ocp_solid, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        dims = sorted([abs(xmax - xmin), abs(ymax - ymin), abs(zmax - zmin)])
        return (dims[0], dims[1], dims[2])
    except Exception:
        return (0.0, 0.0, 0.0)


def _get_face_areas(solid) -> list[float]:
    """Lijst van vlakoppervlaktes voor alle faces (mm²)."""
    areas: list[float] = []
    if not _HAS_OCP:
        return areas
    try:
        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        explorer = TopExp_Explorer(ocp_solid, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            areas.append(float(props.Mass()))
            explorer.Next()
    except Exception:
        pass
    return areas


def _get_top2_face_percent(solid) -> float:
    """Percentage oppervlak gedekt door de twee grootste faces."""
    areas = _get_face_areas(solid)
    if not areas:
        return 0.0
    total = sum(areas)
    if total == 0:
        return 0.0
    top2 = sum(sorted(areas, reverse=True)[:2])
    return 100.0 * top2 / total


def _count_edges_and_large_radius(solid) -> Tuple[int, int]:
    """Tel edges en edges met grote boogstraal."""
    if not _HAS_OCP:
        return (0, 0)
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle

        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        edge_count = 0
        large_radius_count = 0
        explorer = TopExp_Explorer(ocp_solid, TopAbs_EDGE)
        while explorer.More():
            edge_count += 1
            edge = TopoDS.Edge_s(explorer.Current())
            adapter = BRepAdaptor_Curve(edge)
            if adapter.GetType() == GeomAbs_Circle:
                radius = adapter.Circle().Radius()
                if radius >= BENT_SHEET_LARGE_RADIUS_MIN_MM:
                    large_radius_count += 1
            explorer.Next()
        return edge_count, large_radius_count
    except Exception:
        return (0, 0)


def _count_edges(solid) -> int:
    """Tel alleen het aantal edges in het solid."""
    if not _HAS_OCP:
        return 0
    try:
        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
        edge_count = 0
        explorer = TopExp_Explorer(ocp_solid, TopAbs_EDGE)
        while explorer.More():
            edge_count += 1
            explorer.Next()
        return edge_count
    except Exception:
        return 0
