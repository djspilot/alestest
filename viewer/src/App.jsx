import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Dropzone from './Dropzone'
import DebugPanel from './DebugPanel'
import StageDetailsPanel from './StageDetailsPanel'
import { PipelineProvider, usePipelineContext } from './context/PipelineContext'
import { useSelection } from './hooks/useSelection'
import { useViewer } from './hooks/useViewer'
import { fetchFileAsBrowserFile } from './lib/files'
import { normalizeStageName, MERGED_HOLES_STAGE, getPartTimelineEvents, groupEventsByStage } from './pipelineUi'
import { getApiKeyHeaders, getDefaultPipelineApiBase } from './pipelineClient'
import { getViewerMaterialPresets, getViewerRenderModes } from './StepModel'

import { normalizeFoldId, normalizeUnfoldVisuals } from './lib/holes'

import { EMPTY_PIPELINE_STATE } from './hooks/usePipeline'

const ViewerCanvas = lazy(() => import('./ViewerCanvas'))

const VIEWER_REVISION = '026734d'

function mergeJobWithUnfoldResult(job, unfoldStatus) {
  const unfoldResult = normalizeUnfoldVisuals(unfoldStatus?.result)
  if (!job || !unfoldResult) return job

  const visuals = { ...(job.result?.visuals || {}) }
  visuals.unfold = {
    ...(visuals.unfold || {}),
    ...unfoldResult,
  }

  return {
    ...job,
    unfold: unfoldStatus,
    result: job.result
      ? {
          ...job.result,
          visuals,
        }
      : job.result,
  }
}

function mergePartWithUnfoldResult(result, partIndex, unfoldStatus) {
  const unfoldResult = normalizeUnfoldVisuals(unfoldStatus?.result)
  if (!result?.is_assembly || partIndex == null || !unfoldResult) return result

  const parts = [...(result.parts || [])]
  const currentPart = parts[partIndex]
  if (!currentPart) return result

  parts[partIndex] = {
    ...currentPart,
    unfold: unfoldStatus,
    visuals: {
      ...(currentPart.visuals || {}),
      unfold: {
        ...(currentPart.visuals?.unfold || {}),
        ...unfoldResult,
      },
    },
  }

  return {
    ...result,
    parts,
  }
}

function resolvePartFromJob(job, partIndex) {
  if (partIndex == null) return null
  const parts = job?.result?.parts || []
  return (
    parts.find((part, index) => {
      const solidIndex = Number.isInteger(part?.solid_index) ? part.solid_index : index
      return solidIndex === partIndex
    }) || null
  )
}

function getTimelineForJobView(job, partIndex) {
  const part = resolvePartFromJob(job, partIndex)
  if (part) {
    const partEvents = getPartTimelineEvents(part)
    if (partEvents.length > 0) {
      return {
        events: partEvents,
        summary: part.timeline_summary || job?.timeline_summary || null,
      }
    }
    return {
      events: job?.timeline_events || [],
      summary: job?.timeline_summary || null,
    }
  }
  return {
    events: job?.timeline_events || [],
    summary: job?.timeline_summary || null,
  }
}

function ViewerCanvasFallback() {
  return (
    <div className="loading-overlay">
      <div className="spinner" />
      <div className="loading-text">3D engine laden...</div>
      <div className="loading-sub">Three.js en viewer chunk worden opgehaald</div>
    </div>
  )
}

