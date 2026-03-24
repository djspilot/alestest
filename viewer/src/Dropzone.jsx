import React, { useCallback, useState, useRef } from 'react'

export default function Dropzone({ onFile }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) onFile(file)
  }, [onFile])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  const handleDragLeave = useCallback(() => setDragging(false), [])
  const handleClick = useCallback(() => inputRef.current?.click(), [])

  const handleChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) onFile(file)
  }, [onFile])

  return (
    <div
      className={`dropzone-overlay ${dragging ? 'dragging' : ''}`}
      onClick={handleClick}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      <div className="dropzone-icon">⚙</div>
      <div className="dropzone-text">Sleep een STEP bestand hierheen</div>
      <div className="dropzone-hint">of klik om een bestand te selecteren (.step, .stp)</div>
      <input ref={inputRef} type="file" accept=".step,.stp,.STEP,.STP" onChange={handleChange} />
    </div>
  )
}
