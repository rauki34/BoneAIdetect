// ESLint 配置（阶段 12）
//
// **只开"代码跑不起来"这一类规则**，与后端 ruff.toml 同一思路：
//
//   no-undef        未定义的标识符引用
//   no-unused-vars  未使用的变量/导入
//   no-dupe-keys    对象字面量里的重复键（后者静默覆盖前者）
//   no-const-assign 给 const 赋值
//   use-isnan / no-unsafe-negation / no-dupe-args / no-unreachable
//
// 价值已被验证过一次：把 `chartRegistry` 的声明删掉却漏了引用时，
// **`vite build` 照样通过**（ES 里未定义变量只有运行时才炸），而这类引用
// 一跑起来就是 ReferenceError。前端没有测试也没有浏览器自动化，静态检查
// 在这里不是锦上添花。
//
// 为什么不上 eslint-plugin-vue 的 recommended：本仓库此前没有 linter，
// 一把开起来会在既有代码上报出成百上千条风格告警（缩进、属性顺序、v-for
// 加 key……），把真问题淹掉。先只上上面这些 —— 与 ruff 的取舍一致：
// 等现有告警清零了，再逐条讨论要不要加。
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/base'],
  {
    files: ['**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        ResizeObserver: 'readonly',
        WebSocket: 'readonly',
        FormData: 'readonly',
        File: 'readonly',
        FileReader: 'readonly',
        Blob: 'readonly',
        URL: 'readonly',
        Image: 'readonly',
        EventSource: 'readonly',
        navigator: 'readonly',
        history: 'readonly',
        location: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        CustomEvent: 'readonly',
        Event: 'readonly',
        HTMLElement: 'readonly',
        MediaStream: 'readonly',
        MediaRecorder: 'readonly',
        performance: 'readonly',
        getComputedStyle: 'readonly',
      },
    },
    rules: {
      'no-undef': 'error',
      // 降级为 warn：本文件建立时既有代码里还有约 24 处历史遗留的未使用变量
      // 与几个"改了交互方式后没人调"的处理函数。**逐条删除需要确认模板引用**，
      // 不适合在收尾阶段批量动手（已删掉 3 个确认为桩函数/重复实现的：
      // disableDoctor / saveConfig / publishModel）。先让它们以警告形式可见，
      // 而不是把这条规则整条关掉 —— 它抓到的"导入了却没接线"通常是真问题。
      'no-unused-vars': ['warn', { args: 'none', caughtErrors: 'none' }],
      'no-dupe-keys': 'error',
      'no-dupe-args': 'error',
      'no-const-assign': 'error',
      'no-unreachable': 'error',
      'use-isnan': 'error',
      'no-unsafe-negation': 'error',
      'no-unsafe-optional-chaining': 'error',
      'no-self-assign': 'error',
      'no-cond-assign': 'error',
      // base 配置已含 vue/no-undef-components 等；这里把风格类关掉
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'error',
      'vue/no-dupe-keys': 'error',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', '*.config.js'],
  },
]
