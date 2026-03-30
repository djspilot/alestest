import React, { useMemo } from 'react'
import { formatDetailValue } from '../pipelineUi'
import { normalizeFoldId } from '../lib/holes'

export default function UnfoldPanel({ unfoldVisuals, selectedFoldId, onFoldSelect }) {
  const foldRows = useMemo(() => {
    const bends = unfoldVisuals?.bends_logical || []
    const foldDetails = unfoldVisuals?.fold_details || []
    const rowCount = Math.max(bends.length, foldDetails.length)
    return Array.from({ length: rowCount }, (_, i) => {
      const bend = bends[i] || {}
      const detail = foldDetails[i] || {}
      const id = normalizeFoldId(detail.id || bend.id || i + 1)
      return {
        id,
        direction: bend.type || '–',
        angle: bend.angle ?? null,
        radius: bend.radius ?? null,
        length: detail.length ?? null,
        center: detail.center ?? null,
        axis: detail.axis ?? null,
        start: detail.start ?? null,
        end: detail.end ?? null,
        segmentIndices: detail.segment_indices || [],
      }
    })
  }, [unfoldVisuals])

  const normalizedSelectedFoldId = normalizeFoldId(selectedFoldId)
  const selectedFold = foldRows.find((row) => row.id === normalizedSelectedFoldId) || null

  return (
    <div className="visual-stage-card">
      <div className="timeline-title">Unfold data</div>

      {unfoldVisuals ? (
        unfoldVisuals.success ? (
          <div className="timeline-text" style={{ color: '#4caf50', fontWeight: 600 }}>✓ Unfold geslaagd</div>
        ) : (
          <div className="timeline-text" style={{ color: '#f44336', fontWeight: 600 }}>
            ✗ Unfold niet geslaagd{unfoldVisuals.error ? `: ${unfoldVisuals.error}` : ''}
            {unfoldVisuals.skipped && <span style={{ color: '#aaa', fontWeight: 400 }}> (overgeslagen – {unfoldVisuals.reason})</span>}
          </div>
        )
      ) : (
        <div className="timeline-text" style={{ color: '#aaa' }}>Geen unfold data beschikbaar</div>
      )}

      {unfoldVisuals?.success && (
        <div style={{ marginTop: 10 }}>
          <div className="timeline-stage" style={{ marginBottom: 4 }}>Uitslag afmetingen</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <tbody>
              <tr>
                <td style={{ padding: '2px 8px 2px 0', color: '#aaa' }}>Lengte</td>
                <td style={{ fontWeight: 600 }}>{unfoldVisuals.flat_length ? `${Math.round(unfoldVisuals.flat_length)} mm` : '–'}</td>
                <td style={{ padding: '2px 0 2px 16px', color: '#aaa' }}>Breedte</td>
                <td style={{ fontWeight: 600 }}>{unfoldVisuals.flat_width ? `${Math.round(unfoldVisuals.flat_width)} mm` : '–'}</td>
              </tr>
              <tr>
                <td style={{ color: '#aaa' }}>Zetlijnen</td>
                <td style={{ fontWeight: 600 }}>{unfoldVisuals.fold_lines ?? '–'}</td>
              </tr>
            </tbody>
          </table>
          <div className="timeline-text" style={{ marginTop: 8 }}>
            Klik op een zetlijn in de tabel of in de viewer om die lijn te markeren.
          </div>
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <div className="timeline-stage" style={{ marginBottom: 4 }}>Criteria &amp; thresholds (freecad_unfold)</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#ccc' }}>
          <tbody>
            {[
              ['K-factor', '0.44 (vast voor alle plaatdiktes)'],
              ['Max pogingen (base face)', '5'],
              ['Subprocess timeout', '300 s'],
              ['Bend filter: min hoek', '> 0.3 rad (≈ 17°)'],
              ['Bend filter: min lengte', '> 5 mm'],
              ['Deduplicatie key', '(round(hoek,1), round(lengte,1))'],
              ['Bij duplicaat', 'Kleinste radius wint (inner radius)'],
              ['Merge gesplitste bends', 'Exact gelijke hoek + radius'],
            ].map(([label, val]) => (
              <tr key={label}>
                <td style={{ padding: '2px 8px 2px 0', color: '#888', whiteSpace: 'nowrap' }}>{label}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{val}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {unfoldVisuals?.success && (() => {
        if (foldRows.length === 0) return null
        return (
          <div style={{ marginTop: 12 }}>
            <div className="timeline-stage" style={{ marginBottom: 6 }}>Zetlijnen ({foldRows.length} gevonden)</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ color: '#888', borderBottom: '1px solid #333' }}>
                  <th style={{ textAlign: 'left', padding: '2px 6px 4px 0', fontWeight: 400 }}>#</th>
                  <th style={{ textAlign: 'left', padding: '2px 6px 4px 0', fontWeight: 400 }}>Richting</th>
                  <th style={{ textAlign: 'right', padding: '2px 6px 4px 0', fontWeight: 400 }}>Hoek (°)</th>
                  <th style={{ textAlign: 'right', padding: '2px 6px 4px 0', fontWeight: 400 }}>Radius (mm)</th>
                  <th style={{ textAlign: 'right', padding: '2px 0 4px 0', fontWeight: 400 }}>Lengte (mm)</th>
                </tr>
              </thead>
              <tbody>
                {foldRows.map((row, i) => {
                  const dir = row.direction || '–'
                  const angle = row.angle != null ? Math.round(row.angle * 10) / 10 : '–'
                  const radius = row.radius != null ? Math.round(row.radius * 10) / 10 : '–'
                  const length = row.length != null ? Math.round(row.length * 10) / 10 : '–'
                  const dirColor = dir === 'up' ? '#81c784' : dir === 'down' ? '#e57373' : '#aaa'
                  return (
                    <tr
                      key={row.id ?? i}
                      style={{
                        borderBottom: '1px solid #222',
                        cursor: 'pointer',
                        background: normalizedSelectedFoldId === row.id ? 'rgba(255, 59, 48, 0.15)' : 'transparent',
                      }}
                      onClick={() => onFoldSelect?.(row.id)}
                    >
                      <td style={{ padding: '3px 6px 3px 0', color: '#888' }}>{row.id}</td>
                      <td style={{ padding: '3px 6px 3px 0', fontWeight: 600, color: dirColor }}>
                        {dir === 'up' ? '▲ Op' : dir === 'down' ? '▼ Neer' : dir}
                      </td>
                      <td style={{ textAlign: 'right', padding: '3px 6px 3px 0', fontFamily: 'monospace' }}>{angle}</td>
                      <td style={{ textAlign: 'right', padding: '3px 6px 3px 0', fontFamily: 'monospace' }}>{radius}</td>
                      <td style={{ textAlign: 'right', padding: '3px 0 3px 0', fontFamily: 'monospace' }}>{length}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      })()}

      {selectedFold && (
        <div className="reasoning-list" style={{ marginTop: 12 }}>
          <div className="reasoning-card">
            <div className="timeline-stage">Geselecteerde zetlijn #{selectedFold.id}</div>
            <div className="timeline-text">
              Richting: {selectedFold.direction || 'onbekend'} | Hoek: {selectedFold.angle != null ? `${Math.round(selectedFold.angle * 10) / 10}°` : '–'} | Radius: {selectedFold.radius != null ? `${Math.round(selectedFold.radius * 10) / 10} mm` : '–'}
            </div>
            <div className="timeline-text">
              Lengte: {selectedFold.length != null ? `${Math.round(selectedFold.length * 10) / 10} mm` : '–'}
            </div>
            <pre className="timeline-payload-value">
              {formatDetailValue({
                center: selectedFold.center,
                axis: selectedFold.axis,
                start: selectedFold.start,
                end: selectedFold.end,
                segment_indices: selectedFold.segmentIndices,
              })}
            </pre>
          </div>
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <div className="timeline-stage" style={{ marginBottom: 4 }}>SheetMetalUnfolder foutcodes</div>
        <div style={{ fontSize: 11, color: '#777', lineHeight: 1.6 }}>
          {[
            [1, 'Volume onbruikbaar'],
            [3, 'Dikte inconsistent of te complex'],
            [5, 'Onnodige edges (Refine Shape nodig)'],
            [11, 'Dubbele buigingen niet ondersteund'],
            [12, 'Meer dan één bend-child'],
            [17, 'Oppervlaktype niet ondersteund'],
            [21, 'Section wire niet gesloten'],
            [26, 'Niet-ondersteund curve type in unbendFace'],
          ].map(([code, msg]) => (
            <div key={code}>
              <span style={{ color: '#555', fontFamily: 'monospace', marginRight: 8 }}>{code}</span>
              {msg}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
