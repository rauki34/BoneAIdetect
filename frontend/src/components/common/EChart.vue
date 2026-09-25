<template>
  <div ref="el" :style="{ width: '100%', height: typeof height === 'number' ? height + 'px' : height }" />
</template>

<script setup>
/**
 * ECharts 封装（阶段 12）
 *
 * 为什么要有它：改造前有 7 处裸 `echarts.init`，散在 AdminApproval.vue 里。
 * 那些代码的**初始化**部分其实写得不错（有 `if (!chart)` 防止重复 init，
 * 也有 resize 与 dispose），真正缺的是**卸载清理**：
 *
 *   - `onUnmounted` 只清了训练轮询定时器，7 个图表实例一个都没 dispose
 *   - 挂在 window 上的 resize 监听从未移除，它的回调闭包持有整个组件作用域
 *
 * 后果是每进一次管理页就多留一份实例与闭包（图表持有 canvas 与 DOM 引用），
 * 反复切换页面时内存只增不减。这种 bug 不会报错，只会让页面越用越卡 ——
 * 所以放进封装里一次性解决，而不是在每个调用点各写一遍。
 *
 * 用 ResizeObserver 而不是 window.resize：容器尺寸变化（侧边栏折叠、Tab 切换、
 * 弹窗展开）根本不会触发 window 的 resize，那正是图表"变窄了却不跟着缩放"
 * 的原因。
 */
import { onMounted, onUnmounted, shallowRef, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [Number, String], default: 300 },
  // 数据量大时可关掉动画，避免频繁 setOption 时的抖动
  animation: { type: Boolean, default: true },
  // 无数据时是否显示空状态（图表区域留白）
  empty: { type: Boolean, default: false }
})

const emit = defineEmits(['click'])
const el = shallowRef(null)          // shallowRef：DOM 节点不需要深层响应式
const chart = shallowRef(null)       // echarts 实例同样不该被 Vue 代理包裹
let observer = null

const render = () => {
  if (!chart.value) return
  chart.value.setOption(props.option || {}, { notMerge: true })
}

onMounted(() => {
  if (!el.value) return
  chart.value = echarts.init(el.value)
  chart.value.on('click', params => emit('click', params))
  render()
  // 容器尺寸变化时自动 resize（比 window.resize 精确：侧边栏折叠也能捕获）
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => chart.value?.resize())
    observer.observe(el.value)
  }
})

onUnmounted(() => {
  // 顺序要紧：先断开观察、再销毁实例，否则销毁过程中 observer 还可能触发一次
  observer?.disconnect()
  observer = null
  chart.value?.dispose()
  chart.value = null
})

watch(() => props.option, render, { deep: true })
watch(() => props.empty, () => chart.value?.clear())

defineExpose({
  /** 拿到原始实例（少数场景需要：如 toDataURL 导出图片） */
  getInstance: () => chart.value
})
</script>
