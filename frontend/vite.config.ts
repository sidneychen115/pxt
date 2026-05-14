import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Match docker/nginx: avoid 504 while FastAPI is blocked by a background backtest.
        timeout: 600_000,
      },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
