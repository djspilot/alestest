#!/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
"""
FreeCAD Sheet Metal Unfolder

Gebruikt FreeCAD's SheetMetal workbench om gebogen plaatwerk te ontbuigen
en een vlakke uitslag (flat pattern) te genereren.

Kan STEP files inladen, analyseren en ontvouwen naar DXF.
"""
import sys
import os

# FreeCAD paths voor Mac (Homebrew installatie)
FREECAD_APP = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
FREECAD_LIB = os.path.join(FREECAD_APP, "Contents/Resources/lib")
FREECAD_MOD = os.path.join(FREECAD_APP, "Contents/Resources/Mod")
FREECAD_USER_MOD = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

# Add paths before importing FreeCAD modules
sys.path.insert(0, FREECAD_LIB)
sys.path.insert(0, FREECAD_MOD)
sys.path.insert(0, FREECAD_USER_MOD)
sys.path.insert(0, os.path.join(FREECAD_USER_MOD, "sheetmetal"))

import FreeCAD
import Part
import math

# Mock FreeCADGui voor headless mode
class MockSelection:
    """Mock Selection class voor headless gebruik"""
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
    """Mock FreeCADGui module voor headless gebruik"""
    Selection = MockSelection()


# Probeer echte FreeCADGui, anders gebruik mock
try:
    import FreeCADGui
    # Test of Selection werkt
    FreeCADGui.Selection.getSelection()
except (ImportError, AttributeError):
    # Gebruik mock in headless mode
    import sys
    sys.modules['FreeCADGui'] = MockFreeCADGui()
    FreeCADGui = MockFreeCADGui()


def find_largest_planar_face(shape):
    """
    Vind het grootste vlakke oppervlak in een shape.
    Dit is typisch de 'base' face voor het ontbuigen.
    """
    largest_face = None
    largest_area = 0

    for i, face in enumerate(shape.Faces):
        # Check of het een vlak (plane) is
        surface = face.Surface
        if hasattr(surface, 'isPlanar') and surface.isPlanar():
            area = face.Area
            if area > largest_area:
                largest_area = area
                largest_face = (i, face)

    return largest_face


def find_base_face_for_unfold(shape):
    """
    Automatisch de beste base face vinden voor het ontbuigen.
    Zoekt naar het grootste vlakke oppervlak.
    """
    planar_faces = []

    for i, face in enumerate(shape.Faces):
        try:
            # Probeer te bepalen of het vlak is
            surf_type = face.Surface.TypeId
            if 'Plane' in surf_type:
                planar_faces.append({
                    'index': i,
                    'face': face,
                    'area': face.Area,
                    'normal': face.normalAt(0, 0)
                })
        except Exception:
            continue

    if not planar_faces:
        return None

    # Sorteer op oppervlakte (grootste eerst)
    planar_faces.sort(key=lambda x: x['area'], reverse=True)

    return planar_faces[0]


def find_all_base_face_candidates(shape):
    """
    Vind alle mogelijke base faces, gesorteerd op geschiktheid.
    Returns lijst van candidates voor als de eerste niet werkt.
    """
    planar_faces = []

    for i, face in enumerate(shape.Faces):
        try:
            surf_type = face.Surface.TypeId
            if 'Plane' in surf_type:
                planar_faces.append({
                    'index': i,
                    'face': face,
                    'area': face.Area,
                    'normal': face.normalAt(0, 0)
                })
        except Exception:
            continue

    if not planar_faces:
        return []

    # Sorteer op oppervlakte (grootste eerst)
    planar_faces.sort(key=lambda x: x['area'], reverse=True)

    return planar_faces


# Error code vertaling
UNFOLD_ERROR_MESSAGES = {
    1: "Volume onbruikbaar - geen echt 3D sheet metal met uniforme dikte",
    2: "Ongeldige punt voor dikte meting",
    3: "Ongeldige dikte - plaatdikte niet consistent of te complex",
    4: "Ongeldige shape",
    5: "Shape heeft onnodige edges - gebruik 'Refine Shape' eerst",
    10: "Geen wires in sheet edge analyse",
    11: "Dubbele buigingen niet ondersteund",
    12: "Meer dan één bend-child niet ondersteund",
    13: "Plaatdikte ongeldig voor dit vlak",
    14: "Edges zonder buur-vlakken",
    15: "Alle sheet edges moeten een vlak hebben",
    16: "Starthoek van buiging niet gevonden",
    17: "Type oppervlak niet ondersteund voor sheet metal",
    20: "Section wire met minder dan 4 edges",
    21: "Section wire niet gesloten",
    22: "Section gefaald",
    23: "CutToolWire niet gesloten",
    24: "Bend-face zonder child niet geïmplementeerd",
    26: "Niet-ondersteund curve type in unbendFace",
}


