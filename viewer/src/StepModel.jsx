import React, { useEffect, useState, useMemo } from 'react'
import * as THREE from 'three'
import { parseStepFile } from './stepLoader'

function createThreeData(meshes) {
  return meshes.map((mesh) => {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(mesh.positions, 3))
    geometry.setIndex(new THREE.BufferAttribute(mesh.indices, 1))
    if (mesh.normals) {
      geometry.setAttribute('normal', new THREE.BufferAttribute(mesh.normals, 3))
    } else {
      geometry.computeVertexNormals()
    }
    const edgesGeo = new THREE.EdgesGeometry(geometry, 38)
    const color = mesh.color
      ? new THREE.Color(mesh.color[0], mesh.color[1], mesh.color[2])
      : new THREE.Color('#7899aa')
    return { geometry, edgesGeo, color }
  })
}

function buildBackendMeshes(mesh) {
  if (!mesh?.vertices?.length || !mesh?.indices?.length) return null

  return [{
    positions: new Float32Array(mesh.vertices),
    indices: new Uint32Array(mesh.indices),
    normals: mesh.normals?.length ? new Float32Array(mesh.normals) : null,
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

function StepGeometry({ buffer, mesh, onLoaded, onError, onStatus, parseMode = 'auto' }) {
  const [meshData, setMeshData] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const backendMeshes = buildBackendMeshes(mesh)
      if (backendMeshes) {
        setMeshData(backendMeshes)
        onLoaded?.(summarizeMeshes(backendMeshes))
        onStatus?.('3D mesh geladen via pipeline')
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
    return () => { cancelled = true }
  }, [buffer, mesh, onLoaded, onError, onStatus, parseMode])

  const threeData = useMemo(() => {
    if (!meshData) return null
    const summary = summarizeMeshes(meshData)
    return {
      items: createThreeData(meshData),
      center: summary.center,
    }
  }, [meshData])

  if (!threeData) return null

  return (
    <group position={[-threeData.center.x, -threeData.center.y, -threeData.center.z]}>
      {threeData.items.map((item, i) => (
        <React.Fragment key={i}>
          <mesh geometry={item.geometry} castShadow receiveShadow>
            <meshStandardMaterial
              color="#d7e1e8"
              metalness={0.05}
              roughness={0.92}
              transparent
              opacity={0.045}
              side={THREE.DoubleSide}
            />
          </mesh>
          <lineSegments geometry={item.edgesGeo}>
            <lineBasicMaterial color="#08131d" transparent opacity={1} />
          </lineSegments>
        </React.Fragment>
      ))}
    </group>
  )
}

export default function StepModel({ buffer, mesh, onLoaded, onError, onStatus, parseMode }) {
  return (
    <StepGeometry
      buffer={buffer}
      mesh={mesh}
      onLoaded={onLoaded}
      onError={onError}
      onStatus={onStatus}
      parseMode={parseMode}
    />
  )
}
