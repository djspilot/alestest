
import sys
import os
import json

# FreeCAD paths
freecad_app = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
freecad_lib = f"{freecad_app}/Contents/Resources/lib"
freecad_mod = f"{freecad_app}/Contents/Resources/Mod"
freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

sys.path.insert(0, freecad_lib)
sys.path.insert(0, freecad_mod)
sys.path.insert(0, freecad_user_mod)
sys.path.insert(0, os.path.join(freecad_user_mod, "sheetmetal"))

# Mock GUI
class MockObject:
    Refine = True
class MockSelection:
    _selection = [MockObject()]
    @staticmethod
    def getSelection(): return MockSelection._selection
    @staticmethod
    def addSelection(*args): pass
class MockGui:
    Selection = MockSelection()
sys.modules["FreeCADGui"] = MockGui()

import FreeCAD
import Part
import SheetMetalUnfolder

step_path = "/Users/ds/Projecten/alestest/parts/fwofferte20253515bestanden/10000703900_Rev_00.step"
shape = Part.Shape()
shape.read(step_path)

kFactorLookup = {t: 0.44 for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]}

# Get solids
solids = shape.Solids if shape.Solids else [shape]
solid = sorted(solids, key=lambda s: s.Volume, reverse=True)[0]

# Find base face
planar_faces = []
for i, face in enumerate(solid.Faces):
    try:
        if "Plane" in face.Surface.TypeId:
            planar_faces.append({"index": i, "area": face.Area})
    except:
        pass
planar_faces.sort(key=lambda x: x["area"], reverse=True)
base_idx = planar_faces[0]["index"]

doc = FreeCAD.newDocument("UnfoldDoc")
obj = doc.addObject("Part::Feature", "SheetPart")
obj.Shape = solid
doc.recompute()

unfold_tree = SheetMetalUnfolder.SheetTree(solid, base_idx, kFactorLookup)
unfold_tree.Bend_analysis(base_idx, None)

print("Root object attributes:")
print(dir(unfold_tree.root))

print("\nTraversing tree:")
def traverse(node, depth=0):
    indent = "  " * depth
    print(f"{indent}Node: {node}")
    
    # Inspect attributes found in dir()
    attrs = ['actual_angle', 'bend_angle', 'bend_dir', 'node_type', 'innerRadius']
    for attr in attrs:
        if hasattr(node, attr):
            print(f"{indent}  {attr}: {getattr(node, attr)}")
            
    if hasattr(node, "child_list"):
        for child in node.child_list:
            traverse(child, depth + 1)
            
traverse(unfold_tree.root)
