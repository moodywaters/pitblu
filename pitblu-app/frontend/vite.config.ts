import react from '@vitejs/plugin-react';
import {VitePWA} from 'vite-plugin-pwa';
import {defineConfig} from 'vitest/config';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'pitblu-logo.png'],
      manifest: {
        name: 'Pitblu',
        short_name: 'Pitblu',
        description: 'Calm, cook-aware temperature monitoring',
        theme_color: '#0868d7',
        background_color: '#eef6ff',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [{src: '/pitblu-logo.png', sizes: '1536x1536', type: 'image/png', purpose: 'any maskable'}]
      },
      workbox: {
        navigateFallback: '/index.html',
        runtimeCaching: [],
        navigateFallbackDenylist: [/^\/api\//, /^\/health$/, /^\/ready$/]
      }
    })
  ],
  build: {
    outDir: '../src/pitblu_app/static',
    emptyOutDir: true,
    sourcemap: false
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8081',
      '/health': 'http://127.0.0.1:8081',
      '/ready': 'http://127.0.0.1:8081'
    }
  },
  test: {
    exclude: ['visual-tests/**', 'node_modules/**'],
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    restoreMocks: true
  }
});
