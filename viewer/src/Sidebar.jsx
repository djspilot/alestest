import React, { useState } from 'react'
import { normalizeStageName, STATUS_LABELS, formatDuration, getStageMeta } from './pipelineUi'

export default function Sidebar({
  modelInfo,
  fileName,
  onReset,
  pipelineEnabled,
  onPipelineToggle,
  aagFallbackEnabled,
  onAagFallbackToggle,
  disabledStages,
  onStageToggle,
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
  pipelineDebug,
  onResetPipelineApiBase,
}) {
  const [showExtraOptions, setShowExtraOptions] = useState(false)

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
        <label className="sidebar-toggle" style={{ marginTop: 8, opacity: pipelineEnabled ? 1 : 0.6 }}>
          <input
            type="checkbox"
            checked={aagFallbackEnabled}
            onChange={(event) => onAagFallbackToggle(event.target.checked)}
            disabled={!pipelineEnabled}
          />
          <span>AAG fallback inschakelen</span>
        </label>

        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: '0.82rem', color: '#888', marginBottom: 6 }}>Analyse fases</div>
          {[
            { key: 'classify_geometry', label: 'Profile Router (classif.)' },
            { key: 'detect_holes_pre_unfold', label: 'Detect holes (pre-unfold)' },
            { key: 'unfold', label: 'Unfold' },
            { key: 'detect_holes', label: 'Detect holes' },
            { key: 'aag', label: 'AAG analyse' },
          ].map(({ key, label }) => (
            <label className="sidebar-toggle" key={key} style={{ opacity: pipelineEnabled ? 1 : 0.6 }}>
              <input
                type="checkbox"
                checked={!disabledStages.includes(key)}
                onChange={(event) => onStageToggle(key, event.target.checked)}
                disabled={!pipelineEnabled}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>

      </div>

      <div className="sidebar-section">
        <h3>Keuzes Per Stap</h3>
        {summary && (
          <div className="timeline-summary">
            <div>
              {completedStepCount}/{totalStepsHint} stappen klaar
            </div>
            <div>{summary.event_count || 0} events</div>
            <div>{formatDuration(liveTotalElapsed)}</div>
            <div>
              {summary.active_stage
                ? `${normalizeStageName(summary.active_stage)} actief · ${formatDuration(liveActiveElapsed)}`
                : 'Geen actieve stap'}
            </div>
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
        <button
          className="toolbar-btn"
          style={{ width: '100%' }}
          onClick={() => setShowExtraOptions((value) => !value)}
        >
          {showExtraOptions ? 'Verberg extra opties' : 'Toon extra opties'}
        </button>

        {showExtraOptions && (
          <div style={{ marginTop: 10 }}>
            <h3 style={{ marginTop: 0 }}>API status</h3>
            <div className="sidebar-row" style={{ paddingBottom: 6 }}>
              <span className="label">Status</span>
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
            {(pipelineState?.status === 'unavailable' ||
              pipelineState?.status === 'failed' ||
              pipelineState?.status === 'auth_required') && (
              <div style={{ marginTop: 8, fontSize: '0.78rem', color: '#888', lineHeight: 1.45 }}>
                <div>
                  <strong>Debug</strong>
                </div>
                {pipelineDebug?.checkedBase && <div>Base: {pipelineDebug.checkedBase}</div>}
                {pipelineDebug?.checkedUrl && <div>Check: {pipelineDebug.checkedUrl}</div>}
                {pipelineDebug?.code && <div>Code: {pipelineDebug.code}</div>}
                {pipelineDebug?.fallbackBase && <div>Fallback: {pipelineDebug.fallbackBase}</div>}
                {pipelineDebug?.fallbackUrl && <div>Fallback check: {pipelineDebug.fallbackUrl}</div>}
                <button className="toolbar-btn" style={{ marginTop: 8, width: '100%' }} onClick={onResetPipelineApiBase}>
                  API URL reset naar launcher default
                </button>
              </div>
            )}
            {fileName && pipelineEnabled && (
              <button className="toolbar-btn" style={{ marginTop: 8, width: '100%' }} onClick={onRetryPipeline}>
                Pipeline analyse opnieuw
              </button>
            )}

            {modelInfo && (
              <>
                <h3>3D Model</h3>
                <div className="sidebar-row">
                  <span className="label">Vertices</span>
                  <span className="value">{modelInfo.vertexCount?.toLocaleString() || '-'}</span>
                </div>
                <div className="sidebar-row">
                  <span className="label">Driehoeken</span>
                  <span className="value">{modelInfo.triangleCount?.toLocaleString() || '-'}</span>
                </div>
              </>
            )}

            <h3>Bediening</h3>
            <div style={{ fontSize: '0.82rem', color: '#888', lineHeight: 1.6 }}>
              🖱 Links slepen — roteren
              <br />
              🖱 Scrollwiel — zoomen
            </div>

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
        )}
      </div>
    </div>
  )
}
