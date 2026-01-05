#!/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
"""
Test FreeCAD embedding voor sheet metal unfolding
"""
import sys
import os

# FreeCAD paths voor Mac (Homebrew installatie)
FREECAD_APP = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
FREECAD_LIB = os.path.join(FREECAD_APP, "Contents/Resources/lib")
FREECAD_MOD = os.path.join(FREECAD_APP, "Contents/Resources/Mod")
FREECAD_USER_MOD = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

# Add paths
sys.path.insert(0, FREECAD_LIB)
sys.path.insert(0, FREECAD_MOD)
sys.path.insert(0, FREECAD_USER_MOD)

print(f"Python version: {sys.version}")
print(f"FreeCAD lib path: {FREECAD_LIB}")
print(f"Checking lib exists: {os.path.exists(FREECAD_LIB)}")

try:
    print("\n1. Importing FreeCAD...")
    import FreeCAD
    print(f"   FreeCAD version: {FreeCAD.Version()}")

    print("\n2. Importing Part module...")
    import Part
    print("   Part module loaded OK")

    print("\n3. Creating test document...")
    doc = FreeCAD.newDocument("TestDoc")
    print(f"   Document created: {doc.Name}")

    print("\n4. Trying to import SheetMetal...")
    sys.path.insert(0, os.path.join(FREECAD_USER_MOD, "sheetmetal"))

    # List sheetmetal contents
    sm_path = os.path.join(FREECAD_USER_MOD, "sheetmetal")
    print(f"   SheetMetal path: {sm_path}")
    print(f"   Contents: {os.listdir(sm_path)[:10]}...")

    # Try importing the unfolder
    import SheetMetalUnfolder
    print("   SheetMetalUnfolder imported OK!")

    print("\n5. Testing STEP import...")
    test_step = "parts/fwofferte20253515bestanden/10000890096_Rev_00.step"
    if os.path.exists(test_step):
        shape = Part.read(test_step)
        print(f"   STEP loaded: {shape}")
        print(f"   Shape type: {shape.ShapeType}")
        print(f"   Number of faces: {len(shape.Faces)}")
        print(f"   Number of solids: {len(shape.Solids)}")
    else:
        print(f"   Test file not found: {test_step}")

    print("\n✓ FreeCAD embedding works!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    # Cleanup
    if 'doc' in dir():
        FreeCAD.closeDocument("TestDoc")
