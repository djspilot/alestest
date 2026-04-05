import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Dropzone from './Dropzone'
import DebugPanel from './DebugPanel'
import StageDetailsPanel from './StageDetailsPanel'
import { PipelineProvider, usePipelineContext } from './context/PipelineContext'
import { SelectionProvider, useSelectionContext } from './context/SelectionContext'
import { useViewer } from './hooks/useViewer'
import { fetchFileAsBrowserFile } from './lib/files'
import { normalizeStageName, MERGED_HOLES_STAGE } from './pipelineUi'
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
    const partEvents = Array.isArray(part.timeline_events) ? part.timeline_events : []
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

function AppContent() {
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

  // Selection hook manages hole/fold/probe/stage selection
  const selection = useSelectionContext()

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
        let baseJob = job
        if (partIndex != null) {
          const partResult = resolvePartFromJob(job, partIndex)
          if (partResult) {
            baseJob = {
              ...job,
              result: partResult,
            }
          }
        }
        hydratedJob = baseJob
        if (baseJob?.status !== 'completed') return baseJob
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
            return mergeJobWithUnfoldResult(baseJob, unfoldStatus)
          })
          .catch(() => baseJob)
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
      : pipeline.summary?.total_elapsed_seconds
  const liveActiveElapsed =
    pipeline.pipelineState?.status === 'processing' && pipeline.summary?.active_stage && pipeline.activeStageStartedMs
      ? Math.max(0, (nowMs - pipeline.activeStageStartedMs) / 1000)
      : pipeline.summary?.active_stage_elapsed_seconds
  const totalStepsHint = pipeline.summary?.total_steps_hint || pipeline.summary?.step_count || pipeline.groupedStages.length
  const completedStepCount = pipeline.summary?.completed_step_count || 0
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
    if (partIndex == null) {
      // Clear part selection from URL
      const params = new URLSearchParams(window.location.search)
      params.delete('part')
      const newUrl = `${window.location.pathname}?${params.toString()}`.replace(/\?$/, '')
      window.history.replaceState({}, '', newUrl)
    } else {
      // Update URL with part index
      const params = new URLSearchParams(window.location.search)
      params.set('part', String(partIndex))
      const newUrl = `${window.location.pathname}?${params.toString()}`
      window.history.replaceState({}, '', newUrl)
      
      // Reload unfold for this specific part
      const apiBase = launchApiBase || pipeline.pipelineApiBase || getDefaultPipelineApiBase()
      const jobId = launchParams.get('job')
      if (jobId) {
        const headers = getApiKeyHeaders(pipeline.pipelineApiKey)
        const unfoldUrl = `${apiBase}/api/v1/jobs/${jobId}/parts/${partIndex}/unfold`
        fetch(unfoldUrl, { headers })
          .then(r => r.json())
          .then(unfoldStatus => {
            // Merge unfold result into pipeline state
            const job = pipeline.pipelineState
            if (job && job.result) {
              const mergedJob = mergeJobWithUnfoldResult(
                { ...job, result: job.result },
                unfoldStatus
              )
              pipeline.setPipelineState({
                ...pipeline.pipelineState,
                result: mergedJob.result,
              })
            }
          })
          .catch(err => console.warn('Failed to load unfold for part:', err))
      }
    }
  }, [launchParams, launchApiBase, pipeline, pipeline.pipelineApiKey])

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
                backendVisuals={pipeline.pipelineVisuals}
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
            pipelineVisuals={pipeline.pipelineVisuals}
            pipelineResult={pipeline.pipelineState?.result}
            groupedStages={pipeline.groupedStages}
            summary={pipeline.summary}
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
            onSelectPart={handlePartSelectionChange}
            launchedPartIndex={launchedPartIndex}
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

  return (
    <SelectionProvider
      pipelineVisuals={pipeline.pipelineVisuals}
      flatMesh={pipeline.flatMesh}
      backendMesh={pipeline.backendMesh}
      groupedStages={pipeline.groupedStages}
      pipelineEnabled={pipeline.pipelineEnabled}
      pipelineState={pipeline.pipelineState}
    >
      <AppContent />
    </SelectionProvider>
  )
}

export default function App() {
  return (
    <PipelineProvider>
      <AppWithSelectionProvider />
    </PipelineProvider>
  )
}
