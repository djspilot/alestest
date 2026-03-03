"""
Cut Features Extraction for Sheet Metal Parts
==============================================

Fase 1: Gaten en snijdata voor plaat + gezette_plaat classificaties.

WANNEER wordt dit uitgevoerd?
------------------------------
- Alleen voor parts met classification = "plaat" OF "gezette_plaat"
- Wordt aangeroepen vanuit xml_exporter._process_plaat_item()
- Na unfold poging (als gezette_plaat), vóór XML field population

WAT wordt er gedetecteerd?
---------------------------
1. Gaten (cylindrisch): detect_holes() uit step_processing.py
2. Vormgaten (sleuven/rectangles): detect_shaped_holes() uit step_processing.py
3. Gatcontourlengtes: perimeter van elke hole inner wire
4. Buitencontour: outer wire perimeter van grootste planar face
5. Totale snijlengte: sum(gatcontours) + buitencontour
6. Box dimensions: X en Y van bounding box

FLAT vs 3D strategie:
---------------------
- Als unfold succesvol → analyseer flat pattern (nauwkeuriger voor gezette plaat)
- Als unfold mislukt / niet geprobeerd → analyseer 3D solid

VEILIGHEID:
-----------
- Gebruikt ALLEEN bestaande detectiefuncties (geen nieuwe algoritmes)
- Faalt gracefully: bij exceptions retourneer None i.p.v. crash
- Backwards compatible: caller kan fallback naar placeholders

Auteur: ALES Manufacturing Pipeline
Datum: 3 maart 2026
Fase: 1 (plaat + gezette_plaat)
"""

from typing import Dict, List, Optional, Any
import logging
from dataclasses import dataclass

import cadquery as cq
from OCP.TopAbs import TopAbs_FACE
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape, TopoDS_Face
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

# Import bestaande detectiefuncties (NIET wijzigen in step_processing.py!)
from .step_processing import detect_holes, detect_shaped_holes, deduplicate_holes

logger = logging.getLogger(__name__)


@dataclass
class CutFeatures:
    """
    Result container voor cut features extractie.
    
    Alle lengtes in millimeters.
    """
    nr_holes: int                      # Totaal aantal gaten (cilindrisch + vorm)
    hole_contours: List[float]         # Perimeter van elk gat (mm)
    hole_radii: List[float]            # Radius/halve-breedte per gat (mm)
    outer_contour: float               # Buitencontour lengte (mm)
    total_contour: float               # Totale snijlengte (mm)
    box_x: float                       # X-dimensie bounding box (mm)
    box_y: float                       # Y-dimensie bounding box (mm)
    source: str                        # "flat" of "3d"
    
    # Detail info voor debugging
    nr_cylindrical: int = 0
    nr_shaped: int = 0
    shaped_types: List[str] = None     # ["Slot", "Rect", ...]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict voor logging/debugging."""
        return {
            "nr_holes": self.nr_holes,
            "hole_contours": self.hole_contours,
            "hole_radii": self.hole_radii,
            "outer_contour": self.outer_contour,
            "total_contour": self.total_contour,
            "box_x": self.box_x,
            "box_y": self.box_y,
            "source": self.source,
            "nr_cylindrical": self.nr_cylindrical,
            "nr_shaped": self.nr_shaped,
            "shaped_types": self.shaped_types or []
        }


