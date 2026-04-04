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
