import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FLOWSTATE + BMW backend (flowstate/app/api.py) runs on :8090. In dev we
// proxy /api and /health to it so the app and backend share an origin; in the
// APK / on the Mac, VITE_BACKEND_URL points straight at the tailnet address.
const BACKEND = process.env.VITE_DEV_BACKEND ?? 'http://127.0.0.1:8090'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
})
