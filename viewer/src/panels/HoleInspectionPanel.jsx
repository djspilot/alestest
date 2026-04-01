import React, { useMemo, useState } from 'react'
import { formatDetailValue, formatLabel } from '../pipelineUi'
import { isIrregularHole, isHiddenHoleCandidate } from '../lib/holes'
import { getHoleStatusLabel, getHoleMethodLabel } from './helpers'

export default function HoleInspectionPanel({
  holeVisuals,
  selectedHoleId,
  onHoleSelect,
  selectedProbe,
  showHiddenHoles,
  onShowHiddenHolesChange,
  highlightHiddenHoleLocations,
  onHighlightHiddenHoleLocationsChange,
}) {
  const [holeFilter, setHoleFilter] = useState('all')
  const [showAdvancedHoleDebug, setShowAdvancedHoleDebug] = useState(false)
  const [exportFeedback, setExportFeedback] = useState('')

  const holeItems = holeVisuals?.items || []
  const hiddenHoleItems = useMemo(() => holeItems.filter((hole) => isHiddenHoleCandidate(hole)), [holeItems])
  const normalHoleItems = useMemo(
    () => holeItems.filter((hole) => hole.status === 'accepted' && !isIrregularHole(hole)),
    [holeItems],
  )
  const irregularHoleItems = useMemo(
    () => holeItems.filter((hole) => isIrregularHole(hole) || hole.status === 'rejected'),
    [holeItems],
  )
  const baseVisibleHoleItems = useMemo(() => {
    if (showHiddenHoles) return holeItems
    return holeItems.filter((hole) => !isHiddenHoleCandidate(hole))
  }, [holeItems, showHiddenHoles])
  const visibleHoleItems = useMemo(() => {
    if (holeFilter === 'accepted') return baseVisibleHoleItems.filter((hole) => hole.status === 'accepted')
    if (holeFilter === 'rejected') return baseVisibleHoleItems.filter((hole) => hole.status === 'rejected')
    return baseVisibleHoleItems
  }, [baseVisibleHoleItems, holeFilter])

  const selectedInspection = (holeItems.find((h) => h.id === selectedHoleId) || null) || selectedProbe

  const downloadPreUnfoldDebug = () => {
    const payload = { holes: holeItems, generated_at: new Date().toISOString() }
    const content = JSON.stringify(payload, null, 2)
    try {
      const blob = new Blob([content], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `hole-debug-${Date.now()}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      setExportFeedback(`Debug JSON gedownload: hole-debug-${Date.now()}.json`)
    } catch {
      setExportFeedback('Download mislukt')
    }
  }

  const copyPreUnfoldDebug = async () => {
    const payload = { holes: holeItems, generated_at: new Date().toISOString() }
    const content = JSON.stringify(payload, null, 2)
    try {
      await navigator.clipboard.writeText(content)
      setExportFeedback('Debug JSON gekopieerd naar klembord')
    } catch {
      setExportFeedback('Kopieren mislukt')
    }
  }

  return (
    <div className="visual-stage-card" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
      <div className="timeline-title">Hole Overlay</div>
      <div className="timeline-text">
        Bron: {holeVisuals.source || '-'} | Netto gaten: {holeVisuals.accepted_total || 0}
      </div>
      <div className="timeline-text">
        Viewer: zichtbaar {baseVisibleHoleItems.length}
        {hiddenHoleItems.length > 0 ? ` | debug verborgen ${hiddenHoleItems.length}` : ''}
      </div>
      {holeVisuals.criteria_note && <div className="timeline-text">{holeVisuals.criteria_note}</div>}
      <div className="timeline-text" style={{ marginTop: 8 }}>
        Snel overzicht: normale gaten {normalHoleItems.length} | irregulaire gaten{' '}
        {holeItems.filter((hole) => hole.status === 'accepted' && isIrregularHole(hole)).length}
      </div>
      <div className="hole-filter-row" style={{ marginTop: 8 }}>
        <button
          className={`hole-filter-btn ${showAdvancedHoleDebug ? 'is-active' : ''}`}
          onClick={() => setShowAdvancedHoleDebug((v) => !v)}
        >
          {showAdvancedHoleDebug ? 'Verberg uitgebreide debug' : 'Toon uitgebreide debug'}
        </button>
      </div>

      {/* Simple view: split normal/irregular */}
      {!showAdvancedHoleDebug && (
        <>
          <div className="timeline-text" style={{ marginTop: 4 }}>
            Kleur: <span style={{ color: '#ff4d3b' }}>rood</span> = cilindrisch,{' '}
            <span style={{ color: '#2dd4bf' }}>blauw-groen</span> = gevormd/irregulair,{' '}
            <span style={{ color: '#f5c542' }}>goud</span> = geselecteerd
          </div>
          <div className="hole-toggle-row" style={{ marginTop: 6 }}>
            <button
              className={`hole-filter-btn ${showHiddenHoles ? 'is-active' : ''}`}
              onClick={() => onShowHiddenHolesChange?.(!showHiddenHoles)}
              title="Toon of verberg afgewezen gaten in het 3D model"
            >
              {showHiddenHoles ? 'Verberg afgewezen' : 'Toon afgewezen'}
            </button>
            <button
              className={`hole-filter-btn ${highlightHiddenHoleLocations ? 'is-active' : ''}`}
              onClick={() => onHighlightHiddenHoleLocationsChange?.(!highlightHiddenHoleLocations)}
              title="Toon of verberg extra locatie-markers op het 3D model"
            >
              {highlightHiddenHoleLocations ? 'Locatie-markers aan' : 'Locatie-markers uit'}
            </button>
          </div>

          <div className="timeline-title" style={{ marginTop: 8 }}>Normale gaten</div>
          <div className="hole-list">
            {normalHoleItems.map((hole) => (
              <button
                key={hole.id}
                className={`hole-list-item ${selectedHoleId === hole.id ? 'is-active' : ''} is-${hole.status}`}
                onClick={() => onHoleSelect?.(hole.id)}
              >
                <div className="timeline-item-head">
                  <span className="timeline-stage">{hole.label || formatLabel(hole.type)}</span>
                  <span className={`hole-status-pill is-${hole.status}`}>{getHoleStatusLabel(hole.status)}</span>
                </div>
                <div className="timeline-text">{hole.reason || 'Geen toelichting'}</div>
              </button>
            ))}
          </div>

          <div className="timeline-title" style={{ marginTop: 8 }}>Irregulair / afgewezen</div>
          <div className="hole-list">
            {irregularHoleItems.map((hole) => (
              <button
                key={hole.id}
                className={`hole-list-item ${selectedHoleId === hole.id ? 'is-active' : ''} is-${hole.status}`}
                onClick={() => onHoleSelect?.(hole.id)}
              >
                <div className="timeline-item-head">
                  <span className="timeline-stage">{hole.label || formatLabel(hole.type)}</span>
                  <span className={`hole-status-pill is-${hole.status}`}>{getHoleStatusLabel(hole.status)}</span>
                </div>
                <div className="timeline-text">{hole.reason || 'Geen toelichting'}</div>
              </button>
            ))}
          </div>

          {normalHoleItems.length === 0 && irregularHoleItems.length === 0 && (
            <div className="timeline-text" style={{ marginTop: 8 }}>Geen gaten gevonden in deze stap.</div>
          )}
        </>
      )}

      {/* Advanced debug view */}
      {showAdvancedHoleDebug && (
        <>
          {Array.isArray(holeVisuals.method_order) && holeVisuals.method_order.length > 0 && (
            <div className="timeline-text">Methodiekvolgorde: {holeVisuals.method_order.join(' -> ')}</div>
          )}
          <div className="timeline-text">
            Debugtellingen: kandidaten {holeVisuals.total_candidates || 0} | afgewezen {holeVisuals.rejected_total || 0}
          </div>
          <div className="hole-filter-row" style={{ marginTop: 8 }}>
            <button className="hole-filter-btn" onClick={downloadPreUnfoldDebug}>Download debug JSON</button>
            <button className="hole-filter-btn" onClick={copyPreUnfoldDebug}>Kopieer debug</button>
          </div>
          {exportFeedback && <div className="timeline-text">{exportFeedback}</div>}
          {holeVisuals.thresholds && (
            <div className="reasoning-list" style={{ marginTop: 8 }}>
              <div className="reasoning-card">
                <div className="timeline-title">Thresholds</div>
                <div className="timeline-payload-grid">
                  {Object.entries(holeVisuals.thresholds).map(([key, value]) => (
                    <div className="timeline-payload-row" key={`hole-threshold-${key}`}>
                      <div className="timeline-payload-key">{formatLabel(key)}</div>
                      <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <div className="timeline-text">
            Klik op een gat om exact de gedetecteerde hole-rand te highlighten en de camera erop te focussen.
            In `Probe mode` wordt elke klik op het model altijd een probe op exact die plek, zonder snap naar een bekende hole.
          </div>
          <div className="timeline-text">
            Kleurlegenda: goud = geselecteerde hole-edge, rood = geaccepteerde hole-edge, blauw = afgewezen hole-edge, gedimd = niet geselecteerd.
          </div>
          <div className="hole-filter-row">
            <button className={`hole-filter-btn ${holeFilter === 'all' ? 'is-active' : ''}`} onClick={() => setHoleFilter('all')}>Alle</button>
            <button className={`hole-filter-btn ${holeFilter === 'accepted' ? 'is-active' : ''}`} onClick={() => setHoleFilter('accepted')}>Geaccepteerd</button>
            <button className={`hole-filter-btn ${holeFilter === 'rejected' ? 'is-active' : ''}`} onClick={() => setHoleFilter('rejected')}>Afgewezen</button>
          </div>
          <div className="hole-toggle-row">
            <button
              className={`hole-filter-btn ${showHiddenHoles ? 'is-active' : ''}`}
              onClick={() => onShowHiddenHolesChange?.(!showHiddenHoles)}
              title="Toon of verberg afgewezen en irregulaire kandidaten"
            >
              {showHiddenHoles ? 'Verberg afgewezen/irregulair' : 'Toon afgewezen/irregulair'}
            </button>
            <button
              className={`hole-filter-btn ${highlightHiddenHoleLocations ? 'is-active' : ''}`}
              onClick={() => onHighlightHiddenHoleLocationsChange?.(!highlightHiddenHoleLocations)}
              title="Toon of verberg extra locatie-markers op het 3D model"
            >
              {highlightHiddenHoleLocations ? 'Locatie-markers aan' : 'Locatie-markers uit'}
            </button>
          </div>
          {hiddenHoleItems.length > 0 && (
            <div className="timeline-text">
              Extra locatie-markers staan op de afgewezen/irregulaire gaten zodat direct zichtbaar is waar de ontbrekende gaten op het model zitten.
            </div>
          )}
          <div className="hole-list">
            {visibleHoleItems.map((hole) => (
              <button
                key={hole.id}
                className={`hole-list-item ${selectedHoleId === hole.id ? 'is-active' : ''} is-${hole.status}`}
                onClick={() => onHoleSelect?.(hole.id)}
              >
                <div className="timeline-item-head">
                  <span className="timeline-stage">{hole.label || formatLabel(hole.type)}</span>
                  <span className={`hole-status-pill is-${hole.status}`}>{getHoleStatusLabel(hole.status)}</span>
                </div>
                <div className="timeline-text">{hole.reason || 'Geen toelichting'}</div>
                <div className="timeline-text">{formatLabel(hole.type)} | {hole.source || '-'}</div>
              </button>
            ))}
          </div>
        </>
      )}

      {/* Selected inspection details */}
      {selectedInspection && showAdvancedHoleDebug && (
        <div className="reasoning-list">
          <div className="reasoning-card">
            <div className="timeline-stage">
              {selectedInspection.label || formatLabel(selectedInspection.type)} |{' '}
              {getHoleStatusLabel(selectedInspection.status)}
            </div>
            <div className="timeline-text">{selectedInspection.reason || 'Geen toelichting'}</div>
            <div className="timeline-text">Methodiek: {getHoleMethodLabel(selectedInspection.method)}</div>
            <pre className="timeline-payload-value">{formatDetailValue(selectedInspection.position)}</pre>
            {selectedInspection.inferredContour && (
              <div className="timeline-text">
                Inferred contour: {selectedInspection.inferredContour.label || formatLabel(selectedInspection.inferredContour.type)}
              </div>
            )}
            {selectedInspection.nearestHole && (
              <div className="timeline-text">
                Dichtstbijzijnde bekende kandidaat: {selectedInspection.nearestHole.label || formatLabel(selectedInspection.nearestHole.type)} op{' '}
                {formatDetailValue(selectedInspection.nearestHoleDistance)} mm.
              </div>
            )}
          </div>
          <div className="reasoning-card">
            <div className="timeline-title">Criteria</div>
            <div className="timeline-payload-grid">
              {(selectedInspection.criteria || []).map((criterion, index) => (
                <div className="timeline-payload-row" key={`${selectedInspection.id}-criterion-${index}`}>
                  <div className="timeline-item-head">
                    <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                    <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                      {criterion.passed ? 'Pass' : 'Fail'}
                    </span>
                  </div>
                  <pre className="timeline-payload-value">
                    {formatDetailValue({ value: criterion.value, threshold: criterion.threshold, note: criterion.note })}
                  </pre>
                </div>
              ))}
            </div>
          </div>
          {selectedInspection.inferredContour?.debug && (
            <div className="reasoning-card">
              <div className="timeline-title">Probe Debug</div>
              <div className="timeline-text">
                Viewer heuristic: {selectedInspection.inferredContour.debug.inferred_family} | confidence{' '}
                {formatDetailValue(selectedInspection.inferredContour.debug.confidence)}
              </div>
              <div className="timeline-payload-grid">
                {Object.entries(selectedInspection.inferredContour.debug).map(([key, value]) => (
                  <div className="timeline-payload-row" key={`${selectedInspection.id}-debug-${key}`}>
                    <div className="timeline-payload-key">{formatLabel(key)}</div>
                    <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {selectedInspection == null && showAdvancedHoleDebug && (
        <div className="timeline-text" style={{ marginTop: 8 }}>
          Kies een gat links of klik in het 3D-model om criteria en viewer-focus te zien.
        </div>
      )}
      {visibleHoleItems.length === 0 && showAdvancedHoleDebug && (
        <div className="timeline-text" style={{ marginTop: 8 }}>Geen gaten in deze filter.</div>
      )}
    </div>
  )
}