def extract_cut_features_for_sheet(
    solid: TopoDS_Shape,
    unfold_result: Optional[Dict[str, Any]] = None,
    part_classification: str = "plaat"
) -> Optional[CutFeatures]:
    """
    Extraheer gaten, snijlengtes en box dimensions voor plaatwerk.
    
    FLOW:
    -----
    1. Bepaal analyse domain (flat pattern of 3D solid)
    2. Detect cylindrische gaten via detect_holes()
    3. Detect vormgaten via detect_shaped_holes()
    4. Dedupliceer overlappende gaten
    5. Bereken hole contours (inner wire perimeters)
    6. Bereken outer contour (grootste face outer wire)
    7. Bereken bounding box dimensions
    8. Return CutFeatures object
    
    Parameters:
    -----------
    solid : TopoDS_Shape
        De te analyseren solid (3D) of flat pattern
    unfold_result : dict, optional
        Als unfold is uitgevoerd: {"success": bool, "flat_pattern": TopoDS_Shape, ...}
    part_classification : str
        "plaat" of "gezette_plaat" (voor logging)
    
    Returns:
    --------
    CutFeatures of None bij falen
    
    VEILIGHEID:
    -----------
    - Faalt gracefully bij exceptions
    - Gebruikt alleen gevalideerde bestaande functies
    - Geen side effects op input shapes
    """
    try:
        logger.info(f"[CutFeatures] Start extractie voor {part_classification}")
        
        # STAP 1: Bepaal analyse domain
        # ==============================
        # Als unfold succesvol: gebruik flat pattern (nauwkeuriger)
        # Anders: gebruik 3D solid
        analysis_shape = solid
        source = "3d"
        
        if unfold_result and unfold_result.get("success") and unfold_result.get("flat_pattern"):
            logger.info("[CutFeatures] Gebruik flat pattern voor analyse")
            analysis_shape = unfold_result["flat_pattern"]
            source = "flat"
        else:
            logger.info("[CutFeatures] Gebruik 3D solid voor analyse (geen unfold)")
        
        # Convert naar CadQuery object voor detect_holes()
        cq_solid = cq.Solid(analysis_shape)
        cq_object = cq.Workplane("XY").newObject([cq_solid])
        
        # STAP 2: Detect cylindrische gaten
        # ==================================
        # Gebruikt detect_holes() uit step_processing.py
        # filter_bores=True: sluit draaideel boring gaten uit
        # is_flat_pattern: geeft aan of we flat of 3D analyseren
        is_flat = (source == "flat")
        logger.info(f"[CutFeatures] Detect cylindrische gaten (flat={is_flat})...")
        
        cylindrical_holes = detect_holes(
            cq_object,
            filter_bores=True,
            is_flat_pattern=is_flat
        )
        logger.info(f"[CutFeatures] Gevonden: {len(cylindrical_holes)} cylindrische gaten")
        
        # STAP 3: Detect vormgaten (sleuven, rectangles, polygonen)
        # ==========================================================
        # Gebruikt detect_shaped_holes() uit step_processing.py
        # BELANGRIJK: detect_shaped_holes verwacht CadQuery Workplane
        logger.info("[CutFeatures] Detect vormgaten (sleuven/rectangles)...")
        
        # Create Workplane object for detect_shaped_holes
        cq_workplane = cq.Workplane(obj=cq_solid)
        shaped_holes = detect_shaped_holes(cq_workplane)
        logger.info(f"[CutFeatures] Gevonden: {len(shaped_holes)} vormgaten")
        
        # STAP 4: Dedupliceer overlappende gaten
        # ========================================
        # detect_shaped_holes kan cirkels detecteren die al door detect_holes gevonden zijn
        logger.info("[CutFeatures] Dedupliceer overlappende detecties...")
        cylindrical_holes = deduplicate_holes(cylindrical_holes, shaped_holes)
        logger.info(f"[CutFeatures] Na dedup: {len(cylindrical_holes)} cylindrisch, {len(shaped_holes)} vorm")
        
        # STAP 5: Bereken hole contours (perimeters)
        # ===========================================
        hole_contours = []
        hole_radii = []
        shaped_types = []
        
        # Cylindrische gaten: contour = 2*pi*r, radius = diameter/2
        for hole in cylindrical_holes:
            radius = hole.diameter / 2.0
            perimeter = 2.0 * 3.14159265359 * radius
            hole_contours.append(perimeter)
            hole_radii.append(radius)
        
        # Vormgaten: bereken perimeter uit dimensions
        for shaped in shaped_holes:
            # shaped bevat "dim" string zoals "120.5x50.0" (length x width)
            # of "type" zoals "Slot", "Rect", "Poly"
            # Parse dimensions from dim string
            dim_str = shaped.get("dim", "")
            dimensions = _parse_dimensions_from_string(dim_str)
            
            if dimensions:
                length_dim, width_dim = dimensions
                # Perimeter approximation based on shape type
                shape_type = shaped.get("type", "Rect")
                if shape_type == "Slot":
                    # Slot: 2 straight sections + 2 semicircles = 2*length + pi*width
                    # (assuming slot is capsule shape with rounded ends)
                    perimeter = 2.0 * length_dim + 3.14159265359 * width_dim
                else:
                    # Rectangle/Poly: approximate as rectangle
                    perimeter = 2.0 * (length_dim + width_dim)
            else:
                # Fallback: geen dimensions gevonden, gebruik default
                perimeter = 40.0  # Default small hole
                length_dim = 20.0
                width_dim = 10.0
            
            hole_contours.append(perimeter)
            
            # Voor vormgaten: "radius" = halve breedte (gebruikelijk voor ERP)
            radius = width_dim / 2.0
            hole_radii.append(radius)
            
            shaped_types.append(shaped.get("type", "Unknown"))
        
        # STAP 6: Bereken outer contour
        # ==============================
        # Vind grootste planaire face, neem outer wire perimeter
        logger.info("[CutFeatures] Bereken buitencontour...")
        outer_contour = _get_outer_contour_length(analysis_shape)
        logger.info(f"[CutFeatures] Buitencontour: {outer_contour:.2f} mm")
        
        # STAP 7: Totale snijlengte
        # ==========================
        total_contour = sum(hole_contours) + outer_contour
        logger.info(f"[CutFeatures] Totale snijlengte: {total_contour:.2f} mm")
        
        # STAP 8: Bounding box dimensions
        # ================================
        bbox = _get_bounding_box(analysis_shape)
        box_x = bbox["xlen"]
        box_y = bbox["ylen"]
        logger.info(f"[CutFeatures] Box dimensions: X={box_x:.2f} mm, Y={box_y:.2f} mm")
        
        # STAP 9: Return resultaat
        # =========================
        result = CutFeatures(
            nr_holes=len(cylindrical_holes) + len(shaped_holes),
            hole_contours=hole_contours,
            hole_radii=hole_radii,
            outer_contour=outer_contour,
            total_contour=total_contour,
            box_x=box_x,
            box_y=box_y,
            source=source,
            nr_cylindrical=len(cylindrical_holes),
            nr_shaped=len(shaped_holes),
            shaped_types=shaped_types
        )
        
        logger.info(f"[CutFeatures] Extractie compleet: {result.to_dict()}")
        return result
        
    except Exception as e:
        logger.error(f"[CutFeatures] FOUT tijdens extractie: {e}", exc_info=True)
        return None


