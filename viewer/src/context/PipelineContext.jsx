import { createContext, useContext } from 'react'
import { usePipeline } from '../hooks/usePipeline'

const PipelineContext = createContext(null)

export function PipelineProvider({ children }) {
  const pipeline = usePipeline()
  return <PipelineContext.Provider value={pipeline}>{children}</PipelineContext.Provider>
}

export function usePipelineContext() {
  return useContext(PipelineContext)
}
