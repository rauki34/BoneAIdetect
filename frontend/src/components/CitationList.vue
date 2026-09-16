<!--
  引用溯源卡片

  医疗场景下"这句结论出自哪"和结论本身一样重要，因此引用不是装饰：
  每条都显示来源文档、章节、页码与**来源性质**（公开原文 / 整理摘要 / 本人病历）。

  安全：标题与片段都来自上传的文档，属于可被影响的输入，
  一律用插值渲染，**绝不 v-html** —— 否则就是每位医生屏幕上的存储型 XSS。
-->
<template>
  <div v-if="references && references.length" :class="['citation-list', { compact }]">
    <div class="citation-header">
      <el-icon size="13"><Collection /></el-icon>
      <span>{{ label }}（{{ references.length }}）</span>
    </div>

    <div class="citation-items">
      <button
        v-for="ref in references"
        :key="ref.chunk_id ?? ref.index"
        type="button"
        class="citation-item"
        @click="open(ref)"
      >
        <span class="citation-index">[{{ ref.index }}]</span>
        <span class="citation-body">
          <span class="citation-title">《{{ ref.doc }}》</span>
          <span v-if="ref.section" class="citation-section">{{ ref.section }}</span>
          <span v-if="ref.page" class="citation-page">第{{ ref.page }}页</span>
        </span>
        <span :class="['citation-badge', originClass(ref.origin)]">
          {{ ref.origin_label || originLabel(ref.origin) }}
        </span>
      </button>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="active ? `引用 [${active.index}]` : '引用'"
      width="640px"
      append-to-body
    >
      <template v-if="active">
        <div class="ref-detail">
          <div class="ref-detail-row">
            <span class="ref-detail-label">来源</span>
            <span class="ref-detail-value">《{{ active.doc }}》</span>
          </div>
          <div v-if="active.section" class="ref-detail-row">
            <span class="ref-detail-label">章节</span>
            <span class="ref-detail-value">{{ active.section }}</span>
          </div>
          <div v-if="active.page" class="ref-detail-row">
            <span class="ref-detail-label">页码</span>
            <span class="ref-detail-value">第 {{ active.page }} 页</span>
          </div>
          <div class="ref-detail-row">
            <span class="ref-detail-label">性质</span>
            <span class="ref-detail-value">
              <span :class="['citation-badge', originClass(active.origin)]">
                {{ active.origin_label || originLabel(active.origin) }}
              </span>
            </span>
          </div>
          <div v-if="active.source" class="ref-detail-row">
            <span class="ref-detail-label">出处</span>
            <span class="ref-detail-value">
              <a v-if="isUrl(active.source)" :href="active.source" target="_blank" rel="noopener noreferrer">
                {{ active.source }}
              </a>
              <template v-else>{{ active.source }}</template>
            </span>
          </div>
          <div class="ref-detail-row">
            <span class="ref-detail-label">相关度</span>
            <span class="ref-detail-value">{{ active.score }}</span>
          </div>

          <div class="ref-snippet">{{ active.snippet || active.content }}</div>

          <p class="ref-disclaimer">
            以上内容为 AI 依据检索到的资料生成，仅供参考，最终诊断与用药请遵医嘱。
          </p>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Collection } from '@element-plus/icons-vue'

const props = defineProps({
  references: { type: Array, default: () => [] },
  label: { type: String, default: '参考资料' },
  compact: { type: Boolean, default: false }   // 聊天气泡内使用（更紧凑）
})

const dialogVisible = ref(false)
const active = ref(null)

const ORIGIN_LABELS = {
  public: '公开原文',
  curated: '整理摘要',
  patient_record: '本人病历'
}

const originLabel = (origin) => ORIGIN_LABELS[origin] || '来源'

const originClass = (origin) => {
  if (origin === 'public') return 'is-public'
  if (origin === 'patient_record') return 'is-personal'
  return 'is-curated'
}

const isUrl = (value) => typeof value === 'string' && value.startsWith('http')

const open = (ref_) => {
  active.value = ref_
  dialogVisible.value = true
}

defineExpose({ open })
</script>

<style scoped>
.citation-list {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e4e7ed;
}

.citation-header {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.citation-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.citation-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 5px 9px;
  font-size: 12px;
  text-align: left;
  color: #303133;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.citation-item:hover {
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.citation-index {
  color: #4f6ef7;
  font-weight: 600;
}

.citation-body {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.citation-title {
  font-weight: 500;
}

.citation-section,
.citation-page {
  color: #909399;
  margin-left: 5px;
}

.citation-badge {
  flex-shrink: 0;
  padding: 1px 5px;
  font-size: 11px;
  border-radius: 3px;
  white-space: nowrap;
}

.citation-badge.is-public {
  color: #0d9488;
  background: #f0fdfa;
}

.citation-badge.is-curated {
  color: #b88230;
  background: #fdf6ec;
}

.citation-badge.is-personal {
  color: #4f6ef7;
  background: #ecf5ff;
}

/* 聊天气泡内更紧凑 */
.citation-list.compact .citation-body {
  max-width: 180px;
}

/* 弹窗 */
.ref-detail {
  font-size: 13px;
  line-height: 1.7;
}

.ref-detail-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.ref-detail-label {
  flex-shrink: 0;
  width: 48px;
  color: #909399;
}

.ref-detail-value {
  flex: 1;
  color: #303133;
  word-break: break-all;
}

.ref-detail-value a {
  color: #4f6ef7;
}

.ref-snippet {
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}

.ref-disclaimer {
  margin: 12px 0 0;
  font-size: 12px;
  color: #909399;
}

html.dark .citation-item {
  background: #262727;
  border-color: #414243;
  color: #e5eaf3;
}

html.dark .citation-item:hover {
  background: #1d2b3a;
  border-color: #3a5a8c;
}

html.dark .ref-snippet {
  background: #262727;
  color: #e5eaf3;
}
</style>
