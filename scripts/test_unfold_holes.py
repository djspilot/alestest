#!/usr/bin/env python3
"""
Test unfold-based hole counting.

Strategy:
1. Try to unfold the part first
2. Count holes on the flat pattern (most accurate, like Spaceclaim)
3. Compare with Spaceclaim reference data
"""
import sys
import os
import glob
import xml.etree.ElementTree as ET

# FreeCAD paths
FREECAD_APP = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
FREECAD_LIB = f"{FREECAD_APP}/Contents/Resources/lib"
FREECAD_MOD = f"{FREECAD_APP}/Contents/Resources/Mod"
FREECAD_USER_MOD = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

sys.path.insert(0, FREECAD_LIB)
sys.path.insert(0, FREECAD_MOD)
sys.path.insert(0, FREECAD_USER_MOD)
sys.path.insert(0, os.path.join(FREECAD_USER_MOD, "sheetmetal"))

import FreeCAD
import Part

# Mock FreeCADGui for headless mode
class MockSelection:
    _selection = []

    @classmethod
    def getSelection(cls):
        return cls._selection

    @classmethod
    def clearSelection(cls):
        cls._selection = []

    @classmethod
    def addSelection(cls, obj):
        cls._selection.append(obj)


class MockFreeCADGui:
    Selection = MockSelection()


# Install mock
try:
    import FreeCADGui
    FreeCADGui.Selection.getSelection()
except (ImportError, AttributeError):
    import sys
    sys.modules['FreeCADGui'] = MockFreeCADGui()
    FreeCADGui = MockFreeCADGui()


def try_unfold(shape):
    """Try to unfold the shape and return flat pattern info."""
    try:
        import SheetMetalUnfolder

        solid = shape.Solids[0] if shape.Solids else shape

        # Find base face candidates (largest planar faces)
        planar_faces = []
        for i, face in enumerate(solid.Faces):
            try:
                if 'Plane' in face.Surface.TypeId:
                    planar_faces.append({'index': i, 'area': face.Area})
            except:
                pass

        if not planar_faces:
            return None

        planar_faces.sort(key=lambda x: x['area'], reverse=True)

        # K-factor lookup
        kFactorLookup = {t: 0.44 for t in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]}

        # Try up to 3 base faces
        for base_info in planar_faces[:3]:
            try:
                doc = FreeCAD.newDocument("UnfoldDoc")
                obj = doc.addObject("Part::Feature", "SheetPart")
                obj.Shape = solid
                doc.recompute()

                # Mock object wrapper with Refine attribute
                class ObjWrapper:
                    def __init__(self, real_obj):
                        self._obj = real_obj
                        self.Refine = False

                    def __getattr__(self, name):
                        return getattr(self._obj, name)

                wrapped_obj = ObjWrapper(obj)
                MockSelection._selection = [wrapped_obj]

                unfold_tree = SheetMetalUnfolder.SheetTree(solid, base_info['index'], kFactorLookup)

                if unfold_tree.error_code:
                    FreeCAD.closeDocument("UnfoldDoc")
                    continue

                unfold_tree.Bend_analysis(base_info['index'], None)

                if unfold_tree.error_code:
                    FreeCAD.closeDocument("UnfoldDoc")
                    continue

                if hasattr(unfold_tree, 'root') and unfold_tree.root:
                    theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                    if not unfold_tree.error_code and theFaceList:
                        try:
                            flat_shell = Part.Shell(theFaceList)
                        except:
                            flat_shell = Part.Compound(theFaceList)

                        FreeCAD.closeDocument("UnfoldDoc")
                        return {'shape': flat_shell, 'bend_lines': foldLines, 'bend_count': len(foldLines)}

                FreeCAD.closeDocument("UnfoldDoc")
            except Exception as e:
                try:
                    FreeCAD.closeDocument("UnfoldDoc")
                except:
                    pass
                continue

        return None
    except ImportError:
        return None
    except Exception:
        return None


def count_holes_on_flat(flat_shape):
    """Count holes on the unfolded flat pattern.

    Even on a flat pattern, the shell has TOP and BOTTOM faces.
    So we count inner wires on ALL planar faces and divide by 2.
    """
    total_holes = 0

    for face in flat_shape.Faces:
        try:
            if 'Plane' in face.Surface.TypeId:
                # Count inner wires (holes) on this face
                inner_wires = len(face.Wires) - 1  # Subtract outer wire
                if inner_wires > 0:
                    total_holes += inner_wires
        except:
            pass

    # Divide by 2 because flat pattern shell has top + bottom faces
    return total_holes // 2


def count_holes_on_3d(shape):
    """Count holes on the 3D shape (fallback method).

    For 3D parts, holes appear on both top and bottom faces, so we divide by 2.
    """
    inner_wire_count = 0
    for face in shape.Faces:
        try:
            if 'Plane' in face.Surface.TypeId:
                inner_wire_count += len(face.Wires) - 1  # Inner wires = holes
        except:
            pass

    return inner_wire_count // 2  # Divide by 2 for top/bottom


