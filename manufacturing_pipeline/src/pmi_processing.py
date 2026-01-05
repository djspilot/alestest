from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application

def read_step_with_pmi(filename):
    """
    Read STEP file with PMI data (AP242).
    """
    # Create XCAF document
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document("XDE")
    app.NewDocument("MDTV-XCAF", doc)
    
    # Configure reader for PMI
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetGDTMode(True)  # Enable GD&T import
    
    status = reader.ReadFile(filename)
    if not status:
        raise ValueError(f"Failed to read STEP file with PMI: {filename}")
        
    reader.Transfer(doc)
    
    # Access PMI through XCAFDoc tools
    # shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dim_tol_tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    
    # Iterate through dimensions
    dim_labels = []
    # dim_tol_tool.GetDimensionLabels(dim_labels) # This might need adjustment for OCP list handling
    
    # Placeholder for processing dimensional tolerances
    # In a real implementation, you would iterate dim_labels and extract values
    
    return doc, dim_labels
