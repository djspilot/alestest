import { describe, expect, it } from 'vitest'

import { getPartTimelineEvents, isDetectHolesStageName, isUnfoldStageName } from '../pipelineUi'

describe('getPartTimelineEvents', () => {
  it('prefers timeline_events when present', () => {
    const events = [{ stage: 'Classify geometry', type: 'stage_end' }]
    const fallback = [{ stage: 'Unfold', type: 'stage_end' }]

    expect(getPartTimelineEvents({ timeline_events: events, timeline: fallback })).toEqual(events)
  })

  it('falls back to timeline for assembly part results', () => {
    const fallback = [{ stage: 'Detect holes', type: 'stage_end' }]

    expect(getPartTimelineEvents({ timeline: fallback })).toEqual(fallback)
  })

  it('returns an empty list when no timeline is available', () => {
    expect(getPartTimelineEvents({})).toEqual([])
  })
})

describe('stage helpers', () => {
  it('recognizes raw detect holes stages', () => {
    expect(isDetectHolesStageName('Detect holes')).toBe(true)
    expect(isDetectHolesStageName('Unfold / Detect holes')).toBe(true)
    expect(isDetectHolesStageName('Unfold')).toBe(false)
  })

  it('recognizes raw unfold stages', () => {
    expect(isUnfoldStageName('Unfold')).toBe(true)
    expect(isUnfoldStageName('Unfold / Detect holes')).toBe(true)
    expect(isUnfoldStageName('Detect holes')).toBe(false)
  })
})
