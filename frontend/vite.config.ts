/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import cesium from 'vite-plugin-cesium-build';
import path from 'node:path';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    cesium(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          cesium: ['cesium', 'resium'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'node',
  },
});
