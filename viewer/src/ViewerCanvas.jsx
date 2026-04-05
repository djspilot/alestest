import React, { useCallback, useEffect, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import StepModel from './StepModel'
import { isPreUnfoldStageName, MERGED_HOLES_STAGE, PRE_UNFOLD_HOLES_STAGE } from './pipelineUi'
import { getFoldSegmentId, normalizeFoldId, isIrregularHole, isHiddenHoleCandidate } from './lib/holes'

function axisVectorForKey(key) {
  if (key === 'x') return new THREE.Vector3(1, 0, 0)
  if (key === 'y') return new THREE.Vector3(0, 1, 0)
  return new THREE.Vector3(0, 0, 1)
}

function toLocalPoint(point, center, normalVector, epsilon) {
  if (!Array.isArray(point) || point.length < 3 || !center) return null
  return new THREE.Vector3(
    Number(point[0] || 0) - center.x + normalVector.x * epsilon,
    Number(point[1] || 0) - center.y + normalVector.y * epsilon,
    Number(point[2] || 0) - center.z + normalVector.z * epsilon,
  )
}

function averagePoint(points) {
  if (!Array.isArray(points) || points.length === 0) return null
  const total = points.reduce(
    (acc, point) => {
      acc.x += Number(point[0] || 0)
      acc.y += Number(point[1] || 0)
      acc.z += Number(point[2] || 0)
      return acc
    },
    { x: 0, y: 0, z: 0 },
  )
  return new THREE.Vector3(total.x / points.length, total.y / points.length, total.z / points.length)
}

function contourNormal(points, fallback = [0, 0, 1]) {
  if (!Array.isArray(points) || points.length < 3) {
    return new THREE.Vector3(...fallback).normalize()
  }

  const normal = new THREE.Vector3()
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]
    const next = points[(index + 1) % points.length]
    const cx = Number(current[0] || 0)
    const cy = Number(current[1] || 0)
    const cz = Number(current[2] || 0)
    const nx = Number(next[0] || 0)
    const ny = Number(next[1] || 0)
    const nz = Number(next[2] || 0)
    normal.x += (cy - ny) * (cz + nz)
    normal.y += (cz - nz) * (cx + nx)
    normal.z += (cx - nx) * (cy + ny)
  }

  if (normal.lengthSq() < 1e-8) {
    return new THREE.Vector3(...fallback).normalize()
  }
  return normal.normalize()
}

function projectPointsToPlane(points, origin, normal) {
  if (!Array.isArray(points) || !origin || !normal) return []
  return points.map((point) => {
    const candidate = new THREE.Vector3(
      Number(point[0] || 0),
      Number(point[1] || 0),
      Number(point[2] || 0),
    )
    const distance = candidate.clone().sub(origin).dot(normal)
    const projected = candidate.clone().addScaledVector(normal, -distance)
    return [projected.x, projected.y, projected.z]
  })
}

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

function StudioEnvironment({ renderMode }) {
  const { gl, scene } = useThree()

  useEffect(() => {
    const previousToneMapping = gl.toneMapping
    const previousToneMappingExposure = gl.toneMappingExposure
    const previousOutputColorSpace = gl.outputColorSpace
    gl.toneMapping = THREE.ACESFilmicToneMapping
    gl.toneMappingExposure = renderMode === 'studio' ? 1.45 : renderMode === 'xray' ? 1.28 : 1.2
    gl.outputColorSpace = THREE.SRGBColorSpace

    const pmrem = new THREE.PMREMGenerator(gl)
    const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.05).texture
    const previousEnvironment = scene.environment
    scene.environment = envTexture
    return () => {
      scene.environment = previousEnvironment || null
      gl.toneMapping = previousToneMapping
      gl.toneMappingExposure = previousToneMappingExposure
      gl.outputColorSpace = previousOutputColorSpace
      envTexture.dispose?.()
      pmrem.dispose()
    }
  }, [gl, renderMode, scene])

  useEffect(() => {
    if (renderMode === 'xray') {
      scene.background = new THREE.Color('#edf4fb')
      return () => {
        scene.background = null
      }
    }
    if (renderMode === 'analysis') {
      scene.background = new THREE.Color('#eef2f7')
      return () => {
        scene.background = null
      }
    }
    scene.background = new THREE.Color('#e8eef5')
    return () => {
      scene.background = null
    }
  }, [renderMode, scene])

  return null
}

function CameraRigLights({ modelInfo, lightMode, renderMode }) {
  const { camera } = useThree()
  const keyRef = React.useRef(null)
  const fillRef = React.useRef(null)
  const rimRef = React.useRef(null)
  const pointRef = React.useRef(null)
  const headRef = React.useRef(null)

  const lighting = useMemo(() => {
    if (lightMode === 'soft') {
      return {
        ambient: 0.42 * Math.PI,
        hemi: 0.75,
        key: 0.95,
        fill: 0.42,
        rim: 0.22,
        point: 24,
        head: 1.1,
      }
    }
    if (lightMode === 'contrast') {
      return {
        ambient: 0.24 * Math.PI,
        hemi: 0.5,
        key: 1.35,
        fill: 0.68,
        rim: 0.42,
        point: 35,
        head: 1.45,
      }
    }
    return {
      ambient: 0.5 * Math.PI,
      hemi: 0.95,
      key: 1.55,
      fill: 0.85,
      rim: 0.5,
      point: 55,
      head: 1.75,
    }
  }, [lightMode])

  useFrame(() => {
    const radius = Math.max(modelInfo?.boundingRadius || 120, 60)
    const target = new THREE.Vector3(0, 0, 0)
    const forward = new THREE.Vector3()
    camera.getWorldDirection(forward)
    const up = camera.up.clone().normalize()
    const right = new THREE.Vector3().crossVectors(forward, up).normalize()

    const keyPos = camera.position
      .clone()
      .add(right.clone().multiplyScalar(radius * 0.55))
      .add(up.clone().multiplyScalar(radius * 0.35))
      .add(forward.clone().multiplyScalar(radius * 0.18))
    const fillPos = camera.position
      .clone()
      .add(right.clone().multiplyScalar(-radius * 0.7))
      .add(up.clone().multiplyScalar(radius * 0.1))
      .add(forward.clone().multiplyScalar(-radius * 0.08))
    const rimPos = camera.position
      .clone()
      .add(right.clone().multiplyScalar(radius * 0.15))
      .add(up.clone().multiplyScalar(-radius * 0.5))
      .add(forward.clone().multiplyScalar(-radius * 0.95))
    const pointPos = camera.position
      .clone()
      .add(up.clone().multiplyScalar(radius * 0.08))
    const headPos = camera.position
      .clone()
      .add(forward.clone().multiplyScalar(radius * 0.12))

    if (keyRef.current) {
      keyRef.current.position.copy(keyPos)
      keyRef.current.target.position.copy(target)
      keyRef.current.target.updateMatrixWorld()
    }
    if (fillRef.current) {
      fillRef.current.position.copy(fillPos)
      fillRef.current.target.position.copy(target)
      fillRef.current.target.updateMatrixWorld()
    }
    if (rimRef.current) {
      rimRef.current.position.copy(rimPos)
      rimRef.current.target.position.copy(target)
      rimRef.current.target.updateMatrixWorld()
    }
    if (pointRef.current) {
      pointRef.current.position.copy(pointPos)
    }
    if (headRef.current) {
      headRef.current.position.copy(headPos)
      headRef.current.target.position.copy(target)
      headRef.current.target.updateMatrixWorld()
    }
  })

  return (
    <>
      <ambientLight intensity={lighting.ambient} />
      <hemisphereLight args={['#ffffff', '#b7c2cf', renderMode === 'xray' ? Math.max(lighting.hemi, 1.05) : lighting.hemi]} />
      <directionalLight ref={keyRef} intensity={lighting.key} />
      <directionalLight ref={fillRef} intensity={lighting.fill} color="#dbeafe" />
      <directionalLight ref={rimRef} intensity={lighting.rim} color="#fff7ed" />
      <pointLight ref={pointRef} intensity={lighting.point} distance={Math.max((modelInfo?.boundingRadius || 120) * 12, 1400)} decay={2} color="#ffffff" />
      <spotLight
        ref={headRef}
        intensity={lighting.head}
        angle={0.7}
        penumbra={0.9}
        distance={Math.max((modelInfo?.boundingRadius || 120) * 16, 1800)}
        decay={1.4}
        color="#ffffff"
      />
    </>
  )
}

