"""
Part Analyzer - Grondige analyse van CAD onderdelen met uitleg

Dit module analyseert STEP files en geeft gedetailleerde uitleg over:
- Waarom een onderdeel als plaat/profiel/draaistuk wordt geclassificeerd
- Hoe gaten worden geteld (cilindrische faces + inner wires)
- Waarom bepaalde zettingen wel/niet worden geteld
- Unfold mogelijkheden

Doel: Transparante analyse die overeenkomt met ERP/Spaceclaim verwachtingen
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum


class PartType(Enum):
    """Classificatie van onderdeel types"""
    PLAAT = "plaat"              # Vlakke plaat (kan gebogen zijn)
    KOKER = "koker"              # Gesloten profiel (4 zettingen = 360°)
    HOEKPROFIEL = "hoekprofiel"  # L-profiel (1 zetting)
    U_PROFIEL = "u_profiel"      # U-profiel (2 zettingen)
    C_PROFIEL = "c_profiel"      # C-profiel (3 zettingen)
    BUIS = "buis"                # Ronde buis
    KOKER_PROFIEL = "koker_profiel"  # Rechthoekig kokerprofiel (ingekocht)
    DRAAISTUK = "draaistuk"      # Gedraaid onderdeel
    FREESDEEL = "freesdeel"      # Gefreesd onderdeel
    COMPLEX = "complex"          # Complex plaatwerk
    OVERIG = "overig"            # Niet geclassificeerd


@dataclass
class HoleInfo:
    """Informatie over een gedetecteerd gat"""
    diameter: float
    depth: float
    hole_type: str  # 'cylindrical', 'inner_wire', 'slot', 'rectangular'
    position: Tuple[float, float, float]
    reason: str  # Uitleg waarom dit als gat is gedetecteerd


@dataclass
class BendInfo:
    """Informatie over een gedetecteerde zetting"""
    angle: float
    radius: float
    length: float
    is_counted: bool  # Wordt deze zetting geteld voor ERP?
    reason: str  # Uitleg waarom wel/niet geteld


@dataclass
class AnalysisReason:
    """Een stap in de analyse met uitleg"""
    step: str
    observation: str
    conclusion: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PartAnalysis:
    """Complete analyse van een onderdeel"""
    # Identificatie
    name: str

    # Classificatie
    part_type: PartType
    is_sheet_metal: bool
    is_profile: bool  # Ingekocht profiel (geen zettingen tellen)
    is_turned: bool

    # Afmetingen
    length: float
    width: float
    height: float  # Kleinste dim = vaak dikte
    thickness: float  # Gedetecteerde plaatdikte

    # Gaten analyse
    holes: List[HoleInfo]
    total_hole_count: int
    max_hole_diameter: float

    # Zettingen analyse
    bends: List[BendInfo]
    bend_count_total: int  # Alle gedetecteerde zettingen
    bend_count_erp: int    # Zettingen voor ERP (0 voor profielen)

    # Uitleg
    reasoning: List[AnalysisReason]

    # Unfold
    can_unfold: bool
    unfold_reason: str
    flat_length: float = 0
    flat_width: float = 0

    # Ruwe data
    volume: float = 0
    surface_area: float = 0


def analyze_part_geometry(shape, name: str = "Part") -> PartAnalysis:
    """
    Voer grondige analyse uit op een STEP shape.

    Args:
        shape: CadQuery shape of OCC solid
        name: Naam van het onderdeel

    Returns:
        PartAnalysis met volledige analyse en uitleg
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Cone
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE

    reasoning = []

    # Haal solid op
    if hasattr(shape, 'val'):
        solid = shape.val().wrapped
    elif hasattr(shape, 'wrapped'):
        solid = shape.wrapped
    else:
        solid = shape

    # === STAP 1: Bounding box en basis afmetingen ===
    bbox = Bnd_Box()
    BRepBndLib.Add_s(solid, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])

    length = dims[2]  # Grootste
    width = dims[1]   # Middelste
    height = dims[0]  # Kleinste

    reasoning.append(AnalysisReason(
        step="Bounding Box",
        observation=f"Afmetingen: {length:.1f} x {width:.1f} x {height:.1f} mm",
        conclusion=f"Kleinste dimensie ({height:.1f}mm) is waarschijnlijk de dikte",
        details={"length": length, "width": width, "height": height}
    ))

    # === STAP 2: Surface type analyse ===
    faces = []
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        faces.append(exp.Current())
        exp.Next()

    planar_area = 0.0
    cylindrical_area = 0.0
    cone_area = 0.0
    other_area = 0.0

    planar_faces = []
    cylindrical_faces = []

    cylinder_axes = []
    cylinder_radii = []

    for face in faces:
        from OCP.TopoDS import TopoDS
        face_shape = TopoDS.Face_s(face)
        surf = BRepAdaptor_Surface(face_shape, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face_shape, props)
        area = props.Mass()

        if stype == GeomAbs_Plane:
            planar_area += area
            planar_faces.append((face_shape, area))
        elif stype == GeomAbs_Cylinder:
            cylindrical_area += area
            cylindrical_faces.append((face_shape, area, surf))
            cyl = surf.Cylinder()
            cylinder_radii.append(cyl.Radius())
            axis = cyl.Axis().Direction()
            cylinder_axes.append((axis.X(), axis.Y(), axis.Z()))
        elif stype == GeomAbs_Cone:
            cone_area += area
        else:
            other_area += area

    total_area = planar_area + cylindrical_area + cone_area + other_area

    reasoning.append(AnalysisReason(
        step="Surface Analyse",
        observation=f"Planar: {100*planar_area/total_area:.0f}%, Cylindrisch: {100*cylindrical_area/total_area:.0f}%",
        conclusion="Bepaalt of het plaatwerk, draaistuk of complex is",
        details={
            "planar_pct": 100*planar_area/total_area,
            "cylindrical_pct": 100*cylindrical_area/total_area,
            "total_faces": len(faces)
        }
    ))

    # === STAP 3: Volume berekening ===
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    volume = props.Mass()

    # === STAP 4: Draaistuk detectie ===
    is_turned = False
    if cylindrical_area / total_area > 0.40 and len(cylinder_axes) >= 2:
        # Check of assen uitgelijnd zijn
        ref_axis = cylinder_axes[0]
        aligned = sum(1 for ax in cylinder_axes
                     if abs(ref_axis[0]*ax[0] + ref_axis[1]*ax[1] + ref_axis[2]*ax[2]) > 0.95)
        if aligned / len(cylinder_axes) > 0.7:
            is_turned = True
            reasoning.append(AnalysisReason(
                step="Draaistuk Detectie",
                observation=f"{100*cylindrical_area/total_area:.0f}% cilindrisch, {100*aligned/len(cylinder_axes):.0f}% assen uitgelijnd",
                conclusion="Dit is een DRAAISTUK (gedraaid onderdeel)",
                details={"cylinder_alignment": aligned/len(cylinder_axes)}
            ))

    # === STAP 5: Plaatwerk detectie ===
    is_sheet_metal = False
    detected_thickness = 0.0

    if not is_turned:
        # Methode 1: Zoek tegenoverliggende vlakke faces
        from OCP.gp import gp_Vec

        thickness_candidates = {}
        for i, (f1, area1) in enumerate(planar_faces):
            surf1 = BRepAdaptor_Surface(f1, True)
            pln1 = surf1.Plane()
            n1 = pln1.Axis().Direction()
            loc1 = pln1.Location()
            d1 = -(n1.X()*loc1.X() + n1.Y()*loc1.Y() + n1.Z()*loc1.Z())

            for j, (f2, area2) in enumerate(planar_faces):
                if i >= j:
                    continue
                surf2 = BRepAdaptor_Surface(f2, True)
                pln2 = surf2.Plane()
                n2 = pln2.Axis().Direction()
                loc2 = pln2.Location()

                # Tegenoverliggende normalen?
                dot = n1.X()*n2.X() + n1.Y()*n2.Y() + n1.Z()*n2.Z()
                if abs(dot + 1.0) < 0.01:  # Anti-parallel
                    d2 = -(n2.X()*loc2.X() + n2.Y()*loc2.Y() + n2.Z()*loc2.Z())
                    thickness = abs(d1 + d2)
                    if thickness > 0.1 and thickness < 25:
                        t_round = round(thickness, 1)
                        if t_round not in thickness_candidates:
                            thickness_candidates[t_round] = 0
                        thickness_candidates[t_round] += min(area1, area2)

        # Methode 2: Schat dikte uit cilindrische faces (buigradii)
        # Binnen-buigradius is typisch gelijk aan plaatdikte
        thickness_from_bends = 0.0
        if cylinder_radii:
            # Filter kleine radii (waarschijnlijk gaten) en grote radii (walsen)
            bend_radii = [r for r in cylinder_radii if 0.5 <= r <= 15]
            if bend_radii:
                # Kleinste radius = waarschijnlijk de binnenradius = dikte
                thickness_from_bends = min(bend_radii)

        # Bepaal beste dikte schatting
        if thickness_candidates:
            detected_thickness = max(thickness_candidates, key=thickness_candidates.get)
            coverage = thickness_candidates[detected_thickness] * 2 / total_area

            # Voor complexe gebogen plaatwerk is coverage lager, maar nog steeds sheet metal
            # als we ook cilindrische faces hebben (buigingen)
            if coverage > 0.05 or (coverage > 0.01 and cylindrical_area > 0):
                is_sheet_metal = True
                reasoning.append(AnalysisReason(
                    step="Plaatwerk Detectie",
                    observation=f"Dikte {detected_thickness}mm gevonden met {100*coverage:.0f}% oppervlakte match",
                    conclusion="Dit is PLAATWERK",
                    details={"thickness": detected_thickness, "coverage": coverage}
                ))

        # Fallback: gebruik dikte uit buigradii als we geen opposing faces vonden
        # maar wel >90% planaire faces en <10% cilindrische faces (typisch plaatwerk)
        if not is_sheet_metal and thickness_from_bends > 0:
            planar_pct = planar_area / total_area
            if planar_pct > 0.85 and cylindrical_area > 0:
                detected_thickness = thickness_from_bends
                is_sheet_metal = True
                reasoning.append(AnalysisReason(
                    step="Plaatwerk Detectie (Buigradius)",
                    observation=f"Dikte ~{detected_thickness}mm geschat uit kleinste buigradius, {100*planar_pct:.0f}% planair",
                    conclusion="Dit is PLAATWERK (uit buigradius analyse)",
                    details={"thickness_from_bends": thickness_from_bends, "planar_pct": planar_pct}
                ))

        # Fallback 2: Hoog % planair + cilindrisch = sheet metal
        if not is_sheet_metal:
            planar_pct = planar_area / total_area
            cyl_pct = cylindrical_area / total_area
            if planar_pct > 0.90 and cyl_pct > 0.01 and cyl_pct < 0.15:
                # Dit is waarschijnlijk sheet metal, schat dikte uit kleinste dim of buigradius
                if thickness_from_bends > 0:
                    detected_thickness = thickness_from_bends
                else:
                    # Gebruik kleinste bounding box dim als fallback
                    detected_thickness = height if height < 25 else 2.0  # default 2mm
                is_sheet_metal = True
                reasoning.append(AnalysisReason(
                    step="Plaatwerk Detectie (Surface %)",
                    observation=f"{100*planar_pct:.0f}% planair, {100*cyl_pct:.0f}% cilindrisch",
                    conclusion="Dit is PLAATWERK (typische surface verdeling)",
                    details={"planar_pct": planar_pct, "cyl_pct": cyl_pct}
                ))

    # === STAP 6: Zettingen analyse ===
    bends = []
    bend_count_total = 0
    is_closed_profile = False

    if is_sheet_metal and cylindrical_faces:
        for face, area, surf in cylindrical_faces:
            cyl = surf.Cylinder()
            radius = cyl.Radius()

            # U parameter geeft hoek
            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            # V parameter geeft buiglengte
            v_min = surf.FirstVParameter()
            v_max = surf.LastVParameter()
            bend_length = abs(v_max - v_min)

            # Is dit een zetting?
            is_counted = True
            reason = ""

            if bend_length < 20:
                is_counted = False
                reason = f"Buiglengte {bend_length:.1f}mm < 20mm (waarschijnlijk gat-rand)"
            elif radius > 15:
                is_counted = False
                reason = f"Radius {radius:.1f}mm > 15mm (walsen, niet kanten)"
            elif angle_deg < 30:
                is_counted = False
                reason = f"Hoek {angle_deg:.0f}° < 30° (geen echte zetting)"
            else:
                # Check orientatie (REVERSED = binnenradius)
                if face.Orientation() == TopAbs_REVERSED:
                    reason = f"Binnenradius R{radius:.1f}mm, hoek {angle_deg:.0f}°, lengte {bend_length:.0f}mm"
                else:
                    is_counted = False
                    reason = f"Buitenradius (niet tellen)"

            if is_counted:
                bends.append(BendInfo(
                    angle=angle_deg,
                    radius=radius,
                    length=bend_length,
                    is_counted=True,
                    reason=reason
                ))

        bend_count_total = len(bends)

        # Check voor gesloten profiel (koker)
        if bend_count_total >= 4:
            total_angle = sum(b.angle for b in bends)
            if 350 <= total_angle <= 370:
                is_closed_profile = True
                reasoning.append(AnalysisReason(
                    step="Gesloten Profiel Check",
                    observation=f"{bend_count_total} zettingen met totaal {total_angle:.0f}°",
                    conclusion="Dit is een KOKER (gesloten profiel) - zettingen niet tellen voor ERP",
                    details={"total_bend_angle": total_angle}
                ))

    # === STAP 7: Profiel classificatie ===
    is_profile = False
    part_type = PartType.OVERIG
    bend_count_erp = bend_count_total

    if is_turned:
        # Check aspect ratio (Length / Diameter)
        # Assuming height is diameter (smallest dim) or width
        diameter = max(width, height)
        aspect_ratio = length / diameter if diameter > 0 else 0
        
        # Determine if it's a tube/bar profile vs a machined part
        # High aspect ratio usually implies stock material (bar/tube)
        if aspect_ratio > 4.0:
            part_type = PartType.BUIS
            is_profile = True
            reasoning.append(AnalysisReason(
                step="Profiel Type",
                observation=f"Cilindrisch met aspect ratio {aspect_ratio:.1f}",
                conclusion="BUIS/STAF - ingekocht profiel",
                details={"aspect_ratio": aspect_ratio}
            ))
        else:
            part_type = PartType.DRAAISTUK
    elif is_sheet_metal:
        if is_closed_profile:
            part_type = PartType.KOKER
            is_profile = True
            bend_count_erp = 0
            reasoning.append(AnalysisReason(
                step="Profiel Type",
                observation=f"Gesloten profiel met {bend_count_total} zettingen",
                conclusion="KOKER PROFIEL - ingekocht, 0 zettingen voor ERP",
                details={}
            ))
        elif bend_count_total == 0:
            part_type = PartType.PLAAT
        elif bend_count_total == 1:
            part_type = PartType.HOEKPROFIEL
        elif bend_count_total == 2:
            part_type = PartType.U_PROFIEL
        elif bend_count_total == 3:
            part_type = PartType.C_PROFIEL
        else:
            part_type = PartType.COMPLEX
    else:
        # Check aspect ratio voor profiel detectie
        aspect_ratio = length / width if width > 0 else 0
        if aspect_ratio > 5:
            is_profile = True
            part_type = PartType.KOKER_PROFIEL
            reasoning.append(AnalysisReason(
                step="Profiel Type",
                observation=f"Aspect ratio {aspect_ratio:.1f} (lengte/breedte > 5)",
                conclusion="Langwerpig PROFIEL - waarschijnlijk ingekocht",
                details={"aspect_ratio": aspect_ratio}
            ))

    # === STAP 8: Gaten analyse ===
    holes = []
    seen_holes = set()  # Track unieke posities om duplicaten te voorkomen

    if not is_turned:  # Draaistukken hebben boren, geen snijgaten
        # A) Cilindrische gaten (traditionele detectie)
        for face, area, surf in cylindrical_faces:
            if face.Orientation() != TopAbs_REVERSED:
                continue

            cyl = surf.Cylinder()
            radius = cyl.Radius()
            diameter = radius * 2

            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            # Alleen volle cirkels of bijna-volle cirkels
            if angle_deg > 270:
                arc_len = radius * abs(u_max - u_min)
                depth = area / arc_len if arc_len > 0 else 0

                # Filter: niet te groot (dat zijn buigingen) en niet te klein
                # Voor plaatwerk: gaten gaan door de plaat, diepte ≈ plaatdikte
                is_hole = False
                if detected_thickness > 0:
                    # Relaxed filter: diepte moet in de buurt van plaatdikte zijn
                    if depth < detected_thickness * 3 and depth > detected_thickness * 0.3:
                        is_hole = True
                elif depth < 20 and depth > 0.5:  # Fallback zonder bekende dikte
                    is_hole = True

                if is_hole:
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties_s(face, props)
                    center = props.CentreOfMass()

                    # Check voor duplicaten (zelfde positie)
                    pos_key = (round(center.X(), 1), round(center.Y(), 1), round(center.Z(), 1))
                    if pos_key not in seen_holes:
                        seen_holes.add(pos_key)
                        holes.append(HoleInfo(
                            diameter=diameter,
                            depth=depth,
                            hole_type="cylindrical",
                            position=(center.X(), center.Y(), center.Z()),
                            reason=f"Cilindrisch gat Ø{diameter:.1f}mm, diepte {depth:.1f}mm"
                        ))

        # B) Inner wires in planar faces (voor niet-ronde gaten)
        # Deze worden apart geteld omdat ze slots, rechthoeken, etc kunnen zijn
        # Let op: inner wires komen op BEIDE zijden van de plaat voor (top + bottom)
        inner_wire_total = 0
        if is_sheet_metal:
            # Groepeer faces per area (top/bottom hebben zelfde area)
            area_to_inner_wires = {}

            for face, area in planar_faces:
                # Check of dit een grote face is (niet een klein gaatje zelf)
                if area < 100:  # Skip kleine faces
                    continue

                # Tel inner wires
                wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
                wire_count = 0
                while wire_exp.More():
                    wire_count += 1
                    wire_exp.Next()

                if wire_count > 1:  # Eerste wire is outer boundary
                    inner_wire_count = wire_count - 1
                    area_key = round(area, 0)

                    # Neem het maximum aantal inner wires voor faces met dezelfde area
                    # (voorkomt dubbel tellen van top+bottom)
                    if area_key not in area_to_inner_wires:
                        area_to_inner_wires[area_key] = inner_wire_count
                    else:
                        area_to_inner_wires[area_key] = max(area_to_inner_wires[area_key], inner_wire_count)

            # Tel totaal aantal unieke inner wires (gaten)
            for area_key, count in area_to_inner_wires.items():
                for i in range(count):
                    holes.append(HoleInfo(
                        diameter=0,  # Niet circulair
                        depth=detected_thickness,
                        hole_type="shaped",
                        position=(0, 0, 0),  # Positie niet beschikbaar
                        reason=f"Shaped gat (inner wire) in face {area_key:.0f}mm²"
                    ))
                    inner_wire_total += 1

            if inner_wire_total > 0:
                reasoning.append(AnalysisReason(
                    step="Inner Wire Analyse",
                    observation=f"Totaal {inner_wire_total} inner wires gevonden (uniek per face area)",
                    conclusion=f"{inner_wire_total} shaped holes (slots, rechthoeken, etc)",
                    details={"inner_wire_total": inner_wire_total}
                ))
    else:
        reasoning.append(AnalysisReason(
            step="Gaten Analyse",
            observation="Draaistuk gedetecteerd",
            conclusion="Interne cilinders zijn BOREN (machinaal), geen snijgaten",
            details={}
        ))

    # === STAP 9: Unfold mogelijkheid ===
    can_unfold = is_sheet_metal and not is_profile
    unfold_reason = ""

    if is_sheet_metal:
        if is_profile:
            can_unfold = False
            unfold_reason = "Profiel - ingekocht, geen ontbuigen nodig"
        elif bend_count_total == 0:
            can_unfold = False
            unfold_reason = "Vlakke plaat - geen buigingen om te ontbuigen"
        else:
            can_unfold = True
            unfold_reason = f"Plaatwerk met {bend_count_total} zettingen - kan worden ontbogen"
    elif is_turned:
        can_unfold = False
        unfold_reason = "Draaistuk - geen plaatwerk"
    else:
        can_unfold = False
        unfold_reason = "Geen plaatwerk gedetecteerd"

    reasoning.append(AnalysisReason(
        step="Unfold Analyse",
        observation=f"Sheet metal: {is_sheet_metal}, Profiel: {is_profile}, Zettingen: {bend_count_total}",
        conclusion=unfold_reason,
        details={"can_unfold": can_unfold}
    ))

    # === SAMENVATTING ===
    total_holes = len(holes)
    max_diameter = max((h.diameter for h in holes), default=0)

    reasoning.append(AnalysisReason(
        step="SAMENVATTING",
        observation=f"Type: {part_type.value}, Dikte: {detected_thickness}mm",
        conclusion=f"Zettingen ERP: {bend_count_erp}, Snijgaten: {total_holes}",
        details={
            "part_type": part_type.value,
            "thickness": detected_thickness,
            "bend_count_erp": bend_count_erp,
            "hole_count": total_holes
        }
    ))

    return PartAnalysis(
        name=name,
        part_type=part_type,
        is_sheet_metal=is_sheet_metal,
        is_profile=is_profile,
        is_turned=is_turned,
        length=length,
        width=width,
        height=height,
        thickness=detected_thickness,
        holes=holes,
        total_hole_count=total_holes,
        max_hole_diameter=max_diameter,
        bends=bends,
        bend_count_total=bend_count_total,
        bend_count_erp=bend_count_erp,
        reasoning=reasoning,
        can_unfold=can_unfold,
        unfold_reason=unfold_reason,
        volume=volume,
        surface_area=total_area
    )


