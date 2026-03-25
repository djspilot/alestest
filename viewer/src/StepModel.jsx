import React, { useEffect, useState, useMemo } from 'react'
import * as THREE from 'three'
import { parseStepFile } from './stepLoader'

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

  return [{
    positions: new Float32Array(mesh.vertices),
    indices: new Uint32Array(mesh.indices),
    normals: mesh.normals?.length ? new Float32Array(mesh.normals) : null,
    edgeSegments: mesh.display_edges?.length ? new Float32Array(mesh.display_edges) : null,
    color: null,
    name: 'pipeline-mesh',
  }]
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

function StepGeometry({ buffer, mesh, onLoaded, onError, onStatus, onSurfacePick, parseMode = 'auto', renderMode = 'clean' }) {
  const [meshData, setMeshData] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const backendMeshes = buildBackendMeshes(mesh)
      if (backendMeshes) {
        setMeshData(backendMeshes)
        onLoaded?.(summarizeMeshes(backendMeshes))
        onStatus?.('Viewer asset geladen via pipeline')
        return
      }

      if (!buffer || parseMode === 'backend-only') {
        setMeshData(null)
        return
      }

      try {
        onStatus?.('OpenCascade WASM laden...')
        const result = await parseStepFile(buffer)
        if (cancelled) return

        setMeshData(result.meshes)
        onLoaded?.(summarizeMeshes(result.meshes))
        onStatus?.('Klaar')
      } catch (err) {
        if (!cancelled) {
          console.error('[ALES] STEP load error:', err)
          onError?.(err.message || String(err))
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
            <mesh geometry={item.geometry} onClick={(event) => onSurfacePick?.(event.point, event)}>
              <meshStandardMaterial
                color="#dfe6ec"
                roughness={0.88}
                metalness={0.02}
                transparent
                opacity={renderMode === 'ghost' ? 0.08 : 0.22}
                side={THREE.DoubleSide}
                polygonOffset
                polygonOffsetFactor={1}
                polygonOffsetUnits={1}
              />
            </mesh>
          )}
          <lineSegments geometry={item.lineGeometry}>
            <lineBasicMaterial color="#1d2a35" transparent opacity={0.82} />
          </lineSegments>
        </React.Fragment>
      ))}
    </group>
  )
}

export default function StepModel({ buffer, mesh, onLoaded, onError, onStatus, onSurfacePick, parseMode, renderMode }) {
  return (
    <StepGeometry
      buffer={buffer}
      mesh={mesh}
      onLoaded={onLoaded}
      onError={onError}
      onStatus={onStatus}
      onSurfacePick={onSurfacePick}
      parseMode={parseMode}
      renderMode={renderMode}
    />
  )
}
