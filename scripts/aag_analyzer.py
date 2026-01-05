#!/usr/bin/env python3
"""
AAG-Based Sheet Metal Feature Recognition

Attributed Adjacency Graph (AAG) implementation for sheet metal analysis.
Based on computational geometry best practices for feature recognition.

Architecture:
- TopologyGraph: Builds face-edge adjacency graph with convexity attributes
- FeatureRecognizer: Pattern matching for holes, slots, bends, hems
- SheetMetalCalculator: Bend allowance, deduction, K-factor calculations
- CostEstimator: Laser cutting time estimation

This module integrates with the existing compare_erp.py pipeline.
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
from collections import defaultdict


# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

class EdgeConvexity(Enum):
    """Edge convexity classification per AAG framework."""
    CONVEX = "convex"       # Outer angle > 180° (material on convex side)
    CONCAVE = "concave"     # Outer angle < 180° (material on concave side)
    TANGENT = "tangent"     # Smooth transition (G1 continuity)
    SHARP = "sharp"         # Sharp edge, undefined convexity
    UNKNOWN = "unknown"


class FaceType(Enum):
    """Face surface type classification."""
    PLANAR = "planar"
    CYLINDRICAL = "cylindrical"
    CONICAL = "conical"
    SPHERICAL = "spherical"
    TOROIDAL = "toroidal"
    BSPLINE = "bspline"
    UNKNOWN = "unknown"


class FeatureType(Enum):
    """Recognized manufacturing feature types."""
    HOLE_ROUND = "hole_round"           # Circular hole (Q ≈ 1)
    HOLE_SLOT = "hole_slot"             # Obround/slot (Q < 1, 2 lines + 2 arcs)
    HOLE_RECTANGULAR = "hole_rectangular"
    HOLE_COMPLEX = "hole_complex"
    BEND_STANDARD = "bend_standard"     # Standard cylindrical bend
    BEND_HEM_OPEN = "bend_hem_open"     # Open hem (180° bend with gap)
    BEND_HEM_CLOSED = "bend_hem_closed" # Closed/flattened hem
    BEND_LOFTED = "bend_lofted"         # Conical bend (variable radius)
    SKIN_FACE = "skin_face"             # Top/bottom sheet face
    THICKNESS_FACE = "thickness_face"   # Edge/thickness face


# K-factor lookup based on R/T ratio (Table 1 from framework)
K_FACTOR_TABLE = {
    # R/T ratio : K-factor
    0.0: 0.33,   # Very tight bend
    0.5: 0.35,
    1.0: 0.38,
    1.5: 0.40,
    2.0: 0.42,
    2.5: 0.44,
    3.0: 0.46,
    4.0: 0.48,
    5.0: 0.50,
}

# Default tolerances
DEFAULT_TOLERANCE = 1e-6  # Will be overridden by STEP uncertainty if available
ANGLE_TOLERANCE = 0.01   # Radians (~0.5°)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FaceNode:
    """Node in the AAG representing a face."""
    index: int
    face_type: FaceType
    area: float
    normal: Optional[Tuple[float, float, float]] = None
    center: Optional[Tuple[float, float, float]] = None
    radius: Optional[float] = None  # For cylindrical/conical
    # Classification
    is_skin: bool = False
    is_thickness: bool = False
    feature_type: Optional[FeatureType] = None


@dataclass
class EdgeArc:
    """Arc in the AAG representing an edge between faces."""
    face1_idx: int
    face2_idx: int
    convexity: EdgeConvexity
    length: float
    edge_index: int
    # For bend edges
    bend_angle: Optional[float] = None
    bend_radius: Optional[float] = None


@dataclass
class HoleFeature:
    """Detected hole feature."""
    face_indices: List[int]
    hole_type: FeatureType
    diameter: Optional[float] = None
    length: Optional[float] = None  # For slots
    width: Optional[float] = None   # For slots
    perimeter: float = 0
    area: float = 0
    isoperimetric_quotient: float = 1.0  # Q = 4πA/P² (1.0 for circle)
    edge_count: int = 0
    arc_count: int = 0
    line_count: int = 0


@dataclass
class BendFeature:
    """Detected bend feature."""
    cylindrical_face_idx: int
    adjacent_faces: List[int]
    bend_type: FeatureType
    bend_angle: float  # Degrees
    bend_radius: float  # Inner radius
    bend_length: float  # Along bend axis
    k_factor: float = 0.44
    bend_allowance: float = 0
    bend_deduction: float = 0


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    # Counts
    hole_count: int = 0
    bend_count: int = 0
    slot_count: int = 0

    # Features
    holes: List[HoleFeature] = field(default_factory=list)
    bends: List[BendFeature] = field(default_factory=list)

    # Geometry
    thickness: float = 0
    flat_length: float = 0
    flat_width: float = 0
    flat_area: float = 0

    # Costs
    cut_length: float = 0
    total_cut_length: float = 0
    pierce_count: int = 0
    estimated_cut_time: float = 0
    laser_cut_time: float = 0

    # Metadata
    face_count: int = 0
    edge_count: int = 0
    skin_faces: int = 0
    thickness_faces: int = 0


# =============================================================================
# TOPOLOGY GRAPH
# =============================================================================

class TopologyGraph:
    """
    Attributed Adjacency Graph (AAG) for topology analysis.

    Nodes = Faces with attributes (type, area, normal, etc.)
    Arcs = Edges with attributes (convexity, length, etc.)
    """

    def __init__(self, tolerance: float = DEFAULT_TOLERANCE):
        self.tolerance = tolerance
        self.nodes: Dict[int, FaceNode] = {}
        self.arcs: List[EdgeArc] = []
        self.adjacency: Dict[int, Set[int]] = defaultdict(set)

    def build_from_freecad(self, shape) -> None:
        """Build AAG from FreeCAD Part.Shape."""
        # Add face nodes
        for i, face in enumerate(shape.Faces):
            node = self._analyze_face(i, face)
            self.nodes[i] = node

        # Add edge arcs
        self._build_edge_adjacency(shape)

        # Classify skin vs thickness faces
        self._classify_skin_thickness()

    def _analyze_face(self, index: int, face) -> FaceNode:
        """Analyze a single face and create a node."""
        try:
            surf_type = face.Surface.TypeId

            if 'Plane' in surf_type:
                face_type = FaceType.PLANAR
                normal = (face.Surface.Axis.x, face.Surface.Axis.y, face.Surface.Axis.z)
                center = (face.CenterOfMass.x, face.CenterOfMass.y, face.CenterOfMass.z)
                radius = None
            elif 'Cylinder' in surf_type:
                face_type = FaceType.CYLINDRICAL
                normal = (face.Surface.Axis.x, face.Surface.Axis.y, face.Surface.Axis.z)
                center = (face.Surface.Center.x, face.Surface.Center.y, face.Surface.Center.z)
                radius = face.Surface.Radius
            elif 'Cone' in surf_type:
                face_type = FaceType.CONICAL
                normal = (face.Surface.Axis.x, face.Surface.Axis.y, face.Surface.Axis.z)
                center = (face.Surface.Apex.x, face.Surface.Apex.y, face.Surface.Apex.z)
                radius = None
            elif 'Sphere' in surf_type:
                face_type = FaceType.SPHERICAL
                center = (face.Surface.Center.x, face.Surface.Center.y, face.Surface.Center.z)
                normal = None
                radius = face.Surface.Radius
            elif 'Toroid' in surf_type:
                face_type = FaceType.TOROIDAL
                center = (face.Surface.Center.x, face.Surface.Center.y, face.Surface.Center.z)
                normal = (face.Surface.Axis.x, face.Surface.Axis.y, face.Surface.Axis.z)
                radius = face.Surface.MajorRadius
            else:
                face_type = FaceType.BSPLINE
                normal = None
                center = (face.CenterOfMass.x, face.CenterOfMass.y, face.CenterOfMass.z)
                radius = None

            return FaceNode(
                index=index,
                face_type=face_type,
                area=face.Area,
                normal=normal,
                center=center,
                radius=radius
            )
        except Exception:
            return FaceNode(
                index=index,
                face_type=FaceType.UNKNOWN,
                area=0
            )

    def _build_edge_adjacency(self, shape) -> None:
        """Build edge-based adjacency between faces."""
        try:
            # Map edges to faces
            edge_to_faces: Dict[int, List[int]] = defaultdict(list)

            for face_idx, face in enumerate(shape.Faces):
                try:
                    for edge in face.Edges:
                        try:
                            # Use edge hash for identification
                            edge_hash = hash((round(edge.CenterOfMass.x, 4),
                                              round(edge.CenterOfMass.y, 4),
                                              round(edge.CenterOfMass.z, 4),
                                              round(edge.Length, 4)))
                            edge_to_faces[edge_hash].append((face_idx, edge))
                        except:
                            pass
                except:
                    pass

            # Create arcs for shared edges
            edge_index = 0
            for edge_hash, face_edges in edge_to_faces.items():
                if len(face_edges) == 2:
                    try:
                        (f1_idx, edge1), (f2_idx, edge2) = face_edges

                        # Determine convexity (simplified, no Surface.parameter calls)
                        convexity = self._determine_convexity(
                            shape.Faces[f1_idx],
                            shape.Faces[f2_idx],
                            edge1
                        )

                        arc = EdgeArc(
                            face1_idx=f1_idx,
                            face2_idx=f2_idx,
                            convexity=convexity,
                            length=edge1.Length,
                            edge_index=edge_index
                        )

                        self.arcs.append(arc)
                        self.adjacency[f1_idx].add(f2_idx)
                        self.adjacency[f2_idx].add(f1_idx)
                        edge_index += 1
                    except:
                        pass
        except Exception as e:
            # If edge adjacency building fails completely, continue without it
            pass

    def _determine_convexity(self, face1, face2, shared_edge) -> EdgeConvexity:
        """Determine edge convexity between two faces (simplified version)."""
        try:
            # Simplified: use face surface axis/normals directly
            # This avoids the problematic Surface.parameter() call

            # Get normals from surface (works for planes and cylinders)
            n1 = None
            n2 = None

            try:
                if hasattr(face1.Surface, 'Axis'):
                    n1 = face1.Surface.Axis
                elif hasattr(face1.Surface, 'Normal'):
                    n1 = face1.Surface.Normal
            except:
                pass

            try:
                if hasattr(face2.Surface, 'Axis'):
                    n2 = face2.Surface.Axis
                elif hasattr(face2.Surface, 'Normal'):
                    n2 = face2.Surface.Normal
            except:
                pass

            if n1 is None or n2 is None:
                return EdgeConvexity.UNKNOWN

            # Check for tangent (parallel normals)
            normal_dot = abs(n1.dot(n2))
            if normal_dot > 1.0 - ANGLE_TOLERANCE:
                return EdgeConvexity.TANGENT

            # Simplified convexity: check if normals point "outward"
            # For sheet metal, most edges are either tangent or convex
            if normal_dot < 0.1:  # Nearly perpendicular
                return EdgeConvexity.CONVEX
            else:
                return EdgeConvexity.SHARP

        except Exception:
            return EdgeConvexity.UNKNOWN

    def _classify_skin_thickness(self) -> None:
        """
        Classify faces as skin (top/bottom) or thickness (edge) faces.

        Skin faces: Large planar faces, typically parallel pairs
        Thickness faces: Smaller faces connecting skin faces
        """
        planar_faces = [n for n in self.nodes.values() if n.face_type == FaceType.PLANAR]

        if len(planar_faces) < 2:
            return

        # Sort by area (largest = likely skin faces)
        planar_faces.sort(key=lambda x: x.area, reverse=True)

        # Find parallel face pairs (potential skin pairs)
        for i, f1 in enumerate(planar_faces):
            if f1.is_skin:
                continue
            for f2 in planar_faces[i+1:]:
                if f2.is_skin:
                    continue
                if f1.normal and f2.normal:
                    # Check if anti-parallel (opposite normals)
                    dot = sum(a*b for a, b in zip(f1.normal, f2.normal))
                    if abs(dot + 1.0) < ANGLE_TOLERANCE:  # Anti-parallel
                        f1.is_skin = True
                        f2.is_skin = True
                        break

        # Remaining faces are thickness faces
        for node in self.nodes.values():
            if not node.is_skin:
                node.is_thickness = True

    def get_adjacent_faces(self, face_idx: int) -> Set[int]:
        """Get indices of faces adjacent to given face."""
        return self.adjacency[face_idx]

    def get_edge_between(self, face1_idx: int, face2_idx: int) -> Optional[EdgeArc]:
        """Get the edge arc between two faces."""
        for arc in self.arcs:
            if (arc.face1_idx == face1_idx and arc.face2_idx == face2_idx) or \
               (arc.face1_idx == face2_idx and arc.face2_idx == face1_idx):
                return arc
        return None


# =============================================================================
# FEATURE RECOGNIZER
# =============================================================================

class FeatureRecognizer:
    """
    Pattern-based feature recognition using AAG subgraph matching.

    Hole Detection:
    - Isoperimetric Quotient Q = 4πA/P² (Q≈1 for circles, Q<1 for slots)
    - Edge counting: 2 lines + 2 arcs = obround slot

    Bend Detection:
    - Cylindrical face between two planar faces
    - Convex/concave edge classification
    """

    def __init__(self, graph: TopologyGraph, shape, tolerance: float = DEFAULT_TOLERANCE):
        self.graph = graph
        self.shape = shape
        self.tolerance = tolerance
        self.holes: List[HoleFeature] = []
        self.bends: List[BendFeature] = []

    def recognize_all(self) -> None:
        """Run all feature recognition."""
        self._recognize_holes()
        self._recognize_bends()

    def _recognize_holes(self) -> None:
        """
        Recognize holes using inner wire analysis.

        For each planar skin face:
        1. Find inner wires (holes)
        2. Calculate isoperimetric quotient
        3. Count edge types (lines vs arcs)
        4. Classify hole type
        """
        for node in self.graph.nodes.values():
            if node.face_type != FaceType.PLANAR or not node.is_skin:
                continue

            face = self.shape.Faces[node.index]

            # Skip if no inner wires (outer wire is Wires[0])
            if len(face.Wires) <= 1:
                continue

            # Analyze each inner wire as a potential hole
            for wire in face.Wires[1:]:
                hole = self._analyze_wire_as_hole(wire, node.index)
                if hole:
                    self.holes.append(hole)

    def _analyze_wire_as_hole(self, wire, face_idx: int) -> Optional[HoleFeature]:
        """Analyze a wire to determine hole type."""
        try:
            perimeter = wire.Length

            # Calculate enclosed area (approximate)
            # For proper calculation would need to project to face plane
            bbox = wire.BoundBox
            approx_area = bbox.XLength * bbox.YLength * 0.785  # π/4 for ellipse approx

            # Isoperimetric quotient: Q = 4πA/P²
            # Q = 1 for perfect circle, Q < 1 for elongated shapes
            if perimeter > self.tolerance:
                Q = (4 * math.pi * approx_area) / (perimeter * perimeter)
            else:
                Q = 0

            # Count edge types
            line_count = 0
            arc_count = 0

            for edge in wire.Edges:
                try:
                    curve_type = edge.Curve.TypeId
                    if 'Line' in curve_type:
                        line_count += 1
                    elif 'Circle' in curve_type or 'Arc' in curve_type:
                        arc_count += 1
                except:
                    pass

            # Classify hole type
            if Q > 0.95:  # Nearly circular
                hole_type = FeatureType.HOLE_ROUND
                diameter = perimeter / math.pi
                length = width = diameter
            elif line_count == 2 and arc_count == 2:
                # Obround slot: 2 lines + 2 semicircles
                hole_type = FeatureType.HOLE_SLOT
                # Estimate dimensions from bbox
                length = max(bbox.XLength, bbox.YLength)
                width = min(bbox.XLength, bbox.YLength)
                diameter = width
            elif line_count == 4 and arc_count == 0:
                hole_type = FeatureType.HOLE_RECTANGULAR
                length = max(bbox.XLength, bbox.YLength)
                width = min(bbox.XLength, bbox.YLength)
                diameter = None
            else:
                hole_type = FeatureType.HOLE_COMPLEX
                length = max(bbox.XLength, bbox.YLength)
                width = min(bbox.XLength, bbox.YLength)
                diameter = None

            return HoleFeature(
                face_indices=[face_idx],
                hole_type=hole_type,
                diameter=diameter,
                length=length,
                width=width,
                perimeter=perimeter,
                area=approx_area,
                isoperimetric_quotient=Q,
                edge_count=line_count + arc_count,
                arc_count=arc_count,
                line_count=line_count
            )

        except Exception:
            return None

    def _recognize_bends(self) -> None:
        """
        Recognize bends using subgraph pattern matching.

        Pattern: Cylindrical face adjacent to two planar faces
        with concave edges on both sides.
        """
        for node in self.graph.nodes.values():
            if node.face_type != FaceType.CYLINDRICAL:
                continue

            # Find adjacent planar faces
            adjacent_planar = []
            for adj_idx in self.graph.get_adjacent_faces(node.index):
                adj_node = self.graph.nodes[adj_idx]
                if adj_node.face_type == FaceType.PLANAR:
                    edge = self.graph.get_edge_between(node.index, adj_idx)
                    adjacent_planar.append((adj_idx, edge))

            # Standard bend: cylindrical between exactly 2 planar faces
            if len(adjacent_planar) >= 2:
                bend = self._analyze_bend(node, adjacent_planar)
                if bend:
                    self.bends.append(bend)

    def _analyze_bend(self, cyl_node: FaceNode, adjacent_planar: List[Tuple[int, EdgeArc]]) -> Optional[BendFeature]:
        """Analyze a cylindrical face as a potential bend."""
        try:
            cyl_face = self.shape.Faces[cyl_node.index]

            # Get bend radius (inner radius of cylinder)
            bend_radius = cyl_node.radius
            if bend_radius is None:
                return None

            # Calculate bend angle from cylindrical face extent
            # The angular extent of the cylindrical face = bend angle
            u_min, u_max, v_min, v_max = cyl_face.ParameterRange
            bend_angle_rad = abs(u_max - u_min)
            bend_angle_deg = math.degrees(bend_angle_rad)

            # Bend length (along axis)
            bend_length = abs(v_max - v_min)

            # Determine bend type
            if bend_angle_deg > 170:  # Near 180°
                # Check for hem (closed or open)
                bend_type = FeatureType.BEND_HEM_CLOSED
            else:
                bend_type = FeatureType.BEND_STANDARD

            # Calculate K-factor based on R/T ratio
            # We need thickness - estimate from adjacent faces
            thickness = self._estimate_thickness_from_bend(cyl_node, adjacent_planar)
            if thickness > 0:
                rt_ratio = bend_radius / thickness
                k_factor = self._get_k_factor(rt_ratio)
            else:
                k_factor = 0.44  # Default
                thickness = 1.0

            # Calculate Bend Allowance and Deduction
            ba = self._calculate_bend_allowance(bend_angle_deg, bend_radius, thickness, k_factor)
            bd = self._calculate_bend_deduction(bend_angle_deg, bend_radius, thickness, k_factor)

            return BendFeature(
                cylindrical_face_idx=cyl_node.index,
                adjacent_faces=[ap[0] for ap in adjacent_planar],
                bend_type=bend_type,
                bend_angle=bend_angle_deg,
                bend_radius=bend_radius,
                bend_length=bend_length,
                k_factor=k_factor,
                bend_allowance=ba,
                bend_deduction=bd
            )

        except Exception:
            return None

    def _estimate_thickness_from_bend(self, cyl_node: FaceNode, adjacent_planar: List) -> float:
        """Estimate sheet thickness from bend geometry."""
        # The thickness can be estimated from the distance between
        # the two planar faces adjacent to the cylindrical bend face
        if len(adjacent_planar) < 2:
            return 0

        try:
            face1 = self.shape.Faces[adjacent_planar[0][0]]
            face2 = self.shape.Faces[adjacent_planar[1][0]]

            # Get face centers
            c1 = face1.CenterOfMass
            c2 = face2.CenterOfMass

            # Distance between centers projected onto normal
            n1 = face1.Surface.Axis
            diff = c2 - c1
            dist = abs(diff.dot(n1))

            # Subtract bend radius contribution
            thickness = dist - cyl_node.radius if cyl_node.radius else dist
            return max(thickness, 0.5)  # Minimum 0.5mm

        except Exception:
            return 0

    def _get_k_factor(self, rt_ratio: float) -> float:
        """Get K-factor from R/T ratio using lookup table with interpolation."""
        if rt_ratio <= 0:
            return 0.33

        # Find bracketing values
        ratios = sorted(K_FACTOR_TABLE.keys())

        if rt_ratio >= ratios[-1]:
            return K_FACTOR_TABLE[ratios[-1]]
        if rt_ratio <= ratios[0]:
            return K_FACTOR_TABLE[ratios[0]]

        # Linear interpolation
        for i in range(len(ratios) - 1):
            if ratios[i] <= rt_ratio <= ratios[i + 1]:
                r1, r2 = ratios[i], ratios[i + 1]
                k1, k2 = K_FACTOR_TABLE[r1], K_FACTOR_TABLE[r2]
                t = (rt_ratio - r1) / (r2 - r1)
                return k1 + t * (k2 - k1)

        return 0.44  # Default fallback

    def _calculate_bend_allowance(self, angle_deg: float, radius: float,
                                   thickness: float, k_factor: float) -> float:
        """
        Calculate Bend Allowance (BA).

        BA = π/180 × angle × (radius + k_factor × thickness)

        This is the arc length of the neutral axis.
        """
        angle_rad = math.radians(angle_deg)
        neutral_radius = radius + k_factor * thickness
        return angle_rad * neutral_radius

    def _calculate_bend_deduction(self, angle_deg: float, radius: float,
                                   thickness: float, k_factor: float) -> float:
        """
        Calculate Bend Deduction (BD).

        BD = 2 × setback - BA
        where setback = (radius + thickness) × tan(angle/2)

        BD is what to subtract from flat length.
        """
        angle_rad = math.radians(angle_deg)
        setback = (radius + thickness) * math.tan(angle_rad / 2)
        ba = self._calculate_bend_allowance(angle_deg, radius, thickness, k_factor)
        return 2 * setback - ba


# =============================================================================
# COST ESTIMATOR
# =============================================================================

class CostEstimator:
    """
    Laser cutting cost estimation.

    T_total = T_cut + T_pierce + T_traverse

    Where:
    - T_cut = cutting length / cutting speed
    - T_pierce = pierce_count × pierce_time
    - T_traverse = rapid_distance / rapid_speed
    """

    # Default machine parameters (can be overridden)
    DEFAULT_PARAMS = {
        'cut_speed': 20.0,        # mm/s (depends on material/thickness)
        'pierce_time': 0.5,       # seconds per pierce
        'rapid_speed': 100.0,     # mm/s
        'setup_time': 60.0,       # seconds
        'hourly_rate': 75.0,      # EUR/hour
    }

    # Cutting speed by material and thickness (mm/s)
    SPEED_TABLE = {
        # (material, thickness_mm): speed_mm_s
        ('steel', 1.0): 35,
        ('steel', 2.0): 25,
        ('steel', 3.0): 18,
        ('steel', 5.0): 10,
        ('steel', 10.0): 4,
        ('aluminum', 1.0): 50,
        ('aluminum', 2.0): 40,
        ('aluminum', 3.0): 30,
        ('aluminum', 5.0): 18,
        ('stainless', 1.0): 30,
        ('stainless', 2.0): 20,
        ('stainless', 3.0): 12,
    }

    def __init__(self, params: Optional[Dict] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    def estimate_cut_time(self, cut_length: float, pierce_count: int,
                          material: str = 'steel', thickness: float = 2.0) -> Dict:
        """
        Estimate total cutting time and cost.

        Args:
            cut_length: Total cutting length in mm
            pierce_count: Number of pierces (= number of contours)
            material: Material type
            thickness: Material thickness in mm

        Returns:
            Dict with time breakdown and cost
        """
        # Get cutting speed for material/thickness
        cut_speed = self._get_cut_speed(material, thickness)

        # Calculate times
        t_cut = cut_length / cut_speed if cut_speed > 0 else 0
        t_pierce = pierce_count * self.params['pierce_time']

        # Estimate traverse distance (rough: 20% of cut length)
        traverse_dist = cut_length * 0.2
        t_traverse = traverse_dist / self.params['rapid_speed']

        t_total = t_cut + t_pierce + t_traverse
        t_with_setup = t_total + self.params['setup_time']

        # Calculate cost
        hours = t_with_setup / 3600
        cost = hours * self.params['hourly_rate']

        return {
            'cut_time': round(t_cut, 1),
            'pierce_time': round(t_pierce, 1),
            'traverse_time': round(t_traverse, 1),
            'total_time': round(t_total, 1),
            'time_with_setup': round(t_with_setup, 1),
            'cut_speed': round(cut_speed, 1),
            'estimated_cost': round(cost, 2),
        }

    def _get_cut_speed(self, material: str, thickness: float) -> float:
        """Get cutting speed for material/thickness combination."""
        material = material.lower()

        # Find closest thickness in table
        available = [(m, t) for m, t in self.SPEED_TABLE.keys() if m == material]

        if not available:
            # Default to steel if material not found
            available = [(m, t) for m, t in self.SPEED_TABLE.keys() if m == 'steel']

        if not available:
            return self.params['cut_speed']

        # Find closest thickness
        thicknesses = sorted(set(t for m, t in available))

        if thickness <= thicknesses[0]:
            return self.SPEED_TABLE[(material, thicknesses[0])]
        if thickness >= thicknesses[-1]:
            return self.SPEED_TABLE[(material, thicknesses[-1])]

        # Interpolate
        for i in range(len(thicknesses) - 1):
            if thicknesses[i] <= thickness <= thicknesses[i + 1]:
                t1, t2 = thicknesses[i], thicknesses[i + 1]
                s1 = self.SPEED_TABLE[(material, t1)]
                s2 = self.SPEED_TABLE[(material, t2)]
                ratio = (thickness - t1) / (t2 - t1)
                return s1 + ratio * (s2 - s1)

        return self.params['cut_speed']


# =============================================================================
# MAIN ANALYZER
# =============================================================================

class AAGAnalyzer:
    """
    Main analyzer class integrating all components.

    Usage:
        analyzer = AAGAnalyzer()
        result = analyzer.analyze(shape)
    """

    def __init__(self, tolerance: float = DEFAULT_TOLERANCE):
        self.tolerance = tolerance
        self.graph: Optional[TopologyGraph] = None
        self.recognizer: Optional[FeatureRecognizer] = None
        self.cost_estimator = CostEstimator()

    def analyze(self, shape, material: str = 'steel') -> AnalysisResult:
        """
        Perform complete AAG-based analysis on a shape.

        Args:
            shape: FreeCAD Part.Shape or OCC shape
            material: Material type for cost estimation

        Returns:
            AnalysisResult with all detected features
        """
        result = AnalysisResult()

        try:
            # Build topology graph
            self.graph = TopologyGraph(self.tolerance)
            self.graph.build_from_freecad(shape)

            result.face_count = len(self.graph.nodes)
            result.edge_count = len(self.graph.arcs)
            result.skin_faces = sum(1 for n in self.graph.nodes.values() if n.is_skin)
            result.thickness_faces = sum(1 for n in self.graph.nodes.values() if n.is_thickness)
        except Exception as e:
            # Fallback: simple face counting
            result.face_count = len(shape.Faces)
            result.edge_count = len(shape.Edges)
            result.skin_faces = 0
            result.thickness_faces = 0

        # Detect thickness from parallel face pairs
        try:
            result.thickness = self._detect_thickness()
        except Exception:
            result.thickness = self._simple_thickness_detection(shape)

        # Recognize features
        try:
            if self.graph:
                self.recognizer = FeatureRecognizer(self.graph, shape, self.tolerance)
                self.recognizer.recognize_all()
                result.holes = self.recognizer.holes
                result.bends = self.recognizer.bends
            else:
                # Fallback: use simple detection methods
                result.holes = []
                result.bends = []
                result.hole_count, result.bend_count = self._simple_feature_detection(shape)
        except Exception as e:
            result.holes = []
            result.bends = []
            result.hole_count, result.bend_count = self._simple_feature_detection(shape)

        # Count features
        if result.holes:
            result.hole_count = len([h for h in result.holes
                                     if h.hole_type in (FeatureType.HOLE_ROUND,
                                                        FeatureType.HOLE_RECTANGULAR,
                                                        FeatureType.HOLE_COMPLEX)])
            result.slot_count = len([h for h in result.holes
                                     if h.hole_type == FeatureType.HOLE_SLOT])
        if result.bends:
            result.bend_count = len(result.bends)

        # Calculate cut length (sum of hole perimeters)
        try:
            result.cut_length = sum(h.perimeter for h in result.holes) if result.holes else 0
            result.pierce_count = len(result.holes) + 1 if result.holes else 1

            # Add outer contour length
            outer_contour = self._get_outer_contour_length(shape)
            result.cut_length += outer_contour
            result.total_cut_length = result.cut_length

            # Estimate cutting cost
            cost_data = self.cost_estimator.estimate_cut_time(
                result.cut_length,
                result.pierce_count,
                material,
                result.thickness
            )
            result.laser_cut_time = cost_data['total_time']
            result.estimated_cut_time = cost_data['total_time']
        except Exception:
            result.cut_length = 0
            result.total_cut_length = 0
            result.laser_cut_time = 0
            result.estimated_cut_time = 0

        return result

    def _simple_thickness_detection(self, shape) -> float:
        """Simple thickness detection from parallel face pairs."""
        try:
            planar_faces = []
            for face in shape.Faces:
                try:
                    if 'Plane' in face.Surface.TypeId:
                        normal = (face.Surface.Axis.x, face.Surface.Axis.y, face.Surface.Axis.z)
                        center = (face.CenterOfMass.x, face.CenterOfMass.y, face.CenterOfMass.z)
                        planar_faces.append({'normal': normal, 'center': center, 'area': face.Area})
                except:
                    pass

            if len(planar_faces) < 2:
                return 0

            distances = []
            for i, f1 in enumerate(planar_faces):
                for f2 in planar_faces[i+1:]:
                    # Check if parallel (anti-parallel normals)
                    dot = sum(a*b for a, b in zip(f1['normal'], f2['normal']))
                    if abs(dot + 1.0) < 0.05:  # Anti-parallel
                        diff = tuple(a - b for a, b in zip(f2['center'], f1['center']))
                        dist = abs(sum(a*b for a, b in zip(diff, f1['normal'])))
                        if 0.3 <= dist <= 20:
                            distances.append(dist)

            if distances:
                return min(distances)
            return 0
        except:
            return 0

    def _simple_feature_detection(self, shape) -> tuple:
        """Simple hole and bend detection as fallback."""
        hole_count = 0
        bend_count = 0

        try:
            # Count holes from inner wires on largest planar face
            planar_faces = []
            for face in shape.Faces:
                try:
                    if 'Plane' in face.Surface.TypeId:
                        planar_faces.append((face.Area, face))
                except:
                    pass

            if planar_faces:
                planar_faces.sort(reverse=True)
                largest = planar_faces[0][1]
                hole_count = len(largest.Wires) - 1  # Inner wires = holes

            # Count bends from cylindrical faces
            bend_cyl = 0
            for face in shape.Faces:
                try:
                    if 'Cylinder' in face.Surface.TypeId:
                        radius = face.Surface.Radius
                        bbox = face.BoundBox
                        height = max(bbox.XLength, bbox.YLength, bbox.ZLength)
                        if 0.3 <= radius <= 15 and height > 15 and height > 2 * radius:
                            bend_cyl += 1
                except:
                    pass
            bend_count = bend_cyl // 2

        except:
            pass

        return hole_count, bend_count

    def _detect_thickness(self) -> float:
        """Detect sheet thickness from AAG skin face analysis."""
        skin_faces = [n for n in self.graph.nodes.values() if n.is_skin]

        if len(skin_faces) < 2:
            return 0

        # Find minimum distance between parallel skin face pairs
        min_thickness = float('inf')

        for i, f1 in enumerate(skin_faces):
            for f2 in skin_faces[i+1:]:
                if f1.normal and f2.normal and f1.center and f2.center:
                    # Check if anti-parallel
                    dot = sum(a*b for a, b in zip(f1.normal, f2.normal))
                    if abs(dot + 1.0) < ANGLE_TOLERANCE:
                        # Calculate distance
                        diff = tuple(a - b for a, b in zip(f2.center, f1.center))
                        dist = abs(sum(a*b for a, b in zip(diff, f1.normal)))
                        if 0.3 < dist < min_thickness:
                            min_thickness = dist

        return min_thickness if min_thickness < float('inf') else 0

    def _get_outer_contour_length(self, shape) -> float:
        """Get outer contour length from largest skin face."""
        if not self.graph:
            return 0

        # Find largest skin face
        skin_faces = [(n.index, n.area) for n in self.graph.nodes.values()
                      if n.is_skin and n.face_type == FaceType.PLANAR]

        if not skin_faces:
            return 0

        largest_idx = max(skin_faces, key=lambda x: x[1])[0]

        try:
            face = shape.Faces[largest_idx]
            if face.Wires:
                return face.Wires[0].Length  # Outer wire
        except:
            pass

        return 0


# =============================================================================
# INTEGRATION FUNCTION
# =============================================================================

def analyze_with_aag(shape, material: str = 'steel') -> Dict:
    """
    Convenience function for AAG analysis.

    Returns dict compatible with compare_erp.py pipeline.
    """
    analyzer = AAGAnalyzer()
    result = analyzer.analyze(shape, material)

    return {
        'source': 'AAG',
        'holes': result.hole_count + result.slot_count,
        'holes_round': result.hole_count,
        'holes_slot': result.slot_count,
        'bends': result.bend_count,
        'thickness': round(result.thickness, 2),
        'cut_length': round(result.cut_length, 1),
        'pierce_count': result.pierce_count,
        'estimated_cut_time': round(result.estimated_cut_time, 1),
        'face_count': result.face_count,
        'edge_count': result.edge_count,
        'skin_faces': result.skin_faces,
        'thickness_faces': result.thickness_faces,
        'hole_details': [
            {
                'type': h.hole_type.value,
                'diameter': round(h.diameter, 2) if h.diameter else None,
                'perimeter': round(h.perimeter, 1),
                'Q': round(h.isoperimetric_quotient, 3),
            }
            for h in result.holes
        ],
        'bend_details': [
            {
                'type': b.bend_type.value,
                'angle': round(b.bend_angle, 1),
                'radius': round(b.bend_radius, 2),
                'length': round(b.bend_length, 1),
                'k_factor': round(b.k_factor, 3),
                'bend_allowance': round(b.bend_allowance, 2),
                'bend_deduction': round(b.bend_deduction, 2),
            }
            for b in result.bends
        ],
    }


if __name__ == "__main__":
    print("AAG Analyzer Module")
    print("=" * 50)
    print("Classes available:")
    print("  - TopologyGraph: AAG construction")
    print("  - FeatureRecognizer: Pattern matching")
    print("  - CostEstimator: Laser cut time")
    print("  - AAGAnalyzer: Main analyzer")
    print()
    print("Usage:")
    print("  from aag_analyzer import analyze_with_aag")
    print("  result = analyze_with_aag(shape, material='steel')")
