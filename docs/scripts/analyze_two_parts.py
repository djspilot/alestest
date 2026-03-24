"""
Stapsgewijze analyse van 2 problematische parts uit 31686-080:
1. EN 10210-2 (ronde buis 88.9x4, L=65mm) → foutief als plaat
2. DIN 1026 - U 160 - 600 (UNP160) → foutief als plaat

Doel: Begrijpen WAAROM ze fout geclassificeerd worden en hoe te verbeteren.
"""

import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import (
    classify_solid, 
    get_solid_bounding_box,
    get_solid_volume,
    _is_plate_by_face_analysis,
    _get_top2_face_percent
)
from manufacturing_pipeline.analysis.classification_variables import (
    PLATE_FACE_TOP2_THRESHOLD_PCT,
    PLATE_THICK_MAX_MM,
    PLATE_THICKNESS_RATIO_MAX,
    PLATE_ASPECT_RATIO_MIN,
    PROFILE_SMALLEST_MIN_MM,
    PROFILE_LENGTH_RATIO_MIN,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_CROSS_RATIO_MAX,
    PROFILE_VOLUME_RATIO_STRONG_MIN,
    PROFILE_VOLUME_RATIO_WEAK_MIN,
    PROFILE_SA_V_RATIO_MAX
)
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
from OCP.TopoDS import TopoDS
from pathlib import Path
import sys


