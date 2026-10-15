import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const base = process.env.VITE_BASE || env.VITE_BASE || '/mgr/'
  return {
    base,
    plugins: [react()],
    server: {
      port: 5175,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:9100',
          changeOrigin: true,
        },
      },
    },
  }
})
