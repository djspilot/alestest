import React, { useMemo, useState } from 'react'

function formatValue(value) {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'NaN'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export default function DebugPanel({
  viewer,
  pipeline,
  parseMode,
  activeMesh,
}) {
  const [copyState, setCopyState] = useState('idle')
  const combinedEvents = useMemo(
    () => [...(viewer.debugEvents || []), ...(pipeline.debugEvents || [])].sort((a, b) => {
      const left = new Date(a.timestamp || 0).getTime()
      const right = new Date(b.timestamp || 0).getTime()
      return left - right
    }),
    [pipeline.debugEvents, viewer.debugEvents],
  )

  const summary = useMemo(
    () => [
      { label: 'Engine status', value: viewer.engineStatus },
      { label: 'Loading', value: viewer.loading },
      { label: 'Bestand', value: viewer.fileName || '—' },
      { label: 'Buffer bytes', value: viewer.fileBuffer?.byteLength || 0 },
      { label: 'Actieve mesh', value: Boolean(activeMesh) },
      { label: 'Parse mode', value: parseMode },
      { label: 'Viewer fout', value: viewer.error || '—' },
      { label: 'Pipeline status', value: pipeline.pipelineState?.status || 'idle' },
      { label: 'Pipeline job', value: pipeline.pipelineState?.jobId || '—' },
      { label: 'Actieve stage', value: pipeline.summary?.active_stage || '—' },
      { label: 'Pipeline fout', value: pipeline.pipelineState?.error || '—' },
      { label: 'Unfold success', value: pipeline.pipelineState?.result?.visuals?.unfold?.success ?? '—' },
      { label: 'Unfold fold_lines', value: pipeline.pipelineState?.result?.visuals?.unfold?.fold_lines ?? '—' },
      { label: 'Unfold raw_fold_lines', value: pipeline.pipelineState?.result?.visuals?.unfold?.raw_fold_lines ?? '—' },
      { label: 'Pipeline debug code', value: pipeline.pipelineState?.debug?.code || '—' },
      { label: 'Pipeline debug bericht', value: pipeline.pipelineState?.debug?.message || '—' },
      { label: 'Health URL', value: pipeline.pipelineState?.debug?.checkedUrl || '—' },
      { label: 'API base', value: pipeline.pipelineApiBase || '—' },
      { label: 'User agent', value: navigator.userAgent },
    ],
    [
      activeMesh,
      parseMode,
      pipeline.pipelineApiBase,
      pipeline.pipelineState?.debug?.checkedUrl,
      pipeline.pipelineState?.debug?.code,
      pipeline.pipelineState?.debug?.message,
      pipeline.pipelineState?.error,
      pipeline.pipelineState?.jobId,
      pipeline.pipelineState?.result?.visuals?.unfold?.fold_lines,
      pipeline.pipelineState?.result?.visuals?.unfold?.raw_fold_lines,
      pipeline.pipelineState?.result?.visuals?.unfold?.success,
      pipeline.pipelineState?.status,
      pipeline.summary?.active_stage,
      viewer.engineStatus,
      viewer.error,
      viewer.fileBuffer,
      viewer.fileName,
      viewer.loading,
    ],
  )

  const copyDebugDump = async () => {
    const unfoldVisuals = pipeline.pipelineState?.result?.visuals?.unfold || null
    const payload = {
      generatedAt: new Date().toISOString(),
      summary: Object.fromEntries(summary.map((item) => [item.label, item.value])),
      viewerEvents: viewer.debugEvents || [],
      pipelineDebugEvents: pipeline.debugEvents || [],
      pipelineEvents: pipeline.debugEvents || [],
      timelineEvents: pipeline.pipelineState?.events || [],
      timelineSummary: pipeline.pipelineState?.summary || null,
      unfoldStatus: unfoldVisuals
        ? {
            success: unfoldVisuals.success ?? null,
            fold_lines: unfoldVisuals.fold_lines ?? null,
            raw_fold_lines: unfoldVisuals.raw_fold_lines ?? null,
            error: unfoldVisuals.error ?? null,
            attempts: unfoldVisuals.attempts ?? null,
            route: unfoldVisuals.route ?? null,
          }
        : null,
      events: combinedEvents,
      pipelineDebug: pipeline.pipelineState?.debug || null,
    }
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 1500)
    } catch {
      setCopyState('failed')
      window.setTimeout(() => setCopyState('idle'), 1500)
    }
  }

  return (
    <div className="debug-panel">
      <div className="debug-panel-head">
        <strong>Viewer debug</strong>
        <button className="toolbar-btn" type="button" onClick={copyDebugDump}>
          {copyState === 'copied' ? 'Gekopieerd' : copyState === 'failed' ? 'Copy faalde' : 'Kopieer debug'}
        </button>
      </div>

      <div className="debug-summary-grid">
        {summary.map((item) => (
          <div className="debug-summary-row" key={item.label}>
            <span className="debug-summary-label">{item.label}</span>
            <span className="debug-summary-value">{formatValue(item.value)}</span>
          </div>
        ))}
      </div>

      <div className="debug-event-list">
        {combinedEvents.length === 0 ? (
          <div className="debug-empty">Nog geen debug-events. Laad een STEP-bestand om de keten te volgen.</div>
        ) : (
          [...combinedEvents].reverse().map((event) => (
            <div className="debug-event" key={event.id}>
              <div className="debug-event-head">
                <span className="debug-event-source">{event.source || 'viewer'}</span>
                <span className="debug-event-stage">{event.stage || 'event'}</span>
                <span className="debug-event-time">{new Date(event.timestamp).toLocaleTimeString()}</span>
              </div>
              <pre className="debug-event-body">{JSON.stringify(event, null, 2)}</pre>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
