import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [vue()],
  root: __dirname,
  base: '/static/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    cors: true,
    allowedHosts: true,
    watch: {
      usePolling: true,
    },
  },
  build: {
    outDir: resolve(__dirname, 'dist'),
    manifest: 'manifest.json',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/main.js',
    },
  },
})