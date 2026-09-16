<!--
  知识库管理（医生 / 管理员）

  医护人员把资料丢进来就能被检索到——这是知识库的实用价值所在。
  文档只负责"进得来、看得到、删得掉"，检索预览面板则把混合检索
  （向量 / BM25 / RRF / 重排）的排序过程摊开给人看。
-->
<template>
  <div class="kb-page">
    <div class="kb-header">
      <div class="kb-title">
        <el-icon size="22"><Collection /></el-icon>
        <h2>知识库管理</h2>
        <el-tag v-if="stats" size="small" type="info">
          {{ stats.docs_ready }} 篇 / {{ stats.chunks }} 切片
        </el-tag>
      </div>
      <div class="kb-actions">
        <el-button @click="loadAll" :loading="loading">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button type="primary" @click="uploadVisible = true">
          <el-icon><Upload /></el-icon>上传文档
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="stats && !stats.embedder_ready"
      type="warning"
      :closable="false"
      title="嵌入模型未就绪，检索将降级为关键词匹配"
      description="请检查模型是否已下载（首次使用需下载 bge-m3，约 2.2GB），或查看后端日志。"
      style="margin-bottom: 16px;"
    />

    <!-- 文档列表 -->
    <el-card shadow="never" class="kb-card">
      <template #header>
        <div class="card-head">
          <span>文档列表</span>
          <div class="card-head-filters">
            <el-input
              v-model="keyword"
              placeholder="按标题搜索"
              size="small"
              style="width: 200px;"
              clearable
              @keyup.enter="loadDocs"
              @clear="loadDocs"
            />
            <el-select v-model="statusFilter" size="small" style="width: 130px;" @change="loadDocs">
              <el-option label="全部状态" value="" />
              <el-option label="就绪" value="ready" />
              <el-option label="处理中" value="processing" />
              <el-option label="失败" value="failed" />
            </el-select>
          </div>
        </div>
      </template>

      <el-table :data="docs" v-loading="loading" style="width: 100%" empty-text="暂无文档">
        <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="doc_type" label="类型" width="110" />
        <el-table-column label="来源性质" width="110">
          <template #default="{ row }">
            <el-tag :type="originTagType(row.origin)" size="small">
              {{ originLabel(row.origin) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="归属" width="100">
          <template #default="{ row }">
            <span v-if="row.is_shared">共享库</span>
            <span v-else>患者 #{{ row.patient_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="切片" width="80" align="center" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDoc(row)">切片</el-button>
            <el-button
              v-if="row.status === 'failed' && row.file_path"
              link type="warning" size="small"
              @click="reingest(row)"
            >重试</el-button>
            <el-button
              link type="danger" size="small"
              :disabled="!canDelete(row)"
              @click="removeDoc(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="docs.some(d => d.status === 'failed' && d.error_msg)"
        type="error"
        :closable="false"
        style="margin-top: 12px;"
      >
        <template #title>有文档入库失败</template>
        <div v-for="d in docs.filter(x => x.status === 'failed')" :key="d.id" class="fail-line">
          《{{ d.title }}》：{{ d.error_msg }}
        </div>
      </el-alert>
    </el-card>

    <!-- 检索预览 -->
    <el-card shadow="never" class="kb-card">
      <template #header>
        <div class="card-head">
          <span>检索预览</span>
          <span class="card-head-hint">
            展示向量 / BM25 / RRF / 重排四步的排序变化
          </span>
        </div>
      </template>

      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="输入一个临床问题，例如：股骨远端骨折的AO分型标准是什么"
          @keyup.enter="runSearch"
          clearable
        />
        <el-select v-model="searchTopK" style="width: 110px;">
          <el-option v-for="n in [3, 5, 10]" :key="n" :label="`Top ${n}`" :value="n" />
        </el-select>
        <el-button type="primary" :loading="searching" @click="runSearch">检索</el-button>
      </div>

      <div v-if="searchMeta" class="search-meta">
        用时 {{ searchMeta.took_ms }}ms ·
        重排{{ searchMeta.rerank_used ? '已启用' : '未启用（按 RRF 排序）' }} ·
        范围：{{ searchMeta.scope.include_personal ? '共享库 + 患者病历' : '仅共享库' }}
      </div>

      <div v-if="searchResults.length" class="search-results">
        <div v-for="item in searchResults" :key="item.chunk_id" class="result-item">
          <div class="result-head">
            <span class="result-score">{{ item.score }}</span>
            <span class="result-title">《{{ item.doc }}》</span>
            <span v-if="item.section" class="result-section">{{ item.section }}</span>
            <el-tag :type="originTagType(item.origin)" size="small">
              {{ item.origin_label || originLabel(item.origin) }}
            </el-tag>
          </div>
          <div class="result-ranks">
            向量 #{{ item.vec_rank ?? '-' }} ·
            BM25 #{{ item.bm25_rank ?? '-' }} ·
            RRF {{ item.rrf_score }}
          </div>
          <div class="result-content">{{ item.content }}</div>
        </div>
      </div>
      <el-empty v-else-if="searched" description="没有检索到内容" />
    </el-card>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadVisible" title="上传文档" width="560px">
      <el-form label-width="90px">
        <el-form-item label="文件" required>
          <el-upload
            ref="uploaderRef"
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-exceed="onExceed"
            accept=".pdf,.docx,.md,.markdown,.txt"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">把文件拖到这里，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                支持 PDF / DOCX / MD / TXT。扫描件（无文字层）无法入库。
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="uploadForm.title" placeholder="留空则取文档内的标题" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="uploadForm.doc_type" style="width: 100%;">
            <el-option v-for="t in docTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源性质">
          <el-radio-group v-model="uploadForm.origin">
            <el-radio value="public">公开原文</el-radio>
            <el-radio value="curated">整理摘要</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="出处">
          <el-input
            v-model="uploadForm.source"
            placeholder="文献引用或 URL —— 引用卡片会展示它"
          />
        </el-form-item>
        <el-form-item label="归属患者">
          <PatientSelector v-model="uploadForm.patient_id" />
          <div class="form-hint">不选则入共享知识库</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">
          上传并入库
        </el-button>
      </template>
    </el-dialog>

    <!-- 切片查看 -->
    <el-dialog v-model="chunksVisible" :title="`切片：${activeDoc?.title || ''}`" width="760px">
      <div v-if="chunksLoading" v-loading="true" style="height: 120px;"></div>
      <div v-else class="chunk-list">
        <div v-for="c in chunks" :key="c.id" class="chunk-item">
          <div class="chunk-head">
            <span class="chunk-index">#{{ c.chunk_index }}</span>
            <span class="chunk-section">{{ c.section || '（无章节）' }}</span>
            <span v-if="c.page" class="chunk-page">第 {{ c.page }} 页</span>
            <span class="chunk-tokens">{{ c.token_count }} token</span>
          </div>
          <div class="chunk-content">{{ c.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection, Refresh, Upload, UploadFilled
} from '@element-plus/icons-vue'
import axios from '../utils/axios'
import PatientSelector from '../components/PatientSelector.vue'

const loading = ref(false)
const docs = ref([])
const stats = ref(null)
const keyword = ref('')
const statusFilter = ref('')

const searchQuery = ref('')
const searchTopK = ref(5)
const searching = ref(false)
const searched = ref(false)
const searchResults = ref([])
const searchMeta = ref(null)

const uploadVisible = ref(false)
const uploading = ref(false)
const uploaderRef = ref(null)
const selectedFile = ref(null)
const uploadForm = ref({
  title: '', doc_type: 'guideline', origin: 'curated', source: '', patient_id: null
})

const chunksVisible = ref(false)
const chunksLoading = ref(false)
const chunks = ref([])
const activeDoc = ref(null)

let pollTimer = null

const docTypes = [
  { label: '诊疗指南', value: 'guideline' },
  { label: '骨折分型', value: 'classification' },
  { label: '康复', value: 'rehab' },
  { label: '药物', value: 'drug' },
  { label: '解剖与影像', value: 'anatomy' },
  { label: '教材', value: 'textbook' },
  { label: '其他', value: 'other' }
]

const ORIGIN_LABELS = {
  public: '公开原文',
  curated: '整理摘要',
  patient_record: '本人病历'
}

const originLabel = (origin) => ORIGIN_LABELS[origin] || '来源'
const originTagType = (origin) => {
  if (origin === 'public') return 'success'
  if (origin === 'patient_record') return 'primary'
  return 'warning'
}

const STATUS_LABELS = { ready: '就绪', processing: '处理中', pending: '待处理', failed: '失败' }
const statusLabel = (s) => STATUS_LABELS[s] || s
const statusTagType = (s) => {
  if (s === 'ready') return 'success'
  if (s === 'failed') return 'danger'
  return 'info'
}

const role = ref(localStorage.getItem('userRole') || '')
const canDelete = (row) => role.value === 'admin' || !row.is_shared

const formatTime = (value) => {
  if (!value) return '-'
  const d = new Date(value)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const loadDocs = async () => {
  loading.value = true
  try {
    const params = {}
    if (keyword.value) params.keyword = keyword.value
    if (statusFilter.value) params.status = statusFilter.value
    const res = await axios.get('/api/knowledge/docs', { params })
    if (res.data.success) {
      docs.value = res.data.data || []
      schedulePoll()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '加载文档列表失败')
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const res = await axios.get('/api/knowledge/stats')
    if (res.data.success) stats.value = res.data.data
  } catch (e) {
    // 统计是附加信息，失败不打扰用户
    console.warn('加载统计失败', e)
  }
}

const loadAll = () => {
  loadDocs()
  loadStats()
}

// 有文档在入库中时轮询刷新状态
const schedulePoll = () => {
  const pending = docs.value.some(d => d.status === 'pending' || d.status === 'processing')
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  if (pending) {
    pollTimer = setTimeout(loadDocs, 3000)
  }
}

const runSearch = async () => {
  const query = searchQuery.value.trim()
  if (!query) {
    ElMessage.warning('请输入查询内容')
    return
  }
  searching.value = true
  searched.value = true
  try {
    const res = await axios.post('/api/knowledge/search', {
      query, top_k: searchTopK.value
    }, { timeout: 120000 })
    if (res.data.success) {
      searchResults.value = res.data.results || []
      searchMeta.value = res.data
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '检索失败')
  } finally {
    searching.value = false
  }
}

const viewDoc = async (row) => {
  activeDoc.value = row
  chunksVisible.value = true
  chunksLoading.value = true
  chunks.value = []
  try {
    const res = await axios.get(`/api/knowledge/docs/${row.id}/chunks`)
    if (res.data.success) chunks.value = res.data.data || []
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '加载切片失败')
  } finally {
    chunksLoading.value = false
  }
}

const reingest = async (row) => {
  try {
    const res = await axios.post(`/api/knowledge/docs/${row.id}/reingest`)
    if (res.data.success) {
      ElMessage.success(`重新入库完成，${res.data.chunks} 个切片`)
      loadAll()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '重新入库失败')
  }
}

const removeDoc = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定删除《${row.title}》及其 ${row.chunk_count} 个切片？`,
      '删除确认', { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res = await axios.delete(`/api/knowledge/docs/${row.id}`)
    if (res.data.success) {
      ElMessage.success('已删除')
      loadAll()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '删除失败')
  }
}

const onFileChange = (file) => {
  selectedFile.value = file.raw
}

const onExceed = () => {
  ElMessage.warning('一次只能上传一个文件')
}

const submitUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    // 空值不要发，避免后端把空字符串当成有效值覆盖默认
    Object.entries(uploadForm.value).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) {
        form.append(key, value)
      }
    })
    const res = await axios.post('/api/knowledge/docs', form, {
      timeout: 300000        // 入库是同步的，长文档需要时间
    })
    if (res.data.success) {
      ElMessage.success(`入库完成，${res.data.chunks} 个切片`)
      if (res.data.warning) ElMessage.warning(res.data.warning)
      uploadVisible.value = false
      selectedFile.value = null
      uploadForm.value = { title: '', doc_type: 'guideline', origin: 'curated', source: '', patient_id: null }
      uploaderRef.value?.clearFiles()
      loadAll()
    }
  } catch (e) {
    // 扫描件等用户可纠正的问题，后端返回 422 与明确文案，原样展示
    ElMessage.error(e.response?.data?.error || '上传失败')
    loadDocs()
  } finally {
    uploading.value = false
  }
}

onMounted(loadAll)

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<style scoped>
.kb-page {
  padding: 20px;
}

.kb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.kb-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kb-title h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary, #303133);
}

.kb-card {
  margin-bottom: 20px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-head-filters {
  display: flex;
  gap: 8px;
}

.card-head-hint {
  font-size: 12px;
  color: #909399;
}

.fail-line {
  font-size: 12px;
  margin-top: 4px;
}

.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.search-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 12px;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.result-score {
  font-weight: 600;
  color: #4f6ef7;
}

.result-title {
  font-weight: 500;
}

.result-section {
  color: #909399;
  font-size: 12px;
}

.result-ranks {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.result-content {
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow-y: auto;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 10px;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
}

.chunk-item {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.chunk-head {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.chunk-index {
  color: #4f6ef7;
  font-weight: 600;
}

.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

html.dark .result-item,
html.dark .chunk-item {
  background: #262727;
}

html.dark .result-content,
html.dark .chunk-content {
  color: #e5eaf3;
}
</style>
