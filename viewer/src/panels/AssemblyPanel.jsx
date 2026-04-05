import React, { useState } from 'react'

function fmt(value, unit = '') {
  if (value == null || value === 0) return '–'
  return `${Number(value).toFixed(1)}${unit}`
}

function PartRow({ part, index }) {
  const [open, setOpen] = useState(false)
  const dims = part.dimensions || {}
  const prod = part.production || {}

  return (
    <div className="reasoning-card" style={{ marginBottom: 4 }}>
      <button
        className="timeline-item-head"
        style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="timeline-stage" style={{ flex: 1 }}>
          {index + 1}. {part.solid_name || part.file || `Onderdeel ${index + 1}`}
        </div>
        <span className="hole-status-pill is-accepted" style={{ marginLeft: 8 }}>
          {part.category || part.part_type || '–'}
        </span>
        <span style={{ marginLeft: 8, fontSize: '0.75rem', color: '#888' }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={{ marginTop: 8 }}>
          <div className="timeline-payload-grid">
            <div className="timeline-payload-row">
              <div className="timeline-payload-key">Dikte</div>
              <pre className="timeline-payload-value">{fmt(part.thickness, ' mm')}</pre>
            </div>
            <div className="timeline-payload-row">
              <div className="timeline-payload-key">Afmetingen</div>
              <pre className="timeline-payload-value">
                {fmt(dims.length)} × {fmt(dims.width)} × {fmt(dims.height)} mm
              </pre>
            </div>
            <div className="timeline-payload-row">
              <div className="timeline-payload-key">Zettingen</div>
              <pre className="timeline-payload-value">{prod.bends_total ?? '–'}</pre>
            </div>
            <div className="timeline-payload-row">
              <div className="timeline-payload-key">Gaten</div>
              <pre className="timeline-payload-value">{prod.holes_total ?? '–'}</pre>
            </div>
            {part.flat_dimensions && (
              <div className="timeline-payload-row">
                <div className="timeline-payload-key">Uitslag</div>
                <pre className="timeline-payload-value">
                  {fmt(part.flat_dimensions.length)} × {fmt(part.flat_dimensions.width)} mm
                </pre>
              </div>
            )}
            {part.error && (
              <div className="timeline-payload-row">
                <div className="timeline-payload-key" style={{ color: '#f87171' }}>Fout</div>
                <pre className="timeline-payload-value" style={{ color: '#f87171' }}>{part.error}</pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function AssemblyPanel({ pipelineResult, selectedPartIndex, onSelectPartIndex }) {
  if (!pipelineResult?.is_assembly) return null

  const parts = pipelineResult.parts || []
  const solidCount = pipelineResult.solid_count || parts.length
  const selectedPart = parts[selectedPartIndex] || null

  return (
    <div className="visual-stage-card">
      <div className="timeline-item-head" style={{ marginBottom: 8 }}>
        <div className="timeline-title">Assembly gedetecteerd</div>
        <span className="hole-status-pill is-warning">{solidCount} onderdelen</span>
      </div>
      <div className="timeline-text" style={{ marginBottom: 10 }}>
        Dit STEP bestand bevat {solidCount} losse solids. Elk is afzonderlijk geanalyseerd.
        Selecteer een onderdeel om de pipeline-stages per onderdeel te zien.
      </div>
      <div style={{ marginBottom: 12 }}>
        {parts.map((part, i) => (
          <button
            key={part.solid_name || i}
            onClick={() => onSelectPartIndex(i)}
            style={{
              background: selectedPartIndex === i ? '#e5e7eb' : '#ffffff',
              border: selectedPartIndex === i ? '2px solid #3b82f6' : '1px solid #d1d5db',
              color: '#0f172a',
              padding: '8px 12px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: selectedPartIndex === i ? '600' : '500',
              marginBottom: '6px',
              width: '100%',
              textAlign: 'left',
            }}
          >
            {i + 1}. {part.solid_name || part.file || `Onderdeel ${i + 1}`}
            <span style={{ float: 'right', fontSize: '0.75rem', color: '#666' }}>
              {part.category || part.part_type || '–'}
            </span>
          </button>
        ))}
      </div>
      {selectedPart && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 10 }}>
          <PartRow part={selectedPart} index={selectedPartIndex} />
        </div>
      )}
    </div>
  )
}
