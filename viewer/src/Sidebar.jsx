import React, { useEffect, useMemo, useState } from 'react'

const STATUS_LABELS = {
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

function summarizePayload(payload) {
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

function parseIsoToMs(value) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function formatDuration(seconds) {
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

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatDetailValue(value) {
  if (value === null || value === undefined || value === '') return 'n.v.t.'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'boolean') return value ? 'ja' : 'nee'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export default function Sidebar({
  modelInfo,
  fileName,
  onReset,
  pipelineEnabled,
  onPipelineToggle,
  pipelineApiBase,
  onPipelineApiBaseChange,
  pipelineApiKey,
  onPipelineApiKeyChange,
  pipelineState,
  pipelineVisuals,
  onStageFocus,
  onRetryPipeline,
}) {
  const events = pipelineState?.events || []
  const summary = pipelineState?.summary
  const pipelineResult = pipelineState?.result
  const [nowMs, setNowMs] = useState(() => Date.now())
  const groupedStages = useMemo(() => {
    const order = []
    const map = new Map()

    events.forEach((event, index) => {
      const stageKey = event.stage || 'Onbekende stap'
      if (!map.has(stageKey)) {
        const group = { stage: stageKey, events: [], firstIndex: index }
        map.set(stageKey, group)
        order.push(group)
      }
      map.get(stageKey).events.push({ ...event, originalIndex: index })
    })

    return order
  }, [events])
  const [selectedStageIndex, setSelectedStageIndex] = useState(0)
  const [selectedEventIndex, setSelectedEventIndex] = useState(0)
  const selectedStage = groupedStages[selectedStageIndex] || null
  const selectedEvent = selectedStage?.events?.[selectedEventIndex] || null
  const selectedPayloadEntries = Object.entries(selectedEvent?.payload || {})
    .filter(([, value]) => value !== undefined)
  const analysisStartedMs = parseIsoToMs(summary?.analysis_started_at)
  const activeStageStartedMs = parseIsoToMs(summary?.active_stage_started_at)
  const liveTotalElapsed =
    pipelineState?.status === 'processing' && analysisStartedMs
      ? Math.max(0, (nowMs - analysisStartedMs) / 1000)
      : summary?.total_elapsed_seconds
  const liveActiveElapsed =
    pipelineState?.status === 'processing' && summary?.active_stage && activeStageStartedMs
      ? Math.max(0, (nowMs - activeStageStartedMs) / 1000)
      : summary?.active_stage_elapsed_seconds
  const totalStepsHint = summary?.total_steps_hint || summary?.step_count || groupedStages.length
  const completedStepCount = summary?.completed_step_count || 0

  useEffect(() => {
    setSelectedStageIndex(0)
    setSelectedEventIndex(0)
  }, [events])

  useEffect(() => {
    setSelectedEventIndex(0)
  }, [selectedStageIndex])

  useEffect(() => {
    onStageFocus?.(selectedStage?.stage || null)
  }, [onStageFocus, selectedStage])

  useEffect(() => {
    if (pipelineState?.status !== 'processing') return undefined
    const id = window.setInterval(() => setNowMs(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [pipelineState?.status])

  const routerVisuals = pipelineVisuals?.router || null
  const classificationVisuals = pipelineVisuals?.classification || null
  const holeVisuals = pipelineVisuals?.holes || null
  const unfoldVisuals = pipelineVisuals?.unfold || null

  function getStageMeta(group) {
    const finishedEvent = [...group.events].reverse().find((event) =>
      ['stage_end', 'stage_failed', 'stage_skipped'].includes(event.type)
    )

    if (finishedEvent) {
      let stateLabel = 'Klaar'
      if (finishedEvent.type === 'stage_failed') stateLabel = 'Mislukt'
      if (finishedEvent.type === 'stage_skipped') stateLabel = 'Overgeslagen'
      return {
        stateLabel,
        elapsed: finishedEvent.payload?.elapsed_seconds,
      }
    }

    if (summary?.active_stage === group.stage) {
      return {
        stateLabel: 'Bezig',
        elapsed: liveActiveElapsed,
      }
    }

    if (group.events.some((event) => event.type === 'stage_start')) {
      return {
        stateLabel: 'Gestart',
        elapsed: null,
      }
    }

    return {
      stateLabel: `${group.events.length} events`,
      elapsed: null,
    }
  }

  return (
    <div className="sidebar">
      <div className="sidebar-section">
        <h3>Bestand</h3>
        {fileName ? (
          <>
            <div className="sidebar-row">
              <span className="label">Naam</span>
              <span className="value">{fileName}</span>
            </div>
            <button className="toolbar-btn" style={{ marginTop: 8, width: '100%' }} onClick={onReset}>
              Nieuw bestand laden
            </button>
          </>
        ) : (
          <div style={{ fontSize: '0.85rem', color: '#999' }}>Geen bestand geladen</div>
        )}
      </div>

      {modelInfo && (
        <div className="sidebar-section">
          <h3>3D Model</h3>
          <div className="sidebar-row">
            <span className="label">Vertices</span>
            <span className="value">{modelInfo.vertexCount?.toLocaleString() || '-'}</span>
          </div>
          <div className="sidebar-row">
            <span className="label">Driehoeken</span>
            <span className="value">{modelInfo.triangleCount?.toLocaleString() || '-'}</span>
          </div>
        </div>
      )}

      <div className="sidebar-section">
        <h3>Pipeline Koppeling</h3>
        <label className="sidebar-toggle">
          <input
            type="checkbox"
            checked={pipelineEnabled}
            onChange={(event) => onPipelineToggle(event.target.checked)}
          />
          <span>Manufacturing/Profile pipeline inschakelen</span>
        </label>

        <div style={{ marginTop: 10 }}>
          <div className="sidebar-row" style={{ paddingBottom: 6 }}>
            <span className="label">API status</span>
            <span className={`status-pill status-${pipelineState?.status || 'idle'}`}>
              {STATUS_LABELS[pipelineState?.status] || pipelineState?.status || 'Onbekend'}
            </span>
          </div>
          <input
            className="sidebar-input"
            value={pipelineApiBase}
            onChange={(event) => onPipelineApiBaseChange(event.target.value)}
            placeholder="http://localhost:8000"
          />
          <input
            className="sidebar-input"
            style={{ marginTop: 8 }}
            value={pipelineApiKey}
            onChange={(event) => onPipelineApiKeyChange(event.target.value)}
            placeholder="Optionele X-API-Key"
          />
          {pipelineState?.jobId && (
            <div className="sidebar-row" style={{ marginTop: 6 }}>
              <span className="label">Job ID</span>
              <span className="value" style={{ maxWidth: 170, wordBreak: 'break-all' }}>
                {pipelineState.jobId}
              </span>
            </div>
          )}
          {pipelineState?.error && (
            <div className="sidebar-error">{pipelineState.error}</div>
          )}
          {fileName && pipelineEnabled && (
            <button className="toolbar-btn" style={{ marginTop: 8, width: '100%' }} onClick={onRetryPipeline}>
              Pipeline analyse opnieuw
            </button>
          )}
        </div>
      </div>

      <div className="sidebar-section">
        <h3>Keuzes Per Stap</h3>
        {summary && (
          <div className="timeline-summary">
            <div>{completedStepCount}/{totalStepsHint} stappen klaar</div>
            <div>{summary.event_count || 0} events</div>
            <div>{formatDuration(liveTotalElapsed)}</div>
            <div>
              {summary.active_stage
                ? `${summary.active_stage} actief · ${formatDuration(liveActiveElapsed)}`
                : 'Geen actieve stap'}
            </div>
          </div>
        )}
        {pipelineResult?.route && (
          <div className="timeline-card">
            <div className="timeline-title">Classificatie keuze</div>
            <div className="timeline-text">
              {pipelineResult.route.category || 'onbekend'} | {pipelineResult.route.profile_label || '-'}
            </div>
            <div className="timeline-text">{pipelineResult.route.reasoning || 'Geen toelichting'}</div>
          </div>
        )}
        {events.length === 0 ? (
          <div style={{ fontSize: '0.82rem', color: '#888', lineHeight: 1.5 }}>
            Nog geen timeline events. Laad een STEP bestand om de analysebeslissingen per stap te zien.
          </div>
        ) : (
          <>
            <div className="timeline-stage-list">
              {groupedStages.map((group, index) => (
                (() => {
                  const stageMeta = getStageMeta(group)
                  return (
                    <button
                      key={`${group.stage}-${group.firstIndex}`}
                      className={`timeline-stage-button ${selectedStageIndex === index ? 'is-active' : ''}`}
                      onClick={() => setSelectedStageIndex(index)}
                    >
                      <span className="timeline-stage-button-copy">
                        <span className="timeline-stage-button-title">{group.stage}</span>
                        <span className="timeline-stage-button-meta">{stageMeta.stateLabel}</span>
                      </span>
                      <span className="timeline-stage-button-side">
                        <span className="timeline-stage-button-time">{formatDuration(stageMeta.elapsed)}</span>
                        <span className="timeline-stage-button-meta">{group.events.length} events</span>
                      </span>
                    </button>
                  )
                })()
              ))}
            </div>

            {selectedStage && (
              <div className="timeline-detail-card">
                <div className="timeline-detail-head">
                    <div>
                      <div className="timeline-title">{selectedStage.stage}</div>
                      <div className="timeline-text">
                        Stap {selectedStageIndex + 1} van {groupedStages.length}
                      </div>
                      <div className="timeline-text">
                        {(() => {
                          const stageMeta = getStageMeta(selectedStage)
                          return `${stageMeta.stateLabel} · ${formatDuration(stageMeta.elapsed)}`
                        })()}
                      </div>
                    </div>
                  <div className="timeline-nav">
                    <button
                      className="timeline-nav-btn"
                      onClick={() => setSelectedStageIndex((value) => Math.max(0, value - 1))}
                      disabled={selectedStageIndex === 0}
                    >
                      Vorige
                    </button>
                    <button
                      className="timeline-nav-btn"
                      onClick={() => setSelectedStageIndex((value) => Math.min(groupedStages.length - 1, value + 1))}
                      disabled={selectedStageIndex === groupedStages.length - 1}
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
                      onClick={() => setSelectedEventIndex(index)}
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

                    {selectedStage.stage === 'Detect holes' && holeVisuals && (
                      <div className="visual-stage-card">
                        <div className="timeline-title">Hole Overlay</div>
                        <div className="timeline-text">
                          Bron: {holeVisuals.source || '-'} | Totaal: {holeVisuals.total || 0}
                        </div>
                        <div className="timeline-text">
                          De gaten worden nu als echte edge-traces met leader line getoond op de brongeometrie. Bij `flat` schakelt de viewer automatisch naar de uitslag.
                        </div>
                        <div className="reasoning-list">
                          {(holeVisuals.items || []).map((hole, index) => (
                            <div className="reasoning-card" key={`${hole.type}-${index}`}>
                              <div className="timeline-stage">{formatLabel(hole.type)} {hole.label ? `| ${hole.label}` : ''}</div>
                              <div className="timeline-text">{hole.reason || 'Geen toelichting'}</div>
                              <pre className="timeline-payload-value">{formatDetailValue(hole.position)}</pre>
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
            )}
          </>
        )}
      </div>

      <div className="sidebar-section">
        <h3>Bediening</h3>
        <div style={{ fontSize: '0.82rem', color: '#888', lineHeight: 1.6 }}>
          🖱 Links slepen — roteren<br />
          🖱 Scrollwiel — zoomen
        </div>
      </div>

      <div className="sidebar-section">
        <h3>Engine</h3>
        <div className="sidebar-row">
          <span className="label">Backend</span>
          <span className="value">OpenCascade WASM</span>
        </div>
        <div className="sidebar-row">
          <span className="label">Viewer</span>
          <span className="value">buerli.io + Three.js</span>
        </div>
      </div>
    </div>
  )
}
