import { useCallback, useEffect, useState } from 'react'
import { readFileAsArrayBuffer } from '../lib/files'

export function useViewer({ startPipeline, pipelineEnabled, pipelineState, activeMesh, parseMode }) {
  const [fileBuffer, setFileBuffer] = useState(null)
  const [fileName, setFileName] = useState(null)
  const [sourceFile, setSourceFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)
  const [engineStatus, setEngineStatus] = useState('Klaar')
  const [debugEvents, setDebugEvents] = useState([])

  const pushDebugEvent = useCallback((event) => {
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      ...event,
    }
    setDebugEvents((current) => [...current.slice(-199), entry])
  }, [])

  // Clear loading when mesh is available
  useEffect(() => {
    if (activeMesh) {
      setLoading(false)
      pushDebugEvent({
        source: 'viewer',
        stage: 'active_mesh_available',
      })
    }
  }, [activeMesh, pushDebugEvent])

  const handleFile = useCallback(
    (file, options = {}) => {
      const { skipPipelineStart = false } = options
      const ext = file.name.split('.').pop().toLowerCase()
      if (!['step', 'stp'].includes(ext)) {
        setError('Ongeldig bestandstype. Alleen .step/.stp bestanden.')
        pushDebugEvent({
          source: 'viewer',
          stage: 'file_rejected',
          fileName: file.name,
          extension: ext,
        })
        return
      }

      setError(null)
      setLoading(true)
      setFileName(file.name)
      setSourceFile(file)
      setModelInfo(null)
      setEngineStatus('Bestand laden...')
      setFileBuffer(null)
      pushDebugEvent({
        source: 'viewer',
        stage: 'file_selected',
        fileName: file.name,
        bytes: file.size || 0,
        pipelineEnabled,
      })

      if (pipelineEnabled && !skipPipelineStart) {
        void readFileAsArrayBuffer(file)
          .then((result) => {
            setFileBuffer(result)
            setLoading(false)
            pushDebugEvent({
              source: 'viewer',
              stage: 'local_preview_buffer_ready',
              bytes: result?.byteLength || 0,
            })
            setEngineStatus((currentStatus) =>
              currentStatus === 'Pipeline analyse starten...' ? 'Lokale STEP preview laden...' : currentStatus,
            )
          })
          .catch((readError) => {
            setError(readError.message || 'Bestand lezen mislukt.')
            setLoading(false)
            setEngineStatus('Fout')
            pushDebugEvent({
              source: 'viewer',
              stage: 'file_read_error',
              error: readError.message || 'Bestand lezen mislukt.',
            })
          })
        setEngineStatus('Pipeline analyse starten...')
        pushDebugEvent({
          source: 'viewer',
          stage: 'pipeline_start_requested',
          fileName: file.name,
        })
        void startPipeline(file)
        return
      }

      void readFileAsArrayBuffer(file)
        .then((result) => {
          setFileBuffer(result)
          setLoading(false)
          pushDebugEvent({
            source: 'viewer',
            stage: 'local_parse_buffer_ready',
            bytes: result?.byteLength || 0,
          })
          setEngineStatus('STEP verwerken via OpenCascade WASM...')
        })
        .catch((readError) => {
          setError(readError.message || 'Bestand lezen mislukt.')
          setLoading(false)
          setEngineStatus('Fout')
          pushDebugEvent({
            source: 'viewer',
            stage: 'file_read_error',
            error: readError.message || 'Bestand lezen mislukt.',
          })
        })
    },
    [pipelineEnabled, pushDebugEvent, startPipeline],
  )

  // Fallback to browser WASM when pipeline finishes without backend mesh
  useEffect(() => {
    const pipelineSettled = ['completed', 'failed', 'unavailable', 'auth_required'].includes(pipelineState.status)
    if (!pipelineEnabled || !pipelineSettled || !sourceFile || activeMesh || fileBuffer) return

    let cancelled = false
    setEngineStatus('Backend mesh ontbreekt, browser fallback laden...')
    pushDebugEvent({
      source: 'viewer',
      stage: 'backend_mesh_missing_fallback_start',
      pipelineStatus: pipelineState.status,
    })

    void readFileAsArrayBuffer(sourceFile)
      .then((result) => {
        if (cancelled) return
        setFileBuffer(result)
        setLoading(false)
        setEngineStatus('STEP verwerken via OpenCascade WASM...')
        pushDebugEvent({
          source: 'viewer',
          stage: 'fallback_buffer_ready',
          bytes: result?.byteLength || 0,
        })
      })
      .catch((readError) => {
        if (cancelled) return
        setError(readError.message || 'Bestand lezen mislukt.')
        setLoading(false)
        setEngineStatus('Fout')
        pushDebugEvent({
          source: 'viewer',
          stage: 'fallback_read_error',
          error: readError.message || 'Bestand lezen mislukt.',
        })
      })

    return () => {
      cancelled = true
    }
  }, [activeMesh, fileBuffer, pipelineEnabled, pipelineState.status, pushDebugEvent, sourceFile])

  const handleModelLoaded = useCallback((info) => {
    setModelInfo(info)
    setEngineStatus('OpenCascade actief')
    pushDebugEvent({
      source: 'viewer',
      stage: 'model_loaded',
      vertexCount: info?.vertexCount || 0,
      triangleCount: info?.triangleCount || 0,
      meshCount: info?.meshCount || 0,
      boundingRadius: info?.boundingRadius || 0,
    })
  }, [pushDebugEvent])

  const handleModelError = useCallback((message) => {
    setError(`Model laden mislukt: ${message}`)
    setEngineStatus('Fout')
    pushDebugEvent({
      source: 'viewer',
      stage: 'model_error',
      error: message,
    })
  }, [pushDebugEvent])

  const handleStatus = useCallback((status) => {
    setEngineStatus(status)
    pushDebugEvent({
      source: 'viewer',
      stage: 'status',
      status,
    })
  }, [pushDebugEvent])

  const resetViewer = useCallback(
    (stopPipelineRequest, setPipelineState, EMPTY_PIPELINE_STATE, resetSelection) => {
      stopPipelineRequest()
      setFileBuffer(null)
      setFileName(null)
      setSourceFile(null)
      setModelInfo(null)
      setError(null)
      setEngineStatus('Klaar')
      setDebugEvents([])
      setPipelineState(EMPTY_PIPELINE_STATE)
      if (resetSelection) resetSelection()
    },
    [],
  )

  return {
    fileBuffer,
    fileName,
    sourceFile,
    loading,
    error,
    modelInfo,
    engineStatus,
    debugEvents,
    pushDebugEvent,
    setEngineStatus,
    setFileBuffer,
    setFileName,
    setSourceFile,
    setLoading,
    setError,
    setModelInfo,
    handleFile,
    handleModelLoaded,
    handleModelError,
    handleStatus,
    resetViewer,
  }
}
