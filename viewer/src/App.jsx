import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Dropzone from './Dropzone'
import DebugPanel from './DebugPanel'
import Sidebar from './Sidebar'
import StageDetailsPanel from './StageDetailsPanel'
import { PipelineProvider, usePipelineContext } from './context/PipelineContext'
import { SelectionProvider, useSelectionContext } from './context/SelectionContext'
import { useViewer } from './hooks/useViewer'
import { fetchFileAsBrowserFile } from './lib/files'
import { normalizeStageName, MERGED_HOLES_STAGE } from './pipelineUi'
import { getApiKeyHeaders, getDefaultPipelineApiBase } from './pipelineClient'

import { normalizeFoldId } from './lib/holes'

import { EMPTY_PIPELINE_STATE } from './hooks/usePipeline'

const ViewerCanvas = lazy(() => import('./ViewerCanvas'))

const VIEWER_REVISION = '026734d'

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
  const [leftPanelOpen, setLeftPanelOpen] = useState(true)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [debugPanelOpen, setDebugPanelOpen] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [loadingDefaultStep, setLoadingDefaultStep] = useState(false)

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

  return (
    <div className="app">
      <div className="header">
        <h1>ALES STEP Viewer</h1>
        <div className="header-actions">
          <button className="header-toggle-btn" onClick={() => setLeftPanelOpen((v) => !v)}>
            {leftPanelOpen ? 'Verberg links' : 'Toon links'}
          </button>
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
          <button className="toolbar-btn" style={{ marginLeft: 'auto' }} onClick={() => viewer.setError(null)}>✕</button>
        </div>
      )}

      <div className="main-content">
        {leftPanelOpen && (
          <Sidebar
            modelInfo={viewer.modelInfo}
            fileName={viewer.fileName}
            onReset={resetViewer}
            pipelineEnabled={pipeline.pipelineEnabled}
            onPipelineToggle={pipeline.setPipelineEnabled}
            aagFallbackEnabled={pipeline.aagFallbackEnabled}
            onAagFallbackToggle={pipeline.handleAagFallbackToggle}
            disabledStages={pipeline.disabledStages}
            onStageToggle={pipeline.handleStageToggle}
            pipelineApiBase={pipeline.pipelineApiBase}
            onPipelineApiBaseChange={pipeline.setPipelineApiBase}
            pipelineApiKey={pipeline.pipelineApiKey}
            onPipelineApiKeyChange={pipeline.setPipelineApiKey}
            pipelineState={pipeline.pipelineState}
            groupedStages={pipeline.groupedStages}
            summary={pipeline.summary}
            pipelineResult={pipeline.pipelineState?.result}
            totalStepsHint={totalStepsHint}
            completedStepCount={completedStepCount}
            liveTotalElapsed={liveTotalElapsed}
            liveActiveElapsed={liveActiveElapsed}
            selectedStageIndex={selection.selectedStageIndex}
            onSelectStageIndex={selection.handleSelectStageIndex}
            onRetryPipeline={() => {
              if (!viewer.sourceFile) return
              pipeline.setPipelineState(EMPTY_PIPELINE_STATE)
              void pipeline.startPipeline(viewer.sourceFile)
            }}
            pipelineStatus={pipeline.pipelineState.status}
            pipelineDebug={pipeline.pipelineState.debug || null}
            onResetPipelineApiBase={() => pipeline.setPipelineApiBase(getDefaultPipelineApiBase())}
          />
        )}

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
              />
            </Suspense>
          )}
        </div>

        {rightPanelOpen && (
          <StageDetailsPanel
            pipelineVisuals={pipeline.pipelineVisuals}
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
