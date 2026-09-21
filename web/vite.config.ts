import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// base: the site is served from a repository subpath on GitHub Pages.
export default defineConfig({
  plugins: [preact()],
  base: process.env.PIDX_WEB_BASE ?? '/parts-index/',
  server: { port: 5173, strictPort: false },
  build: { outDir: 'dist', emptyOutDir: true },
})
