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

  // Clear loading when mesh is available
  useEffect(() => {
    if (activeMesh) {
      setLoading(false)
    }
  }, [activeMesh])

  const handleFile = useCallback(
    (file) => {
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
      setEngineStatus('Bestand laden...')
      setFileBuffer(null)

      if (pipelineEnabled) {
        void readFileAsArrayBuffer(file)
          .then((result) => {
            setFileBuffer(result)
            setLoading(false)
            setEngineStatus((currentStatus) =>
              currentStatus === 'Pipeline analyse starten...' ? 'Lokale STEP preview laden...' : currentStatus,
            )
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
    },
    [pipelineEnabled, startPipeline],
  )

  // Fallback to browser WASM when pipeline finishes without backend mesh
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

  const resetViewer = useCallback(
    (stopPipelineRequest, setPipelineState, EMPTY_PIPELINE_STATE, resetSelection) => {
      stopPipelineRequest()
      setFileBuffer(null)
      setFileName(null)
      setSourceFile(null)
      setModelInfo(null)
      setError(null)
      setEngineStatus('Klaar')
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
