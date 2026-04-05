import React, { useEffect, useState, useMemo } from 'react'
import * as THREE from 'three'
import { parseStepFile } from './stepLoader'

const MATERIAL_PRESETS = {
  technical_steel: {
    label: 'Technisch staal',
    color: '#d1d8df',
    roughness: 0.36,
    metalness: 0.82,
    edgeColor: '#223243',
    envIntensity: 1.38,
  },
  s235jr_en10025: {
    label: 'S235JR (NEN-EN 10025-2)',
    color: '#b7c0c7',
    roughness: 0.68,
    metalness: 0.42,
    edgeColor: '#243443',
    envIntensity: 0.92,
  },
  aluminium_5754: {
    label: 'Aluminium EN AW-5754 (NEN-EN 485)',
    color: '#d8dee3',
    roughness: 0.34,
    metalness: 0.82,
    edgeColor: '#43596c',
    envIntensity: 1.28,
  },
  rvs_304: {
    label: 'RVS 304 / 1.4301 (NEN-EN 10088-2)',
    color: '#dfe5e8',
    roughness: 0.24,
    metalness: 0.94,
    edgeColor: '#546270',
    envIntensity: 1.42,
  },
  dx51d_z: {
    label: 'Verzinkt DX51D+Z (NEN-EN 10346)',
    color: '#d2d6db',
    roughness: 0.52,
    metalness: 0.66,
    edgeColor: '#3e4f5e',
    envIntensity: 1.08,
  },
}

export function getViewerMaterialPresets() {
  return MATERIAL_PRESETS
}

export function getViewerRenderModes() {
  return [
    { value: 'studio', label: 'Studio' },
    { value: 'analysis', label: 'Analyse' },
    { value: 'xray', label: 'X-ray' },
    { value: 'wireframe', label: 'Wireframe' },
    { value: 'edges', label: 'Edges only' },
  ]
}

function edgeThresholdForMesh(vertexCount) {
  if (vertexCount > 250000) return 72
  if (vertexCount > 120000) return 58
  if (vertexCount > 60000) return 46
  return 38
}

function createThreeData(meshes) {
  return meshes.map((mesh) => {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(mesh.positions, 3))
    geometry.setIndex(new THREE.BufferAttribute(mesh.indices, 1))
    if (mesh.normals?.length === mesh.positions.length) {
      geometry.setAttribute('normal', new THREE.BufferAttribute(mesh.normals, 3))
    } else {
      geometry.computeVertexNormals()
    }
    const vertexCount = (mesh.positions?.length || 0) / 3
    const edgePositions = mesh.edgeSegments
    let lineGeometry
    if (edgePositions?.length) {
      lineGeometry = new THREE.BufferGeometry()
      lineGeometry.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3))
    } else {
      lineGeometry = new THREE.EdgesGeometry(geometry, edgeThresholdForMesh(vertexCount))
    }
    return { geometry, lineGeometry }
  })
}

function buildBackendMeshes(mesh) {
  if (!mesh?.vertices?.length || !mesh?.indices?.length) return null

  return [
    {
      positions: new Float32Array(mesh.vertices),
      indices: new Uint32Array(mesh.indices),
      normals: mesh.normals?.length ? new Float32Array(mesh.normals) : null,
      edgeSegments: mesh.display_edges?.length ? new Float32Array(mesh.display_edges) : null,
      color: null,
      name: 'pipeline-mesh',
    },
  ]
}

function summarizeMeshes(meshes) {
  const box = new THREE.Box3()
  const point = new THREE.Vector3()
  let vertexCount = 0
  let triangleCount = 0

  meshes.forEach((mesh) => {
    const positions = mesh.positions || []
    const indices = mesh.indices || []

    vertexCount += positions.length / 3
    triangleCount += indices.length / 3

    for (let i = 0; i < positions.length; i += 3) {
      point.set(positions[i], positions[i + 1], positions[i + 2])
      box.expandByPoint(point)
    }
  })

  const center = new THREE.Vector3()
  const size = new THREE.Vector3()
  const sphere = new THREE.Sphere()
  box.getCenter(center)
  box.getSize(size)
  box.getBoundingSphere(sphere)

  return {
    vertexCount,
    triangleCount,
    meshCount: meshes.length,
    center,
    size,
    boundingRadius: sphere.radius || 1,
  }
}

function disposeThreeData(threeData) {
  if (!threeData?.items) return
  threeData.items.forEach((item) => {
    item.geometry?.dispose?.()
    item.lineGeometry?.dispose?.()
  })
}

