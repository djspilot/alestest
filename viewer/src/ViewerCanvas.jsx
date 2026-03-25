import React, { useCallback, useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import StepModel from './StepModel'

function CameraFitter({ modelInfo, controlsRef }) {
  const { camera, invalidate } = useThree()

  useEffect(() => {
    if (!modelInfo?.boundingRadius || !controlsRef.current) return

    const radius = Math.max(modelInfo.boundingRadius, 1)
    const distance = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.15

    camera.position.set(distance * 0.9, distance * 0.7, distance * 0.9)
    camera.near = Math.max(distance / 1000, 0.1)
    camera.far = Math.max(distance * 25, 1000)
    camera.updateProjectionMatrix()

    controlsRef.current.target.set(0, 0, 0)
    controlsRef.current.minDistance = Math.max(radius * 0.35, 1)
    controlsRef.current.maxDistance = Math.max(radius * 12, 50)
    controlsRef.current.update()
    controlsRef.current.saveState()
    invalidate()
  }, [camera, controlsRef, invalidate, modelInfo])

  return null
}

function SceneControls({ controlsRef }) {
  const { invalidate } = useThree()

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.08}
      enablePan={false}
      onChange={invalidate}
    />
  )
}

function HoleFocusController({ selectedHole, modelInfo, controlsRef }) {
  const { camera, invalidate } = useThree()

  useEffect(() => {
    if (!selectedHole || !modelInfo?.center || !controlsRef.current) return

    const target = new THREE.Vector3(
      selectedHole.position[0] - modelInfo.center.x,
      selectedHole.position[1] - modelInfo.center.y,
      selectedHole.position[2] - modelInfo.center.z
    )
    const direction = new THREE.Vector3(...(selectedHole.axis || selectedHole.normal || [1, 0, 0])).normalize()
    const focusSize =
      selectedHole.diameter ||
      Math.max(...parseHoleSize(selectedHole.size || selectedHole.label || '', 12)) ||
      12
    const distance = Math.max(focusSize * 6, modelInfo.boundingRadius * 0.14, 24)
    const cameraOffset = direction.multiplyScalar(distance).add(new THREE.Vector3(distance * 0.25, distance * 0.12, distance * 0.22))

    camera.position.copy(target.clone().add(cameraOffset))
    controlsRef.current.target.copy(target)
    controlsRef.current.update()
    invalidate()
  }, [camera, controlsRef, invalidate, modelInfo, selectedHole])

  return null
}

function longestAxisInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => b.value - a.value)
  return entries[0]
}

function orderedAxesInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => b.value - a.value)
  return entries
}

function parseHoleSize(value, fallback = 12) {
  if (!value) return [fallback, fallback]
  const match = String(value).match(/(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)/i)
  if (!match) return [fallback, fallback]
  return [Number(match[1]), Number(match[2])]
}

function quaternionFromDirection(direction) {
  const normal = new THREE.Vector3(...direction).normalize()
  return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
}

function crossSectionDimensions(size, axisKey) {
  if (!size) return [20, 20]
  if (axisKey === 'x') return [size.y || 20, size.z || 20]
  if (axisKey === 'y') return [size.x || 20, size.z || 20]
  return [size.x || 20, size.y || 20]
}

function rectanglePoints(width, height) {
  const halfW = Math.max(width, 1) / 2
  const halfH = Math.max(height, 1) / 2
  return [
    [-halfW, -halfH, 0],
    [halfW, -halfH, 0],
    [halfW, halfH, 0],
    [-halfW, halfH, 0],
  ]
}

function toFloat32(points) {
  return new Float32Array(points.flat())
}

function buildLineSegments(points) {
  const segments = []
  for (let index = 0; index < points.length - 1; index += 1) {
    segments.push(points[index], points[index + 1])
  }
  return toFloat32(segments)
}

