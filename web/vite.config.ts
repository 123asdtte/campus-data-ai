import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发期把 /api 代理到 Import API，避免浏览器直接跨域访问后端。
// 目标地址可用 VITE_PROXY_TARGET 覆盖，默认指向本机容器映射端口。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // PR-B：开发期把 /gw 代理到本机网关映射端口
      '/gw': {
        target: process.env.VITE_GATEWAY_TARGET ?? 'http://127.0.0.1:9190',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/gw/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
