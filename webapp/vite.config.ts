import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Use relative asset URLs so the Telegram WebView works correctly even when
  // Amvera/reverse-proxy serves the Mini App under /app/ or rewrites the prefix.
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/assets': 'http://127.0.0.1:8080',
    },
  },
})
