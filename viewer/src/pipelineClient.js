const DEFAULT_API_BASE =
  import.meta.env.VITE_PIPELINE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

function trimTrailingSlash(value) {
  return (value || '').replace(/\/$/, '')
}

function validateHeaderValue(value, label) {
  const stringValue = String(value ?? '')
  for (let index = 0; index < stringValue.length; index += 1) {
    const codePoint = stringValue.charCodeAt(index)
    if (codePoint > 0xff) {
      throw new Error(`${label} bevat niet-ondersteunde tekens. Gebruik alleen standaard ASCII/Latin-1 tekens.`)
    }
  }
  if (/[\r\n]/.test(stringValue)) {
    throw new Error(`${label} bevat ongeldige regeleinden.`)
  }
  return stringValue
}

export function getApiKeyHeaders(apiKey = '', extraHeaders = {}) {
  const headers = new Headers(extraHeaders)
  const trimmedApiKey = String(apiKey || '').trim()
  if (!trimmedApiKey) return headers
  headers.set('X-API-Key', validateHeaderValue(trimmedApiKey, 'API key'))
  return headers
}

export function sanitizeUploadFileName(fileName = 'upload.step') {
  const trimmed = String(fileName || '').trim()
  const fallback = 'upload.step'
  const normalized = trimmed || fallback
  const lastDotIndex = normalized.lastIndexOf('.')
  const rawBase = lastDotIndex > 0 ? normalized.slice(0, lastDotIndex) : normalized
  const rawExtension = lastDotIndex > 0 ? normalized.slice(lastDotIndex).toLowerCase() : ''
  const safeBase = rawBase
    .normalize('NFKD')
    .replace(/[^\x20-\x7e]/g, '_')
    .replace(/[^A-Za-z0-9._-]/g, '_')
    .replace(/_+/g, '_')
  const collapsedBase = safeBase.replace(/^[_\.]+|[_\.]+$/g, '')
  const candidateBase = collapsedBase || 'upload'
  const extension = rawExtension === '.stp' ? '.stp' : '.step'
  return `${candidateBase}${extension}`
}

function buildHeaders(apiKey, extraHeaders = {}) {
  return getApiKeyHeaders(apiKey, extraHeaders)
}

function getErrorMessage(error, fallback) {
  if (error?.name === 'AbortError') return 'Pipeline request afgebroken'
  return error?.message || fallback
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options)
  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.json()
      detail = payload?.detail || ''
    } catch {
      detail = await response.text()
    }
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json()
}

async function fetchStatus(url, options = {}) {
  let response
  try {
    response = await fetch(url, options)
  } catch (error) {
    return {
      ok: false,
      status: 'unavailable',
      message: getErrorMessage(error, 'Pipeline backend niet bereikbaar'),
      url,
      code: 'network_error',
    }
  }

  if (response.ok) {
    return { ok: true, status: 'ready', message: null, url, code: null }
  }

  if (response.status === 401) {
    return {
      ok: false,
      status: 'auth_required',
      message: 'Pipeline API vereist een geldige X-API-Key',
      url,
      code: 'auth_required',
    }
  }

  let detail = ''
  try {
    const payload = await response.json()
    detail = payload?.detail || ''
  } catch {
    detail = await response.text()
  }

  return {
    ok: false,
    status: 'unavailable',
    message: detail || `${response.status} ${response.statusText}`,
    url,
    code: `http_${response.status}`,
  }
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms)
    if (!signal) return

    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(id)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

export function getDefaultPipelineApiBase() {
  return trimTrailingSlash(DEFAULT_API_BASE)
}

export async function checkPipelineConnection(options = {}) {
  const { apiBase = getDefaultPipelineApiBase(), apiKey = '', signal } = options

  const base = trimTrailingSlash(apiBase)
  if (!base) {
    return {
      ok: false,
      status: 'unavailable',
      message: 'Pipeline API URL ontbreekt',
    }
  }

  return fetchStatus(`${base}/api/v1/health`, {
    method: 'GET',
    signal,
    headers: buildHeaders(apiKey),
  })
}

export async function runPipelineAnalysis(file, options = {}) {
  const {
    apiBase = getDefaultPipelineApiBase(),
    apiKey = '',
    aag = true,
    disableStages = [],
    onProgress,
    signal,
    pollIntervalMs = 1200,
    pollTimeoutMs = 10 * 60 * 1000,
  } = options

  const base = trimTrailingSlash(apiBase)
  if (!base) {
    throw new Error('Pipeline API URL ontbreekt')
  }

  const parts = [`aag=${aag ? 'true' : 'false'}`]
  if (disableStages.length > 0) {
    parts.push(`disable_stages=${disableStages.join(',')}`)
  }
  const analyzeUrl = `${base}/api/v1/analyze?${parts.join('&')}`
  const formData = new FormData()
  formData.append('file', file, sanitizeUploadFileName(file?.name))

  let created
  try {
    created = await fetchJson(analyzeUrl, {
      method: 'POST',
      body: formData,
      signal,
      headers: buildHeaders(apiKey),
    })
  } catch (error) {
    throw new Error(`${getErrorMessage(error, 'Upload naar pipeline mislukt')} (${analyzeUrl})`)
  }

  const jobId = created?.job_id
  if (!jobId) {
    throw new Error('Geen job_id terug van API')
  }

  onProgress?.({ stage: 'queued', status: 'queued', jobId })

  const startedAt = Date.now()
  while (true) {
    if (Date.now() - startedAt > pollTimeoutMs) {
      throw new Error('Pipeline timeout: job duurde te lang')
    }

    let job
    try {
      job = await fetchJson(`${base}/api/v1/jobs/${jobId}`, {
        signal,
        headers: buildHeaders(apiKey),
      })
    } catch (error) {
      throw new Error(`${getErrorMessage(error, 'Job status ophalen mislukt')} (${base}/api/v1/jobs/${jobId})`)
    }

    onProgress?.({
      stage: 'job_status',
      status: job?.status || 'unknown',
      jobId,
      job,
      timeline: {
        events: job?.timeline_events || [],
        summary: job?.timeline_summary || null,
      },
    })

    if (job?.status === 'completed') {
      let timeline
      try {
        timeline = await fetchJson(`${base}/api/v1/jobs/${jobId}/timeline`, {
          signal,
          headers: buildHeaders(apiKey),
        })
      } catch (error) {
        throw new Error(`${getErrorMessage(error, 'Timeline ophalen mislukt')} (${base}/api/v1/jobs/${jobId}/timeline)`)
      }

      onProgress?.({
        stage: 'timeline',
        status: 'completed',
        jobId,
        job,
        timeline,
      })

      return { jobId, job, timeline }
    }

    if (job?.status === 'failed') {
      const reason = job?.error || 'Onbekende fout in pipeline'
      throw new Error(`Pipeline job mislukt: ${reason}`)
    }

    await delay(pollIntervalMs, signal)
  }
}
