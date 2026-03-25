import React, { useMemo, useState } from 'react'
import {
  formatDetailValue,
  formatDeviation,
  formatDuration,
  formatLabel,
  getStageMeta,
  summarizePayload,
} from './pipelineUi'

function getHoleStatusLabel(status) {
  if (status === 'accepted') return 'Geaccepteerd'
  if (status === 'rejected') return 'Afgewezen'
  return status || 'Onbekend'
}

export default function StageDetailsPanel({
  pipelineVisuals,
  groupedStages,
  summary,
  liveActiveElapsed,
  selectedStageIndex,
  selectedEventIndex,
  onSelectStageIndex,
  onSelectEventIndex,
  selectedHoleId,
  onHoleSelect,
  pipelineStatus,
}) {
  const [holeFilter, setHoleFilter] = useState('all')
  const selectedStage = groupedStages[selectedStageIndex] || null
  const selectedEvent = selectedStage?.events?.[selectedEventIndex] || null
  const selectedPayloadEntries = Object.entries(selectedEvent?.payload || {})
    .filter(([, value]) => value !== undefined)

  const routerVisuals = pipelineVisuals?.router || null
  const classificationVisuals = pipelineVisuals?.classification || null
  const holeVisuals = pipelineVisuals?.holes || null
  const unfoldVisuals = pipelineVisuals?.unfold || null
  const holeItems = holeVisuals?.items || []
  const selectedHole = holeItems.find((hole) => hole.id === selectedHoleId) || null
  const visibleHoleItems = useMemo(() => {
    if (holeFilter === 'accepted') return holeItems.filter((hole) => hole.status === 'accepted')
    if (holeFilter === 'rejected') return holeItems.filter((hole) => hole.status === 'rejected')
    return holeItems
  }, [holeFilter, holeItems])

  if (!selectedStage) {
    return (
      <div className="details-panel">
        <div className="details-placeholder">
          Kies links een afgeronde pipeline-stap om hier de details te zien.
        </div>
      </div>
    )
  }

  const stageMeta = getStageMeta(selectedStage, summary, liveActiveElapsed, pipelineStatus)
  const previousSelectableIndex = groupedStages
    .slice(0, selectedStageIndex)
    .map((group, index) => ({ index, selectable: getStageMeta(group, summary, liveActiveElapsed, pipelineStatus).isSelectable }))
    .filter((item) => item.selectable)
    .map((item) => item.index)
    .pop()
  const nextSelectableIndex = groupedStages
    .slice(selectedStageIndex + 1)
    .map((group, offset) => ({
      index: selectedStageIndex + offset + 1,
      selectable: getStageMeta(group, summary, liveActiveElapsed, pipelineStatus).isSelectable,
    }))
    .find((item) => item.selectable)?.index

  return (
    <div className="details-panel">
      <div className="timeline-detail-card">
        <div className="timeline-detail-head">
          <div>
            <div className="timeline-title">{selectedStage.stage}</div>
            <div className="timeline-text">
              Stap {selectedStageIndex + 1} van {groupedStages.length}
            </div>
            <div className="timeline-text">{`${stageMeta.stateLabel} · ${formatDuration(stageMeta.elapsed)}`}</div>
          </div>
          <div className="timeline-nav">
            <button
              className="timeline-nav-btn"
              onClick={() => {
                if (previousSelectableIndex == null) return
                onSelectStageIndex(previousSelectableIndex)
              }}
              disabled={previousSelectableIndex == null}
            >
              Vorige
            </button>
            <button
              className="timeline-nav-btn"
              onClick={() => {
                if (nextSelectableIndex == null) return
                onSelectStageIndex(nextSelectableIndex)
              }}
              disabled={nextSelectableIndex == null}
            >
              Volgende
            </button>
          </div>
        </div>

        <div className="timeline-event-list">
          {selectedStage.events.map((event, index) => (
            <button
              key={`${event.type}-${event.stage}-${event.originalIndex}`}
              className={`timeline-item ${selectedEventIndex === index ? 'is-active' : ''}`}
              onClick={() => onSelectEventIndex(index)}
            >
              <div className="timeline-item-head">
                <span className="timeline-stage">{formatLabel(event.type)}</span>
                <span className="timeline-type">
                  {event.status || '-'} · {formatDuration((event.timestamp_ms || 0) / 1000)}
                </span>
              </div>
              <div className="timeline-text">{summarizePayload(event.payload)}</div>
            </button>
          ))}
        </div>

        {selectedEvent && (
          <div className="timeline-payload">
            {selectedStage.stage === 'Detect holes' && holeVisuals && (
              <div className="visual-stage-card" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
                <div className="timeline-title">Hole Overlay</div>
                <div className="timeline-text">
                  Bron: {holeVisuals.source || '-'} | Geaccepteerd: {holeVisuals.accepted_total || 0} | Afgewezen: {holeVisuals.rejected_total || 0} | Kandidaten: {holeVisuals.total_candidates || 0}
                </div>
                <div className="timeline-text">
                  Klik op een gat om exact de gedetecteerde hole-rand te highlighten en de camera erop te focussen. Afgewezen kandidaten blijven ook zichtbaar met hun criteria.
                </div>
                <div className="timeline-text">
                  Kleurlegenda: goud = geselecteerde hole-edge, rood = geaccepteerde hole-edge, blauw = afgewezen hole-edge, gedimd = niet geselecteerd.
                </div>
                <div className="hole-filter-row">
                  <button className={`hole-filter-btn ${holeFilter === 'all' ? 'is-active' : ''}`} onClick={() => setHoleFilter('all')}>Alle</button>
                  <button className={`hole-filter-btn ${holeFilter === 'accepted' ? 'is-active' : ''}`} onClick={() => setHoleFilter('accepted')}>Geaccepteerd</button>
                  <button className={`hole-filter-btn ${holeFilter === 'rejected' ? 'is-active' : ''}`} onClick={() => setHoleFilter('rejected')}>Afgewezen</button>
                </div>
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
                {selectedHole && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-stage">
                        {selectedHole.label || formatLabel(selectedHole.type)} | {getHoleStatusLabel(selectedHole.status)}
                      </div>
                      <div className="timeline-text">{selectedHole.reason || 'Geen toelichting'}</div>
                      <pre className="timeline-payload-value">{formatDetailValue(selectedHole.position)}</pre>
                    </div>
                    <div className="reasoning-card">
                      <div className="timeline-title">Criteria</div>
                      <div className="timeline-payload-grid">
                        {(selectedHole.criteria || []).map((criterion, index) => (
                          <div className="timeline-payload-row" key={`${selectedHole.id}-criterion-${index}`}>
                            <div className="timeline-item-head">
                              <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                              <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                                {criterion.passed ? 'Pass' : 'Fail'}
                              </span>
                            </div>
                            <pre className="timeline-payload-value">{formatDetailValue({
                              value: criterion.value,
                              threshold: criterion.threshold,
                              note: criterion.note,
                            })}</pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {selectedHole == null && (
                  <div className="timeline-text" style={{ marginTop: 8 }}>
                    Kies een gat links om criteria en viewer-focus te zien.
                  </div>
                )}
                {visibleHoleItems.length === 0 && (
                  <div className="timeline-text" style={{ marginTop: 8 }}>
                    Geen gaten in deze filter.
                  </div>
                )}
              </div>
            )}

            <div className="timeline-title">Geselecteerde keuze</div>
            <div className="timeline-text">
              {formatLabel(selectedEvent.type)} {selectedEvent.status ? `| ${selectedEvent.status}` : ''}
            </div>
            {selectedPayloadEntries.length === 0 ? (
              <div className="timeline-text">Geen extra details voor dit event.</div>
            ) : (
              <div className="timeline-payload-grid">
                {selectedPayloadEntries.map(([key, value]) => (
                  <div className="timeline-payload-row" key={key}>
                    <div className="timeline-payload-key">{formatLabel(key)}</div>
                    <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                  </div>
                ))}
              </div>
            )}

            {selectedStage.stage === 'Profile Router' && routerVisuals && (
              <div className="visual-stage-card">
                <div className="timeline-title">Router Visualisatie</div>
                <div className="timeline-text">
                  Label: {routerVisuals.profile_label || '-'} | Confidence: {Math.round((routerVisuals.confidence || 0) * 100)}%
                </div>
                <div className="timeline-text">
                  Methode: {routerVisuals.method || '-'} | Secties: {routerVisuals.sections_total || 0}
                </div>
                <div className="timeline-text">{routerVisuals.reason || routerVisuals.reasoning || 'Geen extra router-uitleg'}</div>
                {routerVisuals.features && (
                  <div className="timeline-payload-grid">
                    {Object.entries(routerVisuals.features).map(([key, value]) => (
                      <div className="timeline-payload-row" key={key}>
                        <div className="timeline-payload-key">{formatLabel(key)}</div>
                        <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedStage.stage === 'Classify geometry' && classificationVisuals && (
              <div className="visual-stage-card">
                <div className="timeline-title">Classificatie Basis</div>
                <div className="timeline-text">
                  Categorie: {classificationVisuals.part_category || '-'} | Type: {classificationVisuals.part_type || '-'}
                </div>
                <div className="timeline-text">Dikte: {classificationVisuals.thickness ?? '-'} mm</div>
                <div className="timeline-text">
                  Visualisatie: donkerrood = section contouren, oranje = buitenmaat, roze = tweede maat, geel = dikte-as.
                </div>
                {classificationVisuals.matrix_doc && (
                  <div className="timeline-text">Threshold matrix: {classificationVisuals.matrix_doc}</div>
                )}
                {(classificationVisuals.rules || []).length > 0 && (
                  <div className="timeline-text">
                    Beslispad: {(classificationVisuals.rules || []).join(' -> ')}
                  </div>
                )}
                {(classificationVisuals.criteria || []).length > 0 && (
                  <div className="reasoning-list">
                    {(classificationVisuals.criteria || []).map((criterion, index) => (
                      <div className="reasoning-card" key={`${criterion.step}-${criterion.name}-${index}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">{criterion.step} | {criterion.name}</div>
                          {typeof criterion.passed === 'boolean' && (
                            <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                              {criterion.passed ? 'Pass' : 'Fail'}
                            </span>
                          )}
                        </div>
                        <div className="timeline-text">
                          Actual: {formatDetailValue(criterion.actual)} | Threshold: {formatDetailValue(criterion.threshold)} | Delta: {formatDeviation(criterion.deviation)}
                        </div>
                        {criterion.note && <div className="timeline-text">{criterion.note}</div>}
                      </div>
                    ))}
                  </div>
                )}
                <div className="reasoning-list">
                  {(classificationVisuals.reasoning || []).map((reason, index) => (
                    <div className="reasoning-card" key={`${reason.step}-${index}`}>
                      <div className="timeline-stage">{reason.step}</div>
                      <div className="timeline-text">{reason.observation}</div>
                      <div className="timeline-text">{reason.conclusion}</div>
                      {reason.details && Object.keys(reason.details).length > 0 && (
                        <pre className="timeline-payload-value">{formatDetailValue(reason.details)}</pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedStage.stage === 'Unfold' && unfoldVisuals && (
              <div className="visual-stage-card">
                <div className="timeline-title">Unfold Visualisatie</div>
                <div className="timeline-text">
                  Fold lines: {unfoldVisuals.fold_lines || 0} | Flat: {unfoldVisuals.flat_length || '-'} x {unfoldVisuals.flat_width || '-'}
                </div>
                <div className="timeline-text">
                  Als er een flat mesh is, schakelt de viewer hier naar de uitslagweergave in plaats van het 3D-model.
                </div>
                <div className="reasoning-list">
                  {(unfoldVisuals.fold_details || []).map((fold, index) => (
                    <div className="reasoning-card" key={`fold-${index}`}>
                      <div className="timeline-stage">Fold {fold.id || index + 1}</div>
                      <div className="timeline-text">Lengte: {fold.length || '-'}</div>
                      <pre className="timeline-payload-value">{formatDetailValue(fold.center)}</pre>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
