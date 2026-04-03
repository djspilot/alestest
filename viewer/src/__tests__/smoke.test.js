import { describe, it, expect } from 'vitest'
import { normalizeStageName, formatDuration, formatLabel, formatDetailValue, parseIsoToMs } from '../pipelineUi'
import { getApiKeyHeaders, sanitizeUploadFileName } from '../pipelineClient'

describe('pipelineUi', () => {
  it('normalizes Profile Router to Classify geometry', () => {
    expect(normalizeStageName('Profile Router')).toBe('Classify geometry')
  })

  it('normalizes Detect holes to merged stage', () => {
    expect(normalizeStageName('Detect holes')).toBe('Unfold / Detect holes')
  })

  it('formats short durations', () => {
    expect(formatDuration(5.3)).toBe('5.3s')
  })

  it('formats minute durations', () => {
    expect(formatDuration(125)).toBe('2m 05s')
  })

  it('formats labels with underscores', () => {
    expect(formatLabel('stage_start')).toBe('Stage Start')
  })

  it('formats detail values for null', () => {
    expect(formatDetailValue(null)).toBe('n.v.t.')
  })

  it('formats detail values for booleans', () => {
    expect(formatDetailValue(true)).toBe('ja')
    expect(formatDetailValue(false)).toBe('nee')
  })

  it('parses ISO timestamps', () => {
    const ms = parseIsoToMs('2024-01-15T10:30:00.000Z')
    expect(ms).toBe(Date.UTC(2024, 0, 15, 10, 30, 0))
  })

  it('returns null for invalid ISO', () => {
    expect(parseIsoToMs('not-a-date')).toBeNull()
    expect(parseIsoToMs(null)).toBeNull()
  })

  it('builds the api key header for latin-1 values', () => {
    const headers = getApiKeyHeaders('abc123')
    expect(headers.get('X-API-Key')).toBe('abc123')
  })

  it('rejects api keys with non latin-1 characters', () => {
    expect(() => getApiKeyHeaders('abc€')).toThrow(/niet-ondersteunde tekens/i)
  })

  it('sanitizes upload file names before multipart upload', () => {
    expect(sanitizeUploadFileName('Müller “plaat” 🚀.step')).toBe('Mu_ller_plaat.step')
  })
})
