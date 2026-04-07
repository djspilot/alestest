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

function formatWorkerCrashMessage(event) {
  const message = event?.message || 'STEP worker crashte'
  const location = event?.filename
    ? ` @ ${event.filename}${event?.lineno ? `:${event.lineno}` : ''}${event?.colno ? `:${event.colno}` : ''}`
    : ''
  return `${message}${location}`
}

function getWorkerScriptUrl() {
  const baseUrl = import.meta.env.BASE_URL || '/'
  const normalizedBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  return `${normalizedBase}step-worker.js`
}

function getWorker(onDebug) {
  if (workerInstance) return workerInstance

  const workerScript = getWorkerScriptUrl()
  workerInstance = new Worker(workerScript)
  emitDebug(onDebug, 'worker_created', { script: workerScript })
  workerInstance.onmessage = (event) => {
    const { id, success, error, errorDetail, ...payload } = event.data || {}
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
      errorDetail: errorDetail || null,
    })
    const failure = new Error(error || 'STEP parsing mislukt')
    if (errorDetail) failure.cause = errorDetail
    request.reject(failure)
  }
  workerInstance.onerror = (event) => {
    const message = formatWorkerCrashMessage(event)
    pendingRequests.forEach(({ reject, onDebug }) => {
      emitDebug(onDebug, 'worker_error', {
        error: message,
        filename: event?.filename || null,
        lineno: event?.lineno || null,
        colno: event?.colno || null,
      })
      reject(new Error(message))
    })
    pendingRequests.clear()
    workerInstance.terminate()
    workerInstance = null
  }
  workerInstance.onmessageerror = () => {
    pendingRequests.forEach(({ reject, onDebug }) => {
      emitDebug(onDebug, 'worker_message_error', {
        error: 'Worker response kon niet worden gelezen',
      })
      reject(new Error('Worker response kon niet worden gelezen'))
    })
    pendingRequests.clear()
    workerInstance.terminate()
    workerInstance = null
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
    worker.postMessage({ id, buffer })
  })
}

export function disposeStepWorker() {
  if (!workerInstance) return
  workerInstance.terminate()
  workerInstance = null
  pendingRequests.clear()
}
