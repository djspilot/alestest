import sys
import os
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name

def probe_pmi(filename):
    print(f"Probing {filename} for PMI and Metadata...")
    
    # Create XCAF App and Document
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    
    # Initialize Reader
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetGDTMode(True)
    reader.SetMatMode(True)
    
    # Read File
    status = reader.ReadFile(filename)
    if status != 1: # IFSelect_RetDone
        print("Error: Could not read STEP file.")
        return

    # Transfer to Document
    if not reader.Transfer(doc):
        print("Error: Could not transfer to document.")
        return

    # Get Tools
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    dim_tol_tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    
    # 1. Check for Shapes and Names
    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)
    print(f"\nFound {labels.Length()} top-level shapes.")
    
    for i in range(1, labels.Length() + 1):
        label = labels.Value(i)
        name_attr = TDataStd_Name()
        name = "Unknown"
        if label.FindAttribute(TDataStd_Name.GetID_s(), name_attr):
            name = name_attr.Get().ToExtString()
        print(f"  Shape {i}: {name}")

    # 2. Check for GD&T (Dimensions and Tolerances)
    dim_labels = TDF_LabelSequence()
    dim_tol_tool.GetDimensionLabels(dim_labels)
    print(f"\nFound {dim_labels.Length()} Dimensions.")
    
    tol_labels = TDF_LabelSequence()
    dim_tol_tool.GetGeomToleranceLabels(tol_labels)
    print(f"Found {tol_labels.Length()} Geometric Tolerances.")
    
    # 3. Check for Datums
    datum_labels = TDF_LabelSequence()
    dim_tol_tool.GetDatumLabels(datum_labels)
    print(f"Found {datum_labels.Length()} Datums.")

    # 4. Check for Notes/Annotations (often stored as D&GT or separate annotations)
    # Note: OCP/OCC handling of notes can be complex, often attached to shapes.
    
    print("\nProbe complete.")

if __name__ == "__main__":
    probe_pmi("core_one_assembly.step")
