import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy /api to the FastAPI backend. Prod: `npm run build` -> dist, served by FastAPI at / (same origin) or by
// Vercel, where src/api.js sends API calls to the Render service. Vercel sets VERCEL=1 during its builds.
export default defineConfig({
  plugins: [react()],
  define: { __VERCEL_BUILD__: JSON.stringify(Boolean(process.env.VERCEL)) },
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_BASE || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { outDir: 'dist', sourcemap: false },
})
