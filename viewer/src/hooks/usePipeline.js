import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { checkPipelineConnection, getDefaultPipelineApiBase, runPipelineAnalysis } from '../pipelineClient'
import {
  groupEventsByStage,
  isMergedHolesStageName,
  isPreUnfoldStageName,
  normalizeStageName,
  parseIsoToMs,
} from '../pipelineUi'
import { normalizeFoldId } from '../lib/holes'

const EMPTY_PIPELINE_STATE = {
  status: 'idle',
  jobId: null,
  events: [],
  summary: null,
  error: null,
  result: null,
}

function buildPipelineDebug(details = {}) {
  return {
    checkedBase: details.checkedBase || null,
    checkedUrl: details.checkedUrl || null,
    fallbackBase: details.fallbackBase || null,
    fallbackUrl: details.fallbackUrl || null,
    code: details.code || null,
    message: details.message || null,
  }
}

export { EMPTY_PIPELINE_STATE }

export function usePipeline() {
  const [pipelineEnabled, setPipelineEnabled] = useState(() => {
    const stored = window.localStorage.getItem('ales-pipeline-enabled')
    return stored == null ? true : stored === 'true'
  })
  const [aagFallbackEnabled, setAagFallbackEnabled] = useState(() => {
    const stored = window.localStorage.getItem('ales-aag-fallback-enabled')
    return stored == null ? true : stored === 'true'
  })
  const [disabledStages, setDisabledStages] = useState(() => {
    const stored = window.localStorage.getItem('ales-disabled-stages')
    return stored ? JSON.parse(stored) : []
  })
  const [pipelineApiBase, setPipelineApiBase] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-base') || getDefaultPipelineApiBase()
  })
  const [pipelineApiKey, setPipelineApiKey] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-key') || ''
  })
  const [pipelineState, setPipelineState] = useState(EMPTY_PIPELINE_STATE)
  const [debugEvents, setDebugEvents] = useState([])
  const pipelineAbortRef = useRef(null)
  const pendingRestartRef = useRef(false)

  const pushDebugEvent = useCallback((stage, details = {}) => {
    setDebugEvents((prev) => {
      const next = [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          timestamp: new Date().toISOString(),
          source: 'pipeline',
          stage,
          ...details,
        },
      ]
      return next.slice(-200)
    })
  }, [])

  // Persist settings
  useEffect(() => {
    window.localStorage.setItem('ales-pipeline-enabled', String(pipelineEnabled))
  }, [pipelineEnabled])
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
    window.localStorage.setItem('ales-disabled-stages', JSON.stringify(disabledStages))
  }, [disabledStages])

  const stopPipelineRequest = useCallback(() => {
    if (pipelineAbortRef.current) {
      pipelineAbortRef.current.abort()
      pipelineAbortRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!pipelineEnabled) {
      stopPipelineRequest()
      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'disabled' })
      pushDebugEvent('pipeline_disabled', { message: 'Pipeline is disabled in viewer settings' })
    }
  }, [pipelineEnabled, pushDebugEvent, stopPipelineRequest])

  const handleStageToggle = useCallback((stageKey, enabled) => {
    setDisabledStages((prev) => {
      const next = enabled ? prev.filter((s) => s !== stageKey) : [...prev, stageKey]
      window.localStorage.setItem('ales-disabled-stages', JSON.stringify(next))
      return next
    })
    pendingRestartRef.current = true
  }, [])

  const handleAagFallbackToggle = useCallback((value) => {
    setAagFallbackEnabled(value)
    pendingRestartRef.current = true
  }, [])

  const startPipeline = useCallback(
    async (file) => {
      if (!pipelineEnabled) {
        setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'disabled' })
        return
      }

      stopPipelineRequest()
      const controller = new AbortController()
      pipelineAbortRef.current = controller

      setDebugEvents([])
      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'checking' })

      try {
        const configuredBase = (pipelineApiBase || '').trim()
        const defaultBase = getDefaultPipelineApiBase()
        pushDebugEvent('connection_check_started', {
          configuredBase: configuredBase || null,
          defaultBase,
          fileName: file?.name || null,
          fileSize: file?.size || null,
        })

        let connection = await checkPipelineConnection({
          apiBase: pipelineApiBase,
          apiKey: pipelineApiKey,
          signal: controller.signal,
        })
        pushDebugEvent('connection_check_result', connection)

        let usedBase = configuredBase
        let fallbackAttempt = null

        if (!connection.ok && configuredBase && configuredBase !== defaultBase) {
          pushDebugEvent('connection_fallback_started', {
            fallbackBase: defaultBase,
            originalBase: configuredBase,
          })
          fallbackAttempt = await checkPipelineConnection({
            apiBase: defaultBase,
            apiKey: pipelineApiKey,
            signal: controller.signal,
          })
          pushDebugEvent('connection_fallback_result', fallbackAttempt)
          if (fallbackAttempt.ok) {
            usedBase = defaultBase
            connection = fallbackAttempt
            setPipelineApiBase(defaultBase)
          }
        }

        if (!connection.ok) {
          setPipelineState((prev) => ({
            ...prev,
            status: connection.status,
            error: connection.message,
            debug: buildPipelineDebug({
              checkedBase: configuredBase,
              checkedUrl: connection.url,
              fallbackBase: fallbackAttempt ? defaultBase : null,
              fallbackUrl: fallbackAttempt?.url || null,
              code: connection.code,
              message: connection.message,
            }),
          }))
          pushDebugEvent('connection_check_failed', {
            status: connection.status,
            code: connection.code,
            message: connection.message,
            checkedUrl: connection.url || null,
            fallbackUrl: fallbackAttempt?.url || null,
          })
          return
        }

        setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'queued' })
        pushDebugEvent('analysis_requested', {
          apiBase: usedBase,
          analyzeUrl: `${usedBase}/api/v1/analyze`,
          aag: aagFallbackEnabled,
          disabledStages,
        })

        const result = await runPipelineAnalysis(file, {
          apiBase: usedBase,
          apiKey: pipelineApiKey,
          aag: aagFallbackEnabled,
          disableStages: disabledStages,
          signal: controller.signal,
          onProgress: (progress) => {
            pushDebugEvent('progress', {
              progressStage: progress.stage || null,
              status: progress.status || null,
              jobId: progress.jobId || null,
              activeStage: progress.timeline?.summary?.active_stage || null,
              eventCount: progress.timeline?.events?.length || 0,
              error: progress.job?.error || null,
            })
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
          debug: buildPipelineDebug({
            checkedBase: usedBase,
            checkedUrl: `${usedBase}/api/v1/health`,
          }),
        }))
        pushDebugEvent('analysis_completed', {
          jobId: result.jobId,
          activeStage: result.timeline?.summary?.active_stage || null,
          eventCount: result.timeline?.events?.length || 0,
        })
      } catch (pipelineError) {
        if (pipelineError?.name === 'AbortError') return
        pushDebugEvent('analysis_failed', {
          message: pipelineError?.message || 'Pipeline analyse mislukt',
          checkedBase: (pipelineApiBase || '').trim(),
          checkedUrl: `${(pipelineApiBase || '').trim()}/api/v1/health`,
        })
        setPipelineState((prev) => ({
          ...prev,
          status: 'failed',
          error: pipelineError?.message || 'Pipeline analyse mislukt',
          debug: buildPipelineDebug({
            checkedBase: (pipelineApiBase || '').trim(),
            checkedUrl: `${(pipelineApiBase || '').trim()}/api/v1/health`,
            message: pipelineError?.message || 'Pipeline analyse mislukt',
          }),
        }))
      }
    },
    [aagFallbackEnabled, disabledStages, pipelineApiBase, pipelineApiKey, pipelineEnabled, stopPipelineRequest],
  )

  // Auto-restart when settings change
  const triggerAutoRestart = useCallback(
    (sourceFile) => {
      if (!pendingRestartRef.current) return false
      if (!sourceFile || !pipelineEnabled) return false
      const settled = ['completed', 'failed', 'unavailable', 'auth_required', 'disabled']
      if (!settled.includes(pipelineState.status)) return false
      pendingRestartRef.current = false
      setPipelineState(EMPTY_PIPELINE_STATE)
      void startPipeline(sourceFile)
      return true
    },
    [pipelineEnabled, pipelineState.status, startPipeline],
  )

  // Derived values
  const backendMesh = pipelineState?.result?.mesh || null
  const backendVisuals = pipelineState?.result?.visuals || null
  const pipelineVisuals = useMemo(() => {
    const visuals = { ...(backendVisuals || {}) }
    for (const event of pipelineState?.events || []) {
      if (!event?.payload) continue
      if (event.stage === 'Profile Router' && event.type === 'classification_decision') {
        visuals.router = { ...(visuals.router || {}), ...event.payload }
      }
      if (event.stage === 'Classify geometry' && event.type === 'geometry_classified') {
        visuals.classification = { ...(visuals.classification || {}), ...event.payload }
      }
      if (event.stage === 'Detect holes' && event.type === 'holes_detected') {
        visuals.holes = { ...(visuals.holes || {}), ...event.payload }
      }
      if (isPreUnfoldStageName(event.stage) && event.type === 'holes_detected_pre_unfold') {
        visuals.holes_pre_unfold = { ...(visuals.holes_pre_unfold || {}), ...event.payload }
      }
      if (event.stage === 'Unfold' && event.type === 'unfold_result') {
        visuals.unfold = { ...(visuals.unfold || {}), ...event.payload }
      }
    }
    return visuals
  }, [backendVisuals, pipelineState?.events])

  const flatMesh = backendVisuals?.unfold?.flat_mesh || null
  const groupedStages = useMemo(() => groupEventsByStage(pipelineState?.events || []), [pipelineState?.events])
  const summary = pipelineState?.summary
  const analysisStartedMs = parseIsoToMs(summary?.analysis_started_at)
  const activeStageStartedMs = parseIsoToMs(summary?.active_stage_started_at)

  return {
    pipelineEnabled,
    setPipelineEnabled,
    aagFallbackEnabled,
    handleAagFallbackToggle,
    disabledStages,
    handleStageToggle,
    pipelineApiBase,
    setPipelineApiBase,
    pipelineApiKey,
    setPipelineApiKey,
    pipelineState,
    setPipelineState,
    debugEvents,
    startPipeline,
    stopPipelineRequest,
    triggerAutoRestart,
    backendMesh,
    pipelineVisuals,
    flatMesh,
    groupedStages,
    summary,
    analysisStartedMs,
    activeStageStartedMs,
  }
}
