const STEP_HEADER = 'ISO-10303-21;'
const STEP_HEADER_BYTES = new TextEncoder().encode(STEP_HEADER)

let occtInstancePromise = null

function normalizeStepBuffer(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)

  let startIndex = 0
  const searchLimit = Math.min(bytes.length - STEP_HEADER_BYTES.length, 256)
  for (let i = 0; i <= searchLimit; i += 1) {
    let matches = true
    for (let j = 0; j < STEP_HEADER_BYTES.length; j += 1) {
      if (bytes[i + j] !== STEP_HEADER_BYTES[j]) {
        matches = false
        break
      }
    }
    if (matches) {
      startIndex = i
      break
    }
  }

  return startIndex > 0 ? bytes.slice(startIndex) : bytes
}

async function initOcct() {
  if (!occtInstancePromise) {
    occtInstancePromise = (async () => {
      self.importScripts('/occt-import-js.js')

      if (typeof self.occtimportjs !== 'function') {
        throw new Error('occt-import-js niet beschikbaar in worker')
      }

      return self.occtimportjs({
        locateFile: (name) => {
          if (name.endsWith('.wasm')) return '/occt-import-js.wasm'
          return name
        },
      })
    })()
  }

  return occtInstancePromise
}

self.onmessage = async (event) => {
  const { id, buffer } = event.data || {}

  try {
    const occt = await initOcct()
    const fileBuffer = normalizeStepBuffer(buffer)
    const result = occt.ReadStepFile(fileBuffer, null)

    if (!result?.success) {
      const detail = result?.error || result?.message || 'onbekende parserfout'
      throw new Error(`STEP parsing mislukt: ${detail}`)
    }

    if (!result.meshes || result.meshes.length === 0) {
      throw new Error('Geen geometrie gevonden in STEP bestand')
    }

    let totalVertices = 0
    let totalTriangles = 0
    const transferables = []

    const meshes = result.meshes.map((mesh) => {
      const positions = new Float32Array(mesh.attributes.position.array)
      const indices = new Uint32Array(mesh.index.array)
      const normals = mesh.attributes.normal?.array?.length
        ? new Float32Array(mesh.attributes.normal.array)
        : null

      totalVertices += positions.length / 3
      totalTriangles += indices.length / 3

      transferables.push(positions.buffer, indices.buffer)
      if (normals) transferables.push(normals.buffer)

      return {
        positions,
        indices,
        normals,
        color: mesh.color || null,
        name: mesh.name || '',
      }
    })

    self.postMessage({
      id,
      success: true,
      meshes,
      vertexCount: totalVertices,
      triangleCount: totalTriangles,
      meshCount: meshes.length,
    }, transferables)
  } catch (error) {
    self.postMessage({
      id,
      success: false,
      error: error?.message || String(error),
    })
  }
}
