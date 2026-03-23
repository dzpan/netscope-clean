import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev backend defaults to localhost:8000; override with VITE_API_TARGET env var
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:8000'

// Proxy all versioned API requests and root health check to the backend
const proxyConfig = {
  '/api': { target: API_TARGET, changeOrigin: true },
  '/health': { target: API_TARGET, changeOrigin: true },
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: proxyConfig,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1000,
  },
})
