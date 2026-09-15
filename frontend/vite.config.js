import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],

  build: {
    // 按依赖体积分包，避免单个 chunk 过大
    // 页面级组件由 router 的动态 import 自动分包，不在此配置
    rollupOptions: {
      output: {
        manualChunks: {
          'vue': ['vue', 'vue-router'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'echarts': ['echarts'],
          'pdf': ['jspdf', 'html2canvas', 'html2pdf.js'],
          'markdown': ['vue-markdown-render', 'github-markdown-css'],
        }
      }
    }
  },

  server: {
    port: 5173
  }
})