def unfold_sheet_metal(step_path, output_dxf=None, k_factor=0.44, max_attempts=5):
    """
    Ontbuig een sheet metal STEP file naar een vlakke uitslag.

    Args:
        step_path: Pad naar STEP bestand
        output_dxf: Pad voor DXF output (optioneel)
        k_factor: K-factor voor buigberekening (default 0.44)
        max_attempts: Max aantal base faces om te proberen

    Returns:
        dict met resultaten:
            - success: bool
            - flat_shape: Part.Shape van de vlakke uitslag
            - flat_length: lengte van uitslag
            - flat_width: breedte van uitslag
            - bend_lines: lijst met buiglijnen
            - error: foutmelding indien mislukt
            - attempts: aantal pogingen
            - error_details: gedetailleerde foutinfo
    """
    result = {
        'success': False,
        'flat_shape': None,
        'flat_length': 0,
        'flat_width': 0,
        'bend_lines': [],
        'error': None,
        'attempts': 0,
        'error_details': [],
        'used_face_idx': None
    }

    try:
        # Import STEP
        print(f"Loading STEP: {step_path}")
        shape = Part.read(step_path)

        if not shape.Solids:
            result['error'] = "Geen solids gevonden in STEP file"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape

        # Vind ALLE mogelijke base faces
        base_candidates = find_all_base_face_candidates(solid)
        if not base_candidates:
            result['error'] = "Geen vlakke oppervlakken gevonden - niet geschikt voor ontbuigen"
            return result

        print(f"Gevonden {len(base_candidates)} kandidaat base faces")

        # Import SheetMetal Unfolder
        import SheetMetalUnfolder

        # K-factor lookup (standaard waarden per dikte)
        kFactorLookup = {}
        for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
            kFactorLookup[t] = k_factor

        # Probeer meerdere base faces
        attempts_to_try = min(max_attempts, len(base_candidates))

        for attempt, base_info in enumerate(base_candidates[:attempts_to_try]):
            result['attempts'] = attempt + 1
            base_face_idx = base_info['index']

            print(f"\nPoging {attempt + 1}/{attempts_to_try}: face {base_face_idx} (area {base_info['area']:.1f} mm²)")

            # Maak een FreeCAD document voor de operatie
            doc = FreeCAD.newDocument("UnfoldDoc")

            try:
                # Voeg shape toe aan document
                obj = doc.addObject("Part::Feature", "SheetPart")
                obj.Shape = solid
                doc.recompute()

                # Mock object wrapper die Refine attribuut heeft
                class ObjWrapper:
                    def __init__(self, real_obj):
                        self._obj = real_obj
                        self.Refine = False

                    def __getattr__(self, name):
                        return getattr(self._obj, name)

                wrapped_obj = ObjWrapper(obj)
                MockSelection._selection = [wrapped_obj]

                # SheetTree neemt: (TheShape, f_idx, k_factor_lookup)
                unfold_tree = SheetMetalUnfolder.SheetTree(
                    solid,
                    base_face_idx,
                    kFactorLookup
                )

                # Check for init errors
                if unfold_tree.error_code:
                    err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'init',
                        'error_code': unfold_tree.error_code,
                        'message': err_msg
                    })
                    print(f"  ✗ Init fout: {err_msg}")
                    continue

                # Bend analysis
                unfold_tree.Bend_analysis(base_face_idx, None)

                if unfold_tree.error_code:
                    err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'analysis',
                        'error_code': unfold_tree.error_code,
                        'message': err_msg
                    })
                    print(f"  ✗ Analysis fout: {err_msg}")
                    continue

                # Genereer de unfolded shape
                if hasattr(unfold_tree, 'root') and unfold_tree.root:
                    theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                    if unfold_tree.error_code:
                        err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                        result['error_details'].append({
                            'face_idx': base_face_idx,
                            'stage': 'unfold',
                            'error_code': unfold_tree.error_code,
                            'message': err_msg
                        })
                        print(f"  ✗ Unfold fout: {err_msg}")
                        continue

                    if theFaceList:
                        # Maak shell van de faces
                        try:
                            flat_shell = Part.Shell(theFaceList)
                        except Exception:
                            flat_shell = Part.Compound(theFaceList)

                        # Bereken bounding box
                        bbox = flat_shell.BoundBox
                        result['flat_length'] = bbox.XLength
                        result['flat_width'] = bbox.YLength
                        result['flat_shape'] = flat_shell
                        result['bend_lines'] = foldLines
                        result['success'] = True
                        result['used_face_idx'] = base_face_idx

                        print(f"  ✓ Unfold geslaagd: {bbox.XLength:.1f} x {bbox.YLength:.1f} mm")
                        print(f"  ✓ Fold lines: {len(foldLines)}")

                        # Export naar DXF indien gewenst
                        if output_dxf:
                            export_to_dxf(flat_shell, output_dxf, foldLines)
                            print(f"  ✓ DXF: {output_dxf}")

                        return result  # Success!
                    else:
                        result['error_details'].append({
                            'face_idx': base_face_idx,
                            'stage': 'unfold',
                            'error_code': -1,
                            'message': 'Lege face list'
                        })
                        print(f"  ✗ Lege face list")
                else:
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'analysis',
                        'error_code': -1,
                        'message': 'Geen root node'
                    })
                    print(f"  ✗ Geen root node")

            except Exception as e:
                result['error_details'].append({
                    'face_idx': base_face_idx,
                    'stage': 'exception',
                    'error_code': -1,
                    'message': str(e)
                })
                print(f"  ✗ Exception: {str(e)}")

            finally:
                try:
                    FreeCAD.closeDocument("UnfoldDoc")
                except Exception:
                    pass

        # Geen van de pogingen werkte
        if result['error_details']:
            # Vind meest voorkomende fout
            error_codes = [e['error_code'] for e in result['error_details']]
            most_common_code = max(set(error_codes), key=error_codes.count)
            result['error'] = UNFOLD_ERROR_MESSAGES.get(most_common_code, f"Unfold gefaald na {result['attempts']} pogingen")
        else:
            result['error'] = f"Unfold gefaald na {result['attempts']} pogingen"

    except Exception as e:
        result['error'] = f"Error: {str(e)}"
        import traceback
        traceback.print_exc()

    return result


