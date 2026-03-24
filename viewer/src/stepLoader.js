/**
 * STEP file loader using occt-import-js (OpenCascade WASM).
 * No external API or key required — runs entirely in the browser.
 */

let occtInstance = null
let occtScriptPromise = null
const STEP_HEADER = 'ISO-10303-21;'

const OCCT_SCRIPT_URLS = [
  'https://cdn.jsdelivr.net/npm/occt-import-js@0.0.23/dist/occt-import-js.js',
  'https://unpkg.com/occt-import-js@0.0.23/dist/occt-import-js.js',
]

async function ensureOcctScriptLoaded() {
  if (typeof globalThis.occtimportjs === 'function') return

  if (!occtScriptPromise) {
    occtScriptPromise = (async () => {
      let lastError = null
      for (const url of OCCT_SCRIPT_URLS) {
        try {
          await new Promise((resolve, reject) => {
            const script = document.createElement('script')
            script.src = url
            script.async = true
            script.onload = resolve
            script.onerror = () => reject(new Error(`Script laden mislukt: ${url}`))
            document.head.appendChild(script)
          })
          if (typeof globalThis.occtimportjs === 'function') return
        } catch (error) {
          lastError = error
        }
      }
      throw lastError || new Error('occt-import-js script laden mislukt')
    })()
  }

  await occtScriptPromise
}

export async function initOcct() {
  if (occtInstance) return occtInstance

  // Load occt-import-js via CDN script tag (CJS module, not ESM compatible)
  await ensureOcctScriptLoaded()

  if (typeof globalThis.occtimportjs !== 'function') {
    throw new Error('occt-import-js niet beschikbaar na laden')
  }

  occtInstance = await globalThis.occtimportjs({
    locateFile: (name) => {
      if (name.endsWith('.wasm')) return '/occt-import-js.wasm'
      return name
    },
  })

  console.log('[ALES] OpenCascade WASM geladen')
  return occtInstance
}

function normalizeStepBuffer(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
  const headerBytes = new TextEncoder().encode(STEP_HEADER)

  let startIndex = 0
  const searchLimit = Math.min(bytes.length - headerBytes.length, 256)
  for (let i = 0; i <= searchLimit; i += 1) {
    let matches = true
    for (let j = 0; j < headerBytes.length; j += 1) {
      if (bytes[i + j] !== headerBytes[j]) {
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

/**
 * Parse a STEP file buffer and return mesh data compatible with Three.js.
 * @param {ArrayBuffer} buffer - The raw STEP file bytes
 * @returns {{ meshes, vertexCount, triangleCount, meshCount }}
 */
export async function parseStepFile(buffer) {
  const occt = await initOcct()
  const fileBuffer = normalizeStepBuffer(buffer)

  const attempts = [{ label: 'standaard', args: [fileBuffer, null] }]

  let result = null
  let lastError = null

  for (const attempt of attempts) {
    try {
      const candidate = occt.ReadStepFile(...attempt.args)
      if (candidate?.success) {
        result = candidate
        break
      }

      const detail = candidate?.error || candidate?.message || 'onbekende parserfout'
      lastError = new Error(`STEP parsing mislukt (${attempt.label}): ${detail}`)
    } catch (error) {
      lastError = new Error(`STEP parsing crashte (${attempt.label}): ${error.message || String(error)}`)
    }
  }

  if (!result?.success) {
    throw lastError || new Error('STEP parsing mislukt')
  }

  if (!result.meshes || result.meshes.length === 0) {
    throw new Error('Geen geometrie gevonden in STEP bestand')
  }

  let totalVertices = 0
  let totalTriangles = 0

  const meshes = result.meshes.map((mesh) => {
    const positions = new Float32Array(mesh.attributes.position.array)
    const indices = new Uint32Array(mesh.index.array)
    const hasNormals = mesh.attributes.normal?.array?.length > 0
    const normals = hasNormals ? new Float32Array(mesh.attributes.normal.array) : null
    const color = mesh.color || null

    totalVertices += positions.length / 3
    totalTriangles += indices.length / 3

    return { positions, indices, normals, color, name: mesh.name || '' }
  })

  console.log(`[ALES] STEP geparsed: ${meshes.length} meshes, ${totalVertices} vertices, ${totalTriangles} driehoeken`)

  return {
    meshes,
    vertexCount: totalVertices,
    triangleCount: totalTriangles,
    meshCount: meshes.length,
  }
}
