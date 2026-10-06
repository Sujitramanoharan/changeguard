import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7860',
    },
  },
  build: {
    outDir: '../frontend_dist',
    // outDir is outside web/, so Vite won't clear it unless told to;
    // without this every build left its old bundles behind.
    emptyOutDir: true,
  },
})