function SceneControls({ controlsRef }) {
  const { invalidate } = useThree()

  return <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.08} enablePan={false} onChange={invalidate} />
}

function HoleFocusController({ selectedHole, modelInfo, controlsRef }) {
  const { camera, invalidate } = useThree()

  useEffect(() => {
    if (!selectedHole || !modelInfo?.center || !controlsRef.current) return

    const target = new THREE.Vector3(
      selectedHole.position[0] - modelInfo.center.x,
      selectedHole.position[1] - modelInfo.center.y,
      selectedHole.position[2] - modelInfo.center.z,
    )
    const direction = new THREE.Vector3(...(selectedHole.axis || selectedHole.normal || [1, 0, 0])).normalize()
    const focusSize =
      selectedHole.diameter || Math.max(...parseHoleSize(selectedHole.size || selectedHole.label || '', 12)) || 12
    const distance = Math.max(focusSize * 6, modelInfo.boundingRadius * 0.14, 24)
    const cameraOffset = direction
      .multiplyScalar(distance)
      .add(new THREE.Vector3(distance * 0.25, distance * 0.12, distance * 0.22))

    camera.position.copy(target.clone().add(cameraOffset))
    controlsRef.current.target.copy(target)
    controlsRef.current.update()
    invalidate()
  }, [camera, controlsRef, invalidate, modelInfo, selectedHole])

  return null
}

