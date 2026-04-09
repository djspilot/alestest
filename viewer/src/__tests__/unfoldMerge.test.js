import { describe, expect, it } from 'vitest'

import { mergeUnfoldVisuals } from '../lib/unfoldMerge'

describe('mergeUnfoldVisuals', () => {
  it('preserves meaningful bend geometry when the incoming payload only contains zero placeholders', () => {
    const existing = {
      bends_logical: [
        { id: 1, type: 'up', angle: 90, radius: 5 },
        { id: 2, type: 'down', angle: 45, radius: 3 },
      ],
      bend_angles_erp: [90, 45],
    }

    const incoming = {
      bends_logical: [
        { id: 1, type: 'up', angle: 0, radius: 0 },
        { id: 2, type: 'down', angle: 0, radius: 0 },
      ],
    }

    const merged = mergeUnfoldVisuals(existing, incoming)

    expect(merged.bends_logical).toEqual([
      { id: 1, type: 'up', angle: 90, radius: 5 },
      { id: 2, type: 'down', angle: 45, radius: 3 },
    ])
    expect(merged.bend_angles_erp).toEqual([90, 45])
  })
})