def analyze_step(step_path):
    """Analyze a STEP file with unfold-first strategy."""
    shape = Part.Shape()
    shape.read(step_path)

    # Try unfold first
    unfold_result = try_unfold(shape)

    if unfold_result:
        # Count holes on flat pattern
        holes = count_holes_on_flat(unfold_result['shape'])
        bends = unfold_result['bend_count']
        method = 'unfold'
    else:
        # Fallback to 3D
        holes = count_holes_on_3d(shape)

        # Count bends from cylindrical faces
        bends = 0
        for face in shape.Faces:
            try:
                if 'Cylinder' in face.Surface.TypeId:
                    cyl = face.Surface
                    radius = cyl.Radius
                    axis = cyl.Axis
                    cyl_bbox = face.BoundBox

                    if abs(axis.z) > 0.9:
                        cyl_height = cyl_bbox.ZLength
                    elif abs(axis.x) > 0.9:
                        cyl_height = cyl_bbox.XLength
                    else:
                        cyl_height = cyl_bbox.YLength

                    if 0.3 <= radius <= 15 and cyl_height > 15:
                        bends += 1
            except:
                pass
        bends = bends // 2
        method = '3D'

    return {'holes': holes, 'bends': bends, 'method': method}


def get_spaceclaim_data(folder):
    """Get Spaceclaim reference data from XML."""
    sc_data = {}
    for xml_file in glob.glob(f"{folder}/*.xml"):
        try:
            tree = ET.parse(xml_file)
            for calc in tree.getroot().findall('.//CalculationResult'):
                part = calc.findtext('Sheet_PartName', '')
                if part:
                    sc_data[part] = {
                        'holes': int(calc.findtext('Sheet_NrHoles', '0') or 0),
                        'bends': int(calc.findtext('Sheet_NrBends', '0') or 0)
                    }
        except:
            pass
    return sc_data


def main():
    base = "/Users/ds/Projecten/alestest/AI-voorbeelden"

    results = []

    for folder in sorted(glob.glob(f"{base}/*")):
        if not os.path.isdir(folder):
            continue

        step_files = glob.glob(f"{folder}/*.stp") + glob.glob(f"{folder}/*.step") + glob.glob(f"{folder}/*.STEP")
        sc_data = get_spaceclaim_data(folder)

        for step_file in step_files:
            part_name = os.path.splitext(os.path.basename(step_file))[0]

            # Find matching Spaceclaim data
            sc = sc_data.get(part_name)
            if not sc:
                for key in sc_data:
                    if key in part_name or part_name in key:
                        sc = sc_data[key]
                        break

            if not sc:
                continue  # Skip if no reference data

            print(f"Analyzing: {part_name}...", end=" ", flush=True)

            try:
                pipe = analyze_step(step_file)

                holes_match = pipe['holes'] == sc['holes']
                bends_match = pipe['bends'] == sc['bends']

                results.append({
                    'part': part_name,
                    'sc_holes': sc['holes'],
                    'sc_bends': sc['bends'],
                    'pipe_holes': pipe['holes'],
                    'pipe_bends': pipe['bends'],
                    'method': pipe['method'],
                    'holes_match': holes_match,
                    'bends_match': bends_match
                })

                status = "✓" if holes_match and bends_match else "✗"
                print(f"{status} SC={sc['holes']}/{sc['bends']} Pipe={pipe['holes']}/{pipe['bends']} ({pipe['method']})")

            except Exception as e:
                print(f"ERROR: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("SAMENVATTING - Unfold-based Hole Detection")
    print("=" * 70)

    total = len(results)
    holes_match = sum(1 for r in results if r['holes_match'])
    bends_match = sum(1 for r in results if r['bends_match'])
    unfold_count = sum(1 for r in results if r['method'] == 'unfold')

    print(f"\nTotaal onderdelen met Spaceclaim data: {total}")
    print(f"Unfold geslaagd: {unfold_count}/{total} ({100*unfold_count/total:.0f}%)")

    print(f"\nGaten detectie:")
    print(f"  Exact match: {holes_match}/{total} ({100*holes_match/total:.0f}%)")

    print(f"\nZettingen detectie:")
    print(f"  Exact match: {bends_match}/{total} ({100*bends_match/total:.0f}%)")

    # Show mismatches
    print(f"\n--- Mismatches ---")
    for r in results:
        if not r['holes_match'] or not r['bends_match']:
            print(f"  {r['part']}: SC={r['sc_holes']}/{r['sc_bends']} Pipe={r['pipe_holes']}/{r['pipe_bends']} ({r['method']})")


if __name__ == "__main__":
    main()