def format_analysis_report(analysis: PartAnalysis) -> str:
    """
    Genereer een leesbaar rapport van de analyse.
    """
    lines = []
    lines.append("=" * 70)
    lines.append(f"ANALYSE RAPPORT: {analysis.name}")
    lines.append("=" * 70)

    lines.append(f"\n--- CLASSIFICATIE ---")
    lines.append(f"Type:           {analysis.part_type.value.upper()}")
    lines.append(f"Sheet Metal:    {'Ja' if analysis.is_sheet_metal else 'Nee'}")
    lines.append(f"Profiel:        {'Ja (ingekocht)' if analysis.is_profile else 'Nee'}")
    lines.append(f"Draaistuk:      {'Ja' if analysis.is_turned else 'Nee'}")

    lines.append(f"\n--- AFMETINGEN ---")
    lines.append(f"L x B x H:      {analysis.length:.1f} x {analysis.width:.1f} x {analysis.height:.1f} mm")
    lines.append(f"Plaatdikte:     {analysis.thickness:.1f} mm")

    lines.append(f"\n--- PRODUCTIE DATA (ERP) ---")
    lines.append(f"Zettingen:      {analysis.bend_count_erp}")
    lines.append(f"Snijgaten:      {analysis.total_hole_count}")
    lines.append(f"Max Ø gat:      {analysis.max_hole_diameter:.1f} mm")

    lines.append(f"\n--- UNFOLD ---")
    lines.append(f"Kan ontbuigen:  {'Ja' if analysis.can_unfold else 'Nee'}")
    lines.append(f"Reden:          {analysis.unfold_reason}")
    if analysis.flat_length > 0:
        lines.append(f"Uitslag:        {analysis.flat_length:.1f} x {analysis.flat_width:.1f} mm")

    lines.append(f"\n--- ANALYSE STAPPEN ---")
    for r in analysis.reasoning:
        lines.append(f"\n[{r.step}]")
        lines.append(f"  Observatie:  {r.observation}")
        lines.append(f"  Conclusie:   {r.conclusion}")

    if analysis.bends:
        lines.append(f"\n--- ZETTINGEN DETAIL ---")
        for i, b in enumerate(analysis.bends, 1):
            status = "✓" if b.is_counted else "✗"
            lines.append(f"  {status} Zetting {i}: {b.reason}")

    if analysis.holes:
        lines.append(f"\n--- GATEN DETAIL ---")
        for i, h in enumerate(analysis.holes, 1):
            lines.append(f"  • Gat {i}: Ø{h.diameter:.1f}mm - {h.reason}")

    lines.append("\n" + "=" * 70)

    return "\n".join(lines)
