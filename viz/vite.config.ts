import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Same backend as the phone app: flowstate/app/api.py on :8090. In dev, /api
// and /health are proxied so the dashboard and backend share an origin.
const BACKEND = process.env.VITE_DEV_BACKEND ?? 'http://127.0.0.1:8090'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5174,
    allowedHosts: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
})
