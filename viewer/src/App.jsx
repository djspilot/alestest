import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { ContactShadows, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import StepModel from './StepModel'
import Dropzone from './Dropzone'
import Sidebar from './Sidebar'
import { checkPipelineConnection, getDefaultPipelineApiBase, runPipelineAnalysis } from './pipelineClient'

const EMPTY_PIPELINE_STATE = {
  status: 'idle',
  jobId: null,
  events: [],
  summary: null,
  error: null,
  result: null,
}

function CameraFitter({ modelInfo, controlsRef }) {
  const { camera, invalidate } = useThree()

  useEffect(() => {
    if (!modelInfo?.boundingRadius || !controlsRef.current) return

    const radius = Math.max(modelInfo.boundingRadius, 1)
    const distance = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.15

    camera.position.set(distance * 0.9, distance * 0.7, distance * 0.9)
    camera.near = Math.max(distance / 1000, 0.1)
    camera.far = Math.max(distance * 25, 1000)
    camera.updateProjectionMatrix()

    controlsRef.current.target.set(0, 0, 0)
    controlsRef.current.minDistance = Math.max(radius * 0.35, 1)
    controlsRef.current.maxDistance = Math.max(radius * 12, 50)
    controlsRef.current.update()
    controlsRef.current.saveState()
    invalidate()
  }, [camera, controlsRef, invalidate, modelInfo])

  return null
}

function longestAxisInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => b.value - a.value)
  return entries[0]
}

function shortestAxisInfo(size) {
  const entries = [
    { key: 'x', value: size?.x || 0, vector: [1, 0, 0] },
    { key: 'y', value: size?.y || 0, vector: [0, 1, 0] },
    { key: 'z', value: size?.z || 0, vector: [0, 0, 1] },
  ]
  entries.sort((a, b) => a.value - b.value)
  return entries[0]
}

function parseHoleSize(value, fallback = 12) {
  if (!value) return [fallback, fallback]
  const match = String(value).match(/(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)/i)
  if (!match) return [fallback, fallback]
  return [Number(match[1]), Number(match[2])]
}

function quaternionFromDirection(direction) {
  const normal = new THREE.Vector3(...direction).normalize()
  return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
}

function crossSectionDimensions(size, axisKey) {
  if (!size) return [20, 20]
  if (axisKey === 'x') return [size.y || 20, size.z || 20]
  if (axisKey === 'y') return [size.x || 20, size.z || 20]
  return [size.x || 20, size.y || 20]
}

function rectanglePoints(width, height) {
  const halfW = Math.max(width, 1) / 2
  const halfH = Math.max(height, 1) / 2
  return [
    [-halfW, -halfH, 0],
    [halfW, -halfH, 0],
    [halfW, halfH, 0],
    [-halfW, halfH, 0],
  ]
}

function circlePoints(radius, segments = 64) {
  const safeRadius = Math.max(radius, 1)
  return Array.from({ length: segments }, (_, index) => {
    const angle = (index / segments) * Math.PI * 2
    return [Math.cos(angle) * safeRadius, Math.sin(angle) * safeRadius, 0]
  })
}

function buildSectionContours(partType, size, thickness, axisKey) {
  const [dimA, dimB] = crossSectionDimensions(size, axisKey)
  const width = Math.max(dimA, dimB)
  const height = Math.min(dimA, dimB)
  const normalizedType = String(partType || '').toUpperCase()
  const isRound = normalizedType.includes('BUIS') && !normalizedType.includes('KOKER')
  const isRectangular = normalizedType.includes('KOKER') || normalizedType.includes('KOKERPROFIEL') || !isRound

  if (isRound) {
    const outerRadius = Math.min(width, height) / 2
    const contours = [circlePoints(outerRadius)]
    const innerRadius = outerRadius - Math.max(thickness || 0, 0)
    if (innerRadius > 1) contours.push(circlePoints(innerRadius))
    return contours
  }

  const contours = [rectanglePoints(width, height)]
  const innerWidth = width - (2 * Math.max(thickness || 0, 0))
  const innerHeight = height - (2 * Math.max(thickness || 0, 0))
  if (innerWidth > 2 && innerHeight > 2) {
    contours.push(rectanglePoints(innerWidth, innerHeight))
  }
  if (!isRectangular) {
    contours.push(rectanglePoints(width * 0.9, height * 0.9))
  }
  return contours
}

