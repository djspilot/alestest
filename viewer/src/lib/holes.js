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

  return {
    ...unfoldVisuals,
    fold_lines: derivedFoldLines,
    raw_fold_lines: rawFoldLines,
    fold_details: derivedFoldDetails,
    bends_logical: derivedBendsLogical,
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
