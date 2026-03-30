let workerInstance = null
let requestId = 0
const pendingRequests = new Map()

function emitDebug(onDebug, stage, detail = {}) {
  onDebug?.({
    source: 'step-worker',
    stage,
    ...detail,
  })
}

function getWorker(onDebug) {
  if (workerInstance) return workerInstance

  workerInstance = new Worker('/step-worker.js')
  emitDebug(onDebug, 'worker_created', { script: '/step-worker.js' })
  workerInstance.onmessage = (event) => {
    const { id, success, error, ...payload } = event.data || {}
    const request = pendingRequests.get(id)
    if (!request) return

    pendingRequests.delete(id)
    if (success) {
      emitDebug(request.onDebug, 'worker_success', {
        requestId: id,
        meshCount: Array.isArray(payload.meshes) ? payload.meshes.length : 0,
      })
      request.resolve(payload)
      return
    }
    emitDebug(request.onDebug, 'worker_failure', {
      requestId: id,
      error: error || 'STEP parsing mislukt',
    })
    request.reject(new Error(error || 'STEP parsing mislukt'))
  }
  workerInstance.onerror = (event) => {
    const message = event?.message || 'STEP worker crashte'
    pendingRequests.forEach(({ reject, onDebug }) => {
      emitDebug(onDebug, 'worker_error', { error: message })
      reject(new Error(message))
    })
    pendingRequests.clear()
  }

  return workerInstance
}

export async function parseStepFile(buffer, options = {}) {
  const { onDebug } = options
  const worker = getWorker(onDebug)
  const id = ++requestId

  return new Promise((resolve, reject) => {
    const startedAt = performance.now()
    const warningTimer = window.setTimeout(() => {
      emitDebug(onDebug, 'worker_still_running', {
        requestId: id,
        elapsedMs: Math.round(performance.now() - startedAt),
      })
    }, 8000)

    pendingRequests.set(id, {
      resolve: (payload) => {
        window.clearTimeout(warningTimer)
        resolve(payload)
      },
      reject: (error) => {
        window.clearTimeout(warningTimer)
        reject(error)
      },
      onDebug,
    })
    emitDebug(onDebug, 'worker_request_sent', {
      requestId: id,
      bytes: buffer?.byteLength || 0,
    })
    worker.postMessage({ id, buffer }, [buffer])
  })
}

export function disposeStepWorker() {
  if (!workerInstance) return
  workerInstance.terminate()
  workerInstance = null
  pendingRequests.clear()
}
