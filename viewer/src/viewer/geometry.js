import * as THREE from 'three'

export function axisVectorForKey(key) {
  if (key === 'x') return new THREE.Vector3(1, 0, 0)
  if (key === 'y') return new THREE.Vector3(0, 1, 0)
  return new THREE.Vector3(0, 0, 1)
}

export function toLocalPoint(point, center, normalVector, epsilon) {
  if (!Array.isArray(point) || point.length < 3 || !center) return null
  return new THREE.Vector3(
    Number(point[0] || 0) - center.x + normalVector.x * epsilon,
    Number(point[1] || 0) - center.y + normalVector.y * epsilon,
    Number(point[2] || 0) - center.z + normalVector.z * epsilon,
  )
}

export function longestAxisInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => b.value - a.value)
  return entries[0]
}

export function orderedAxesInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => b.value - a.value)
  return entries
}

export function parseHoleSize(value, fallback = 12) {
  if (!value) return [fallback, fallback]
  const match = String(value).match(/(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)/i)
  if (!match) return [fallback, fallback]
  return [Number(match[1]), Number(match[2])]
}

export function quaternionFromDirection(direction) {
  const normal = new THREE.Vector3(...direction).normalize()
  return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
}

export function crossSectionDimensions(size, axisKey) {
  if (!size) return [20, 20]
  if (axisKey === 'x') return [size.y || 20, size.z || 20]
  if (axisKey === 'y') return [size.x || 20, size.z || 20]
  return [size.x || 20, size.y || 20]
}

export function rectanglePoints(width, height) {
  const halfW = Math.max(width, 1) / 2
  const halfH = Math.max(height, 1) / 2
  return [
    [-halfW, -halfH, 0],
    [halfW, -halfH, 0],
    [halfW, halfH, 0],
    [-halfW, halfH, 0],
  ]
}

export function roundedRectPoints(width, height, radius = 4, cornerSegments = 10) {
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

export function capsulePoints(length, width, arcSegments = 18) {
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

export function scalePoints(points, scaleX = 1, scaleY = 1) {
  return points.map(([x, y, z = 0]) => [x * scaleX, y * scaleY, z])
}

export function toFloat32(points) {
  return new Float32Array(points.flat())
}

export function buildLineSegments(points) {
  const segments = []
  for (let index = 0; index < points.length - 1; index += 1) {
    segments.push(points[index], points[index + 1])
  }
  return toFloat32(segments)
}

export function buildDimensionLine(start, end, capSize = 6, capAxis = 'y') {
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

export function circlePoints(radius, segments = 64) {
  const safeRadius = Math.max(radius, 1)
  return Array.from({ length: segments }, (_, index) => {
    const angle = (index / segments) * Math.PI * 2
    return [Math.cos(angle) * safeRadius, Math.sin(angle) * safeRadius, 0]
  })
}

export function buildSectionContours(partType, size, thickness, axisKey) {
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

export function buildFallbackSections(modelInfo) {
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

export function buildProbeAxes(normalVector) {
  const fallback = Math.abs(normalVector.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0)
  const axisX = new THREE.Vector3().crossVectors(normalVector, fallback).normalize()
  const axisY = new THREE.Vector3().crossVectors(normalVector, axisX).normalize()
  return { axisX, axisY }
}

export function pointToSegmentDistance(point, start, end) {
  const segment = end.clone().sub(start)
  const lengthSq = segment.lengthSq()
  if (lengthSq === 0) return point.distanceTo(start)
  const t = THREE.MathUtils.clamp(point.clone().sub(start).dot(segment) / lengthSq, 0, 1)
  const projection = start.clone().add(segment.multiplyScalar(t))
  return point.distanceTo(projection)
}

export function holePalette(hole, isSelected, hasSelection) {
  const dimmed = hasSelection && !isSelected

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

  return {
    primary: '#7f0008',
    secondary: '#ff4d3b',
    echoOpacity: dimmed ? 0.16 : 0.56,
    primaryOpacity: dimmed ? 0.24 : 0.95,
    selectionOpacity: dimmed ? 0.2 : 0.72,
  }
}

export function holeCenterPosition(hole, center) {
  return [hole.position[0] - center.x, hole.position[1] - center.y, hole.position[2] - center.z]
}

export function holeFocusRadius(hole, modelInfo) {
  const [width, height] = parseHoleSize(hole.size || hole.label || '', 12)
  const featureSize = hole.diameter || Math.max(width, height) || 12
  return Math.max(featureSize * 0.7, modelInfo?.boundingRadius * 0.018 || 0, 6)
}

export function getHoleContourPoints(hole, rectWidth, rectHeight) {
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

export function findClosestHoleByPoint(point, holes, center) {
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

export function inferProbeContour(point, normal, mesh, center, modelInfo) {
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
