#!/usr/bin/env python3
"""Debug script to analyze bend detection issues."""

import os
import sys
import math

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
sys.path.insert(0, PIPELINE_DIR)

from src.step_processing import load_step_file
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

PARTS_DIR = "/Users/ds/Projecten/alestest/parts/fwofferte20253515bestanden"


def debug_part(artikel_nr, expected_bends):
    """Debug bend detection for a specific part."""
    step_file = os.path.join(PARTS_DIR, f"{artikel_nr}.step")
    if not os.path.exists(step_file):
        print(f"File not found: {step_file}")
        return

    print(f"\n{'='*80}")
    print(f"DEBUGGING: {artikel_nr}")
    print(f"Expected bends: {expected_bends}")
    print(f"{'='*80}")

    shape = load_step_file(step_file)
    solid = shape.val().wrapped

    # Get all faces
    faces = []
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()

    print(f"\nTotal faces: {len(faces)}")

    # Analyze cylindrical faces
    cylindrical = []
    planar = []

    for i, face in enumerate(faces):
        surf = BRepAdaptor_Surface(face, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()

        if stype == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            radius = cyl.Radius()

            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            arc_length = radius * abs(u_max - u_min)
            bend_length = area / arc_length if arc_length > 0 else 0

            cylindrical.append({
                "index": i,
                "radius": radius,
                "angle": angle_deg,
                "area": area,
                "bend_length": bend_length
            })

        elif stype == GeomAbs_Plane:
            planar.append({"index": i, "area": area})

    print(f"Planar faces: {len(planar)}")
    print(f"Cylindrical faces: {len(cylindrical)}")

    # Categorize cylindrical faces
    holes = []      # Full cylinders (angle > 270)
    bends = []      # Partial cylinders that could be bends
    fillets = []    # Small radius, small angle - edge fillets
    other = []

    for c in cylindrical:
        if c["angle"] > 270:
            holes.append(c)
        elif c["radius"] < 1.0 and c["angle"] < 100:
            # Small radius + small angle = likely a fillet
            fillets.append(c)
        elif c["radius"] > 15:
            # Large radius = probably rolled/welded, not bent
            other.append(c)
        else:
            bends.append(c)

    print(f"\n--- Categorization ---")
    print(f"Holes (angle > 270°): {len(holes)}")
    print(f"Potential bends: {len(bends)}")
    print(f"Fillets (r<1mm, angle<100°): {len(fillets)}")
    print(f"Other (large radius): {len(other)}")

    if bends:
        print(f"\n--- Potential Bends ---")
        # Group by similar radius
        from collections import defaultdict
        by_radius = defaultdict(list)
        for b in bends:
            r_key = round(b["radius"], 1)
            by_radius[r_key].append(b)

        for r, faces in sorted(by_radius.items()):
            total_angle = sum(f["angle"] for f in faces)
            avg_length = sum(f["bend_length"] for f in faces) / len(faces)
            print(f"  R={r:5.1f}mm: {len(faces):2d} faces, total_angle={total_angle:6.1f}°, avg_length={avg_length:6.1f}mm")

        # Count distinct bends by grouping
        # A real bend typically has:
        # - Inner and outer radius faces (differ by thickness)
        # - Angle typically 85-95° for a 90° bend

        # Simple approach: count faces with 80-100° angle as "90° bends"
        bend_90 = [b for b in bends if 75 <= b["angle"] <= 105]
        bend_other = [b for b in bends if b["angle"] < 75 or b["angle"] > 105]

        print(f"\n--- Bend Analysis ---")
        print(f"  ~90° bends (75-105°): {len(bend_90)} faces")
        print(f"  Other angles: {len(bend_other)} faces")

        # Estimate actual bend count
        # Each bend has inner + outer face = 2 faces per bend
        # But they might be split, so use unique radius pairs
        radii = sorted(set(round(b["radius"], 1) for b in bend_90))
        print(f"  Unique radii in 90° bends: {radii}")

        # Pair inner/outer radii (differ by ~thickness)
        pairs = []
        used = set()
        for r1 in radii:
            if r1 in used:
                continue
            for r2 in radii:
                if r2 in used or r2 <= r1:
                    continue
                diff = r2 - r1
                if 0.5 < diff < 15:  # Likely thickness
                    pairs.append((r1, r2, diff))
                    used.add(r1)
                    used.add(r2)
                    break

        print(f"  Radius pairs (inner, outer, thickness): {pairs}")
        print(f"  Estimated bend count: {max(len(pairs), len(radii) // 2) if radii else 0}")

    if fillets:
        print(f"\n--- Fillets (filtered out) ---")
        for f in fillets[:5]:
            print(f"  R={f['radius']:.2f}mm, angle={f['angle']:.1f}°")
        if len(fillets) > 5:
            print(f"  ... and {len(fillets)-5} more")


def main():
    # Test problematic parts
    test_cases = [
        ("10001059694_Rev_00", 3),   # Expected 3, got 11
        ("10001059687_Rev_00", 6),   # Expected 6, got 14
        ("10001057925_Rev_00", 6),   # Expected 6, got 22
        ("10000707475_Rev_00", 0),   # Expected 0 (koker), got 4
    ]

    for artikel, expected in test_cases:
        debug_part(artikel, expected)


if __name__ == "__main__":
    main()
