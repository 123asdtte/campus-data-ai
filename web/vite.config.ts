import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发期所有业务请求统一经 /gw 代理到 Java 网关。
// PR-D 起移除了 /api 直连 Import API 的代理，避免开发环境出现绕过网关的入口。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // PR-B：开发期把 /gw 代理到本机网关映射端口
      '/gw': {
        target: process.env.VITE_GATEWAY_TARGET ?? 'http://127.0.0.1:9190',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/gw/, ''),
      },
      // 本地开发经 Docker demo 入口代理到 demo-api；需先启动 8083 演示栈
      '/demo-api': {
        target: process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8083',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
