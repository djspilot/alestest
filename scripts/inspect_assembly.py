import cadquery as cq
from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_COMPOUND
from OCP.TopExp import TopExp_Explorer

def inspect_structure(filepath):
    print(f"Inspecting {filepath}...")
    model = cq.importers.importStep(filepath)
    shape = model.val().wrapped
    
    # Count Solids
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    solids = []
    while exp.More():
        solids.append(exp.Current())
        exp.Next()
        
    print(f"Total Solids found: {len(solids)}")
    
    # Count Shells
    exp = TopExp_Explorer(shape, TopAbs_SHELL)
    shells = 0
    while exp.More():
        shells += 1
        exp.Next()
    print(f"Total Shells found: {shells}")

    # Check if it's a compound
    if shape.ShapeType() == TopAbs_COMPOUND:
        print("Root shape is a COMPOUND.")
    else:
        print(f"Root shape type is: {shape.ShapeType()}")

if __name__ == "__main__":
    inspect_structure("core_one_assembly.step")
