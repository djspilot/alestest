/**
 * Shared hole/fold utility functions.
 * Previously duplicated across App.jsx, ViewerCanvas.jsx, and StageDetailsPanel.jsx.
 */

export function normalizeFoldId(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : String(value)
}

export function getFoldSegmentId(segment, fallbackIndex = 0) {
  const rawIndex = Number(segment?.index)
  const segmentIndex = Number.isFinite(rawIndex) ? rawIndex + 1 : fallbackIndex + 1
  return `segment-${segmentIndex}`
}

function getSegmentIndex(segment, fallbackIndex = 0) {
  const rawIndex = Number(segment?.index)
  return Number.isFinite(rawIndex) ? rawIndex : fallbackIndex
}

function buildPointFromSegment(segment, useMax = false) {
  if (!segment) return null
  const center = Array.isArray(segment.center) && segment.center.length >= 3 ? segment.center : [0, 0, 0]
  const axis = String(segment.axis || '').toUpperCase()
  const span = Array.isArray(segment.axis_span) && segment.axis_span.length >= 2 ? segment.axis_span : null
  if (!span) return null
  const fixedX = Number(center[0]) || 0
  const fixedY = Number(center[1]) || 0
  const fixedZ = Number(center[2]) || 0
  const spanValue = useMax ? Math.max(Number(span[0]) || 0, Number(span[1]) || 0) : Math.min(Number(span[0]) || 0, Number(span[1]) || 0)
  if (axis === 'X') return [spanValue, fixedY, fixedZ]
  if (axis === 'Y') return [fixedX, spanValue, fixedZ]
  return null
}

function buildFoldDetailFromGroup(group, segments, index) {
  const memberIndexes = (group?.segment_indices || [])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
  const members = memberIndexes
    .map((segmentIndex) => segments.find((segment, idx) => getSegmentIndex(segment, idx) === segmentIndex))
    .filter(Boolean)
  if (members.length === 0) return null

  const first = members[0]
  const axis = String(group?.axis || first?.axis || '').toLowerCase() || 'y'
  const starts = members.map((segment) => segment.start || buildPointFromSegment(segment, false)).filter(Boolean)
  const ends = members.map((segment) => segment.end || buildPointFromSegment(segment, true)).filter(Boolean)
  const allPoints = [...starts, ...ends]
  if (allPoints.length === 0) return null

  let start = allPoints[0]
  let end = allPoints[allPoints.length - 1]
  if (axis === 'x') {
    const xs = allPoints.map((point) => Number(point[0]) || 0)
    const y = Number(first?.center?.[1]) || 0
    const z = Number(first?.center?.[2]) || 0
    start = [Math.min(...xs), y, z]
    end = [Math.max(...xs), y, z]
  } else {
    const ys = allPoints.map((point) => Number(point[1]) || 0)
    const x = Number(first?.center?.[0]) || 0
    const z = Number(first?.center?.[2]) || 0
    start = [x, Math.min(...ys), z]
    end = [x, Math.max(...ys), z]
  }

  const center = [
    (Number(start[0]) + Number(end[0])) / 2,
    (Number(start[1]) + Number(end[1])) / 2,
    (Number(start[2]) + Number(end[2])) / 2,
  ]
  const length = Math.hypot(
    Number(end[0]) - Number(start[0]),
    Number(end[1]) - Number(start[1]),
    Number(end[2]) - Number(start[2]),
  )

  return {
    id: Number(group?.id) || index + 1,
    axis,
    center,
    start,
    end,
    length,
    segment_indices: memberIndexes.map((value) => value + 1),
  }
}