def export_to_dxf(shape, filepath, bend_lines=None):
    """
    Exporteer een vlakke shape naar DXF formaat.
    """
    try:
        import importDXF

        # Maak tijdelijk document
        doc = FreeCAD.newDocument("ExportDoc")
        obj = doc.addObject("Part::Feature", "FlatPattern")
        obj.Shape = shape

        # Export
        importDXF.export([obj], filepath)

        # Cleanup
        FreeCAD.closeDocument("ExportDoc")

        return True
    except Exception as e:
        print(f"DXF export error: {e}")
        return False


def analyze_for_unfold(step_path):
    """
    Analyseer een STEP file om te bepalen of het geschikt is voor ontbuigen.

    Returns:
        dict met analyse resultaten
    """
    result = {
        'suitable': False,
        'reason': '',
        'thickness': 0,
        'bend_count': 0,
        'planar_faces': 0,
        'cylindrical_faces': 0,
        'base_face_area': 0
    }

    try:
        shape = Part.read(step_path)

        if not shape.Solids:
            result['reason'] = "Geen solids in STEP"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape

        # Tel face types
        planar_count = 0
        cylindrical_count = 0
        cylindrical_radii = []

        for face in solid.Faces:
            try:
                surf_type = face.Surface.TypeId
                if 'Plane' in surf_type:
                    planar_count += 1
                elif 'Cylinder' in surf_type:
                    cylindrical_count += 1
                    cylindrical_radii.append(face.Surface.Radius)
            except Exception:
                continue

        result['planar_faces'] = planar_count
        result['cylindrical_faces'] = cylindrical_count

        # Vind base face
        base_info = find_base_face_for_unfold(solid)
        if base_info:
            result['base_face_area'] = base_info['area']

        # Schat dikte uit kleinste buigradius
        if cylindrical_radii:
            min_radius = min(cylindrical_radii)
            # Typisch: binnenradius ≈ dikte, dus dikte ≈ radius
            result['thickness'] = min_radius
            result['bend_count'] = cylindrical_count // 2  # Binnen + buiten radius

        # Bepaal geschiktheid
        if planar_count >= 2 and cylindrical_count >= 2:
            result['suitable'] = True
            result['reason'] = "Sheet metal part met buigingen gedetecteerd"
        elif planar_count >= 2 and cylindrical_count == 0:
            result['suitable'] = True
            result['reason'] = "Vlakke plaat (geen buigingen)"
        else:
            result['suitable'] = False
            result['reason'] = "Niet herkend als sheet metal"

    except Exception as e:
        result['reason'] = f"Analyse error: {str(e)}"

    return result


