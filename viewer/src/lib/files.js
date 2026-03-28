export function readFileAsArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('Bestand lezen mislukt.'))
    reader.readAsArrayBuffer(file)
  })
}