def analyze_part_thickness_variation(solid):
    """
    Analyseer dikte-variatie in een solid.
    
    Voor platen: min/max dikte uit bbox (constant verwacht)
    Voor profielen: kan variabel zijn (UNP, I-balk, etc.)
    
    Returns:
        {
            'min_thickness': float,
            'max_thickness': float,
            'thickness_variance': float,  # max - min
            'relative_variance': float,   # (max-min)/min
            'is_constant_thickness': bool # variance < threshold
        }
    """
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    
    bbox = Bnd_Box()
    BRepBndLib.Add_s(solid, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dims_sorted = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
    
    # Voor buis/profiel: check shell thickness
    shell_thicknesses = []
    exp_shell = TopExp_Explorer(solid, TopAbs_SHELL)
    
    if exp_shell.More():
        # Heb shells -> mogelijk holle constructie
        # Voor ronde buis: diameter_outer - diameter_inner = 2 * wall_thickness
        # Voor UNP: variabele wanddikte (kenmerkend!)
        
        # Simpele benadering: kleinste bbox dimensie als "dikte"
        thickness_est = dims_sorted[0]
        
        # Voor cylindrische vormen: check of het hol is
        volume = get_solid_volume(solid)
        bbox_vol = dims_sorted[0] * dims_sorted[1] * dims_sorted[2]
        volume_ratio = volume / bbox_vol if bbox_vol > 0 else 0
    else:
        thickness_est = dims_sorted[0]
        volume_ratio = 1.0
    
    # Detecteer dikte-variatie via face analysis
    # Voor constant: alle faces op min/max Z (of X/Y) moeten parallel zijn
    # Voor variabel: faces zijn niet parallel (taper, variabele dikte)
    
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    face_areas = []
    planar_faces = []
    
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor_Surface(face, True)
        
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()
        
        if surf.GetType() == GeomAbs_Plane:
            planar_faces.append((face, area))
        
        face_areas.append(area)
        exp.Next()
    
    # Voor constante dikte: top 2 planaire faces moeten ~gelijk zijn
    if len(planar_faces) >= 2:
        planar_faces.sort(key=lambda x: x[1], reverse=True)
        top_face_area = planar_faces[0][1]
        second_face_area = planar_faces[1][1] if len(planar_faces) > 1 else 0
        
        if top_face_area > 0:
            face_area_ratio = second_face_area / top_face_area
            is_constant = 0.8 < face_area_ratio < 1.2  # Top 2 faces ~gelijk
        else:
            is_constant = False
    else:
        is_constant = False
    
    # Relatieve variatie
    if thickness_est > 0:
        # Voor profielen: wanddikte kan 30-200% variëren (UNP: flens vs web)
        # Voor platen: <5% variatie verwacht
        relative_variance = 0.0  # Placeholder (echte berekening complex)
    else:
        relative_variance = 0.0
    
    return {
        'min_thickness': thickness_est,
        'max_thickness': thickness_est,  # Vereenvoudigd
        'thickness_variance': 0.0,
        'relative_variance': relative_variance,
        'is_constant_thickness': is_constant,
        'has_shell': exp_shell.More(),
        'volume_ratio': volume_ratio
    }


def analyze_hollow_tube(solid):
    """
    Detecteer holle buizen (ronde, vierkante koker).
    
    Kenmerken:
    - Hoge cylindrical face area (>60% voor ronde buis)
    - Lage volume ratio (<0.7, want hol)
    - Aspect ratio L/D (verwacht >1.0 voor profiel buizen)
    
    Returns:
        {
            'is_hollow_tube': bool,
            'is_cylindrical': bool,
            'cylindrical_pct': float,
            'volume_ratio': float,
            'aspect_ratio': float,  # L/D
            'tube_type': 'round' | 'rectangular' | None
        }
    """
    dims = get_solid_bounding_box(solid)
    dims_sorted = sorted(dims)
    smallest, middle, longest = dims_sorted
    
    volume = get_solid_volume(solid)
    bbox_vol = smallest * middle * longest if smallest > 0 else 1.0
    volume_ratio = volume / bbox_vol
    
    # Face area analyse
    total_area = 0
    cylindrical_area = 0
    planar_area = 0
    
    from OCP.TopoDS import TopoDS
    
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor_Surface(face, True)
        
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()
        total_area += area
        
        if surf.GetType() == GeomAbs_Cylinder:
            cylindrical_area += area
        elif surf.GetType() == GeomAbs_Plane:
            planar_area += area
        
        exp.Next()
    
    cylindrical_pct = cylindrical_area / total_area if total_area > 0 else 0
    planar_pct = planar_area / total_area if total_area > 0 else 0
    
    # Aspect ratio
    if middle > 0:
        aspect_ratio = longest / middle
    else:
        aspect_ratio = 0
    
    # Detectie holle ronde buis:
    # - cylindrical_pct > 60%
    # - volume_ratio < 0.7 (hol)
    # - aspect_ratio > 0.5 (niet te plat gedrukt)
    
    is_cylindrical = cylindrical_pct > 0.6
    is_hollow = volume_ratio < 0.7
    is_tube_shape = aspect_ratio > 0.5
    
    is_hollow_tube = is_cylindrical and is_hollow and is_tube_shape
    
    # Type bepalen
    tube_type = None
    if is_hollow_tube:
        tube_type = 'round'
    elif planar_pct > 0.8 and is_hollow:
        tube_type = 'rectangular'  # Vierkante koker
    
    return {
        'is_hollow_tube': is_hollow_tube,
        'is_cylindrical': is_cylindrical,
        'cylindrical_pct': cylindrical_pct * 100,
        'planar_pct': planar_pct * 100,
        'volume_ratio': volume_ratio,
        'aspect_ratio': aspect_ratio,
        'tube_type': tube_type,
        'is_hollow': is_hollow
    }


def analyze_single_part(cq_obj, solid, part_name: str):
    """Volledige analyse van één part met alle diagnostics."""
    print(f"\n{'='*80}")
    print(f"PART ANALYSE: {part_name}")
    print(f"{'='*80}")
    
    # Basis geometrie
    dims = get_solid_bounding_box(solid)
    dims_sorted = sorted(dims)
    smallest, middle, longest = dims_sorted
    volume = get_solid_volume(solid)
    bbox_vol = smallest * middle * longest if smallest > 0 else 1.0
    
    print(f"\n[1] BASIS GEOMETRIE")
    print(f"    BBox dimensies: {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    print(f"    Sorted dims:    {smallest:.1f} × {middle:.1f} × {longest:.1f} mm")
    print(f"    Volume:         {volume:.0f} mm³")
    print(f"    BBox volume:    {bbox_vol:.0f} mm³")
    
    # Ratio's (huidige classificatie regels)
    thickness_ratio = smallest / middle if middle > 0 else 0
    aspect_ratio = longest / middle if middle > 0 else 0
    cross_ratio = smallest / middle if middle > 0 else 0
    length_ratio = longest / smallest if smallest > 0 else 0
    volume_ratio = volume / bbox_vol if bbox_vol > 0 else 0
    
    print(f"\n[2] HUIDIGE CLASSIFICATIE RATIO'S")
    print(f"    thickness_ratio: {thickness_ratio:.3f}  (smallest/middle)")
    print(f"    aspect_ratio:    {aspect_ratio:.3f}  (longest/middle)")
    print(f"    cross_ratio:     {cross_ratio:.3f}  (smallest/middle)")
    print(f"    length_ratio:    {length_ratio:.3f}  (longest/smallest)")
    print(f"    volume_ratio:    {volume_ratio:.3f}  (volume/bbox)")
    
    # Face analyse (plaat detectie)
    top2_pct = _get_top2_face_percent(solid)
    is_plate_face = _is_plate_by_face_analysis(solid, threshold=PLATE_FACE_TOP2_THRESHOLD_PCT)
    
    print(f"\n[3] FACE ANALYSE (Plaat Detectie)")
    print(f"    Top2 face %:     {top2_pct:.1f}%")
    print(f"    Threshold:       {PLATE_FACE_TOP2_THRESHOLD_PCT}%")
    print(f"    → is_plate:      {is_plate_face} {'✓ PLAAT' if is_plate_face else '✗'}")
    
    # Holle buis detectie (NIEUW)
    tube_info = analyze_hollow_tube(solid)
    
    print(f"\n[4] HOLLE BUIS DETECTIE (Nieuw)")
    print(f"    Cylindrical:     {tube_info['cylindrical_pct']:.1f}%")
    print(f"    Planar:          {tube_info['planar_pct']:.1f}%")
    print(f"    Volume ratio:    {tube_info['volume_ratio']:.3f}")
    print(f"    Is hollow:       {tube_info['is_hollow']}")
    print(f"    Aspect L/D:      {tube_info['aspect_ratio']:.2f}")
    print(f"    → is_hollow_tube: {tube_info['is_hollow_tube']} {'✓ BUIS' if tube_info['is_hollow_tube'] else '✗'}")
    if tube_info['tube_type']:
        print(f"    Tube type:       {tube_info['tube_type']}")
    
    # Dikte-variatie analyse (NIEUW)
    thickness_info = analyze_part_thickness_variation(solid)
    
    print(f"\n[5] DIKTE-VARIATIE ANALYSE (Nieuw)")
    print(f"    Min thickness:   {thickness_info['min_thickness']:.2f} mm")
    print(f"    Has shell:       {thickness_info['has_shell']}")
    print(f"    Volume ratio:    {thickness_info['volume_ratio']:.3f}")
    print(f"    → Constant dikte: {thickness_info['is_constant_thickness']} {'✓' if thickness_info['is_constant_thickness'] else '✗ VARIABEL (profiel?)'}")
    
    # Huidige classificatie
    current_class = classify_solid(solid)
    
    print(f"\n[6] HUIDIGE CLASSIFICATIE")
    print(f"    Result:          {current_class.upper()}")
    
    # Regel-by-regel check (debuggen waarom het plaat is)
    print(f"\n[7] CLASSIFICATIE REGELS CHECK")
    
    # PLAAT check 1: Face-based
    if is_plate_face:
        print(f"    ✓ PLAAT regel 1: Top2 faces {top2_pct:.1f}% > {PLATE_FACE_TOP2_THRESHOLD_PCT}%")
    
    # PLAAT check 2: Thin plate
    is_thin_plate = (smallest < PLATE_THICK_MAX_MM and 
                     thickness_ratio < PLATE_THICKNESS_RATIO_MAX and 
                     aspect_ratio > PLATE_ASPECT_RATIO_MIN)
    if is_thin_plate:
        print(f"    ✓ PLAAT regel 2: Thin plate (t<{PLATE_THICK_MAX_MM}, t_ratio<{PLATE_THICKNESS_RATIO_MAX}, aspect>{PLATE_ASPECT_RATIO_MIN})")
    
    # PROFIEL check
    is_profiel_basic = (smallest >= PROFILE_SMALLEST_MIN_MM and 
                        length_ratio >= PROFILE_LENGTH_RATIO_MIN and 
                        PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX)
    
    if is_profiel_basic:
        print(f"    ○ PROFIEL basis: smallest≥{PROFILE_SMALLEST_MIN_MM}, length_ratio≥{PROFILE_LENGTH_RATIO_MIN}, cross_ratio {PROFILE_CROSS_RATIO_MIN}-{PROFILE_CROSS_RATIO_MAX}")
        
        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            print(f"    ✓ PROFIEL regel: vol_ratio {volume_ratio:.3f} > {PROFILE_VOLUME_RATIO_STRONG_MIN} → Solid profiel")
        elif volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            print(f"    ~ PROFIEL ambiguous: vol_ratio {volume_ratio:.3f} in range {PROFILE_VOLUME_RATIO_WEAK_MIN}-{PROFILE_VOLUME_RATIO_STRONG_MIN}")
        else:
            print(f"    ✗ PROFIEL rejected: vol_ratio {volume_ratio:.3f} < {PROFILE_VOLUME_RATIO_WEAK_MIN}")
    else:
        print(f"    ✗ PROFIEL basis NIET voldaan:")
        if smallest < PROFILE_SMALLEST_MIN_MM:
            print(f"       - smallest {smallest:.1f} < {PROFILE_SMALLEST_MIN_MM} mm")
        if length_ratio < PROFILE_LENGTH_RATIO_MIN:
            print(f"       - length_ratio {length_ratio:.1f} < {PROFILE_LENGTH_RATIO_MIN}")
        if not (PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX):
            print(f"       - cross_ratio {cross_ratio:.3f} buiten range {PROFILE_CROSS_RATIO_MIN}-{PROFILE_CROSS_RATIO_MAX}")
    
    # VOORGESTELDE NIEUWE CLASSIFICATIE
    print(f"\n[8] VOORGESTELDE CLASSIFICATIE (met nieuwe regels)")
    
    # Regel 1: Holle buis (cylindrisch + hol)
    if tube_info['is_hollow_tube'] and not thickness_info['is_constant_thickness']:
        print(f"    ✓ Holle buis (cylindrisch {tube_info['cylindrical_pct']:.0f}%, hol, L/D={tube_info['aspect_ratio']:.2f})")
        print(f"    → Classificatie: PROFIEL (standaard buis)")
    
    # Regel 2: Variabele dikte + elongated (UNP, I-balk)
    elif not thickness_info['is_constant_thickness'] and length_ratio > 5:
        print(f"    ✓ Variabele dikte + elongated (L/D={length_ratio:.1f})")
        print(f"    → Classificatie: ANDERS (standaard profiel, bijv. UNP)")
    
    # Regel 3: Top2 faces dominant (plaat)
    elif is_plate_face and thickness_info['is_constant_thickness']:
        print(f"    ✓ Top2 faces {top2_pct:.0f}% + constante dikte")
        print(f"    → Classificatie: PLAAT")
    
    else:
        print(f"    → Classificatie: ANDERS (geen match)")
    
    print(f"\n{'='*80}\n")


def main():
    step_file = Path("../stepfiles/31686-080.stp")
    
    if not step_file.exists():
        print(f"❌ Bestand niet gevonden: {step_file}")
        sys.exit(1)
    
    print(f"Laden: {step_file}")
    result = cq.importers.importStep(str(step_file))
    
    # Haal alle solids
    if hasattr(result, 'val'):
        shape = result.val().wrapped
    else:
        shape = result.wrapped
    
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    
    solids = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()
    
    print(f"✓ Geladen: {len(solids)} solids\n")
    
    # Analyseer alleen de 2 problematische parts
    # Part 14 = DIN 1026 - U 160 - 600 (UNP160)
    # Part 16 = EN 10210-2 (ronde buis 88.9x4x65)
    
    # We moeten de juiste solids vinden op basis van dimensies
    print("Zoek EN 10210-2 (ronde buis ~89×89×65 mm)...")
    for i, solid in enumerate(solids):
        dims = get_solid_bounding_box(solid)
        # Zoek solid met dimensies ~89×89×65
        if 85 < max(dims[0], dims[1]) < 95 and 60 < min(dims) < 70:
            print(f"✓ Gevonden op index {i}: {dims[0]:.1f}×{dims[1]:.1f}×{dims[2]:.1f}")
            analyze_single_part(result, solid, "EN 10210-2 - 88,9 x 4 - 65 (ronde buis)")
            break
    
    print("\nZoek DIN 1026 - U 160 - 600 (UNP160 ~65×600×160 mm)...")
    for i, solid in enumerate(solids):
        dims = get_solid_bounding_box(solid)
        dims_sorted = sorted(dims)
        # Zoek solid met L~600, H~160, D~65
        if 590 < max(dims) < 610 and 155 < dims_sorted[1] < 165 and 60 < min(dims) < 70:
            print(f"✓ Gevonden op index {i}: {dims[0]:.1f}×{dims[1]:.1f}×{dims[2]:.1f}")
            analyze_single_part(result, solid, "DIN 1026 - U 160 - 600 (UNP160)")
            break


if __name__ == "__main__":
    main()
