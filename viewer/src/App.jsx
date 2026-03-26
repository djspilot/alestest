import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Dropzone from './Dropzone'
import Sidebar from './Sidebar'
import StageDetailsPanel from './StageDetailsPanel'
import { checkPipelineConnection, getDefaultPipelineApiBase, runPipelineAnalysis } from './pipelineClient'
import { groupEventsByStage, MERGED_HOLES_STAGE, normalizeStageName, parseIsoToMs } from './pipelineUi'

const ViewerCanvas = lazy(() => import('./ViewerCanvas'))

const EMPTY_PIPELINE_STATE = {
  status: 'idle',
  jobId: null,
  events: [],
  summary: null,
  error: null,
  result: null,
}

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

function readFileAsArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('Bestand lezen mislukt.'))
    reader.readAsArrayBuffer(file)
  })
}

function normalizeFoldId(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : String(value)
}

export default function App() {
  const [fileBuffer, setFileBuffer] = useState(null)
  const [fileName, setFileName] = useState(null)
  const [sourceFile, setSourceFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)
  const [engineStatus, setEngineStatus] = useState('Klaar')
  const [pipelineEnabled, setPipelineEnabled] = useState(true)
  const [aagFallbackEnabled, setAagFallbackEnabled] = useState(() => {
    const stored = window.localStorage.getItem('ales-aag-fallback-enabled')
    return stored == null ? true : stored === 'true'
  })
  const [pipelineApiBase, setPipelineApiBase] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-base') || getDefaultPipelineApiBase()
  })
  const [pipelineApiKey, setPipelineApiKey] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-key') || ''
  })
  const [pipelineState, setPipelineState] = useState(EMPTY_PIPELINE_STATE)
  const [focusedStage, setFocusedStage] = useState(null)
  const [selectedHoleId, setSelectedHoleId] = useState(null)
  const [selectedFoldId, setSelectedFoldId] = useState(null)
  const [selectedProbe, setSelectedProbe] = useState(null)
  const [probeMode, setProbeMode] = useState(false)
  const [selectedStageIndex, setSelectedStageIndex] = useState(0)
  const [selectedEventIndex, setSelectedEventIndex] = useState(0)
  const [leftPanelOpen, setLeftPanelOpen] = useState(true)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const controlsRef = useRef()
  const pipelineAbortRef = useRef(null)

  const backendMesh = pipelineState?.result?.mesh || null
  const backendVisuals = pipelineState?.result?.visuals || null
  const pipelineVisuals = useMemo(() => {
    const visuals = {
      ...(backendVisuals || {}),
    }

    for (const event of pipelineState?.events || []) {
      if (!event?.payload) continue

      if (event.stage === 'Profile Router' && event.type === 'classification_decision') {
        visuals.router = {
          ...(visuals.router || {}),
          ...event.payload,
        }
      }

      if (event.stage === 'Classify geometry' && event.type === 'geometry_classified') {
        visuals.classification = {
          ...(visuals.classification || {}),
          ...event.payload,
        }
      }

      if (event.stage === 'Detect holes' && event.type === 'holes_detected') {
        visuals.holes = {
          ...(visuals.holes || {}),
          ...event.payload,
        }
      }

      if (event.stage === 'Unfold' && event.type === 'unfold_result') {
        visuals.unfold = {
          ...(visuals.unfold || {}),
          ...event.payload,
        }
      }
    }

    return visuals
  }, [backendVisuals, pipelineState?.events])
  const flatMesh = backendVisuals?.unfold?.flat_mesh || null
  const groupedStages = useMemo(() => groupEventsByStage(pipelineState?.events || []), [pipelineState?.events])
  const summary = pipelineState?.summary
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
  const selectedStage = groupedStages[selectedStageIndex] || null
  const holeSource = pipelineVisuals?.holes?.source || null
  const unfoldSuccess = Boolean(pipelineVisuals?.unfold?.success)
  const selectedHole = (pipelineVisuals?.holes?.items || []).find((item) => item.id === selectedHoleId) || null
  const selectedFeature = selectedHole || selectedProbe
  const selectedHoleSource = selectedFeature?.source || null
  const useFlatView =
    focusedStage === MERGED_HOLES_STAGE
    && (unfoldSuccess || selectedHoleSource === 'flat' || (!selectedHoleSource && holeSource === 'flat'))
    && Boolean(flatMesh)
  const activeMesh = useFlatView ? flatMesh : backendMesh
  const shouldWaitForBackendMesh =
    pipelineEnabled &&
    !backendMesh &&
    !fileBuffer &&
    ['checking', 'queued', 'processing'].includes(pipelineState.status)
  const parseMode = shouldWaitForBackendMesh ? 'backend-only' : 'auto'

  const stopPipelineRequest = useCallback(() => {
    if (pipelineAbortRef.current) {
      pipelineAbortRef.current.abort()
      pipelineAbortRef.current = null
    }
  }, [])

  useEffect(() => {
    window.localStorage.setItem('ales-pipeline-api-base', pipelineApiBase)
  }, [pipelineApiBase])

  useEffect(() => {
    window.localStorage.setItem('ales-pipeline-api-key', pipelineApiKey)
  }, [pipelineApiKey])

  useEffect(() => {
    window.localStorage.setItem('ales-aag-fallback-enabled', String(aagFallbackEnabled))
  }, [aagFallbackEnabled])

  useEffect(() => {
    if (!pipelineEnabled) {
      stopPipelineRequest()
      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'disabled' })
    }
  }, [pipelineEnabled, stopPipelineRequest])

  useEffect(() => {
    if (activeMesh) {
      setLoading(false)
    }
  }, [activeMesh])

  useEffect(() => {
    if (pipelineState?.status !== 'processing') return undefined
    const id = window.setInterval(() => setNowMs(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [pipelineState?.status])

  useEffect(() => {
    setSelectedStageIndex((value) => {
      if (groupedStages.length === 0) return 0
      return Math.min(value, groupedStages.length - 1)
    })
  }, [groupedStages.length])

  useEffect(() => {
    setSelectedEventIndex((value) => {
      const eventCount = selectedStage?.events?.length || 0
      if (eventCount === 0) return 0
      return Math.min(value, eventCount - 1)
    })
  }, [selectedStage])

  useEffect(() => {
    setFocusedStage(selectedStage?.stage || null)
  }, [selectedStage])

  useEffect(() => {
    if (!selectedHoleId) return
    const holeItems = pipelineVisuals?.holes?.items || []
    if (!holeItems.some((item) => item.id === selectedHoleId)) {
      setSelectedHoleId(null)
    }
  }, [pipelineVisuals, selectedHoleId])

  useEffect(() => {
    const foldIds = new Set([
      ...(pipelineVisuals?.unfold?.fold_details || []).map((fold, idx) => normalizeFoldId(fold?.id ?? (idx + 1))),
      ...(pipelineVisuals?.unfold?.bends_logical || []).map((bend, idx) => normalizeFoldId(bend?.id ?? (idx + 1))),
    ].filter((id) => id != null))
    if (selectedFoldId != null && !foldIds.has(normalizeFoldId(selectedFoldId))) {
      setSelectedFoldId(null)
    }
  }, [pipelineVisuals, selectedFoldId])

  useEffect(() => {
    if (pipelineState.status === 'processing') {
      if (pipelineState.summary?.active_stage) {
        setEngineStatus(`Pipeline: ${normalizeStageName(pipelineState.summary.active_stage)}`)
      } else {
        setEngineStatus('Pipeline analyseren...')
      }
      return
    }

    if (pipelineState.status === 'queued') {
      setEngineStatus('Pipeline in wachtrij...')
    }
  }, [pipelineState.status, pipelineState.summary])

  const startPipeline = useCallback(async (file) => {
    if (!pipelineEnabled) {
      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'disabled' })
      return
    }

    stopPipelineRequest()
    const controller = new AbortController()
    pipelineAbortRef.current = controller

    setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'checking' })

    try {
      const connection = await checkPipelineConnection({
        apiBase: pipelineApiBase,
        apiKey: pipelineApiKey,
        signal: controller.signal,
      })

      if (!connection.ok) {
        setPipelineState((prev) => ({
          ...prev,
          status: connection.status,
          error: connection.message,
        }))
        return
      }

      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'queued' })

      const result = await runPipelineAnalysis(file, {
        apiBase: pipelineApiBase,
        apiKey: pipelineApiKey,
        aag: aagFallbackEnabled,
        signal: controller.signal,
        onProgress: (progress) => {
          setPipelineState((prev) => ({
            ...prev,
            status: progress.status || prev.status,
            jobId: progress.jobId || prev.jobId,
            result: progress.job?.result || prev.result,
            events: progress.timeline?.events || prev.events,
            summary: progress.timeline?.summary || prev.summary,
          }))
        },
      })

      setPipelineState((prev) => ({
        ...prev,
        status: 'completed',
        jobId: result.jobId,
        result: result.job?.result || null,
        events: result.timeline?.events || [],
        summary: result.timeline?.summary || null,
        error: null,
      }))
    } catch (pipelineError) {
      if (pipelineError?.name === 'AbortError') return
      setPipelineState((prev) => ({
        ...prev,
        status: 'failed',
        error: pipelineError?.message || 'Pipeline analyse mislukt',
      }))
    }
  }, [aagFallbackEnabled, pipelineApiBase, pipelineApiKey, pipelineEnabled, stopPipelineRequest])

  const handleFile = useCallback((file) => {
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['step', 'stp'].includes(ext)) {
      setError('Ongeldig bestandstype. Alleen .step/.stp bestanden.')
      return
    }

    setError(null)
    setLoading(true)
    setFileName(file.name)
    setSourceFile(file)
    setModelInfo(null)
    setFocusedStage(null)
    setSelectedHoleId(null)
    setSelectedFoldId(null)
    setSelectedProbe(null)
    setProbeMode(false)
    setSelectedStageIndex(0)
    setSelectedEventIndex(0)
    setEngineStatus('Bestand laden...')
    setPipelineState(EMPTY_PIPELINE_STATE)
    setFileBuffer(null)

    if (pipelineEnabled) {
      void readFileAsArrayBuffer(file)
        .then((result) => {
          setFileBuffer(result)
          setLoading(false)
          setEngineStatus((currentStatus) => (currentStatus === 'Pipeline analyse starten...' ? 'Lokale STEP preview laden...' : currentStatus))
        })
        .catch((readError) => {
          setError(readError.message || 'Bestand lezen mislukt.')
          setLoading(false)
          setEngineStatus('Fout')
        })
      setEngineStatus('Pipeline analyse starten...')
      void startPipeline(file)
      return
    }

    void readFileAsArrayBuffer(file)
      .then((result) => {
        setFileBuffer(result)
        setLoading(false)
        setEngineStatus('STEP verwerken via OpenCascade WASM...')
      })
      .catch((readError) => {
        setError(readError.message || 'Bestand lezen mislukt.')
        setLoading(false)
        setEngineStatus('Fout')
      })
  }, [startPipeline])

  useEffect(() => {
    const pipelineSettled = ['completed', 'failed', 'unavailable', 'auth_required'].includes(pipelineState.status)
    if (!pipelineEnabled || !pipelineSettled || !sourceFile || activeMesh || fileBuffer) return

    let cancelled = false
    setEngineStatus('Backend mesh ontbreekt, browser fallback laden...')

    void readFileAsArrayBuffer(sourceFile)
      .then((result) => {
        if (cancelled) return
        setFileBuffer(result)
        setLoading(false)
        setEngineStatus('STEP verwerken via OpenCascade WASM...')
      })
      .catch((readError) => {
        if (cancelled) return
        setError(readError.message || 'Bestand lezen mislukt.')
        setLoading(false)
        setEngineStatus('Fout')
      })

    return () => {
      cancelled = true
    }
  }, [activeMesh, fileBuffer, pipelineEnabled, pipelineState.status, sourceFile])

  const handleModelLoaded = useCallback((info) => {
    setModelInfo(info)
    setEngineStatus('OpenCascade actief')
  }, [])

  const handleModelError = useCallback((message) => {
    setError(`Model laden mislukt: ${message}`)
    setEngineStatus('Fout')
  }, [])

  const handleStatus = useCallback((status) => {
    setEngineStatus(status)
  }, [])

  const resetViewer = useCallback(() => {
    stopPipelineRequest()
    setFileBuffer(null)
    setFileName(null)
    setSourceFile(null)
    setModelInfo(null)
    setFocusedStage(null)
    setSelectedHoleId(null)
    setSelectedFoldId(null)
    setSelectedProbe(null)
    setProbeMode(false)
    setSelectedStageIndex(0)
    setSelectedEventIndex(0)
    setError(null)
    setEngineStatus('Klaar')
    setPipelineState(EMPTY_PIPELINE_STATE)
  }, [stopPipelineRequest])

  const resetCamera = useCallback(() => {
    if (controlsRef.current) controlsRef.current.reset()
  }, [])

  const handleSelectStageIndex = useCallback((index) => {
    setSelectedStageIndex(index)
    setSelectedEventIndex(0)
    setRightPanelOpen(true)
  }, [])

  const selectDetectHolesStage = useCallback(() => {
    const detectStageIndex = groupedStages.findIndex((group) => group.stage === MERGED_HOLES_STAGE)
    if (detectStageIndex >= 0) {
      handleSelectStageIndex(detectStageIndex)
    }
    setFocusedStage(MERGED_HOLES_STAGE)
    setRightPanelOpen(true)
  }, [groupedStages, handleSelectStageIndex])

  const selectHole = useCallback((holeId) => {
    selectDetectHolesStage()
    setSelectedFoldId(null)
    setSelectedHoleId(holeId)
    setSelectedProbe(null)
  }, [selectDetectHolesStage])

  const selectFold = useCallback((foldId) => {
    const normalizedFoldId = normalizeFoldId(foldId)
    if (normalizedFoldId == null) return
    selectDetectHolesStage()
    setSelectedFoldId(normalizedFoldId)
    setSelectedHoleId(null)
    setSelectedProbe(null)
    setProbeMode(false)
  }, [selectDetectHolesStage])

  const handleSurfaceProbe = useCallback((sample) => {
    if (!sample?.point) return
    const inferredContour = sample.inferredContour || null
    selectDetectHolesStage()
    setSelectedFoldId(null)
    setSelectedHoleId(null)
    setSelectedProbe({
      id: `probe-${Date.now()}`,
      status: 'probe',
      source: useFlatView ? 'flat' : '3d',
      label: 'Handmatige probe',
      reason: inferredContour
        ? 'Waarschijnlijke hole-edge gevonden op deze kliklocatie, maar hij bestaat niet als backend hole-candidate.'
        : 'Geen gedetecteerde hole-candidate op deze kliklocatie binnen de detectieradius.',
      position: inferredContour?.position || (modelInfo?.center
        ? [
          sample.point.x + modelInfo.center.x,
          sample.point.y + modelInfo.center.y,
          sample.point.z + modelInfo.center.z,
        ]
        : [sample.point.x, sample.point.y, sample.point.z]),
      normal: inferredContour?.normal || (sample.normal ? [sample.normal.x, sample.normal.y, sample.normal.z] : [0, 0, 1]),
      nearestHole: sample.nearestHole || null,
      nearestHoleDistance: sample.nearestHoleDistance || null,
      inferredContour,
      criteria: [
        {
          name: 'detected_candidate',
          value: false,
          threshold: true,
          passed: false,
          note: 'Op deze plek is geen geaccepteerde of afgewezen hole-candidate gevonden.',
        },
        ...(inferredContour
          ? [{
            name: 'inferred_edge_contour',
            value: inferredContour.label || inferredContour.type || 'unknown',
            threshold: 'known candidate expected',
            passed: false,
            note: 'De viewer ziet wel een lokale gesloten edge-loop, maar de pipeline heeft er geen hole-candidate van gemaakt.',
          }, {
            name: 'inferred_edge_segments',
            value: inferredContour.debug?.edge_segment_count ?? null,
            threshold: '>= 5 nearby segments',
            passed: false,
            note: 'Aantal edge-segmenten dat rond de probe als lokale contour is meegenomen.',
          }, {
            name: 'probe_confidence',
            value: inferredContour.debug?.confidence ?? null,
            threshold: 'higher = stronger contour',
            passed: false,
            note: 'Heuristische confidence van de viewer op basis van local edge-shape.',
          }]
          : []),
        ...(sample.nearestHole
          ? [{
            name: 'nearest_known_candidate_distance_mm',
            value: Number(sample.nearestHoleDistance?.toFixed?.(2) || sample.nearestHoleDistance || 0),
            threshold: 'inspect only',
            passed: false,
            note: `${sample.nearestHole.label || sample.nearestHole.type || 'Onbekend'} is de dichtstbijzijnde bekende kandidaat.`,
          }]
          : []),
      ],
    })
  }, [modelInfo?.center, selectDetectHolesStage, useFlatView])

  const canUseProbeMode = focusedStage === MERGED_HOLES_STAGE

  return (
    <div className="app">
      <div className="header">
        <h1>ALES STEP Viewer</h1>
        <div className="header-actions">
          <button className="header-toggle-btn" onClick={() => setLeftPanelOpen((value) => !value)}>
            {leftPanelOpen ? 'Verberg links' : 'Toon links'}
          </button>
          <button className="header-toggle-btn" onClick={() => setRightPanelOpen((value) => !value)}>
            {rightPanelOpen ? 'Verberg rechts' : 'Toon rechts'}
          </button>
          <span className="header-status">rev {VIEWER_REVISION}</span>
          <span className="header-status">{engineStatus}</span>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <strong>Fout:&nbsp;</strong>{error}
          <button className="toolbar-btn" style={{ marginLeft: 'auto' }} onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div className="main-content">
        {leftPanelOpen && (
          <Sidebar
            modelInfo={modelInfo}
            fileName={fileName}
            onReset={resetViewer}
            pipelineEnabled={pipelineEnabled}
            onPipelineToggle={setPipelineEnabled}
            aagFallbackEnabled={aagFallbackEnabled}
            onAagFallbackToggle={setAagFallbackEnabled}
            pipelineApiBase={pipelineApiBase}
            onPipelineApiBaseChange={setPipelineApiBase}
            pipelineApiKey={pipelineApiKey}
            onPipelineApiKeyChange={setPipelineApiKey}
            pipelineState={pipelineState}
            groupedStages={groupedStages}
            summary={summary}
            pipelineResult={pipelineState?.result}
            totalStepsHint={totalStepsHint}
            completedStepCount={completedStepCount}
            liveTotalElapsed={liveTotalElapsed}
            liveActiveElapsed={liveActiveElapsed}
            selectedStageIndex={selectedStageIndex}
            onSelectStageIndex={handleSelectStageIndex}
            onRetryPipeline={() => {
              if (!sourceFile) return
              setPipelineState(EMPTY_PIPELINE_STATE)
              void startPipeline(sourceFile)
            }}
            pipelineStatus={pipelineState.status}
          />
        )}

        <div className="viewer-container">
          {!fileBuffer && !activeMesh && !loading && <Dropzone onFile={handleFile} />}

          {loading && !fileBuffer && !activeMesh && (
            <div className="loading-overlay">
              <div className="spinner" />
              <div className="loading-text">{engineStatus || 'Bestand laden...'}</div>
              <div className="loading-sub">{fileName}</div>
            </div>
          )}

          {fileName && (
            <>
              <div className="viewer-toolbar">
                <button className="toolbar-btn" onClick={resetCamera}>Reset View</button>
                <button
                  className={`toolbar-btn ${probeMode ? 'is-active' : ''}`}
                  onClick={() => {
                    if (!canUseProbeMode) return
                    setProbeMode((value) => !value)
                  }}
                  disabled={!canUseProbeMode}
                  title={canUseProbeMode ? 'Klik in het model om niet-herkende gaten te inspecteren' : `Selecteer eerst ${MERGED_HOLES_STAGE}`}
                >
                  {probeMode ? 'Probe mode aan' : 'Probe mode'}
                </button>
                <button className="toolbar-btn" onClick={resetViewer}>Nieuw bestand</button>
              </div>
              <div className="viewer-info">
                {fileName} {modelInfo ? `— ${modelInfo.vertexCount?.toLocaleString() || '?'} vertices` : '— laden...'}
                {useFlatView ? ' — uitslagweergave' : ' — 3D weergave'}
              </div>
            </>
          )}

          {(fileBuffer || activeMesh) && (
            <Suspense fallback={<ViewerCanvasFallback />}>
              <ViewerCanvas
                fileBuffer={fileBuffer}
                activeMesh={activeMesh}
                onLoaded={handleModelLoaded}
                onError={handleModelError}
                onStatus={handleStatus}
                parseMode={parseMode}
                modelInfo={modelInfo}
                backendVisuals={pipelineVisuals}
                focusedStage={focusedStage}
                selectedHole={selectedFeature}
                selectedFoldId={selectedFoldId}
                onFoldSelect={selectFold}
                onHoleSelect={selectHole}
                onSurfaceProbe={handleSurfaceProbe}
                selectedProbe={selectedProbe}
                probeMode={probeMode}
                controlsRef={controlsRef}
                useFlatView={useFlatView}
              />
            </Suspense>
          )}
        </div>

        {rightPanelOpen && (
          <StageDetailsPanel
            pipelineVisuals={pipelineVisuals}
            groupedStages={groupedStages}
            summary={summary}
            liveActiveElapsed={liveActiveElapsed}
            selectedStageIndex={selectedStageIndex}
            selectedEventIndex={selectedEventIndex}
            onSelectStageIndex={handleSelectStageIndex}
            onSelectEventIndex={setSelectedEventIndex}
            selectedHoleId={selectedHoleId}
            selectedFoldId={selectedFoldId}
            onFoldSelect={selectFold}
            onHoleSelect={selectHole}
            selectedProbe={selectedProbe}
            pipelineStatus={pipelineState.status}
          />
        )}
      </div>
    </div>
  )
}
