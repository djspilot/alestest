let workerInstance = null
let requestId = 0
const pendingRequests = new Map()

function getWorker() {
  if (workerInstance) return workerInstance

  workerInstance = new Worker('/step-worker.js')
  workerInstance.onmessage = (event) => {
    const { id, success, error, ...payload } = event.data || {}
    const request = pendingRequests.get(id)
    if (!request) return

    pendingRequests.delete(id)
    if (success) {
      request.resolve(payload)
      return
    }
    request.reject(new Error(error || 'STEP parsing mislukt'))
  }
  workerInstance.onerror = (event) => {
    const message = event?.message || 'STEP worker crashte'
    pendingRequests.forEach(({ reject }) => reject(new Error(message)))
    pendingRequests.clear()
  }

  return workerInstance
}

export async function parseStepFile(buffer) {
  const worker = getWorker()
  const id = ++requestId

  return new Promise((resolve, reject) => {
    pendingRequests.set(id, { resolve, reject })
    worker.postMessage({ id, buffer }, [buffer])
  })
}

export function disposeStepWorker() {
  if (!workerInstance) return
  workerInstance.terminate()
  workerInstance = null
  pendingRequests.clear()
}