function StepGeometry({
  buffer,
  mesh,
  onLoaded,
  onError,
  onStatus,
  onDebug,
  onSurfacePick,
  parseMode = 'auto',
  renderMode = 'studio',
  materialPreset = 'technical_steel',
}) {
  const [meshData, setMeshData] = useState(null)
  const materialStyle = MATERIAL_PRESETS[materialPreset] || MATERIAL_PRESETS.technical_steel
  const surfaceStyle = useMemo(() => {
    if (renderMode === 'xray') {
      return {
        type: 'physical',
        opacity: 0.16,
        roughness: Math.min(materialStyle.roughness + 0.08, 1),
        metalness: materialStyle.metalness,
        transmission: 0.22,
        thickness: 0.8,
        clearcoat: 0.75,
        reflectivity: 0.9,
        edgeOpacity: 0.96,
        edgeColor: '#0f1720',
      }
    }
    if (renderMode === 'analysis') {
      return {
        type: 'physical',
        opacity: 0.28,
        roughness: Math.min(materialStyle.roughness + 0.04, 1),
        metalness: materialStyle.metalness,
        transmission: 0.0,
        thickness: 0.0,
        clearcoat: 0.95,
        reflectivity: 1.0,
        edgeOpacity: 1,
        edgeColor: '#111827',
      }
    }
    return {
      type: 'physical',
      opacity: 0.96,
      roughness: Math.max(materialStyle.roughness - 0.08, 0.12),
      metalness: Math.max(materialStyle.metalness - 0.08, 0.48),
      transmission: 0.0,
      thickness: 0.0,
      clearcoat: 1.0,
      reflectivity: 1.0,
      edgeOpacity: renderMode === 'edges' ? 1 : 0.9,
      edgeColor: materialStyle.edgeColor,
      emissive: '#3a4148',
      emissiveIntensity: 0.16,
    }
  }, [materialStyle, renderMode])

  useEffect(() => {
    let cancelled = false

    async function load() {
      const backendMeshes = buildBackendMeshes(mesh)
      if (backendMeshes) {
        onDebug?.({
          source: 'step-model',
          stage: 'backend_mesh_used',
          meshCount: backendMeshes.length,
        })
        setMeshData(backendMeshes)
        onLoaded?.(summarizeMeshes(backendMeshes))
        onStatus?.('Viewer asset geladen via pipeline')
        return
      }

      if (!buffer || parseMode === 'backend-only') {
        onDebug?.({
          source: 'step-model',
          stage: 'no_local_parse',
          hasBuffer: Boolean(buffer),
          parseMode,
        })
        setMeshData(null)
        return
      }

      try {
        onDebug?.({
          source: 'step-model',
          stage: 'wasm_parse_start',
          bytes: buffer?.byteLength || 0,
          parseMode,
        })
        onStatus?.('OpenCascade WASM laden...')
        const result = await parseStepFile(buffer, { onDebug })
        if (cancelled) return

        setMeshData(result.meshes)
        onDebug?.({
          source: 'step-model',
          stage: 'wasm_parse_done',
          meshCount: Array.isArray(result.meshes) ? result.meshes.length : 0,
        })
        onLoaded?.(summarizeMeshes(result.meshes))
        onStatus?.('Klaar')
      } catch (err) {
        if (!cancelled) {
          console.error('[ALES] STEP load error:', err)
          const cause = err?.cause || null
          const phase = cause?.phase ? ` [${cause.phase}]` : ''
          const location =
            cause?.filename
              ? ` @ ${cause.filename}${cause?.lineno ? `:${cause.lineno}` : ''}${cause?.colno ? `:${cause.colno}` : ''}`
              : ''
          const errorMessage = `${err.message || String(err)}${phase}${location}`
          onDebug?.({
            source: 'step-model',
            stage: 'wasm_parse_error',
            error: errorMessage,
            cause,
          })
          onError?.(errorMessage)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [buffer, mesh, onLoaded, onError, onStatus, parseMode])

  const threeData = useMemo(() => {
    if (!meshData) return null
    const summary = summarizeMeshes(meshData)
    return {
      items: createThreeData(meshData),
      center: summary.center,
    }
  }, [meshData])

  useEffect(() => {
    return () => disposeThreeData(threeData)
  }, [threeData])

  if (!threeData) return null

  return (
    <group position={[-threeData.center.x, -threeData.center.y, -threeData.center.z]}>
      {threeData.items.map((item, i) => (
        <React.Fragment key={i}>
          {renderMode !== 'edges' && (
            <mesh
              geometry={item.geometry}
              onClick={(event) => {
                const worldNormal = event.face?.normal?.clone?.() || null
                if (worldNormal) {
                  worldNormal.transformDirection(event.object.matrixWorld)
                }
                onSurfacePick?.(
                  {
                    point: event.point?.clone?.() || event.point,
                    normal: worldNormal,
                  },
                  event,
                )
              }}
            >
              {renderMode === 'wireframe' ? (
                <meshBasicMaterial
                  color={materialStyle.edgeColor}
                  wireframe
                  transparent
                  opacity={0.92}
                  side={THREE.DoubleSide}
                />
              ) : (
                <meshPhysicalMaterial
                  color={materialStyle.color}
                  roughness={surfaceStyle.roughness}
                  metalness={surfaceStyle.metalness}
                  envMapIntensity={materialStyle.envIntensity}
                  clearcoat={surfaceStyle.clearcoat}
                  clearcoatRoughness={Math.max(surfaceStyle.roughness * 0.55, 0.08)}
                  reflectivity={surfaceStyle.reflectivity}
                  emissive={surfaceStyle.emissive || '#000000'}
                  emissiveIntensity={surfaceStyle.emissiveIntensity || 0}
                  transmission={surfaceStyle.transmission}
                  thickness={surfaceStyle.thickness}
                  ior={1.5}
                  transparent
                  opacity={surfaceStyle.opacity}
                  side={THREE.DoubleSide}
                  polygonOffset
                  polygonOffsetFactor={1}
                  polygonOffsetUnits={1}
                />
              )}
            </mesh>
          )}
          {renderMode !== 'wireframe' && (
            <lineSegments geometry={item.lineGeometry}>
              <lineBasicMaterial color={surfaceStyle.edgeColor} transparent opacity={surfaceStyle.edgeOpacity} />
            </lineSegments>
          )}
        </React.Fragment>
      ))}
    </group>
  )
}

export default function StepModel({ buffer, mesh, onLoaded, onError, onStatus, onDebug, onSurfacePick, parseMode, renderMode, materialPreset }) {
  return (
    <StepGeometry
      buffer={buffer}
      mesh={mesh}
      onLoaded={onLoaded}
      onError={onError}
      onStatus={onStatus}
      onDebug={onDebug}
      onSurfacePick={onSurfacePick}
      parseMode={parseMode}
      renderMode={renderMode}
      materialPreset={materialPreset}
    />
  )
}
