import React from 'react'
import { STATUS_LABELS, formatDuration, getStageMeta } from './pipelineUi'

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
  groupedStages,
  summary,
  pipelineResult,
  totalStepsHint,
  completedStepCount,
  liveTotalElapsed,
  liveActiveElapsed,
  selectedStageIndex,
  onSelectStageIndex,
  onRetryPipeline,
  pipelineStatus,
}) {
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
          {pipelineState?.error && <div className="sidebar-error">{pipelineState.error}</div>}
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
        {groupedStages.length === 0 ? (
          <div style={{ fontSize: '0.82rem', color: '#888', lineHeight: 1.5 }}>
            Nog geen timeline events. Laad een STEP bestand om de analysebeslissingen per stap te zien.
          </div>
        ) : (
          <div className="timeline-stage-list">
            {groupedStages.map((group, index) => {
              const stageMeta = getStageMeta(group, summary, liveActiveElapsed, pipelineStatus)
              return (
                <button
                  key={`${group.stage}-${group.firstIndex}`}
                  className={`timeline-stage-button ${selectedStageIndex === index ? 'is-active' : ''}`}
                  onClick={() => {
                    if (!stageMeta.isSelectable) return
                    onSelectStageIndex(index)
                  }}
                  disabled={!stageMeta.isSelectable}
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
            })}
          </div>
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
