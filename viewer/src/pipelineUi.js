export const STATUS_LABELS = {
  idle: 'Wacht op bestand',
  disabled: 'Uitgeschakeld',
  checking: 'Controleren',
  queued: 'In wachtrij',
  processing: 'Analyseren',
  completed: 'Klaar',
  failed: 'Mislukt',
  unavailable: 'Niet bereikbaar',
  auth_required: 'API-key nodig',
}

export const MERGED_HOLES_STAGE = 'Unfold / Detect holes'
export const PRE_UNFOLD_HOLES_STAGE = 'Detect holes (pre-unfold)'

export function isPreUnfoldStageName(stage) {
  const normalized = String(stage || '').toLowerCase()
  return normalized.includes('detect holes') && normalized.includes('pre') && normalized.includes('unfold')
}

export function isMergedHolesStageName(stage) {
  const normalized = String(stage || '').toLowerCase()
  return (
    stage === MERGED_HOLES_STAGE ||
    normalized === 'detect holes' ||
    normalized === 'unfold' ||
    normalized === 'unfold / detect holes'
  )
}

export function summarizePayload(payload) {
  if (!payload || typeof payload !== 'object') return ''

  if (payload.reasoning) return payload.reasoning
  if (typeof payload.total === 'number') return `Totaal: ${payload.total}`
  if (typeof payload.elapsed_seconds === 'number') return `${payload.elapsed_seconds}s`
  if (payload.name) return String(payload.name)
  if (payload.error) return String(payload.error)
  return Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' | ')
}

export function parseIsoToMs(value) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function formatDuration(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return '-'
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  if (minutes < 60) return `${minutes}m ${String(remainingSeconds).padStart(2, '0')}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}u ${String(remainingMinutes).padStart(2, '0')}m`
}

export function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function formatDetailValue(value) {
  if (value === null || value === undefined || value === '') return 'n.v.t.'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'boolean') return value ? 'ja' : 'nee'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function formatDeviation(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n.v.t.'
  if (value === 0) return '0.000'
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
}

export function normalizeStageName(stage) {
  if (stage === 'Profile Router') return 'Classify geometry'
  if (isPreUnfoldStageName(stage)) return PRE_UNFOLD_HOLES_STAGE
  if (stage === 'Detect holes' || stage === 'Unfold') return MERGED_HOLES_STAGE
  return stage || 'Onbekende stap'
}

export function groupEventsByStage(events) {
  const order = []
  const map = new Map()

  ;(events || []).forEach((event, index) => {
    const stageKey = normalizeStageName(event.stage)
    if (!map.has(stageKey)) {
      const group = { stage: stageKey, events: [], firstIndex: index }
      map.set(stageKey, group)
      order.push(group)
    }
    map.get(stageKey).events.push({
      ...event,
      stage: stageKey,
      originalStage: event.stage || stageKey,
      originalIndex: index,
    })
  })

  return order
}

export function getStageMeta(group, summary, liveActiveElapsed, pipelineStatus = null) {
  const requiresCompletedJob = group?.stage === 'Classify geometry'
  const finishedEvent = [...(group?.events || [])]
    .reverse()
    .find((event) => ['stage_end', 'stage_failed', 'stage_skipped'].includes(event.type))

  if (finishedEvent) {
    let stateLabel = 'Klaar'
    if (finishedEvent.type === 'stage_failed') stateLabel = 'Mislukt'
    if (finishedEvent.type === 'stage_skipped') stateLabel = 'Overgeslagen'
    return {
      stateLabel,
      elapsed: finishedEvent.payload?.elapsed_seconds,
      isSelectable: !requiresCompletedJob || pipelineStatus === 'completed',
      pendingReason:
        requiresCompletedJob && pipelineStatus !== 'completed'
          ? 'Pas beschikbaar zodra de hele pipeline klaar is.'
          : null,
    }
  }

  if (normalizeStageName(summary?.active_stage) === group?.stage) {
    return {
      stateLabel: 'Bezig',
      elapsed: liveActiveElapsed,
      isSelectable: false,
      pendingReason: null,
    }
  }

  if ((group?.events || []).some((event) => event.type === 'stage_start')) {
    return {
      stateLabel: 'Gestart',
      elapsed: null,
      isSelectable: false,
      pendingReason: null,
    }
  }

  return {
    stateLabel: `${group?.events?.length || 0} events`,
    elapsed: null,
    isSelectable: (group?.events?.length || 0) > 0,
    pendingReason: null,
  }
}
