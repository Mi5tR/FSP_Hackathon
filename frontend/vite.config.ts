import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // API_TARGET позволяет поднять фронтенд против бэкенда на другом порту
    proxy: { '/api': process.env.API_TARGET ?? 'http://127.0.0.1:8000' },
  },
})