function HoleOutline({ hole, center }) {
  const position = [
    hole.position[0] - center.x,
    hole.position[1] - center.y,
    hole.position[2] - center.z,
  ]

  if (hole.type === 'cylindrical') {
    const radius = Math.max((hole.diameter || 8) / 2, 3)
    const quaternion = quaternionFromDirection(hole.axis || [1, 0, 0])
    return (
      <group position={position} quaternion={quaternion} renderOrder={20}>
        <mesh>
          <torusGeometry args={[radius, Math.max(radius * 0.18, 1.4), 16, 72]} />
          <meshBasicMaterial color="#8f0008" transparent opacity={1} depthTest={false} depthWrite={false} />
        </mesh>
        <mesh>
          <torusGeometry args={[radius, Math.max(radius * 0.06, 0.65), 16, 72]} />
          <meshBasicMaterial color="#ff2d2d" transparent opacity={1} depthTest={false} depthWrite={false} />
        </mesh>
      </group>
    )
  }

  const [width, height] = parseHoleSize(hole.size || hole.label, 14)
  const quaternion = quaternionFromDirection(hole.normal || [1, 0, 0])
  return (
    <group position={position} quaternion={quaternion} renderOrder={20}>
      <mesh>
        <planeGeometry args={[Math.max(width, 6), Math.max(height, 6)]} />
        <meshBasicMaterial
          color="#8f0008"
          wireframe
          transparent
          opacity={1}
          side={THREE.DoubleSide}
          depthTest={false}
          depthWrite={false}
        />
      </mesh>
      <mesh>
        <planeGeometry args={[Math.max(width * 0.88, 5), Math.max(height * 0.88, 5)]} />
        <meshBasicMaterial
          color="#ff5a1f"
          wireframe
          transparent
          opacity={1}
          side={THREE.DoubleSide}
          depthTest={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function SectionContour({ points, position, quaternion, color }) {
  const flatPoints = useMemo(() => new Float32Array(points.flat()), [points])

  return (
    <lineLoop position={position} quaternion={quaternion} renderOrder={15}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[flatPoints, 3]} />
      </bufferGeometry>
      <lineBasicMaterial
        color={color}
        transparent
        opacity={1}
        depthTest={false}
        depthWrite={false}
      />
    </lineLoop>
  )
}

function SectionContours({ position, quaternion, contours, color }) {
  return (
    <group position={position} quaternion={quaternion} renderOrder={15}>
      {contours.map((points, index) => (
        <SectionContour
          key={`section-contour-${index}`}
          points={points}
          position={[0, 0, index * 0.25]}
          quaternion={new THREE.Quaternion()}
          color={color}
        />
      ))}
      <mesh>
        <circleGeometry args={[2.4, 24]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.98}
          depthTest={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function buildFallbackSections(modelInfo) {
  if (!modelInfo?.size) return []
  const axis = longestAxisInfo(modelInfo.size)
  const length = axis.value || 1
  const fractions = [0.2, 0.35, 0.5, 0.65, 0.8]
  return fractions.map((fraction) => {
    const offset = (fraction - 0.5) * length
    const position = [0, 0, 0]
    if (axis.key === 'x') position[0] = offset
    if (axis.key === 'y') position[1] = offset
    if (axis.key === 'z') position[2] = offset
    return position
  })
}

function StageOverlays({ modelInfo, visuals, focusedStage }) {
  const center = modelInfo?.center
  if (!center || !visuals || !focusedStage) return null

  const holeVisuals = visuals?.holes?.items || []
  const routerVisuals = visuals?.router || null
  const classificationVisuals = visuals?.classification || null
  const unfoldVisuals = visuals?.unfold || null
  const size = modelInfo?.size
  const overlayExtent = Math.max(size?.x || 0, size?.y || 0, size?.z || 0, 50)

  const makePosition = (position) => [
    position[0] - center.x,
    position[1] - center.y,
    position[2] - center.z,
  ]

  const planeQuaternion = new THREE.Quaternion()
  if (routerVisuals?.axis_direction) {
    const normal = new THREE.Vector3(...routerVisuals.axis_direction).normalize()
    planeQuaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
  }

  const fallbackAxis = longestAxisInfo(size)
  const fallbackQuaternion = quaternionFromDirection(fallbackAxis.vector)
  const contourPartType = classificationVisuals?.part_type || routerVisuals?.profile_label || ''
  const contourThickness = classificationVisuals?.thickness || 0
  const contours = buildSectionContours(contourPartType, size, contourThickness, fallbackAxis.key)
  const routerSections = (routerVisuals?.sampled_sections || []).map((section) => ({
    position: makePosition(section.origin_3d),
    quaternion: planeQuaternion,
  }))
  const fallbackSections = buildFallbackSections(modelInfo).map((position) => ({
    position,
    quaternion: fallbackQuaternion,
  }))
  const sectionVisuals = routerSections.length > 0 ? routerSections : fallbackSections
  const foldVisuals = (unfoldVisuals?.fold_details || []).map((fold) => ({
    position: makePosition(fold.center),
    length: fold.length || overlayExtent * 0.4,
  }))

  return (
    <group>
      {focusedStage === 'Detect holes' && holeVisuals.map((hole, index) => (
        <HoleOutline key={`${hole.type}-${index}`} hole={hole} center={center} />
      ))}

      {focusedStage === 'Profile Router' && sectionVisuals.map((section, index) => (
        <SectionContours
          key={`router-section-${index}`}
          position={section.position}
          quaternion={section.quaternion}
          contours={contours}
          color="#8f0008"
        />
      ))}

      {focusedStage === 'Classify geometry' && sectionVisuals.map((section, index) => (
        <SectionContours
          key={`classify-section-${index}`}
          position={section.position}
          quaternion={section.quaternion}
          contours={contours}
          color="#6f0010"
        />
      ))}

      {focusedStage === 'Unfold' && foldVisuals.map((fold, index) => (
        <group key={`fold-${index}`} position={fold.position} renderOrder={20}>
          <mesh rotation={[0, 0, Math.PI / 4]}>
            <planeGeometry args={[Math.max(fold.length * 0.18, 18), 4]} />
            <meshBasicMaterial
              color="#8f0008"
              transparent
              opacity={1}
              side={THREE.DoubleSide}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>
          <mesh rotation={[0, 0, -Math.PI / 4]}>
            <planeGeometry args={[Math.max(fold.length * 0.18, 18), 4]} />
            <meshBasicMaterial
              color="#ff3b30"
              transparent
              opacity={1}
              side={THREE.DoubleSide}
              depthTest={false}
              depthWrite={false}
            />
          </mesh>
        </group>
      ))}
    </group>
  )
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
  const [pipelineApiBase, setPipelineApiBase] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-base') || getDefaultPipelineApiBase()
  })
  const [pipelineApiKey, setPipelineApiKey] = useState(() => {
    return window.localStorage.getItem('ales-pipeline-api-key') || ''
  })
  const [pipelineState, setPipelineState] = useState(EMPTY_PIPELINE_STATE)
  const [focusedStage, setFocusedStage] = useState(null)
  const controlsRef = useRef()
  const pipelineAbortRef = useRef(null)
  const backendMesh = pipelineState?.result?.mesh || null
  const backendVisuals = pipelineState?.result?.visuals || null
  const flatMesh = backendVisuals?.unfold?.flat_mesh || null
  const holeSource = backendVisuals?.holes?.source || null
  const useFlatView =
    Boolean(flatMesh) &&
    (focusedStage === 'Unfold' || (focusedStage === 'Detect holes' && holeSource === 'flat'))
  const activeMesh = useFlatView ? flatMesh : backendMesh
  const shouldWaitForBackendMesh =
    pipelineEnabled &&
    !backendMesh &&
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
    if (!pipelineEnabled) {
      stopPipelineRequest()
      setPipelineState({ ...EMPTY_PIPELINE_STATE, status: 'disabled' })
    }
  }, [pipelineEnabled, stopPipelineRequest])

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
    } catch (error) {
      if (error?.name === 'AbortError') return
      setPipelineState((prev) => ({
        ...prev,
        status: 'failed',
        error: error?.message || 'Pipeline analyse mislukt',
      }))
    }
  }, [pipelineApiBase, pipelineApiKey, pipelineEnabled, stopPipelineRequest])

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
    setEngineStatus('Bestand laden...')
    setPipelineState(EMPTY_PIPELINE_STATE)

    void startPipeline(file)

    const reader = new FileReader()
    reader.onload = () => {
      setFileBuffer(reader.result)
      setLoading(false)
      setEngineStatus('STEP verwerken via OpenCascade WASM...')
    }
    reader.onerror = () => {
      setError('Bestand lezen mislukt.')
      setLoading(false)
      setEngineStatus('Fout')
    }
    reader.readAsArrayBuffer(file)
  }, [startPipeline])

  const handleModelLoaded = useCallback((info) => {
    setModelInfo(info)
    setEngineStatus('OpenCascade actief')
  }, [])

  const handleModelError = useCallback((err) => {
    setError(`Model laden mislukt: ${err}`)
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
    setError(null)
    setEngineStatus('Klaar')
    setPipelineState(EMPTY_PIPELINE_STATE)
  }, [stopPipelineRequest])

  const resetCamera = useCallback(() => {
    if (controlsRef.current) controlsRef.current.reset()
  }, [])

  return (
    <div className="app">
      <div className="header">
        <h1>ALES STEP Viewer</h1>
        <span className="header-status">{engineStatus}</span>
      </div>

      {error && (
        <div className="error-banner">
          <strong>Fout:&nbsp;</strong>{error}
          <button className="toolbar-btn" style={{ marginLeft: 'auto' }} onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div className="main-content">
        <Sidebar
          modelInfo={modelInfo}
          fileName={fileName}
          onReset={resetViewer}
          pipelineEnabled={pipelineEnabled}
          onPipelineToggle={setPipelineEnabled}
          pipelineApiBase={pipelineApiBase}
          onPipelineApiBaseChange={setPipelineApiBase}
          pipelineApiKey={pipelineApiKey}
          onPipelineApiKeyChange={setPipelineApiKey}
          pipelineState={pipelineState}
          pipelineVisuals={backendVisuals}
          onStageFocus={setFocusedStage}
          onRetryPipeline={() => {
            if (!sourceFile) return
            setPipelineState(EMPTY_PIPELINE_STATE)
            void startPipeline(sourceFile)
          }}
        />

        <div className="viewer-container">
          {!fileBuffer && !loading && <Dropzone onFile={handleFile} />}

          {loading && (
            <div className="loading-overlay">
              <div className="spinner" />
              <div className="loading-text">Bestand laden...</div>
              <div className="loading-sub">{fileName}</div>
            </div>
          )}

          {fileBuffer && (
            <>
              <div className="viewer-toolbar">
                <button className="toolbar-btn" onClick={resetCamera}>Reset View</button>
                <button className="toolbar-btn" onClick={resetViewer}>Nieuw bestand</button>
              </div>
              <div className="viewer-info">
                {fileName} {modelInfo ? `— ${modelInfo.vertexCount?.toLocaleString() || '?'} vertices` : '— laden...'}
                {useFlatView ? ' — uitslagweergave' : ' — 3D weergave'}
              </div>
            </>
          )}

          <Canvas
            shadows
            camera={{ position: [150, 100, 150], fov: 40, near: 0.1, far: 10000 }}
            style={{ background: 'linear-gradient(180deg, #f0f4f8 0%, #e2e8f0 100%)' }}
          >
            <ambientLight intensity={0.5 * Math.PI} />
            <directionalLight position={[100, 150, 100]} intensity={0.8} castShadow />
            <directionalLight position={[-80, 50, -60]} intensity={0.3} />

            {fileBuffer && (
              <StepModel
                buffer={fileBuffer}
                mesh={activeMesh}
                onLoaded={handleModelLoaded}
                onError={handleModelError}
                onStatus={handleStatus}
                parseMode={parseMode}
              />
            )}

            <CameraFitter modelInfo={modelInfo} controlsRef={controlsRef} />
            <StageOverlays modelInfo={modelInfo} visuals={backendVisuals} focusedStage={focusedStage} />
            <ContactShadows position={[0, -0.5, 0]} opacity={0.3} blur={2} />
            <gridHelper args={[500, 25, '#c8ced8', '#e5e9ef']} />
            <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.08} enablePan={false} />
          </Canvas>
        </div>
      </div>
    </div>
  )
}