def _get_outer_contour_length(shape: TopoDS_Shape) -> float:
    """
    Bereken outer contour lengte van grootste planaire face.
    
    Strategie:
    ----------
    1. Vind alle planaire faces (GeomAbs_Plane)
    2. Sorteer op oppervlakte (grootste = skin face)
    3. Neem outer wire van grootste face
    4. Bereken perimeter
    
    Returns:
    --------
    Perimeter in mm, of 0.0 bij falen
    """
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.TopoDS import TopoDS, TopoDS_Face
        from OCP.BRepTools import BRepTools
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        
        # Collect planaire faces met oppervlakte
        planar_faces = []
        
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            
            # Check if planar
            surf = BRepAdaptor_Surface(face)
            if surf.GetType() == GeomAbs_Plane:
                # Bereken oppervlakte
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()
                planar_faces.append((face, area))
            
            exp.Next()
        
        if not planar_faces:
            logger.warning("[CutFeatures] Geen planaire faces gevonden voor outer contour")
            return 0.0
        
        # Sorteer op oppervlakte (grootste eerst)
        planar_faces.sort(key=lambda x: x[1], reverse=True)
        largest_face = planar_faces[0][0]
        
        # Haal outer wire
        outer_wire = BRepTools.OuterWire_s(largest_face)
        
        # Bereken perimeter
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(outer_wire, props)
        perimeter = props.Mass()
        
        return perimeter
        
    except Exception as e:
        logger.error(f"[CutFeatures] Fout bij outer contour berekening: {e}")
        return 0.0


def _get_bounding_box(shape: TopoDS_Shape) -> Dict[str, float]:
    """
    Bereken bounding box dimensions.
    
    Returns:
    --------
    Dict met xlen, ylen, zlen in mm
    """
    try:
        cq_shape = cq.Shape(shape)
        bb = cq_shape.BoundingBox()
        
        return {
            "xlen": bb.xlen,
            "ylen": bb.ylen,
            "zlen": bb.zlen
        }
        
    except Exception as e:
        logger.error(f"[CutFeatures] Fout bij bounding box: {e}")
        return {"xlen": 0.0, "ylen": 0.0, "zlen": 0.0}


def _parse_dimensions_from_string(dim_str: str) -> Optional[tuple]:
    """
    Parse dimensions from string like "120.5x50.0" -> (120.5, 50.0).
    
    Returns:
    --------
    Tuple (length, width) or None if parse fails
    """
    try:
        if not dim_str or 'x' not in dim_str:
            return None
        
        parts = dim_str.lower().split('x')
        if len(parts) != 2:
            return None
        
        length = float(parts[0].strip())
        width = float(parts[1].strip())
        
        return (length, width)
        
    except Exception as e:
        logger.debug(f"[CutFeatures] Could not parse dimensions from '{dim_str}': {e}")
        return None


# ============================================================================
# TOEKOMSTIGE UITBREIDINGEN (Fase 2: profiel)
# ============================================================================

def extract_cut_features_for_profile(
    solid: TopoDS_Shape,
    part_classification: str = "profiel"
) -> Optional[CutFeatures]:
    """
    FASE 2: Gaten en snijdata voor profielen (buis, koker, hoekstaal).
    
    TODO: Implementeer in Fase 2
    - Geen unfold (altijd 3D analyse)
    - Andere strategie voor outer contour (cross-section perimeter?)
    - Box dimensions minder relevant (gebruik diameter/cross-section)
    """
    logger.info("[CutFeatures] Profiel extractie nog niet geïmplementeerd (Fase 2)")
    return None
