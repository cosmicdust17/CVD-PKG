import { readFileSync } from 'node:fs'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const proxy = { '/api': { target: loadEnv(mode, '.', 'HF_').HF_API_TARGET || 'http://127.0.0.1:8088' } }
  const pages = mode === 'pages'
  return {
    plugins: [vue(), {
      name: 'pages-source-graphs',
      apply: 'build',
      generateBundle() {
        if (!pages) return
        const datasets = ['primary-prevention', 'cardiovascular-report-2024', 'healthy-lifestyle']
        for (const dataset of datasets) {
          const file = new URL('../output/' + dataset + '-triples/triples.json', import.meta.url)
          this.emitFile({ type: 'asset', fileName: 'data/sources/' + dataset + '.json', source: readFileSync(file) })
        }
      },
    }],
    base: pages ? '/CVD-PKG/' : './',
    server: { port: 5187, proxy },
    preview: { host: '127.0.0.1', proxy },
  }
})
