export function readFileAsArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('Bestand lezen mislukt.'))
    reader.readAsArrayBuffer(file)
  })
}

export async function fetchFileAsBrowserFile(url, fileName, options = {}) {
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new Error(`Bestand ophalen mislukt (${response.status} ${response.statusText})`)
  }
  const blob = await response.blob()
  return new File([blob], fileName, {
    type: blob.type || 'application/step',
    lastModified: Date.now(),
  })
}