def calculate_theoretical_unfold(step_path, k_factor=0.44):
    """
    Bereken een theoretische uitslag afmeting voor complexe onderdelen
    die niet automatisch ontbogen kunnen worden.

    Deze methode sommeert:
    - Alle vlakke oppervlakken in hun ontbogen oriëntatie
    - Plus de booglengte van alle buigingen (met K-factor correctie)

    Returns:
        dict met:
        - estimated_length: geschatte lengte uitslag
        - estimated_width: geschatte breedte uitslag
        - total_flat_area: totaal vlak oppervlak
        - total_bend_length: totale buiglengte
        - bend_count: aantal buigingen
        - method: 'theoretical' (niet exact, maar indicatief)
    """
    result = {
        'success': False,
        'estimated_length': 0,
        'estimated_width': 0,
        'total_flat_area': 0,
        'total_bend_length': 0,
        'bend_count': 0,
        'thickness': 0,
        'method': 'theoretical',
        'error': None
    }

    try:
        shape = Part.read(step_path)

        if not shape.Solids:
            result['error'] = "Geen solids in STEP"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape

        # Analyseer alle faces
        planar_areas = []
        bend_data = []

        for face in solid.Faces:
            try:
                surf_type = face.Surface.TypeId

                if 'Plane' in surf_type:
                    planar_areas.append(face.Area)

                elif 'Cylinder' in surf_type:
                    cyl = face.Surface
                    radius = cyl.Radius

                    # Bereken hoek (U parameter)
                    u_range = face.ParameterRange[1] - face.ParameterRange[0]
                    angle_rad = abs(u_range)

                    # Bereken buiglengte (V parameter)
                    v_range = face.ParameterRange[3] - face.ParameterRange[2]
                    bend_length = abs(v_range)

                    if angle_rad > 0.5 and bend_length > 10:  # Filter kleine radii
                        # Booglengte = (radius + k*thickness) * hoek
                        # We kennen de dikte niet exact, gebruik radius als schatting
                        arc_length = (radius * (1 + k_factor)) * angle_rad

                        bend_data.append({
                            'radius': radius,
                            'angle_rad': angle_rad,
                            'bend_length': bend_length,
                            'arc_length': arc_length
                        })

            except Exception:
                continue

        # Bereken totalen
        result['total_flat_area'] = sum(planar_areas)
        result['bend_count'] = len(bend_data) // 2  # Binnen + buiten
        result['total_bend_length'] = sum(b['arc_length'] for b in bend_data)

        if bend_data:
            result['thickness'] = min(b['radius'] for b in bend_data)

        # Schat uitslag dimensies
        # Simpele benadering: sqrt(total_area) geeft indicatie van maat
        if result['total_flat_area'] > 0:
            # Gebruik bounding box voor aspect ratio
            bbox = solid.BoundBox
            dims = sorted([bbox.XLength, bbox.YLength, bbox.ZLength])

            # Langste dim blijft ongeveer gelijk bij ontbuigen
            result['estimated_length'] = dims[2]

            # Breedte wordt groter door ontbuigen
            # Schat: vlakke oppervlakte / lengte + buiglengtes
            result['estimated_width'] = (result['total_flat_area'] / dims[2]) + result['total_bend_length'] / 10

            result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


# Command line interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ontbuig sheet metal STEP files")
    parser.add_argument("step_file", help="Pad naar STEP bestand")
    parser.add_argument("-o", "--output", help="Output DXF bestand")
    parser.add_argument("-k", "--kfactor", type=float, default=0.44, help="K-factor (default 0.44)")
    parser.add_argument("--analyze", action="store_true", help="Alleen analyseren, niet ontbuigen")

    args = parser.parse_args()

    if not os.path.exists(args.step_file):
        print(f"Error: Bestand niet gevonden: {args.step_file}")
        sys.exit(1)

    if args.analyze:
        print(f"\nAnalyzing: {args.step_file}")
        result = analyze_for_unfold(args.step_file)
        print(f"\nResultaat:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print(f"\nUnfolding: {args.step_file}")
        output = args.output or args.step_file.replace('.step', '_flat.dxf').replace('.STEP', '_flat.dxf')
        result = unfold_sheet_metal(args.step_file, output, args.kfactor)

        if result['success']:
            print(f"\n✓ Ontbuigen geslaagd!")
            print(f"  Uitslag: {result['flat_length']:.1f} x {result['flat_width']:.1f} mm")
            if args.output:
                print(f"  DXF: {output}")
        else:
            print(f"\n✗ Ontbuigen mislukt: {result['error']}")
            sys.exit(1)
