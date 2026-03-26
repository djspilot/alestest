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
  if (status === 'probe') return 'Handmatige probe'
  return status || 'Onbekend'
}

function getClassificationStatusLabel(status) {
  if (status === 'WINNER') return 'Winner'
  if (status === 'MATCH') return 'Match'
  if (status === 'PASS') return 'Pass'
  if (status === 'FAIL') return 'Fail'
  if (status === 'SKIP') return 'Skip'
  if (status === 'FALLTHROUGH') return 'Fallthrough'
  return status || 'Onbekend'
}

function getClassificationStatusClass(status) {
  if (status === 'WINNER' || status === 'MATCH') return 'is-winner'
  if (status === 'PASS') return 'is-accepted'
  if (status === 'FAIL') return 'is-rejected'
  if (status === 'FALLTHROUGH') return 'is-warning'
  return 'is-neutral'
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
  selectedProbe,
  pipelineStatus,
}) {
  const [holeFilter, setHoleFilter] = useState('all')
  const selectedStage = groupedStages[selectedStageIndex] || null
  const selectedEvent = selectedStage?.events?.[selectedEventIndex] || null
  const selectedPayloadEntries = Object.entries(selectedEvent?.payload || {})
    .filter(([, value]) => value !== undefined)

  const routerVisuals = pipelineVisuals?.router || null
  const classificationVisuals = pipelineVisuals?.classification || null
  const classificationFinal = classificationVisuals?.final_decision || null
  const step0Review = classificationVisuals?.step0_review || null
  const legacyClassification = classificationVisuals?.legacy_classification || null
  const holeVisuals = pipelineVisuals?.holes || null
  const unfoldVisuals = pipelineVisuals?.unfold || null
  const holeItems = holeVisuals?.items || []
  const selectedHole = holeItems.find((hole) => hole.id === selectedHoleId) || null
  const selectedInspection = selectedHole || selectedProbe
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
                {holeVisuals.criteria_note && (
                  <div className="timeline-text">{holeVisuals.criteria_note}</div>
                )}
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
                  Klik op een gat om exact de gedetecteerde hole-rand te highlighten en de camera erop te focussen. In `Probe mode` wordt elke klik op het model altijd een probe op exact die plek, zonder snap naar een bekende hole.
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
                {selectedInspection && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-stage">
                        {selectedInspection.label || formatLabel(selectedInspection.type)} | {getHoleStatusLabel(selectedInspection.status)}
                      </div>
                      <div className="timeline-text">{selectedInspection.reason || 'Geen toelichting'}</div>
                      <pre className="timeline-payload-value">{formatDetailValue(selectedInspection.position)}</pre>
                      {selectedInspection.inferredContour && (
                        <div className="timeline-text">
                          Inferred contour: {selectedInspection.inferredContour.label || formatLabel(selectedInspection.inferredContour.type)}
                        </div>
                      )}
                      {selectedInspection.nearestHole && (
                        <div className="timeline-text">
                          Dichtstbijzijnde bekende kandidaat: {selectedInspection.nearestHole.label || formatLabel(selectedInspection.nearestHole.type)} op {formatDetailValue(selectedInspection.nearestHoleDistance)} mm.
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
                            <pre className="timeline-payload-value">{formatDetailValue({
                              value: criterion.value,
                              threshold: criterion.threshold,
                              note: criterion.note,
                            })}</pre>
                          </div>
                        ))}
                      </div>
                    </div>
                    {selectedInspection.inferredContour?.debug && (
                      <div className="reasoning-card">
                        <div className="timeline-title">Probe Debug</div>
                        <div className="timeline-text">
                          Viewer heuristic: {selectedInspection.inferredContour.debug.inferred_family} | confidence {formatDetailValue(selectedInspection.inferredContour.debug.confidence)}
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
                {selectedInspection == null && (
                  <div className="timeline-text" style={{ marginTop: 8 }}>
                    Kies een gat links of klik in het 3D-model om criteria en viewer-focus te zien.
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

            {selectedStage.stage === 'Classify geometry' && classificationVisuals && (
              <div className="visual-stage-card">
                <div className="timeline-title">Classificatie Flow</div>
                <div className="timeline-text">
                  Categorie: {classificationVisuals.part_category || '-'} | Type: {classificationVisuals.part_type || '-'}
                </div>
                <div className="timeline-text">Dikte: {classificationVisuals.thickness ?? '-'} mm</div>
                <div className="timeline-text">
                  Visualisatie: donkerrood = section contouren, oranje = buitenmaat, roze = tweede maat, geel = dikte-as.
                </div>

                {routerVisuals && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Voorclassificatie uit sections</div>
                        <span className="hole-status-pill is-warning">Router ingebed</span>
                      </div>
                      <div className="timeline-text">
                        Router category: {routerVisuals.category || '-'} | Label: {routerVisuals.profile_label || '-'}
                      </div>
                      <div className="timeline-text">
                        Confidence: {Math.round((routerVisuals.confidence || 0) * 100)}% | Methode: {routerVisuals.method || '-'}
                      </div>
                      <div className="timeline-text">
                        {routerVisuals.reason || routerVisuals.reasoning || 'Geen extra router-uitleg'}
                      </div>
                      {routerVisuals.features && (
                        <div className="timeline-payload-grid">
                          {Object.entries(routerVisuals.features).map(([key, value]) => (
                            <div className="timeline-payload-row" key={`router-${key}`}>
                              <div className="timeline-payload-key">{formatLabel(key)}</div>
                              <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {classificationFinal && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Eindbesluit</div>
                        <span className={`hole-status-pill ${classificationFinal.step0_only ? 'is-accepted' : 'is-warning'}`}>
                          {classificationFinal.step0_only ? 'Step 0 only' : 'Step 0 -> legacy'}
                        </span>
                      </div>
                      <div className="timeline-text">
                        Klasse: {formatLabel(classificationFinal.classification)} | Gestopt in: {classificationFinal.stopped_in || '-'}
                      </div>
                      <div className="timeline-text">
                        Bron: {classificationFinal.source || '-'}
                      </div>
                    </div>
                  </div>
                )}

                {step0Review && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Step 0 Review</div>
                        <span className={`hole-status-pill ${step0Review.fallthrough ? 'is-warning' : 'is-accepted'}`}>
                          {step0Review.fallthrough ? 'Fallthrough' : 'Besliste'}
                        </span>
                      </div>
                      <div className="timeline-text">
                        Bron: {step0Review.doc || classificationVisuals.step0_doc || 'docs/classification_step_review.md'}
                      </div>
                      {step0Review.stopped_in && (
                        <div className="timeline-text">Stopte in: {step0Review.stopped_in}</div>
                      )}
                      {step0Review.error && (
                        <div className="timeline-text">Trace-fout: {step0Review.error}</div>
                      )}
                    </div>
                    {(step0Review.steps || []).map((step) => (
                      <div className="reasoning-card" key={`step0-${step.step}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">{step.step} | {step.name}</div>
                          <span className={`hole-status-pill ${getClassificationStatusClass(step.status)}`}>
                            {getClassificationStatusLabel(step.status)}
                          </span>
                        </div>
                        {step.result && <div className="timeline-text">Resultaat: {formatLabel(step.result)}</div>}
                        {step.next && <div className="timeline-text">Volgende stap: {step.next}</div>}
                        {step.note && <div className="timeline-text">{step.note}</div>}
                        <div className="timeline-payload-grid">
                          {(step.criteria || []).map((criterion, index) => (
                            <div className="timeline-payload-row" key={`step0-${step.step}-${criterion.name}-${index}`}>
                              <div className="timeline-item-head">
                                <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                                {typeof criterion.passed === 'boolean' && (
                                  <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                                    {criterion.passed ? 'Pass' : 'Fail'}
                                  </span>
                                )}
                                {criterion.passed == null && (
                                  <span className="hole-status-pill is-neutral">Info</span>
                                )}
                              </div>
                              <div className="timeline-text">
                                Actual: {formatDetailValue(criterion.actual)} | Threshold: {formatDetailValue(criterion.threshold)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {legacyClassification && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Legacy Classify Fallback</div>
                        <span className="hole-status-pill is-warning">Actief</span>
                      </div>
                      <div className="timeline-text">
                        Bron: {legacyClassification.doc || classificationVisuals.matrix_doc || 'docs/CLASSIFICATION_THRESHOLDS_MATRIX.md'}
                      </div>
                      {legacyClassification.winner_gate && (
                        <div className="timeline-text">Winnende gate: STEP {legacyClassification.winner_gate}</div>
                      )}
                      {(legacyClassification.rules || []).length > 0 && (
                        <div className="timeline-text">
                          Beslispad: {(legacyClassification.rules || []).join(' -> ')}
                        </div>
                      )}
                    </div>
                    {(legacyClassification.gates || []).map((gate) => (
                      <div className="reasoning-card" key={`legacy-${gate.step}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">STEP {gate.step} | {gate.name}</div>
                          <span className={`hole-status-pill ${getClassificationStatusClass(gate.status)}`}>
                            {getClassificationStatusLabel(gate.status)}
                          </span>
                        </div>
                        <div className="timeline-text">{gate.description}</div>
                        {gate.rule && <div className="timeline-text">Winnende rule: {gate.rule}</div>}
                        <div className="timeline-payload-grid">
                          {(gate.criteria || []).map((criterion, index) => (
                            <div className="timeline-payload-row" key={`legacy-${gate.step}-${criterion.name}-${index}`}>
                              <div className="timeline-item-head">
                                <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
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
                      </div>
                    ))}
                  </div>
                )}

                {!step0Review && (classificationVisuals.matrix_doc || (classificationVisuals.rules || []).length > 0) && (
                  <div className="timeline-text">
                    Bron: {classificationVisuals.matrix_doc || '-'}
                  </div>
                )}

                {!step0Review && (classificationVisuals.criteria || []).length > 0 && (
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

                {(classificationVisuals.reasoning || []).length > 0 && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-stage">Aanvullende reasoning</div>
                      <div className="timeline-text">
                        Deze uitleg komt uit de geometrie-analyse en ondersteunt de classify-flow hierboven.
                      </div>
                    </div>
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
                )}
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
