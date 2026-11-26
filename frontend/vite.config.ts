import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  const runtime = process.env.VITE_APP_MODE ?? loadEnv(mode, process.cwd()).VITE_APP_MODE ?? (command === 'build' ? 'api' : 'demo')
  if (runtime !== 'api' && runtime !== 'demo') throw new Error('VITE_APP_MODE must be api or demo.')
  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: { '@fooddiary/runtime': fileURLToPath(new URL('./src/modes/' + runtime + '.ts', import.meta.url)) },
    },
    server: {
      host: '127.0.0.1',
      proxy: { '/api': 'http://127.0.0.1:' + (process.env.FOODDIARY_BACKEND_PORT ?? '8000') },
    },
  }
})
