import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { quasar, transformAssetUrls } from '@quasar/vite-plugin'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/',
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: false }),
    VitePWA({
      // `prompt` e não `autoUpdate`: recarregar sozinho pode descartar uma
      // contagem em digitação no meio da gôndola.
      registerType: 'prompt',
      devOptions: { enabled: true },
      includeAssets: ['favicon-32.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'Coleta de Estoque',
        short_name: 'Estoque',
        description: 'Coleta de estoque em ponto de venda',
        theme_color: '#1a237e',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        lang: 'pt-BR',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            // Clientes e produtos podem vir do cache quando não há sinal
            urlPattern: ({ url }) => url.pathname.startsWith('/merchandising/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'merch-cache',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 },
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { '@': new URL('./src', import.meta.url).pathname },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    allowedHosts: 'all',
    proxy: {
      '/api-proxy': {
        target: 'http://estoque_api:8000',
        rewrite: (path) => path.replace(/^\/api-proxy/, ''),
        changeOrigin: true,
      },
    },
    watch: { usePolling: true, interval: 500 },
  },
  build: { outDir: 'dist', sourcemap: false },
})