function buildDimensionLine(start, end, capSize = 6, capAxis = 'y') {
  const positions = [start, end]
  const capOffsets = {
    x: [capSize, 0, 0],
    y: [0, capSize, 0],
    z: [0, 0, capSize],
  }
  const offset = capOffsets[capAxis] || capOffsets.y

  positions.push(
    [start[0] - offset[0], start[1] - offset[1], start[2] - offset[2]],
    [start[0] + offset[0], start[1] + offset[1], start[2] + offset[2]],
    [end[0] - offset[0], end[1] - offset[1], end[2] - offset[2]],
    [end[0] + offset[0], end[1] + offset[1], end[2] + offset[2]],
  )

  return new Float32Array([
    ...positions[0], ...positions[1],
    ...positions[2], ...positions[3],
    ...positions[4], ...positions[5],
  ])
}

function circlePoints(radius, segments = 64) {
  const safeRadius = Math.max(radius, 1)
  return Array.from({ length: segments }, (_, index) => {
    const angle = (index / segments) * Math.PI * 2
    return [Math.cos(angle) * safeRadius, Math.sin(angle) * safeRadius, 0]
  })
}

function buildSectionContours(partType, size, thickness, axisKey) {
  const [dimA, dimB] = crossSectionDimensions(size, axisKey)
  const width = Math.max(dimA, dimB)
  const height = Math.min(dimA, dimB)
  const normalizedType = String(partType || '').toUpperCase()
  const isRound = normalizedType.includes('BUIS') && !normalizedType.includes('KOKER')

  if (isRound) {
    const outerRadius = Math.min(width, height) / 2
    const contours = [circlePoints(outerRadius)]
    const innerRadius = outerRadius - Math.max(thickness || 0, 0)
    if (innerRadius > 1) contours.push(circlePoints(innerRadius))
    return contours
  }

  const contours = [rectanglePoints(width, height)]
  const innerWidth = width - (2 * Math.max(thickness || 0, 0))
  const innerHeight = height - (2 * Math.max(thickness || 0, 0))
  if (innerWidth > 2 && innerHeight > 2) {
    contours.push(rectanglePoints(innerWidth, innerHeight))
  }
  return contours
}

function holePalette(hole, isSelected, hasSelection) {
  const dimmed = hasSelection && !isSelected

  if (isSelected) {
    return {
      outer: '#f5c542',
      inner: '#fff0a8',
      leader: '#f59e0b',
      marker: '#f59e0b',
      outlineOpacity: 1,
      leaderOpacity: 1,
      fillOpacity: 0.12,
    }
  }

  if (hole.status === 'rejected') {
    return {
      outer: '#315b8a',
      inner: '#60a5fa',
      leader: '#7dd3fc',
      marker: '#7dd3fc',
      outlineOpacity: dimmed ? 0.2 : 0.85,
      leaderOpacity: dimmed ? 0.15 : 0.75,
      fillOpacity: dimmed ? 0.0 : 0.03,
    }
  }

  return {
    outer: '#7f0008',
    inner: '#ff4d3b',
    leader: '#ff7a59',
    marker: '#ff7a59',
    outlineOpacity: dimmed ? 0.22 : 0.92,
    leaderOpacity: dimmed ? 0.16 : 0.82,
    fillOpacity: dimmed ? 0.0 : 0.04,
  }
}

function holeCenterPosition(hole, center) {
  return [
    hole.position[0] - center.x,
    hole.position[1] - center.y,
    hole.position[2] - center.z,
  ]
}

function holeFocusRadius(hole, modelInfo) {
  const [width, height] = parseHoleSize(hole.size || hole.label || '', 12)
  const featureSize = hole.diameter || Math.max(width, height) || 12
  return Math.max(featureSize * 0.7, modelInfo?.boundingRadius * 0.018 || 0, 6)
}