function AppContent({
  selectedPartIndex,
  setSelectedPartIndex,
  effectivePipelineVisuals,
  effectiveGroupedStages,
  effectiveSummary,
  effectiveBackendMesh,
  effectiveFlatMesh,
}) {
  const controlsRef = useRef()
  const launchParamsRef = useRef(null)
  if (!launchParamsRef.current) {
    launchParamsRef.current = new URLSearchParams(window.location.search)
  }
  const launchParams = launchParamsRef.current
  const launchedFromJob = launchParams.has('job')
  const launchedPartIndex = useMemo(() => {
    const raw = launchParams.get('part')
    if (raw == null || raw === '') return null
    const value = Number.parseInt(raw, 10)
    return Number.isFinite(value) ? value : null
  }, [launchParams])
  const launchApiBase = launchParams.get('api') || getDefaultPipelineApiBase()
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [debugPanelOpen, setDebugPanelOpen] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [loadingDefaultStep, setLoadingDefaultStep] = useState(false)
  const [materialPreset, setMaterialPreset] = useState(() => window.localStorage.getItem('ales-viewer-material-preset') || 'technical_steel')
  const [renderMode, setRenderMode] = useState(() => {
    const saved = window.localStorage.getItem('ales-viewer-render-mode')
    if (!saved || saved === 'studio') return 'analysis'
    return saved
  })
  const [lightMode, setLightMode] = useState(() => {
    const saved = window.localStorage.getItem('ales-viewer-light-mode')
    if (!saved || saved === 'soft') return 'bright'
    return saved
  })
  const materialOptions = useMemo(
    () =>
      Object.entries(getViewerMaterialPresets()).map(([value, config]) => ({
        value,
        label: config.label,
      })),
    [],
  )
  const renderModeOptions = useMemo(() => getViewerRenderModes(), [])
  const lightModeOptions = useMemo(
    () => [
      { value: 'bright', label: 'Licht: Helder' },
      { value: 'soft', label: 'Licht: Zacht' },
      { value: 'contrast', label: 'Licht: Contrast' },
    ],
    [],
  )

  // Pipeline hook manages all pipeline state + API communication
  const pipeline = usePipelineContext()
  const selection = useSelection({
    pipelineVisuals: effectivePipelineVisuals,
    flatMesh: effectiveFlatMesh,
    backendMesh: effectiveBackendMesh,
    groupedStages: effectiveGroupedStages,
    pipelineEnabled: pipeline.pipelineEnabled,
    pipelineState: pipeline.pipelineState,
  })

  // Viewer hook manages file buffer, loading, error, model info
  const viewer = useViewer({
    startPipeline: pipeline.startPipeline,
    pipelineEnabled: pipeline.pipelineEnabled,
    pipelineState: pipeline.pipelineState,
    activeMesh: selection.activeMesh,
    parseMode: selection.parseMode,
  })

  useEffect(() => {
    if (viewer.error) setDebugPanelOpen(true)
  }, [viewer.error])

  useEffect(() => {
    window.localStorage.setItem('ales-viewer-material-preset', materialPreset)
  }, [materialPreset])

  useEffect(() => {
    window.localStorage.setItem('ales-viewer-render-mode', renderMode)
  }, [renderMode])

  useEffect(() => {
    window.localStorage.setItem('ales-viewer-light-mode', lightMode)
  }, [lightMode])

  const latestErrorDebugEvent = useMemo(() => {
    const events = viewer.debugEvents || []
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const event = events[index]
      if (['worker_error', 'worker_failure', 'worker_message_error', 'wasm_parse_error', 'model_error'].includes(event.stage)) {
        return event
      }
    }
    return null
  }, [viewer.debugEvents])

  // Auto-load STEP file from URL parameter ?job=<id>[&part=<index>][&api=<base>][&key=<apikey>]
  const jobAutoLoadRef = useRef(false)
  useEffect(() => {
    if (jobAutoLoadRef.current) return
    const params = launchParams
    const jobId = params.get('job')
    if (!jobId) return
    jobAutoLoadRef.current = true

    const apiBase = params.get('api') || pipeline.pipelineApiBase || getDefaultPipelineApiBase()
    const fileName = params.get('name') || 'part.step'
    const partIndex = launchedPartIndex
    const urlKey = params.get('key') || pipeline.pipelineApiKey
    if (params.get('api')) {
      pipeline.setPipelineApiBase(apiBase)
    }
    if (params.get('key')) {
      pipeline.setPipelineApiKey(urlKey)
    }
    viewer.setError(null)

    const headers = getApiKeyHeaders(urlKey)

    let hydratedJob = null

    fetch(`${apiBase}/api/v1/jobs/${jobId}`, { headers })
      .then(async (response) => {
        if (!response.ok) {
          let detail = ''
          try {
            const payload = await response.json()
            detail = payload?.detail || ''
          } catch {
            detail = await response.text()
          }
          throw new Error(detail || `${response.status} ${response.statusText}`)
        }
        return response.json()
      })
      .then((job) => {
        hydratedJob = job
        if (job?.status !== 'completed') return job
        const unfoldUrl = partIndex != null
          ? `${apiBase}/api/v1/jobs/${jobId}/parts/${partIndex}/unfold`
          : `${apiBase}/api/v1/jobs/${jobId}/unfold`
        return fetch(unfoldUrl, { headers })
          .then(async (response) => {
            if (!response.ok) {
              let detail = ''
              try {
                const payload = await response.json()
                detail = payload?.detail || ''
              } catch {
                detail = await response.text()
              }
              throw new Error(detail || `${response.status} ${response.statusText}`)
            }
            return response.json()
          })
          .then((unfoldStatus) => {
            return mergeJobWithUnfoldResult(job, unfoldStatus)
          })
          .catch(() => job)
      })
      .then((job) => {
        hydratedJob = job
        if (job?.status === 'completed') {
          const timeline = getTimelineForJobView(job, partIndex)
          pipeline.setPipelineState({
            ...EMPTY_PIPELINE_STATE,
            status: 'completed',
            jobId: job.job_id,
            result: job.result || null,
            events: timeline.events,
            summary: timeline.summary,
            error: null,
            debug: {
              checkedBase: apiBase,
              checkedUrl: `${apiBase}/api/v1/jobs/${jobId}`,
              fallbackBase: null,
              fallbackUrl: null,
              code: null,
              message: null,
            },
          })
        }
        if (!job?.source_step_available) {
          throw new Error('Bron STEP bestand is niet meer beschikbaar voor deze job.')
        }
        const stepUrl = partIndex != null
          ? `${apiBase}/api/v1/jobs/${jobId}/parts/${partIndex}/step`
          : `${apiBase}/api/v1/jobs/${jobId}/step`
        return fetchFileAsBrowserFile(
          stepUrl,
          fileName,
          { headers },
        )
      })
      .then((file) => viewer.handleFile(file, { skipPipelineStart: true }))
      .catch((err) => {
        if (hydratedJob?.status === 'completed') {
          const timeline = getTimelineForJobView(hydratedJob, partIndex)
          pipeline.setPipelineState({
            ...EMPTY_PIPELINE_STATE,
            status: 'completed',
            jobId: hydratedJob.job_id,
            result: hydratedJob.result || null,
            events: timeline.events,
            summary: timeline.summary,
            error: null,
            debug: {
              checkedBase: apiBase,
              checkedUrl: `${apiBase}/api/v1/jobs/${jobId}`,
              fallbackBase: null,
              fallbackUrl: null,
              code: null,
              message: null,
            },
          })
        }
        viewer.setError(`STEP bestand laden mislukt: ${err.message}`)
      })
  }, [launchParams, launchedPartIndex, pipeline, viewer])

  // Timer for live elapsed display
  useEffect(() => {
    if (pipeline.pipelineState?.status !== 'processing') return undefined
    const id = window.setInterval(() => setNowMs(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [pipeline.pipelineState?.status])

  // Auto-restart when pipeline settings change
  const pendingRestartRef = useRef(false)
  useEffect(() => {
    pipeline.handleAagFallbackToggle // triggers flag in pipeline
    pipeline.handleStageToggle // triggers flag in pipeline
    if (pendingRestartRef.current) {
      pipeline.triggerAutoRestart(viewer.sourceFile)
    }
  }, [pipeline.disabledStages, pipeline.aagFallbackEnabled])

  // Update engine status from pipeline state
  useEffect(() => {
    if (pipeline.pipelineState.status === 'processing') {
      if (pipeline.pipelineState.summary?.active_stage) {
        viewer.setEngineStatus(`Pipeline: ${normalizeStageName(pipeline.pipelineState.summary.active_stage)}`)
      } else {
        viewer.setEngineStatus('Pipeline analyseren...')
      }
      return
    }
    if (pipeline.pipelineState.status === 'queued') {
      viewer.setEngineStatus('Pipeline in wachtrij...')
    }
  }, [pipeline.pipelineState.status, pipeline.pipelineState.summary])

  // Derived display values
  const liveTotalElapsed =
    pipeline.pipelineState?.status === 'processing' && pipeline.analysisStartedMs
      ? Math.max(0, (nowMs - pipeline.analysisStartedMs) / 1000)
      : effectiveSummary?.total_elapsed_seconds
  const liveActiveElapsed =
    pipeline.pipelineState?.status === 'processing' && effectiveSummary?.active_stage && pipeline.activeStageStartedMs
      ? Math.max(0, (nowMs - pipeline.activeStageStartedMs) / 1000)
      : effectiveSummary?.active_stage_elapsed_seconds
  const totalStepsHint = effectiveSummary?.total_steps_hint || effectiveSummary?.step_count || effectiveGroupedStages.length
  const completedStepCount = effectiveSummary?.completed_step_count || 0
  const useFlatView = selection.useFlatView

  const resetViewer = useCallback(() => {
    pipeline.stopPipelineRequest()
    viewer.setFileBuffer(null)
    viewer.setFileName(null)
    viewer.setSourceFile(null)
    viewer.setModelInfo(null)
    selection.setFocusedStage(null)
    selection.setSelectedHoleId(null)
    selection.setSelectedFoldId(null)
    selection.setSelectedProbe(null)
    selection.setProbeMode(false)
    selection.setSelectedStageIndex(0)
    selection.setSelectedEventIndex(0)
    viewer.setError(null)
    viewer.setEngineStatus('Klaar')
    selection.setShowHiddenHoles(false)
    selection.setHighlightHiddenHoleLocations(false)
    pipeline.setPipelineState(EMPTY_PIPELINE_STATE)
  }, [pipeline.stopPipelineRequest, viewer, selection, pipeline.setPipelineState])

  const resetCamera = useCallback(() => {
    if (controlsRef.current) controlsRef.current.reset()
  }, [])

  // Handle part selection changes: update URL and trigger unfold reload
  const handlePartSelectionChange = useCallback((partIndex) => {
    setSelectedPartIndex(partIndex)
    selection.setFocusedStage(null)
    selection.setSelectedHoleId(null)
    selection.setSelectedFoldId(null)
    selection.setSelectedProbe(null)
    selection.setProbeMode(false)
    selection.setSelectedStageIndex(0)
    selection.setSelectedEventIndex(0)

    const parts = pipeline.pipelineState?.result?.parts || []
    const selectedPart = partIndex != null ? parts[partIndex] || null : null
    const solidIndex = Number.isInteger(selectedPart?.solid_index) ? selectedPart.solid_index : partIndex

    if (partIndex == null) {
      // Clear part selection from URL
      const params = new URLSearchParams(window.location.search)
      params.delete('part')
      const newUrl = `${window.location.pathname}?${params.toString()}`.replace(/\?$/, '')
      window.history.replaceState({}, '', newUrl)
    } else {
      // Update URL with part index
      const params = new URLSearchParams(window.location.search)
      params.set('part', String(solidIndex))
      const newUrl = `${window.location.pathname}?${params.toString()}`
      window.history.replaceState({}, '', newUrl)

      const apiBase = launchApiBase || pipeline.pipelineApiBase || getDefaultPipelineApiBase()
      const jobId = launchParams.get('job')
      const fileName = selectedPart?.file || selectedPart?.solid_name || `part_${partIndex + 1}.step`
      if (jobId && selectedPart) {
        const headers = getApiKeyHeaders(pipeline.pipelineApiKey)
        const unfoldUrl = `${apiBase}/api/v1/jobs/${jobId}/parts/${solidIndex}/unfold`
        const stepUrl = `${apiBase}/api/v1/jobs/${jobId}/parts/${solidIndex}/step`

        fetchFileAsBrowserFile(stepUrl, fileName, { headers })
          .then((file) => viewer.handleFile(file, { skipPipelineStart: true }))
          .catch((err) => console.warn('Failed to load STEP for part:', err))

        fetch(unfoldUrl, { headers })
          .then(r => r.json())
          .then(unfoldStatus => {
            pipeline.setPipelineState((prev) => ({
              ...prev,
              result: mergePartWithUnfoldResult(prev.result, partIndex, unfoldStatus),
            }))
          })
          .catch(err => console.warn('Failed to load unfold for part:', err))
      }
    }
  }, [launchParams, launchApiBase, pipeline, pipeline.pipelineApiKey, selection, setSelectedPartIndex, viewer])

  const handleLoadDefaultStep = useCallback(async () => {
    setLoadingDefaultStep(true)
    viewer.setError(null)
    try {
      const file = await fetchFileAsBrowserFile(
        `${pipeline.pipelineApiBase || getDefaultPipelineApiBase()}/api/v1/viewer/default-step`,
        'nieuwmodel.step',
        {
          headers: getApiKeyHeaders(pipeline.pipelineApiKey),
        },
      )
      viewer.handleFile(file)
    } catch (error) {
      viewer.setError(error?.message || 'Demo STEP bestand laden mislukt.')
    } finally {
      setLoadingDefaultStep(false)
    }
  }, [pipeline.pipelineApiBase, pipeline.pipelineApiKey, viewer])

  const handleBackToApi = useCallback(() => {
    window.location.href = launchApiBase
  }, [launchApiBase])

  return (
    <div className="app">
      <div className="header">
        <h1>ALES STEP Viewer</h1>
        <div className="header-actions">
          {launchedFromJob && (
            <button className="header-toggle-btn" onClick={handleBackToApi}>
              Terug naar API
            </button>
          )}
          {viewer.fileName && (
            <select
              className="header-toggle-btn"
              value={materialPreset}
              onChange={(event) => setMaterialPreset(event.target.value)}
              title="Materiaalweergave"
            >
              {materialOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}
          {viewer.fileName && (
            <select
              className="header-toggle-btn"
              value={renderMode}
              onChange={(event) => setRenderMode(event.target.value)}
              title="Render mode"
            >
              {renderModeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}
          {viewer.fileName && (
            <select
              className="header-toggle-btn"
              value={lightMode}
              onChange={(event) => setLightMode(event.target.value)}
              title="Licht mode"
            >
              {lightModeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}
          <button className="header-toggle-btn" onClick={() => setRightPanelOpen((v) => !v)}>
            {rightPanelOpen ? 'Verberg rechts' : 'Toon rechts'}
          </button>
          <button className="header-toggle-btn" onClick={() => setDebugPanelOpen((v) => !v)}>
            {debugPanelOpen ? 'Verberg debug' : 'Toon debug'}
          </button>
          <span className="header-status">rev {VIEWER_REVISION}</span>
          <span className="header-status">{viewer.engineStatus}</span>
        </div>
      </div>

      {viewer.error && (
        <div className="error-banner">
          <strong>Fout:&nbsp;</strong>{viewer.error}
          {latestErrorDebugEvent && (
            <div style={{ width: '100%', marginTop: 8, fontSize: '0.82rem', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
              <div><strong>Debug stage:</strong> {latestErrorDebugEvent.stage}</div>
              {latestErrorDebugEvent.error && <div><strong>Debug error:</strong> {latestErrorDebugEvent.error}</div>}
              {latestErrorDebugEvent.cause && (
                <div>
                  <strong>Cause:</strong> {JSON.stringify(latestErrorDebugEvent.cause)}
                </div>
              )}
              {latestErrorDebugEvent.errorDetail && (
                <div>
                  <strong>Error detail:</strong> {JSON.stringify(latestErrorDebugEvent.errorDetail)}
                </div>
              )}
            </div>
          )}
          <button className="toolbar-btn" style={{ marginLeft: 'auto' }} onClick={() => viewer.setError(null)}>✕</button>
        </div>
      )}

      <div className="main-content">
        <div className="viewer-container">
          {!viewer.fileBuffer && !selection.activeMesh && !viewer.loading && (
            <Dropzone
              onFile={viewer.handleFile}
              onLoadDefaultStep={handleLoadDefaultStep}
              loadingDefaultStep={loadingDefaultStep}
            />
          )}

          {viewer.loading && !viewer.fileBuffer && !selection.activeMesh && (
            <div className="loading-overlay">
              <div className="spinner" />
              <div className="loading-text">{viewer.engineStatus || 'Bestand laden...'}</div>
              <div className="loading-sub">{viewer.fileName}</div>
            </div>
          )}

          {viewer.fileName && (
            <>
              <div className="viewer-toolbar">
                <button className="toolbar-btn" onClick={resetCamera}>Reset View</button>
                <button
                  className={`toolbar-btn ${selection.probeMode ? 'is-active' : ''}`}
                  onClick={() => {
                    if (!selection.canUseProbeMode) return
                    selection.setProbeMode((v) => !v)
                  }}
                  disabled={!selection.canUseProbeMode}
                  title={
                    selection.canUseProbeMode
                      ? 'Klik in het model om niet-herkende gaten te inspecteren'
                      : `Selecteer eerst ${MERGED_HOLES_STAGE}`
                  }
                >
                  {selection.probeMode ? 'Probe mode aan' : 'Probe mode'}
                </button>
                <button className="toolbar-btn" onClick={resetViewer}>Nieuw bestand</button>
              </div>
              <div className="viewer-info">
                {viewer.fileName}{' '}
                {viewer.modelInfo ? `— ${viewer.modelInfo.vertexCount?.toLocaleString() || '?'} vertices` : '— laden...'}
                {useFlatView ? ' — uitslagweergave' : ' — 3D weergave'}
              </div>
            </>
          )}

          {(viewer.fileBuffer || selection.activeMesh) && (
            <Suspense fallback={<ViewerCanvasFallback />}>
              <ViewerCanvas
                fileBuffer={viewer.fileBuffer}
                activeMesh={selection.activeMesh}
                onLoaded={viewer.handleModelLoaded}
                onError={viewer.handleModelError}
                onStatus={viewer.handleStatus}
                onDebug={viewer.pushDebugEvent}
                parseMode={selection.parseMode}
                modelInfo={viewer.modelInfo}
                backendVisuals={effectivePipelineVisuals}
                activeHoleVisuals={selection.activeHoleVisuals}
                focusedStage={selection.focusedStage}
                selectedHole={selection.selectedFeature}
                selectedFoldId={selection.selectedFoldId}
                onFoldSelect={selection.selectFold}
                onHoleSelect={selection.selectHole}
                onSurfaceProbe={selection.handleSurfaceProbe}
                selectedProbe={selection.selectedProbe}
                probeMode={selection.probeMode}
                controlsRef={controlsRef}
                useFlatView={useFlatView}
                showHiddenHoles={selection.showHiddenHoles}
                highlightHiddenHoleLocations={selection.highlightHiddenHoleLocations}
                materialPreset={materialPreset}
                renderMode={renderMode}
                lightMode={lightMode}
              />
            </Suspense>
          )}
        </div>

        {rightPanelOpen && (
          <StageDetailsPanel
            pipelineVisuals={effectivePipelineVisuals}
            pipelineResult={pipeline.pipelineState?.result}
            groupedStages={effectiveGroupedStages}
            summary={effectiveSummary}
            liveActiveElapsed={liveActiveElapsed}
            selectedStageIndex={selection.selectedStageIndex}
            selectedEventIndex={selection.selectedEventIndex}
            onSelectStageIndex={selection.handleSelectStageIndex}
            onSelectEventIndex={selection.setSelectedEventIndex}
            selectedHoleId={selection.selectedHoleId}
            selectedFoldId={selection.selectedFoldId}
            onFoldSelect={selection.selectFold}
            onHoleSelect={selection.selectHole}
            selectedProbe={selection.selectedProbe}
            pipelineStatus={pipeline.pipelineState.status}
            showHiddenHoles={selection.showHiddenHoles}
            onShowHiddenHolesChange={selection.setShowHiddenHoles}
            highlightHiddenHoleLocations={selection.highlightHiddenHoleLocations}
            onHighlightHiddenHoleLocationsChange={selection.setHighlightHiddenHoleLocations}
            selectedPartIndex={selectedPartIndex}
            onSelectPartIndex={handlePartSelectionChange}
          />
        )}

        {debugPanelOpen && (
          <DebugPanel
            viewer={viewer}
            pipeline={pipeline}
            parseMode={selection.parseMode}
            activeMesh={selection.activeMesh}
          />
        )}
      </div>
    </div>
  )
}

function AppWithSelectionProvider() {
  const pipeline = usePipelineContext()
  const launchParams = useMemo(() => new URLSearchParams(window.location.search), [])
  const launchedPartIndex = useMemo(() => {
    const raw = launchParams.get('part')
    if (raw == null || raw === '') return null
    const value = Number.parseInt(raw, 10)
    return Number.isFinite(value) ? value : null
  }, [launchParams])
  const [selectedPartIndex, setSelectedPartIndex] = useState(null)

  const pipelineResult = pipeline.pipelineState?.result
  const parts = pipelineResult?.parts || []

  useEffect(() => {
    if (!pipelineResult?.is_assembly) {
      setSelectedPartIndex(null)
      return
    }

    if (parts.length === 0) {
      setSelectedPartIndex(null)
      return
    }

    setSelectedPartIndex((current) => {
      if (current != null && parts[current]) return current
      if (launchedPartIndex != null) {
        const resolvedIndex = parts.findIndex((part, index) => {
          const solidIndex = Number.isInteger(part?.solid_index) ? part.solid_index : index
          return solidIndex === launchedPartIndex
        })
        if (resolvedIndex >= 0) return resolvedIndex
      }
      return 0
    })
  }, [launchedPartIndex, parts, pipelineResult])

  const selectedPart = pipelineResult?.is_assembly && selectedPartIndex != null ? parts[selectedPartIndex] || null : null
  const effectiveEvents = selectedPart ? getPartTimelineEvents(selectedPart) : pipeline.pipelineState?.events || []
  const effectiveGroupedStages = useMemo(() => groupEventsByStage(effectiveEvents), [effectiveEvents])
  const effectivePipelineVisuals = selectedPart?.visuals || pipeline.pipelineVisuals
  const effectiveSummary = selectedPart?.timeline_summary || pipeline.summary
  const effectiveBackendMesh = selectedPart?.mesh || pipeline.backendMesh
  const effectiveFlatMesh = effectivePipelineVisuals?.unfold?.flat_mesh || null

  return (
    <AppContent
      selectedPartIndex={selectedPartIndex}
      setSelectedPartIndex={setSelectedPartIndex}
      effectivePipelineVisuals={effectivePipelineVisuals}
      effectiveGroupedStages={effectiveGroupedStages}
      effectiveSummary={effectiveSummary}
      effectiveBackendMesh={effectiveBackendMesh}
      effectiveFlatMesh={effectiveFlatMesh}
    />
  )
}

export default function App() {
  return (
    <PipelineProvider>
      <AppWithSelectionProvider />
    </PipelineProvider>
  )
}
