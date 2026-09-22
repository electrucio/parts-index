import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// base: the site is served from a repository subpath on GitHub Pages.
export default defineConfig({
  plugins: [preact()],
  base: process.env.PIDX_WEB_BASE ?? '/parts-index/',
  // Bound to every interface, not just loopback, so the site can be looked at from another machine on
  // the network — this project is developed on a headless box. strictPort: fail rather than wander to
  // another port, because the address is written down in the Makefile and in the README.
  server: {
    host: process.env.PIDX_WEB_HOST ?? '0.0.0.0',
    port: Number(process.env.PIDX_WEB_PORT ?? 8026),
    strictPort: true,
  },
  preview: {
    host: process.env.PIDX_WEB_HOST ?? '0.0.0.0',
    port: Number(process.env.PIDX_WEB_PORT ?? 8026),
    strictPort: true,
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
