import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'
import { controlledStaticAssets } from './build/staticAssets.mjs'

export default defineConfig(() => {
  const useMockApi = process.env.VITE_USE_MOCK_API !== 'false'

  return {
    publicDir: false,
    plugins: [react(), controlledStaticAssets()],
    server: {
      proxy: {
        '/auth': 'http://localhost:5000',
        ...(useMockApi
          ? {}
          : {
              '/api': 'http://localhost:5000',
              '/uploads': 'http://localhost:5000',
              '/trucks': 'http://localhost:5000',
              '/jobs': 'http://localhost:5000',
              '/ai': 'http://localhost:5000',
              '^/client/.*\\.html$': 'http://localhost:5000',
            }),
      }
    }
  }
})
