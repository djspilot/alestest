const DEFAULT_API_BASE =
  import.meta.env.VITE_PIPELINE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

function trimTrailingSlash(value) {
  return (value || '').replace(/\/$/, '')
}

function buildHeaders(apiKey, extraHeaders = {}) {
  const headers = new Headers(extraHeaders)
  if (apiKey) {
    headers.set('X-API-Key', apiKey)
  }
  return headers
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
  formData.append('file', file)

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
