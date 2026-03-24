import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'react-vendor'
          }
          if (id.includes('node_modules/three') || id.includes('@react-three')) {
            return 'viewer-3d'
          }
          if (id.includes('src/ViewerCanvas.jsx') || id.includes('src/StepModel.jsx') || id.includes('src/stepLoader.js')) {
            return 'viewer-runtime'
          }
          return undefined
        },
      },
    },
  },
})