function findNearestHoleByPoint(point, holes, center, modelInfo) {
  if (!holes?.length || !center) return null

  let bestHole = null
  let bestDistance = Infinity
  const clickedPoint = point instanceof THREE.Vector3 ? point : new THREE.Vector3(point.x, point.y, point.z)

  for (const hole of holes) {
    const position = holeCenterPosition(hole, center)
    const holePoint = new THREE.Vector3(...position)
    const distance = holePoint.distanceTo(clickedPoint)
    const maxDistance = holeFocusRadius(hole, modelInfo) * 1.35

    if (distance <= maxDistance && distance < bestDistance) {
      bestHole = hole
      bestDistance = distance
    }
  }

  return bestHole
}

function HoleOutline({ hole, center, isSelected, hasSelection, modelInfo, onSelect }) {
  const position = holeCenterPosition(hole, center)
  const cylindricalRadius = Math.max((hole.diameter || 8) / 2, 3)
  const [rectWidth, rectHeight] = parseHoleSize(hole.size || hole.label, 14)
  const outerLoop = useMemo(() => {
    if (hole.type === 'cylindrical') {
      return toFloat32(circlePoints(cylindricalRadius, 72))
    }
    return toFloat32(rectanglePoints(Math.max(rectWidth, 6), Math.max(rectHeight, 6)))
  }, [hole.type, cylindricalRadius, rectWidth, rectHeight])
  const innerLoop = useMemo(() => {
    if (hole.type === 'cylindrical') {
      return toFloat32(circlePoints(Math.max(cylindricalRadius * 0.82, cylindricalRadius - 1.1), 72))
    }
    return toFloat32(rectanglePoints(Math.max(rectWidth * 0.86, 5), Math.max(rectHeight * 0.86, 5)))
  }, [hole.type, cylindricalRadius, rectWidth, rectHeight])
  const leaderLine = useMemo(() => {
    if (hole.type === 'cylindrical') {
      return buildLineSegments([
        [cylindricalRadius, 0, 0],
        [cylindricalRadius + 8, 0, 0],
        [cylindricalRadius + 18, cylindricalRadius * 0.5, 0],
      ])
    }
    return buildLineSegments([
      [rectWidth / 2, 0, 0],
      [rectWidth / 2 + 8, 0, 0],
      [rectWidth / 2 + 18, rectHeight * 0.35, 0],
    ])
  }, [hole.type, cylindricalRadius, rectWidth, rectHeight])
  const palette = holePalette(hole, isSelected, hasSelection)
  const hitRadius = holeFocusRadius(hole, modelInfo)
  const handleSelect = useCallback((event) => {
    event.stopPropagation()
    onSelect?.(hole.id)
  }, [hole.id, onSelect])

  if (hole.type === 'cylindrical') {
    const quaternion = quaternionFromDirection(hole.axis || [1, 0, 0])
    return (
      <group position={position} quaternion={quaternion} renderOrder={20} onClick={handleSelect}>
        <mesh>
          <circleGeometry args={[Math.max(cylindricalRadius * 1.08, hitRadius * 0.9), 40]} />
          <meshBasicMaterial color={palette.outer} transparent opacity={palette.fillOpacity} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
        <lineLoop>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[outerLoop, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={palette.outer} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
        </lineLoop>
        <lineLoop position={[0, 0, 0.2]}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[innerLoop, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={palette.inner} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
        </lineLoop>
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[leaderLine, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={palette.leader} transparent opacity={palette.leaderOpacity} depthTest={false} depthWrite={false} />
        </lineSegments>
        <mesh position={[cylindricalRadius + 18, cylindricalRadius * 0.5, 0]}>
          <sphereGeometry args={[1.4, 12, 12]} />
          <meshBasicMaterial color={palette.marker} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
        </mesh>
        <mesh>
          <circleGeometry args={[hitRadius, 40]} />
          <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
      </group>
    )
  }

  const quaternion = quaternionFromDirection(hole.normal || [1, 0, 0])
  return (
    <group position={position} quaternion={quaternion} renderOrder={20} onClick={handleSelect}>
      <mesh>
        <planeGeometry args={[Math.max(rectWidth * 1.08, hitRadius * 1.7), Math.max(rectHeight * 1.08, hitRadius * 1.7)]} />
        <meshBasicMaterial color={palette.outer} transparent opacity={palette.fillOpacity} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <lineLoop>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[outerLoop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={palette.outer} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
      </lineLoop>
      <lineLoop position={[0, 0, 0.2]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[innerLoop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={palette.inner} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
      </lineLoop>
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[leaderLine, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={palette.leader} transparent opacity={palette.leaderOpacity} depthTest={false} depthWrite={false} />
        </lineSegments>
      <mesh position={[rectWidth / 2 + 18, rectHeight * 0.35, 0]}>
        <sphereGeometry args={[1.4, 12, 12]} />
        <meshBasicMaterial color={palette.marker} transparent opacity={palette.outlineOpacity} depthTest={false} depthWrite={false} />
      </mesh>
      <mesh>
        <planeGeometry args={[Math.max(rectWidth, hitRadius * 2), Math.max(rectHeight, hitRadius * 2)]} />
        <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function SectionContour({ points, position, quaternion, color }) {
  const flatPoints = useMemo(() => new Float32Array(points.flat()), [points])

  return (
    <lineLoop position={position} quaternion={quaternion} renderOrder={15}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[flatPoints, 3]} />
      </bufferGeometry>
      <lineBasicMaterial
        color={color}
        transparent
        opacity={1}
        depthTest={false}
        depthWrite={false}
      />
    </lineLoop>
  )
}

function SectionContours({ position, quaternion, contours, color }) {
  const identityQuaternion = useMemo(() => new THREE.Quaternion(), [])

  return (
    <group position={position} quaternion={quaternion} renderOrder={15}>
      {contours.map((points, index) => (
        <SectionContour
          key={`section-contour-${index}`}
          points={points}
          position={[0, 0, index * 0.25]}
          quaternion={identityQuaternion}
          color={color}
        />
      ))}
      <mesh>
        <circleGeometry args={[2.4, 24]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.98}
          depthTest={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function BoundingBoxGuide({ size, color = '#d97706' }) {
  const half = {
    x: (size?.x || 0) / 2,
    y: (size?.y || 0) / 2,
    z: (size?.z || 0) / 2,
  }
  const corners = [
    [-half.x, -half.y, -half.z],
    [half.x, -half.y, -half.z],
    [half.x, half.y, -half.z],
    [-half.x, half.y, -half.z],
    [-half.x, -half.y, half.z],
    [half.x, -half.y, half.z],
    [half.x, half.y, half.z],
    [-half.x, half.y, half.z],
  ]
  const edges = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ]
  const positions = new Float32Array(edges.flatMap(([a, b]) => [...corners[a], ...corners[b]]))

  return (
    <lineSegments renderOrder={12}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={0.92} depthTest={false} depthWrite={false} />
    </lineSegments>
  )
}

function DimensionGuide({ start, end, color, capAxis = 'y' }) {
  const positions = useMemo(() => buildDimensionLine(start, end, 8, capAxis), [start, end, capAxis])

  return (
    <lineSegments renderOrder={16}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={1} depthTest={false} depthWrite={false} />
    </lineSegments>
  )
}

function ClassificationGuides({ modelInfo, classificationVisuals }) {
  const size = modelInfo?.size
  if (!size || !classificationVisuals) return null

  const axes = orderedAxesInfo(size)
  const [longAxis, middleAxis, shortAxis] = axes
  const maxSize = Math.max(size.x || 0, size.y || 0, size.z || 0, 10)
  const extent = {
    x: (size.x || 0) / 2,
    y: (size.y || 0) / 2,
    z: (size.z || 0) / 2,
  }
  const offsetBase = maxSize * 0.12
  const positions = {
    long: { x: extent.x, y: -extent.y - offsetBase, z: -extent.z - offsetBase * 0.3 },
    middle: { x: -extent.x - offsetBase * 0.65, y: extent.y, z: -extent.z - offsetBase * 0.15 },
    short: { x: extent.x + offsetBase * 0.35, y: extent.y + offsetBase * 0.15, z: extent.z },
  }

  const makeEndpoints = (axis, anchor) => {
    if (axis.key === 'x') {
      return [[-extent.x, anchor.y, anchor.z], [extent.x, anchor.y, anchor.z]]
    }
    if (axis.key === 'y') {
      return [[anchor.x, -extent.y, anchor.z], [anchor.x, extent.y, anchor.z]]
    }
    return [[anchor.x, anchor.y, -extent.z], [anchor.x, anchor.y, extent.z]]
  }

  const longEndpoints = makeEndpoints(longAxis, positions.long)
  const middleEndpoints = makeEndpoints(middleAxis, positions.middle)
  const shortEndpoints = makeEndpoints(shortAxis, positions.short)

  const capAxisFor = (axisKey) => {
    if (axisKey === 'x') return 'y'
    if (axisKey === 'y') return 'x'
    return 'x'
  }

  return (
    <group>
      <BoundingBoxGuide size={size} color="#b45309" />
      <DimensionGuide start={longEndpoints[0]} end={longEndpoints[1]} color="#f59e0b" capAxis={capAxisFor(longAxis.key)} />
      <DimensionGuide start={middleEndpoints[0]} end={middleEndpoints[1]} color="#fb7185" capAxis={capAxisFor(middleAxis.key)} />
      <DimensionGuide start={shortEndpoints[0]} end={shortEndpoints[1]} color="#facc15" capAxis={capAxisFor(shortAxis.key)} />
    </group>
  )
}

function buildFallbackSections(modelInfo) {
  if (!modelInfo?.size) return []
  const axis = longestAxisInfo(modelInfo.size)
  const length = axis.value || 1
  const fractions = [0.2, 0.35, 0.5, 0.65, 0.8]
  return fractions.map((fraction) => {
    const offset = (fraction - 0.5) * length
    const position = [0, 0, 0]
    if (axis.key === 'x') position[0] = offset
    if (axis.key === 'y') position[1] = offset
    if (axis.key === 'z') position[2] = offset
    return position
  })
}

function StageOverlays({ modelInfo, visuals, focusedStage, selectedHole, onHoleSelect }) {
  const center = modelInfo?.center
  if (!center || !visuals || !focusedStage) return null

  const holeVisuals = visuals?.holes?.items || []
  const routerVisuals = visuals?.router || null
  const classificationVisuals = visuals?.classification || null
  const unfoldVisuals = visuals?.unfold || null
  const size = modelInfo?.size
  const overlayExtent = Math.max(size?.x || 0, size?.y || 0, size?.z || 0, 50)

  const makePosition = (position) => [
    position[0] - center.x,
    position[1] - center.y,
    position[2] - center.z,
  ]

  const planeQuaternion = new THREE.Quaternion()
  if (routerVisuals?.axis_direction) {
    const normal = new THREE.Vector3(...routerVisuals.axis_direction).normalize()
    planeQuaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
  }

  const fallbackAxis = longestAxisInfo(size)
  const fallbackQuaternion = quaternionFromDirection(fallbackAxis.vector)
  const contourPartType = classificationVisuals?.part_type || routerVisuals?.profile_label || ''
  const contourThickness = classificationVisuals?.thickness || 0
  const contours = buildSectionContours(contourPartType, size, contourThickness, fallbackAxis.key)
  const routerSections = (routerVisuals?.sampled_sections || []).map((section) => ({
    position: makePosition(section.origin_3d),
    quaternion: planeQuaternion,
  }))
  const fallbackSections = buildFallbackSections(modelInfo).map((position) => ({
    position,
    quaternion: fallbackQuaternion,
  }))
  const sectionVisuals = routerSections.length > 0 ? routerSections : fallbackSections
  const foldVisuals = (unfoldVisuals?.fold_details || []).map((fold) => ({
    position: makePosition(fold.center),
    length: fold.length || overlayExtent * 0.4,
  }))

  return (
      <group>
      {focusedStage === 'Detect holes' && holeVisuals.map((hole, index) => (
        <HoleOutline
          key={hole.id || `${hole.type}-${index}`}
          hole={hole}
          center={center}
          hasSelection={Boolean(selectedHole?.id)}
          modelInfo={modelInfo}
          isSelected={selectedHole?.id === hole.id}
          onSelect={onHoleSelect}
        />
      ))}

      {focusedStage === 'Profile Router' && sectionVisuals.map((section, index) => (
        <SectionContours
          key={`router-section-${index}`}
          position={section.position}
          quaternion={section.quaternion}
          contours={contours}
          color="#8f0008"
        />
      ))}

      {focusedStage === 'Classify geometry' && sectionVisuals.map((section, index) => (
        <SectionContours
          key={`classify-section-${index}`}
          position={section.position}
          quaternion={section.quaternion}
          contours={contours}
          color="#6f0010"
        />
      ))}

      {focusedStage === 'Classify geometry' && (
        <ClassificationGuides modelInfo={modelInfo} classificationVisuals={classificationVisuals} />
      )}

      {focusedStage === 'Unfold' && foldVisuals.map((fold, index) => (
        <group key={`fold-${index}`} position={fold.position} renderOrder={20}>
          <mesh rotation={[0, 0, Math.PI / 4]}>
            <planeGeometry args={[Math.max(fold.length * 0.18, 18), 4]} />
            <meshBasicMaterial
              color="#8f0008"
              transparent
              opacity={1}
              side={THREE.DoubleSide}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>
          <mesh rotation={[0, 0, -Math.PI / 4]}>
            <planeGeometry args={[Math.max(fold.length * 0.18, 18), 4]} />
            <meshBasicMaterial
              color="#ff3b30"
              transparent
              opacity={1}
              side={THREE.DoubleSide}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>
        </group>
      ))}
    </group>
  )
}

export default function ViewerCanvas({
  fileBuffer,
  activeMesh,
  onLoaded,
  onError,
  onStatus,
  parseMode,
  modelInfo,
  backendVisuals,
  focusedStage,
  selectedHole,
  onHoleSelect,
  controlsRef,
  useFlatView,
}) {
  const renderMode = 'clean'
  const holeItems = backendVisuals?.holes?.items || []
  const handleSurfacePick = useCallback((point, event) => {
    if (!holeItems.length || !modelInfo?.center) return
    event?.stopPropagation?.()
    const nearestHole = findNearestHoleByPoint(point, holeItems, modelInfo.center, modelInfo)
    if (nearestHole?.id) {
      onHoleSelect?.(nearestHole.id)
    }
  }, [holeItems, modelInfo, onHoleSelect])

  return (
    <Canvas
      frameloop="demand"
      performance={{ min: 0.5 }}
      camera={{ position: [150, 100, 150], fov: 40, near: 0.1, far: 10000 }}
      dpr={[1, 1.25]}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      style={{ background: 'linear-gradient(180deg, #f0f4f8 0%, #e2e8f0 100%)' }}
    >
      <ambientLight intensity={0.55 * Math.PI} />
      <hemisphereLight args={['#ffffff', '#cbd5e1', 0.75]} />
      <directionalLight position={[100, 150, 100]} intensity={0.55} />

      <StepModel
        buffer={fileBuffer}
        mesh={activeMesh}
        onLoaded={onLoaded}
        onError={onError}
        onStatus={onStatus}
        onSurfacePick={handleSurfacePick}
        parseMode={parseMode}
        renderMode={renderMode}
      />

      <CameraFitter modelInfo={modelInfo} controlsRef={controlsRef} />
      <HoleFocusController selectedHole={selectedHole} modelInfo={modelInfo} controlsRef={controlsRef} />
      <StageOverlays
        modelInfo={modelInfo}
        visuals={backendVisuals}
        focusedStage={focusedStage}
        selectedHole={selectedHole}
        onHoleSelect={onHoleSelect}
      />
      {!useFlatView && <gridHelper args={[500, 18, '#d4d9e1', '#edf1f5']} />}
      <SceneControls controlsRef={controlsRef} />
    </Canvas>
  )
}
