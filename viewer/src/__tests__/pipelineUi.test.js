import { describe, expect, it } from 'vitest'

import { getPartTimelineEvents, isDetectHolesStageName, isUnfoldStageName } from '../pipelineUi'
import { normalizeUnfoldVisuals } from '../lib/holes'

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

describe('normalizeUnfoldVisuals', () => {
  it('preserves fold pipeline counts from backend and viewer filtering', () => {
    const result = normalizeUnfoldVisuals({
      fold_lines: 1,
      raw_fold_lines: 4,
      discarded_fold_segment_count: 1,
      hidden_fold_candidate_count: 0,
      out_of_scope_fold_candidate_count: 0,
      fold_details: [
        { id: 1, axis: 'x', center: [20, 10, 0], start: [0, 10, 0], end: [40, 10, 0], length: 40, segment_indices: [1, 2] },
      ],
      bends_logical: [{ id: 1, type: 'up', angle: 90, radius: 1 }],
    })

    expect(result.raw_fold_lines).toBe(4)
    expect(result.discarded_fold_segment_count).toBe(1)
    expect(result.filtered_fold_candidate_count).toBe(1)
    expect(result.fold_lines).toBe(1)
  })
})
