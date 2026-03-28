import { createContext, useContext } from 'react'
import { useSelection } from '../hooks/useSelection'

const SelectionContext = createContext(null)

export function SelectionProvider({ children, ...selectionDeps }) {
  const selection = useSelection(...selectionDeps)
  return <SelectionContext.Provider value={selection}>{children}</SelectionContext.Provider>
}

export function useSelectionContext() {
  return useContext(SelectionContext)
}