function FoldFocusController({ selectedFold, modelInfo, controlsRef }) {
  const { camera, invalidate } = useThree()

  useEffect(() => {
    if (!selectedFold || !modelInfo?.center || !controlsRef.current) return

    const target = new THREE.Vector3(
      selectedFold.position[0] - modelInfo.center.x,
      selectedFold.position[1] - modelInfo.center.y,
      selectedFold.position[2] - modelInfo.center.z,
    )
    const axis = new THREE.Vector3(...(selectedFold.axis || [1, 0, 0])).normalize()
    const lateral = new THREE.Vector3(0, 0, 1).cross(axis)
    if (lateral.lengthSq() < 1e-6) lateral.set(0, 1, 0).cross(axis)
    lateral.normalize()

    const distance = Math.max((selectedFold.length || 0) * 0.9, modelInfo.boundingRadius * 0.18, 30)
    const cameraOffset = lateral
      .multiplyScalar(distance)
      .add(new THREE.Vector3(distance * 0.25, distance * 0.12, distance * 0.2))

    camera.position.copy(target.clone().add(cameraOffset))
    controlsRef.current.target.copy(target)
    controlsRef.current.update()
    invalidate()
  }, [camera, controlsRef, invalidate, modelInfo, selectedFold])

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

function roundedRectPoints(width, height, radius = 4, cornerSegments = 10) {
  const halfW = Math.max(width, 1) / 2
  const halfH = Math.max(height, 1) / 2
  const safeRadius = Math.max(Math.min(radius, halfW * 0.92, halfH * 0.92), 0.6)
  const corners = [
    { center: [halfW - safeRadius, halfH - safeRadius], start: 0, end: Math.PI / 2 },
    { center: [-halfW + safeRadius, halfH - safeRadius], start: Math.PI / 2, end: Math.PI },
    { center: [-halfW + safeRadius, -halfH + safeRadius], start: Math.PI, end: Math.PI * 1.5 },
    { center: [halfW - safeRadius, -halfH + safeRadius], start: Math.PI * 1.5, end: Math.PI * 2 },
  ]

  return corners.flatMap((corner, cornerIndex) => {
    const points = []
    for (let segmentIndex = 0; segmentIndex <= cornerSegments; segmentIndex += 1) {
      if (cornerIndex > 0 && segmentIndex === 0) continue
      const progress = segmentIndex / cornerSegments
      const angle = corner.start + (corner.end - corner.start) * progress
      points.push([corner.center[0] + Math.cos(angle) * safeRadius, corner.center[1] + Math.sin(angle) * safeRadius, 0])
    }
    return points
  })
}

function capsulePoints(length, width, arcSegments = 18) {
  const safeLength = Math.max(length, width, 2)
  const safeWidth = Math.max(width, 2)
  const radius = safeWidth / 2
  const straightHalf = Math.max(safeLength / 2 - radius, 0.5)
  const points = []

  for (let index = 0; index <= arcSegments; index += 1) {
    const angle = -Math.PI / 2 + (Math.PI * index) / arcSegments
    points.push([straightHalf + Math.cos(angle) * radius, Math.sin(angle) * radius, 0])
  }

  for (let index = 0; index <= arcSegments; index += 1) {
    const angle = Math.PI / 2 + (Math.PI * index) / arcSegments
    if (index === 0) continue
    points.push([-straightHalf + Math.cos(angle) * radius, Math.sin(angle) * radius, 0])
  }

  return points
}

function scalePoints(points, scaleX = 1, scaleY = 1) {
  return points.map(([x, y, z = 0]) => [x * scaleX, y * scaleY, z])
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
    ...positions[0],
    ...positions[1],
    ...positions[2],
    ...positions[3],
    ...positions[4],
    ...positions[5],
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
  const innerWidth = width - 2 * Math.max(thickness || 0, 0)
  const innerHeight = height - 2 * Math.max(thickness || 0, 0)
  if (innerWidth > 2 && innerHeight > 2) {
    contours.push(rectanglePoints(innerWidth, innerHeight))
  }
  return contours
}

function holePalette(hole, isSelected, hasSelection) {
  const dimmed = hasSelection && !isSelected
  const method = String(hole?.method || '').toLowerCase()

  if (hole.status === 'probe') {
    return {
      primary: isSelected ? '#ff8a1f' : '#d97706',
      secondary: isSelected ? '#ffd27a' : '#fdba74',
      echoOpacity: dimmed ? 0.18 : 0.68,
      primaryOpacity: dimmed ? 0.28 : 1,
      selectionOpacity: dimmed ? 0.2 : 0.92,
    }
  }

  if (isSelected) {
    return {
      primary: '#f5c542',
      secondary: '#fff0a8',
      echoOpacity: 0.78,
      primaryOpacity: 1,
      selectionOpacity: 1,
    }
  }

  if (hole.status === 'rejected') {
    return {
      primary: '#315b8a',
      secondary: '#7dd3fc',
      echoOpacity: dimmed ? 0.14 : 0.52,
      primaryOpacity: dimmed ? 0.22 : 0.92,
      selectionOpacity: dimmed ? 0.18 : 0.68,
    }
  }

  if (method.includes('face_boundary_missing')) {
    return {
      primary: '#b45309',
      secondary: '#f59e0b',
      echoOpacity: dimmed ? 0.16 : 0.56,
      primaryOpacity: dimmed ? 0.24 : 0.95,
      selectionOpacity: dimmed ? 0.2 : 0.72,
    }
  }

  // Accepted: differentiate cylindrical vs shaped/irregular
  const typeStr = String(hole?.type || '').toLowerCase()
  const isShaped = isIrregularHole(hole) || !typeStr.includes('cylindrical')
  if (isShaped) {
    return {
      primary: '#0a6e5c',
      secondary: '#2dd4bf',
      echoOpacity: dimmed ? 0.16 : 0.56,
      primaryOpacity: dimmed ? 0.24 : 0.95,
      selectionOpacity: dimmed ? 0.2 : 0.72,
    }
  }

  return {
    primary: '#7f0008',
    secondary: '#ff4d3b',
    echoOpacity: dimmed ? 0.16 : 0.56,
    primaryOpacity: dimmed ? 0.24 : 0.95,
    selectionOpacity: dimmed ? 0.2 : 0.72,
  }
}

function holeCenterPosition(hole, center) {
  return [hole.position[0] - center.x, hole.position[1] - center.y, hole.position[2] - center.z]
}

function holeFocusRadius(hole, modelInfo) {
  const [width, height] = parseHoleSize(hole.size || hole.label || '', 12)
  const featureSize = hole.diameter || Math.max(width, height) || 12
  return Math.max(featureSize * 0.7, modelInfo?.boundingRadius * 0.018 || 0, 6)
}

function getHoleContourPoints(hole, rectWidth, rectHeight) {
  if (hole.type === 'cylindrical') {
    const cylindricalRadius = Math.max((hole.diameter || 8) / 2, 3)
    return circlePoints(cylindricalRadius, 96)
  }

  const normalizedType = String(hole.type || '').toLowerCase()
  const major = Math.max(rectWidth, rectHeight, 6)
  const minor = Math.max(Math.min(rectWidth, rectHeight), 4)

  if (normalizedType.includes('slot')) {
    return capsulePoints(major, minor)
  }

  if (normalizedType.includes('rect (r)') || normalizedType.includes('(r)')) {
    return roundedRectPoints(major, minor, Math.min(minor * 0.28, 6))
  }

  if (normalizedType.includes('rect')) {
    return roundedRectPoints(major, minor, Math.min(minor * 0.18, 3.5))
  }

  return rectanglePoints(Math.max(rectWidth, 6), Math.max(rectHeight, 6))
}

function findClosestHoleByPoint(point, holes, center) {
  if (!holes?.length || !center) return null

  let bestHole = null
  let bestDistance = Infinity
  const clickedPoint = point instanceof THREE.Vector3 ? point : new THREE.Vector3(point.x, point.y, point.z)

  for (const hole of holes) {
    const position = holeCenterPosition(hole, center)
    const holePoint = new THREE.Vector3(...position)
    const distance = holePoint.distanceTo(clickedPoint)
    if (distance < bestDistance) {
      bestHole = hole
      bestDistance = distance
    }
  }

  if (!bestHole) return null

  return {
    hole: bestHole,
    distance: bestDistance,
  }
}

function pointToSegmentDistance(point, start, end) {
  const segment = end.clone().sub(start)
  const lengthSq = segment.lengthSq()
  if (lengthSq === 0) return point.distanceTo(start)
  const t = THREE.MathUtils.clamp(point.clone().sub(start).dot(segment) / lengthSq, 0, 1)
  const projection = start.clone().add(segment.multiplyScalar(t))
  return point.distanceTo(projection)
}

function buildProbeAxes(normalVector) {
  const fallback = Math.abs(normalVector.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0)
  const axisX = new THREE.Vector3().crossVectors(normalVector, fallback).normalize()
  const axisY = new THREE.Vector3().crossVectors(normalVector, axisX).normalize()
  return { axisX, axisY }
}

function inferProbeContour(point, normal, mesh, center, modelInfo) {
  const edgeBuffer = mesh?.display_edges
  if (!edgeBuffer?.length || !center) return null

  const clickedPoint = point instanceof THREE.Vector3 ? point : new THREE.Vector3(point.x, point.y, point.z)
  const normalVector =
    normal instanceof THREE.Vector3
      ? normal.clone().normalize()
      : new THREE.Vector3(...(normal || [0, 0, 1])).normalize()
  const searchRadius = Math.max(modelInfo?.boundingRadius * 0.032 || 0, 18)
  const planeTolerance = Math.max(searchRadius * 0.26, 2.5)
  const nearbyPoints = []
  let nearbySegments = 0

  for (let index = 0; index < edgeBuffer.length; index += 6) {
    const start = new THREE.Vector3(
      edgeBuffer[index] - center.x,
      edgeBuffer[index + 1] - center.y,
      edgeBuffer[index + 2] - center.z,
    )
    const end = new THREE.Vector3(
      edgeBuffer[index + 3] - center.x,
      edgeBuffer[index + 4] - center.y,
      edgeBuffer[index + 5] - center.z,
    )
    const mid = start.clone().add(end).multiplyScalar(0.5)
    const distanceToSegment = pointToSegmentDistance(clickedPoint, start, end)
    const planeDistance = Math.abs(mid.clone().sub(clickedPoint).dot(normalVector))

    if (distanceToSegment > searchRadius || planeDistance > planeTolerance) continue

    nearbyPoints.push(start, end)
    nearbySegments += 1
  }

  if (nearbyPoints.length < 10) return null

  const centroid = nearbyPoints
    .reduce((acc, current) => acc.add(current), new THREE.Vector3())
    .multiplyScalar(1 / nearbyPoints.length)
  if (centroid.distanceTo(clickedPoint) > searchRadius * 0.95) return null

  const { axisX, axisY } = buildProbeAxes(normalVector)
  const radii = nearbyPoints.map((entry) => entry.distanceTo(centroid))
  const meanRadius = radii.reduce((sum, value) => sum + value, 0) / radii.length
  const radiusVariance = radii.reduce((sum, value) => sum + (value - meanRadius) ** 2, 0) / radii.length
  const radiusStdDev = Math.sqrt(radiusVariance)

  const localPoints = nearbyPoints.map((entry) => {
    const offset = entry.clone().sub(centroid)
    return {
      x: offset.dot(axisX),
      y: offset.dot(axisY),
    }
  })
  const xs = localPoints.map((entry) => entry.x)
  const ys = localPoints.map((entry) => entry.y)
  const width = Math.max(...xs) - Math.min(...xs)
  const height = Math.max(...ys) - Math.min(...ys)
  const aspectRatio = Math.max(width, height) / Math.max(Math.min(width, height), 1)

  const absoluteCenter = [centroid.x + center.x, centroid.y + center.y, centroid.z + center.z]
  const normalArray = [normalVector.x, normalVector.y, normalVector.z]
  const baseDebug = {
    edge_point_count: nearbyPoints.length,
    edge_segment_count: nearbySegments,
    search_radius_mm: Number(searchRadius.toFixed(2)),
    plane_tolerance_mm: Number(planeTolerance.toFixed(2)),
    centroid_offset_mm: Number(centroid.distanceTo(clickedPoint).toFixed(2)),
    mean_radius_mm: Number(meanRadius.toFixed(2)),
    radius_std_dev_mm: Number(radiusStdDev.toFixed(2)),
    circularity_ratio: meanRadius > 0 ? Number((radiusStdDev / meanRadius).toFixed(3)) : null,
    width_mm: Number(width.toFixed(2)),
    height_mm: Number(height.toFixed(2)),
    aspect_ratio: Number(aspectRatio.toFixed(3)),
  }

  if (meanRadius > 2 && radiusStdDev / meanRadius < 0.28) {
    return {
      type: 'cylindrical',
      label: `Probe Ø${(meanRadius * 2).toFixed(1)} mm`,
      diameter: Number((meanRadius * 2).toFixed(2)),
      position: absoluteCenter,
      normal: normalArray,
      debug: {
        ...baseDebug,
        inferred_family: 'circular',
        confidence: Number(Math.max(0, 1 - (radiusStdDev / Math.max(meanRadius, 1)) * 2.2).toFixed(3)),
      },
    }
  }

  if (width > 4 && height > 4) {
    const major = Math.max(width, height)
    const minor = Math.min(width, height)
    return {
      type: aspectRatio > 1.45 ? 'slot' : 'rect (r)',
      label: `Probe ${major.toFixed(1)}x${minor.toFixed(1)} mm`,
      size: `${major.toFixed(1)}x${minor.toFixed(1)}`,
      position: absoluteCenter,
      normal: normalArray,
      debug: {
        ...baseDebug,
        inferred_family: aspectRatio > 1.45 ? 'slot_like' : 'rounded_rect_like',
        confidence: Number(
          Math.min(0.95, 0.52 + (Math.min(major, minor) / Math.max(major, minor)) * 0.3 + nearbySegments / 120).toFixed(
            3,
          ),
        ),
      },
    }
  }

  return null
}


function HoleOutline({ hole, center, isSelected, hasSelection, modelInfo, onSelect }) {
  const position = holeCenterPosition(hole, center)
  const explicitContourData = useMemo(() => {
    if (!Array.isArray(hole.contour_points) || hole.contour_points.length < 3) return null
    const normalized = hole.contour_points
      .filter((point) => Array.isArray(point) && point.length >= 3)
      .map((point) => [
        Number(point[0] || 0) - center.x,
        Number(point[1] || 0) - center.y,
        Number(point[2] || 0) - center.z,
      ])
    if (normalized.length < 3) return null
    const deduped = normalized.filter((point, index) => {
      if (index === normalized.length - 1) {
        const first = normalized[0]
        return Math.hypot(point[0] - first[0], point[1] - first[1], point[2] - first[2]) >= 0.25
      }
      return true
    })
    const contourCenter = averagePoint(deduped)
    if (!contourCenter) return null
    const normal = contourNormal(deduped, hole.normal || hole.axis || [0, 0, 1])
    const projected = projectPointsToPlane(deduped, contourCenter, normal)
    const closed = projected.length > 0 ? [...projected, projected[0]] : projected
    return {
      points: closed,
      center: [contourCenter.x, contourCenter.y, contourCenter.z],
      normal,
    }
  }, [center.x, center.y, center.z, hole.contour_points])
  const [rectWidth, rectHeight] = parseHoleSize(hole.size || hole.label, 14)
  const contourPoints = useMemo(() => getHoleContourPoints(hole, rectWidth, rectHeight), [hole, rectWidth, rectHeight])
  const primaryLoop = useMemo(() => toFloat32(contourPoints), [contourPoints])
  const highlightLoop = useMemo(() => {
    const scale = isSelected ? 1.08 : 1.035
    return toFloat32(scalePoints(contourPoints, scale, scale))
  }, [contourPoints, isSelected])
  const innerLoop = useMemo(() => {
    const scale = hole.type === 'cylindrical' ? 0.95 : 0.965
    return toFloat32(scalePoints(contourPoints, scale, scale))
  }, [contourPoints, hole.type])
  const palette = holePalette(hole, isSelected, hasSelection)
  const hitRadius = holeFocusRadius(hole, modelInfo)
  const handleSelect = useCallback(
    (event) => {
      event.stopPropagation()
      onSelect?.(hole.id)
    },
    [hole.id, onSelect],
  )

  const explicitCenter = explicitContourData?.center || [position[0], position[1], position[2]]

  if (explicitContourData) {
    const normal = explicitContourData.normal
    const contourBase = toFloat32(
      explicitContourData.points.map(([x, y, z]) => [x + normal.x * 0.06, y + normal.y * 0.06, z + normal.z * 0.06]),
    )
    const contourHighlight = toFloat32(
      explicitContourData.points.map(([x, y, z]) => [x + normal.x * 0.2, y + normal.y * 0.2, z + normal.z * 0.2]),
    )
    const contourInner = toFloat32(
      explicitContourData.points.map(([x, y, z]) => [x - normal.x * 0.08, y - normal.y * 0.08, z - normal.z * 0.08]),
    )
    return (
      <group renderOrder={20} onClick={handleSelect}>
        <lineLoop>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[contourHighlight, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.secondary}
            transparent
            opacity={palette.echoOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <lineLoop>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[contourBase, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.primary}
            transparent
            opacity={palette.primaryOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <lineLoop>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[contourInner, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.secondary}
            transparent
            opacity={palette.selectionOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <mesh position={explicitCenter}>
          <sphereGeometry args={[hitRadius, 18, 18]} />
          <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
        {isSelected && (
          <mesh position={explicitCenter}>
            <sphereGeometry args={[Math.max(hitRadius * 0.55, 5.5), 18, 18]} />
            <meshBasicMaterial
              color={palette.secondary}
              transparent
              opacity={0.14}
              blending={THREE.AdditiveBlending}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>
        )}
      </group>
    )
  }

  if (hole.type === 'cylindrical') {
    const quaternion = quaternionFromDirection(hole.axis || [1, 0, 0])
    return (
      <group position={position} quaternion={quaternion} renderOrder={20} onClick={handleSelect}>
        <lineLoop position={[0, 0, -0.26]}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[highlightLoop, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.secondary}
            transparent
            opacity={palette.echoOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <lineLoop>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[primaryLoop, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.primary}
            transparent
            opacity={palette.primaryOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <lineLoop position={[0, 0, 0.22]}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[innerLoop, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={palette.secondary}
            transparent
            opacity={palette.selectionOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
        <mesh>
          <circleGeometry args={[hitRadius, 40]} />
          <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
        {isSelected && (
          <mesh position={[0, 0, 0.12]}>
            <circleGeometry args={[hitRadius * 1.26, 52]} />
            <meshBasicMaterial
              color={palette.secondary}
              transparent
              opacity={0.18}
              blending={THREE.AdditiveBlending}
              depthTest={false}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </mesh>
        )}
      </group>
    )
  }

  const quaternion = quaternionFromDirection(hole.normal || [1, 0, 0])
  return (
    <group position={position} quaternion={quaternion} renderOrder={20} onClick={handleSelect}>
      <lineLoop position={[0, 0, -0.26]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[highlightLoop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial
          color={palette.secondary}
          transparent
          opacity={palette.echoOpacity}
          depthTest={false}
          depthWrite={false}
        />
      </lineLoop>
      <lineLoop>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[primaryLoop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial
          color={palette.primary}
          transparent
          opacity={palette.primaryOpacity}
          depthTest={false}
          depthWrite={false}
        />
      </lineLoop>
      <lineLoop position={[0, 0, 0.22]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[innerLoop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial
          color={palette.secondary}
          transparent
          opacity={palette.selectionOpacity}
          depthTest={false}
          depthWrite={false}
        />
      </lineLoop>
      <mesh>
        <planeGeometry args={[Math.max(rectWidth, hitRadius * 2), Math.max(rectHeight, hitRadius * 2)]} />
        <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      {isSelected && (
        <mesh position={[0, 0, 0.1]}>
          <planeGeometry args={[Math.max(rectWidth, hitRadius * 2) * 1.15, Math.max(rectHeight, hitRadius * 2) * 1.15]} />
          <meshBasicMaterial
            color={palette.secondary}
            transparent
            opacity={0.14}
            blending={THREE.AdditiveBlending}
            depthTest={false}
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  )
}

function HiddenHoleBeacon({ hole, center, modelInfo, onSelect, isSelected = false }) {
  if (!Array.isArray(hole?.position) || hole.position.length < 3) return null
  const position = holeCenterPosition(hole, center)
  if (!position) return null
  const quaternion = quaternionFromDirection(hole.normal || hole.axis || [0, 0, 1])
  const baseRadius = Math.max(holeFocusRadius(hole, modelInfo) * 0.62, 4)
  const crossSegments = useMemo(
    () =>
      new Float32Array([
        -baseRadius,
        0,
        0,
        baseRadius,
        0,
        0,
        0,
        -baseRadius,
        0,
        0,
        baseRadius,
        0,
        -baseRadius * 0.72,
        -baseRadius * 0.72,
        0,
        baseRadius * 0.72,
        baseRadius * 0.72,
        0,
        -baseRadius * 0.72,
        baseRadius * 0.72,
        0,
        baseRadius * 0.72,
        -baseRadius * 0.72,
        0,
      ]),
    [baseRadius],
  )
  const ringSegments = useMemo(() => toFloat32(circlePoints(baseRadius * 1.15, 56)), [baseRadius])
  const statusColor = isIrregularHole(hole) ? '#d97706' : '#1d4ed8'
  const color = isSelected ? '#f5c542' : statusColor
  const handleSelect = useCallback(
    (event) => {
      event.stopPropagation()
      onSelect?.(hole.id)
    },
    [hole.id, onSelect],
  )

  return (
    <group position={position} quaternion={quaternion} renderOrder={24} onClick={handleSelect}>
      <lineSegments position={[0, 0, 0.5]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[crossSegments, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={0.95} depthTest={false} depthWrite={false} />
      </lineSegments>
      <lineLoop position={[0, 0, 0.5]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[ringSegments, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={0.55} depthTest={false} depthWrite={false} />
      </lineLoop>
      <mesh>
        <circleGeometry args={[baseRadius * 1.4, 42]} />
        <meshBasicMaterial transparent opacity={0.01} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function ManualProbeOverlay({ probe, center, modelInfo }) {
  const inferredHole = probe?.inferredContour || null
  const baseHole = inferredHole
    ? {
        ...inferredHole,
        status: 'probe',
        axis: inferredHole.normal || probe.normal,
      }
    : null

  if (baseHole) {
    return <HoleOutline hole={baseHole} center={center} isSelected hasSelection modelInfo={modelInfo} />
  }

  const radius = Math.max(modelInfo?.boundingRadius * 0.018 || 0, 6)
  const position = holeCenterPosition(probe, center)
  const quaternion = quaternionFromDirection(probe.normal || [0, 0, 1])
  const loop = useMemo(() => toFloat32(circlePoints(radius, 72)), [radius])

  return (
    <group position={position} quaternion={quaternion} renderOrder={22}>
      <lineLoop>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[loop, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color="#f5c542" transparent opacity={1} depthTest={false} depthWrite={false} />
      </lineLoop>
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
      <lineBasicMaterial color={color} transparent opacity={1} depthTest={false} depthWrite={false} />
    </lineLoop>
  )
}

// Renders a cross-section polygon using exact 3D world-space coordinates from the backend.
// polygonLines is an array of rings, each ring is an array of [x,y,z] world-space points.
function PolygonOutline3D({ polygonLines, color, isEndMarker = false }) {
  const rings = useMemo(
    () =>
      polygonLines.map((ring) => {
        const closed = [...ring, ring[0]]
        return new Float32Array(closed.flatMap((p) => p))
      }),
    [polygonLines],
  )

  return (
    <group renderOrder={15}>
      {rings.map((pts, i) => (
        <lineLoop key={i} renderOrder={15}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[pts, 3]} />
          </bufferGeometry>
          <lineBasicMaterial
            color={color}
            transparent
            opacity={isEndMarker ? 1 : 0.72}
            linewidth={isEndMarker ? 2 : 1}
            depthTest={false}
            depthWrite={false}
          />
        </lineLoop>
      ))}
      <mesh>
        <circleGeometry args={[2.4, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.98} depthTest={false} depthWrite={false} />
      </mesh>
    </group>
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
        <meshBasicMaterial color={color} transparent opacity={0.98} depthTest={false} depthWrite={false} />
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
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 0],
    [4, 5],
    [5, 6],
    [6, 7],
    [7, 4],
    [0, 4],
    [1, 5],
    [2, 6],
    [3, 7],
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
      return [
        [-extent.x, anchor.y, anchor.z],
        [extent.x, anchor.y, anchor.z],
      ]
    }
    if (axis.key === 'y') {
      return [
        [anchor.x, -extent.y, anchor.z],
        [anchor.x, extent.y, anchor.z],
      ]
    }
    return [
      [anchor.x, anchor.y, -extent.z],
      [anchor.x, anchor.y, extent.z],
    ]
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
      <DimensionGuide
        start={longEndpoints[0]}
        end={longEndpoints[1]}
        color="#f59e0b"
        capAxis={capAxisFor(longAxis.key)}
      />
      <DimensionGuide
        start={middleEndpoints[0]}
        end={middleEndpoints[1]}
        color="#fb7185"
        capAxis={capAxisFor(middleAxis.key)}
      />
      <DimensionGuide
        start={shortEndpoints[0]}
        end={shortEndpoints[1]}
        color="#facc15"
        capAxis={capAxisFor(shortAxis.key)}
      />
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

function BendLineOverlay({ bend, center, isSelected, onSelect }) {
  const position = [bend.position[0] - center.x, bend.position[1] - center.y, bend.position[2] - center.z]
  const axis = new THREE.Vector3(...(bend.axis || [1, 0, 0])).normalize()
  const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis)
  const color = isSelected
    ? '#f59e0b'
    : bend.direction === 'up'
      ? '#10b981'
      : bend.direction === 'down'
        ? '#ef4444'
        : '#8f0008'

  return (
    <group position={position} quaternion={quaternion} renderOrder={22}>
      {isSelected && (
        <mesh>
          <cylinderGeometry args={[2.9, 2.9, Math.max(Number(bend.length) || 0, 10) + 6, 24]} />
          <meshBasicMaterial
            color="#ffd87a"
            transparent
            opacity={0.16}
            blending={THREE.AdditiveBlending}
            depthTest={false}
            depthWrite={false}
          />
        </mesh>
      )}
      <mesh
        onClick={(event) => {
          event.stopPropagation()
          onSelect?.(bend.id)
        }}
      >
        <cylinderGeometry
          args={[isSelected ? 1.4 : 0.95, isSelected ? 1.4 : 0.95, Math.max(Number(bend.length) || 0, 10), 16]}
        />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={isSelected ? 1 : 0.88}
          depthTest={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function UnfoldFoldOverlay({ unfoldVisuals, modelInfo, selectedFoldId, onFoldSelect, drawPlate = false }) {
  const length = Math.max(Number(unfoldVisuals?.flat_length) || 0, 40)
  const width = Math.max(Number(unfoldVisuals?.flat_width) || 0, 20)
  const bends = unfoldVisuals?.bends_logical || []
  const foldDetails = unfoldVisuals?.fold_details || []
  const bendSegments = unfoldVisuals?.bend_line_segments || []
  const foldCount = Math.max(unfoldVisuals?.fold_lines || 0, bends.length, foldDetails.length)

  const foldRows = useMemo(() => {
    if (bendSegments.length <= 0 && foldCount <= 0) return []
    const size = modelInfo?.size || {}
    const rankedAxes = [
      { key: 'x', size: Number(size.x) || 0, index: 0 },
      { key: 'y', size: Number(size.y) || 0, index: 1 },
      { key: 'z', size: Number(size.z) || 0, index: 2 },
    ].sort((a, b) => b.size - a.size)

    const thicknessAxis = rankedAxes[2]?.key || 'z'
    const inPlaneAxes = [rankedAxes[0]?.key || 'x', rankedAxes[1]?.key || 'y']
    const primaryAxis = inPlaneAxes[0]
    const secondaryAxis = inPlaneAxes[1] || inPlaneAxes[0]
    const primarySize = rankedAxes[0]?.size || length
    const secondarySize = rankedAxes[1]?.size || width
    const normalVector = axisVectorForKey(thicknessAxis)
    const epsilon = Math.max((rankedAxes[2]?.size || 0) * 0.6, 0.2)

    let segmentRows
    if (foldDetails.length > 0) {
      segmentRows = foldDetails.map((detail, idx) => {
        const logicalId = normalizeFoldId(detail.id || null)
        const matchingLogical =
          bends.find((bend) => normalizeFoldId(bend.id) === logicalId) || {}
        return { detail, logical: matchingLogical, segment: null, idx }
      })
    } else if (bendSegments.length > 0) {
      segmentRows = bendSegments.map((segment, idx) => {
        const matchingDetail =
          foldDetails.find((detail) => (detail.segment_indices || []).includes((Number(segment.index) || idx) + 1)) || {}
        const logicalId = normalizeFoldId(matchingDetail.id || null)
        const matchingLogical =
          bends.find((bend) => normalizeFoldId(bend.id) === logicalId) || {}
        return { detail: matchingDetail, logical: matchingLogical, segment, idx }
      })
    } else {
      segmentRows = Array.from({ length: foldCount }, (_, idx) => ({
        detail: foldDetails[idx] || {},
        logical: bends[idx] || {},
        segment: bendSegments[idx] || {},
        idx,
      }))
    }

    return segmentRows.map(({ detail, logical, segment, idx }) => {
      const id = detail?.id != null
        ? normalizeFoldId(detail.id)
        : segment
          ? getFoldSegmentId(segment, idx)
          : normalizeFoldId(logical.id || idx + 1)
      const detailCenter =
        Array.isArray(segment?.center) && segment.center.length >= 3
          ? segment.center
        : Array.isArray(detail.center) && detail.center.length >= 3
            ? detail.center
            : [0, 0, 0]
      const segmentAxis = String(segment?.axis || detail.axis || '').toLowerCase()
      const lineAxis = inPlaneAxes.includes(segmentAxis) ? segmentAxis : inPlaneAxes[0]
      const varyingAxis = inPlaneAxes.find((axisKey) => axisKey !== lineAxis) || inPlaneAxes[1] || inPlaneAxes[0]
      const lineVector = axisVectorForKey(lineAxis)
      const varyingVector = axisVectorForKey(varyingAxis)
      const basis = new THREE.Matrix4().makeBasis(lineVector, varyingVector, normalVector)
      const quaternion = new THREE.Quaternion().setFromRotationMatrix(basis)
      const localStart = toLocalPoint(segment?.start || detail.start, modelInfo?.center, normalVector, epsilon)
      const localEnd = toLocalPoint(segment?.end || detail.end, modelInfo?.center, normalVector, epsilon)
      const requestedLength =
        Number(segment?.length || detail.length || logical.length) || Math.max(Math.min(length, width) * 0.9, 10)
      const shouldPreferPrimaryAxis = requestedLength > secondarySize * 1.35 && primarySize > secondarySize * 1.2
      const fallbackAxis = shouldPreferPrimaryAxis ? primaryAxis : lineAxis
      const fallbackQuaternion = new THREE.Quaternion().setFromUnitVectors(
        new THREE.Vector3(1, 0, 0),
        axisVectorForKey(fallbackAxis),
      )
      const position = modelInfo?.center
        ? [
            Number(detailCenter[0] || 0) - modelInfo.center.x + normalVector.x * epsilon,
            Number(detailCenter[1] || 0) - modelInfo.center.y + normalVector.y * epsilon,
            Number(detailCenter[2] || 0) - modelInfo.center.z + normalVector.z * epsilon,
          ]
        : [0, 0, 0]
      return {
        id,
        position,
        quaternion,
        fallbackQuaternion,
        forceFallback: shouldPreferPrimaryAxis,
        localStart,
        localEnd,
        lineLength: requestedLength,
        angle: logical.angle ?? null,
        direction: logical.type || null,
        segmentIndex: Number.isFinite(Number(segment?.index)) ? Number(segment.index) + 1 : idx + 1,
        logicalFoldId: normalizeFoldId(detail.id || logical.id || null),
      }
    })
  }, [bendSegments, bends, foldCount, foldDetails, length, modelInfo, width])

  return (
    <group renderOrder={25}>
      {drawPlate && (
        <>
          <mesh>
            <planeGeometry args={[length, width]} />
            <meshBasicMaterial
              color="#eef4fb"
              transparent
              opacity={0.95}
              side={THREE.DoubleSide}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>

          <lineLoop renderOrder={26}>
            <bufferGeometry>
              <bufferAttribute
                attach="attributes-position"
                args={[
                  new Float32Array([
                    -length / 2,
                    -width / 2,
                    0.2,
                    length / 2,
                    -width / 2,
                    0.2,
                    length / 2,
                    width / 2,
                    0.2,
                    -length / 2,
                    width / 2,
                    0.2,
                  ]),
                  3,
                ]}
              />
            </bufferGeometry>
            <lineBasicMaterial color="#6b7280" transparent opacity={0.9} depthTest={false} depthWrite={false} />
          </lineLoop>
        </>
      )}

      {foldRows.map((row) => {
        const selected = normalizeFoldId(selectedFoldId) === row.id
        const color = selected
          ? '#f59e0b'
          : row.direction === 'up'
            ? '#10b981'
            : row.direction === 'down'
              ? '#ef4444'
              : '#8f0008'
        const segmentVector = row.localStart && row.localEnd ? row.localEnd.clone().sub(row.localStart) : null
        const exactLength = segmentVector?.length?.() || 0
        const exactMidpoint = segmentVector ? row.localStart.clone().add(row.localEnd).multiplyScalar(0.5) : null
        const exactQuaternion =
          segmentVector && exactLength > 1e-6
            ? new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), segmentVector.clone().normalize())
            : null
        const useExactSegment = !row.forceFallback && exactQuaternion && exactLength > 1e-6

        return (
          <group
            key={`flat-fold-${row.id}`}
            position={useExactSegment ? [exactMidpoint.x, exactMidpoint.y, exactMidpoint.z] : row.position}
            quaternion={useExactSegment ? exactQuaternion : row.fallbackQuaternion || row.quaternion}
            onClick={(event) => {
              event.stopPropagation()
              onFoldSelect?.(row.id)
            }}
          >
            {selected && (
              <mesh position={[0, 0, 0.08]}>
                <planeGeometry args={[(useExactSegment ? exactLength : row.lineLength) + 14, 13]} />
                <meshBasicMaterial
                  color="#ffe08a"
                  transparent
                  opacity={0.18}
                  side={THREE.DoubleSide}
                  blending={THREE.AdditiveBlending}
                  depthTest={false}
                  depthWrite={false}
                />
              </mesh>
            )}
            <mesh>
              <planeGeometry args={[useExactSegment ? exactLength : row.lineLength, selected ? 8 : 5]} />
              <meshBasicMaterial
                color={color}
                transparent
                opacity={selected ? 1 : 0.86}
                side={THREE.DoubleSide}
                depthTest={false}
                depthWrite={false}
              />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

function StageOverlays({
  modelInfo,
  visuals,
  holeVisuals,
  focusedStage,
  selectedHole,
  selectedProbe,
  selectedFoldId,
  onFoldSelect,
  onHoleSelect,
  useFlatView,
  showHiddenHoles,
  highlightHiddenHoleLocations,
}) {
  const center = modelInfo?.center
  if (!center || !visuals || !focusedStage) return null

  const isHoleStage = focusedStage === MERGED_HOLES_STAGE || isPreUnfoldStageName(focusedStage)
  const holeItems = holeVisuals?.items || []
  const visibleHoleVisuals = showHiddenHoles ? holeItems : holeItems.filter((hole) => !isHiddenHoleCandidate(hole))
  const hiddenHoleVisuals = holeItems.filter(
    (hole) =>
      isHiddenHoleCandidate(hole) &&
      Array.isArray(hole?.position) &&
      hole.position.length >= 3 &&
      hole.position.every((value) => Number.isFinite(Number(value))),
  )
  const routerVisuals = visuals?.router || null
  const classificationVisuals = visuals?.classification || null
  const unfoldVisuals = visuals?.unfold || null
  const size = modelInfo?.size
  const bend3dItems = unfoldVisuals?.bends_3d || []

  const makePosition = (position) => [position[0] - center.x, position[1] - center.y, position[2] - center.z]

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

  // Build router sections — prefer exact polygon coords from backend when available
  const routerSections = (routerVisuals?.sampled_sections || []).map((section) => {
    const hasPolygon = Array.isArray(section.polygon_exterior) && section.polygon_exterior.length > 0
    let polygonLines3d = null
    if (hasPolygon) {
      const [ox, oy, oz] = section.origin_3d
      const [bux, buy, buz] = section.basis_u
      const [bvx, bvy, bvz] = section.basis_v
      const to3d = ([px, py]) => [
        ox + bux * px + bvx * py - center.x,
        oy + buy * px + bvy * py - center.y,
        oz + buz * px + bvz * py - center.z,
      ]
      polygonLines3d = [
        section.polygon_exterior.map(to3d),
        ...(section.polygon_interiors || []).map((ring) => ring.map(to3d)),
      ]
    }
    return {
      position: makePosition(section.origin_3d),
      quaternion: planeQuaternion,
      isStart: section.is_start === true,
      isEnd: section.is_end === true,
      polygonLines3d,
    }
  })
  const fallbackSections = buildFallbackSections(modelInfo).map((position) => ({
    position,
    quaternion: fallbackQuaternion,
  }))
  const sectionVisuals = routerSections.length > 0 ? routerSections : fallbackSections

  return (
    <group>
      {isHoleStage &&
        visibleHoleVisuals.map((hole, index) => (
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

      {isHoleStage &&
        highlightHiddenHoleLocations &&
        hiddenHoleVisuals.map((hole, index) => (
          <HiddenHoleBeacon
            key={`hidden-hole-${hole.id || index}`}
            hole={hole}
            center={center}
            modelInfo={modelInfo}
            isSelected={selectedHole?.id === hole.id}
            onSelect={onHoleSelect}
          />
        ))}

      {isHoleStage && selectedProbe && (
        <ManualProbeOverlay probe={selectedProbe} center={center} modelInfo={modelInfo} />
      )}

      {focusedStage === MERGED_HOLES_STAGE &&
        !useFlatView &&
        bend3dItems.map((bend) => (
          <BendLineOverlay
            key={`bend-line-${bend.id}`}
            bend={bend}
            center={center}
            isSelected={normalizeFoldId(selectedFoldId) === normalizeFoldId(bend.id)}
            onSelect={onFoldSelect}
          />
        ))}

      {focusedStage === 'Profile Router' &&
        sectionVisuals.map((section, index) =>
          section.polygonLines3d ? (
            <PolygonOutline3D
              key={`router-section-${index}`}
              polygonLines={section.polygonLines3d}
              color={section.isStart || section.isEnd ? '#ff6b35' : '#8f0008'}
              isEndMarker={section.isStart || section.isEnd}
            />
          ) : (
            <SectionContours
              key={`router-section-${index}`}
              position={section.position}
              quaternion={section.quaternion}
              contours={contours}
              color="#8f0008"
            />
          ),
        )}

      {focusedStage === 'Classify geometry' &&
        sectionVisuals.map((section, index) =>
          section.polygonLines3d ? (
            <PolygonOutline3D
              key={`classify-section-${index}`}
              polygonLines={section.polygonLines3d}
              color={section.isStart || section.isEnd ? '#ff6b35' : '#6f0010'}
              isEndMarker={section.isStart || section.isEnd}
            />
          ) : (
            <SectionContours
              key={`classify-section-${index}`}
              position={section.position}
              quaternion={section.quaternion}
              contours={contours}
              color="#6f0010"
            />
          ),
        )}

      {focusedStage === 'Classify geometry' && (
        <ClassificationGuides modelInfo={modelInfo} classificationVisuals={classificationVisuals} />
      )}
    </group>
  )
}

export default function ViewerCanvas({
  fileBuffer,
  activeMesh,
  onLoaded,
  onError,
  onStatus,
  onDebug,
  parseMode,
  modelInfo,
  backendVisuals,
  activeHoleVisuals,
  focusedStage,
  selectedHole,
  selectedFoldId,
  onFoldSelect,
  onHoleSelect,
  onSurfaceProbe,
  selectedProbe,
  probeMode = false,
  controlsRef,
  useFlatView,
  showHiddenHoles = false,
  highlightHiddenHoleLocations = false,
  materialPreset = 'technical_steel',
  renderMode = 'studio',
  lightMode = 'bright',
}) {
  const holeItems = activeHoleVisuals?.items || backendVisuals?.holes?.items || []
  const visibleHoleItems = showHiddenHoles ? holeItems : holeItems.filter((hole) => !isHiddenHoleCandidate(hole))
  const bend3dItems = backendVisuals?.unfold?.bends_3d || []
  const normalizedSelectedFoldId = normalizeFoldId(selectedFoldId)
  const selectedFold = useFlatView
    ? null
    : bend3dItems.find((bend) => normalizeFoldId(bend.id) === normalizedSelectedFoldId) || null
  const handleSurfacePick = useCallback(
    (sample, event) => {
      if (!probeMode) return
      const point = sample?.point || sample
      if (!modelInfo?.center || !point) return
      event?.stopPropagation?.()
      const closest = findClosestHoleByPoint(point, visibleHoleItems, modelInfo.center)
      const inferredContour = inferProbeContour(point, sample?.normal, activeMesh, modelInfo.center, modelInfo)
      onSurfaceProbe?.({
        point,
        normal: sample?.normal || null,
        nearestHole: closest?.hole || null,
        nearestHoleDistance: closest?.distance || null,
        inferredContour,
      })
    },
    [activeMesh, modelInfo, onSurfaceProbe, probeMode, visibleHoleItems],
  )

  return (
    <Canvas
      frameloop="demand"
      performance={{ min: 0.5 }}
      camera={{ position: [150, 100, 150], fov: 40, near: 0.1, far: 10000 }}
      dpr={[1, 1.25]}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      style={{ background: renderMode === 'analysis' ? '#eef2f7' : '#e8eef5' }}
    >
      <StudioEnvironment renderMode={renderMode} />
      <CameraRigLights modelInfo={modelInfo} lightMode={lightMode} renderMode={renderMode} />

      <StepModel
        buffer={fileBuffer}
        mesh={activeMesh}
        onLoaded={onLoaded}
        onError={onError}
        onStatus={onStatus}
        onDebug={onDebug}
        onSurfacePick={handleSurfacePick}
        parseMode={parseMode}
        renderMode={renderMode}
        materialPreset={materialPreset}
      />

      {useFlatView && focusedStage === MERGED_HOLES_STAGE && backendVisuals?.unfold?.success && (
        <UnfoldFoldOverlay
          unfoldVisuals={backendVisuals.unfold}
          modelInfo={modelInfo || null}
          selectedFoldId={selectedFoldId}
          onFoldSelect={onFoldSelect}
          drawPlate={false}
        />
      )}

      <CameraFitter modelInfo={modelInfo} controlsRef={controlsRef} />
      <HoleFocusController selectedHole={selectedHole} modelInfo={modelInfo} controlsRef={controlsRef} />
      <FoldFocusController selectedFold={selectedFold} modelInfo={modelInfo} controlsRef={controlsRef} />
      <StageOverlays
        modelInfo={modelInfo}
        visuals={backendVisuals}
        holeVisuals={activeHoleVisuals || backendVisuals?.holes || null}
        focusedStage={focusedStage}
        selectedHole={selectedHole}
        selectedProbe={selectedProbe}
        selectedFoldId={selectedFoldId}
        onFoldSelect={onFoldSelect}
        onHoleSelect={onHoleSelect}
        useFlatView={useFlatView}
        showHiddenHoles={showHiddenHoles}
        highlightHiddenHoleLocations={highlightHiddenHoleLocations}
      />
      {!useFlatView && renderMode !== 'studio' && <gridHelper args={[500, 18, '#d4d9e1', '#edf1f5']} />}
      <SceneControls controlsRef={controlsRef} />
    </Canvas>
  )
}