export function normalizeUnfoldVisuals(unfoldVisuals) {
  if (!unfoldVisuals) return unfoldVisuals

  const segments = Array.isArray(unfoldVisuals.bend_line_segments) ? unfoldVisuals.bend_line_segments : []
  const groups = Array.isArray(unfoldVisuals.bend_line_groups) ? unfoldVisuals.bend_line_groups : []
  const existingFoldDetails = Array.isArray(unfoldVisuals.fold_details) ? unfoldVisuals.fold_details : []
  const existingBendsLogical = Array.isArray(unfoldVisuals.bends_logical) ? unfoldVisuals.bends_logical : []

  const derivedFoldDetails =
    existingFoldDetails.length > 0
      ? existingFoldDetails
      : groups.map((group, index) => buildFoldDetailFromGroup(group, segments, index)).filter(Boolean)

  const derivedBendsLogical =
    existingBendsLogical.length > 0
      ? existingBendsLogical
      : derivedFoldDetails.map((detail, index) => ({
          id: detail.id ?? index + 1,
          type: null,
          angle: null,
          radius: null,
        }))

  const derivedFoldLines =
    Number(unfoldVisuals.fold_lines) > 0
      ? Number(unfoldVisuals.fold_lines)
      : derivedFoldDetails.length > 0
        ? derivedFoldDetails.length
        : groups.length

  const rawFoldLines =
    unfoldVisuals.raw_fold_lines != null
      ? unfoldVisuals.raw_fold_lines
      : segments.length > 0
        ? segments.length
        : null
  const discardedFoldSegmentCount = Math.max(Number(unfoldVisuals.discarded_fold_segment_count) || 0, 0)
  const flatLength = Math.max(Number(unfoldVisuals.flat_length) || 0, 0)
  const flatWidth = Math.max(Number(unfoldVisuals.flat_width) || 0, 0)
  const inScopeX = Math.max(flatLength * 0.8, flatWidth * 0.8, 40)
  const inScopeY = Math.max(flatWidth * 0.8, flatLength * 0.2, 40)
  const inScopeZ = Math.max(Math.min(flatLength, flatWidth) * 0.15, 8)

  // Compute centroid of all fold detail centers so scope check uses relative
  // coordinates. FreeCAD flat patterns can be far from the origin, so checking
  // abs(center) against the part dimensions (inScopeX/Y/Z) would incorrectly
  // filter valid fold lines that happen to have large absolute coordinates.
  const centersForCentroid = derivedFoldDetails
    .filter((d) => Array.isArray(d?.center) && d.center.length >= 3)
    .map((d) => d.center)
  const centroid =
    centersForCentroid.length > 0
      ? [
          centersForCentroid.reduce((s, c) => s + Number(c[0] || 0), 0) / centersForCentroid.length,
          centersForCentroid.reduce((s, c) => s + Number(c[1] || 0), 0) / centersForCentroid.length,
          centersForCentroid.reduce((s, c) => s + Number(c[2] || 0), 0) / centersForCentroid.length,
        ]
      : [0, 0, 0]

  const normalizedFoldDetails = derivedFoldDetails
    .map((detail, index) => {
      const start = Array.isArray(detail?.start) ? detail.start : null
      const end = Array.isArray(detail?.end) ? detail.end : null
      const measuredLength =
        start && end && start.length >= 3 && end.length >= 3
          ? Math.hypot(
              Number(end[0] || 0) - Number(start[0] || 0),
              Number(end[1] || 0) - Number(start[1] || 0),
              Number(end[2] || 0) - Number(start[2] || 0),
            )
          : null
      const length = Number(detail?.length ?? measuredLength ?? 0)
      return {
        ...detail,
        id: detail?.id ?? index + 1,
        length,
        _sourceIndex: index,
        _outOfScope:
          Array.isArray(detail?.center) &&
          detail.center.length >= 3 &&
          (Math.abs(Number(detail.center[0] || 0) - centroid[0]) > inScopeX ||
            Math.abs(Number(detail.center[1] || 0) - centroid[1]) > inScopeY ||
            Math.abs(Number(detail.center[2] || 0) - centroid[2]) > inScopeZ),
      }
    })
    .filter((detail) => {
      const segmentCount = Array.isArray(detail?.segment_indices) ? detail.segment_indices.length : 0
      return (detail.length > 1 || segmentCount > 1) && !detail._outOfScope
    })

  const dedupedFoldDetails = []
  const dedupeMap = new Map()
  for (const detail of normalizedFoldDetails) {
    const logical = derivedBendsLogical[(detail._sourceIndex ?? 0)] || {}
    const center = Array.isArray(detail.center) ? detail.center : [0, 0, 0]
    const key = [
      String(detail.axis || ''),
      Math.round(Number(center[0] || 0) / 2),
      Math.round(Number(center[1] || 0) / 2),
      Math.round(Number(center[2] || 0) / 2),
      Math.round(Number(logical.angle || 0)),
      Math.round(Number(logical.radius || 0) * 2),
    ].join('|')
    const existingIndex = dedupeMap.get(key)
    if (existingIndex == null) {
      dedupeMap.set(key, dedupedFoldDetails.length)
      dedupedFoldDetails.push(detail)
      continue
    }
    if (detail.length > dedupedFoldDetails[existingIndex].length) {
      dedupedFoldDetails[existingIndex] = detail
    }
  }

  const filteredBendsLogical = dedupedFoldDetails.map((detail) => derivedBendsLogical[detail._sourceIndex ?? 0] || {
    id: detail.id,
    type: null,
    angle: null,
    radius: null,
  })

  const outOfScopeFoldCandidateCount = normalizedFoldDetails.filter((detail) => detail._outOfScope).length
  const hiddenFoldCandidateCount = Math.max(0, derivedFoldDetails.length - dedupedFoldDetails.length)
  const filteredFoldCandidateCount = hiddenFoldCandidateCount + outOfScopeFoldCandidateCount + discardedFoldSegmentCount

  return {
    ...unfoldVisuals,
    fold_lines: dedupedFoldDetails.length > 0 ? dedupedFoldDetails.length : derivedFoldLines,
    raw_fold_lines: rawFoldLines,
    fold_details: dedupedFoldDetails.length > 0 ? dedupedFoldDetails.map(({ _sourceIndex, ...detail }) => detail) : derivedFoldDetails,
    bends_logical: dedupedFoldDetails.length > 0 ? filteredBendsLogical : derivedBendsLogical,
    discarded_fold_segment_count: discardedFoldSegmentCount,
    hidden_fold_candidate_count: hiddenFoldCandidateCount,
    out_of_scope_fold_candidate_count: outOfScopeFoldCandidateCount,
    filtered_fold_candidate_count: filteredFoldCandidateCount,
  }
}

export function isIrregularHole(hole) {
  const type = String(hole?.type || '').toLowerCase()
  const label = String(hole?.label || '').toLowerCase()
  const reason = String(hole?.reason || '').toLowerCase()
  return (
    type.includes('irregular') || label.includes('irregular') || reason.includes('irregular')
  )
}

export function isHiddenHoleCandidate(hole) {
  return hole?.status === 'rejected'
}
