import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const useMockApi = process.env.VITE_USE_MOCK_API !== 'false'

  return {
    plugins: [react()],
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
