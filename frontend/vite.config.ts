import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Keep the dev proxy pointed at wherever the API actually is: run.sh picks a
// free port and exports it, so hard-coding one here would silently break.
const apiPort = process.env.YANGSTUDIO_PORT ?? '8420'
const uiPort = Number(process.env.YANGSTUDIO_UI_PORT ?? 5173)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': new URL('./src', import.meta.url).pathname },
  },
  server: {
    port: uiPort,
    // Talk to the FastAPI backend in dev without CORS gymnastics.
    proxy: {
      '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
    },
  },
})
