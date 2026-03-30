import { formatLabel, } from '../pipelineUi'

export function getHoleStatusLabel(status) {
  if (status === 'accepted') return 'Geaccepteerd'
  if (status === 'rejected') return 'Afgewezen'
  if (status === 'probe') return 'Handmatige probe'
  return status || 'Onbekend'
}

export function getHoleMethodLabel(method) {
  if (method === 'face_boundary_primary') return 'Face Boundary (primair)'
  if (method === 'recovery_bucket_fallback') return 'Recovery Bucket (fallback)'
  if (method === 'cylindrical_detector') return 'Cylindrical detector'
  return method || 'Onbekend'
}

export function getClassificationStatusLabel(status) {
  if (status === 'WINNER') return 'Winner'
  if (status === 'MATCH') return 'Match'
  if (status === 'PASS') return 'Pass'
  if (status === 'FAIL') return 'Fail'
  if (status === 'SKIP') return 'Skip'
  if (status === 'FALLTHROUGH') return 'Fallthrough'
  return status || 'Onbekend'
}

export function getClassificationStatusClass(status) {
  if (status === 'WINNER' || status === 'MATCH') return 'is-winner'
  if (status === 'PASS') return 'is-accepted'
  if (status === 'FAIL') return 'is-rejected'
  if (status === 'FALLTHROUGH') return 'is-warning'
  return 'is-neutral'
}

export function exportDebugJson(payload, filename) {
  const content = JSON.stringify(payload, null, 2)
  try {
    const blob = new Blob([content], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    return `Debug JSON gedownload: ${filename}`
  } catch {
    try {
      const dataUrl = `data:application/json;charset=utf-8,${encodeURIComponent(content)}`
      window.open(dataUrl, '_blank', 'noopener,noreferrer')
      return 'Download fallback geopend in nieuwe tab'
    } catch {
      return 'Download mislukt in deze browser'
    }
  }
}

export async function copyDebugJson(payload) {
  const content = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(content)
    return 'Debug JSON gekopieerd naar klembord'
  } catch {
    try {
      const textArea = document.createElement('textarea')
      textArea.value = content
      textArea.style.position = 'fixed'
      textArea.style.left = '-9999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textArea)
      return ok ? 'Debug JSON gekopieerd (fallback)' : 'Kopieren mislukt (clipboard niet beschikbaar)'
    } catch {
      return 'Kopieren mislukt (clipboard niet beschikbaar)'
    }
  }
}
