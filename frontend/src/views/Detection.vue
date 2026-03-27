<template>
  <el-card class="upload-card">
    <div class="uploader-row">
      <!-- 左侧：模型选择 -->
      <el-select v-model="model" placeholder="选择模型" style="width:200px">
        <el-option-group label="系统模型">
          <el-option
            v-for="m in systemModels"
            :key="m.key"
            :label="m.name"
            :value="m.key"
          />
        </el-option-group>
        <el-option-group label="自定义模型" v-if="customModels.length > 0">
          <el-option
            v-for="m in customModels"
            :key="m.key"
            :label="m.name"
            :value="m.key"
          />
        </el-option-group>
      </el-select>

      <!-- 右侧：按钮组（水平排列） -->
      <div class="btn-group">
        <!-- 选择文件：el-upload 只负责选图，不渲染卡片 -->
        <el-upload
          ref="uploader"
          action=""
          :auto-upload="false"
          accept="image/*"
          :show-file-list="false"
          :on-change="handleChange"
          :before-upload="beforeUpload"
        >
          <el-button type="primary" class="btn">选择文件</el-button>
        </el-upload>

        <!-- 上传并预测 -->
        <el-button
          :disabled="!file"
          type="success"
          class="btn"
          @click="uploadFile"
        >
          上传并预测
        </el-button>
      </div>
    </div>

    <!-- 缩略图（无框） -->
    <div v-if="file" class="thumb-area">
      <img :src="thumbUrl" class="thumb-img" alt="preview" />
    </div>

    <el-divider v-if="result" />

    <!-- 预测结果 -->
    <div v-if="result" class="result-area">
      <!-- 图片双列展示 -->
      <h3 style="margin-bottom: 20px; font-size: 18px;">检测结果对比</h3>
      <el-row :gutter="24" class="image-comparison">
        <el-col :xs="24" :sm="24" :md="12">
          <div class="image-card">
            <div class="image-title">原始图片</div>
            <div class="image-wrapper">
              <el-image
                :src="originalImageUrl"
                fit="contain"
                :preview-src-list="[originalImageUrl, result.result_image]"
              />
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="24" :md="12">
          <div class="image-card">
            <div class="image-title">检测结果</div>
            <div class="image-wrapper">
              <el-image
                :src="result.result_image"
                fit="contain"
                :preview-src-list="[result.result_image, originalImageUrl]"
              />
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 检测详情表格 -->
      <el-row :gutter="20" style="margin-top: 28px;">
        <el-col :span="24">
          <h3 style="font-size: 18px; margin-bottom: 16px;">检测详情</h3>
          <el-table :data="result.predictions" style="width:100%" border size="large">
            <el-table-column prop="class" label="类别" min-width="150" />
            <el-table-column label="置信度" width="200" align="center">
              <template #default="{ row }">
                <div class="confidence-display">
                  <el-progress
                    :percentage="Math.round(row.confidence * 100)"
                    :color="getConfidenceColor(row.confidence)"
                    :stroke-width="18"
                    :show-text="true"
                    class="confidence-progress"
                  />
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="bbox" label="检测框坐标" min-width="300" />
          </el-table>
        </el-col>
      </el-row>

      <!-- 获取医疗建议按钮 -->
      <div class="action-buttons">
        <el-button
          type="primary"
          size="large"
          @click="openInterpretDialog"
        >
          获取医疗建议
        </el-button>
      </div>
    </div>

    <!-- 医疗建议对话框 -->
    <el-dialog
      v-model="interpretDialogVisible"
      title="AI 医疗分析建议"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px">
        <el-form-item label="患者信息">
          <el-row :gutter="10">
            <el-col :span="8">
              <el-input v-model="patientInfo.age" placeholder="年龄" />
            </el-col>
            <el-col :span="8">
              <el-select v-model="patientInfo.gender" placeholder="性别" style="width:100%">
                <el-option label="男" value="男" />
                <el-option label="女" value="女" />
                <el-option label="未指定" value="未指定" />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-input v-model="patientInfo.symptoms" placeholder="症状描述" />
            </el-col>
          </el-row>
        </el-form-item>

        <el-form-item label="分析提示">
          <el-input
            v-model="customPrompt"
            type="textarea"
            :rows="8"
            placeholder="输入您想要咨询的问题..."
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="interpretDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="interpretLoading"
          @click="submitInterpret"
        >
          开始分析
        </el-button>
      </template>
    </el-dialog>

    <!-- 分析结果对话框 -->
    <el-dialog
      v-model="resultDialogVisible"
      title="医疗分析结果"
      width="900px"
      class="interpret-result-dialog"
    >
      <div v-if="interpretResult" class="interpret-result">
        <el-alert
          title="AI 辅助诊断建议"
          type="info"
          :closable="false"
          style="margin-bottom: 16px;"
        >
          此为AI辅助诊断结果仅供参考，具体诊断请咨询专业医生
        </el-alert>
        <div class="markdown-body">
          <vue-markdown :source="interpretResult" />
        </div>
      </div>
      <template #footer>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyResult">复制结果</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import axios from '../utils/axios'
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import VueMarkdown from 'vue-markdown-render'
import 'github-markdown-css/github-markdown-light.css'

/* 响应式变量 */
const file     = ref(null)      // 当前选中的原始 File
const fileList = ref([])        // el-upload 内部 fileList（保留兼容）
const result   = ref(null)      // 预测结果
const uploader = ref(null)      // el-upload 实例
const model    = ref('')        // 当前选中模型
const allModels = ref([])       // 所有模型
const systemModels = ref([])    // 系统模型
const customModels = ref([])    // 自定义模型
const originalImageUrl = ref('') // 原始图片 URL（用于展示）
const currentHistoryId = ref(null) // 当前检测历史记录ID

/* 医疗建议对话框相关 */
const interpretDialogVisible = ref(false)
const resultDialogVisible = ref(false)
const interpretLoading = ref(false)
const interpretResult = ref('')
const patientInfo = ref({
  age: '',
  gender: '',
  symptoms: ''
})
const customPrompt = ref('')

/* 缩略图地址 */
const thumbUrl = computed(() =>
  file.value ? URL.createObjectURL(file.value) : ''
)

/* 选文件回调 */
function handleChange(uploadFile) {
  file.value = uploadFile.raw
  fileList.value = [uploadFile]
  // 保存原始图片URL用于对比展示
  originalImageUrl.value = URL.createObjectURL(uploadFile.raw)
}

/* 拦截 el-upload 默认上传 */
function beforeUpload() {
  return false
}

/* 真正上传并预测 */
async function uploadFile() {
  if (!file.value) return
  const fd = new FormData()
  fd.append('file', file.value)
  if (model.value) fd.append('model', model.value)
  try {
    const res = await axios.post('/api/predict', fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    result.value = res.data
    currentHistoryId.value = res.data.history_id  // 保存历史记录ID
    // 不清除file，保留原始图片用于对比展示
    fileList.value = []
    window.dispatchEvent(new CustomEvent('predictionComplete'))
  } catch (err) {
    console.error('预测失败:', err)
    const errorMsg = err.response?.data?.error || err.response?.data?.message || err.message || '未知错误'
    alert('上传或预测失败: ' + errorMsg)
  }
}

/* 打开医疗建议对话框 */
function openInterpretDialog() {
  if (!result.value || !result.value.predictions || result.value.predictions.length === 0) {
    ElMessage.warning('请先完成骨折检测')
    return
  }
  const predictions = result.value.predictions
  const detectionSummary = predictions.map((p, i) => {
    return `检测${i + 1}: 类别=${p.class}, 置信度=${(p.confidence * 100).toFixed(1)}%, 位置=${p.bbox}`
  }).join('\n')

  customPrompt.value = `你是一位专业的骨科医生助手。我将提供骨折检测的X光片图像和检测结果，请结合图像和检测信息进行专业分析。

检测结果：
${detectionSummary}

请结合X光片图像和检测结果，提供以下信息：
1. 图像分析：观察X光片中的骨折位置、类型和严重程度
2. 风险评估：根据检测到的骨折类型和图像表现，评估病情的严重程度
3. 进一步检查建议：建议进行哪些进一步检查（如CT、MRI等）
4. 处置建议：初步的处置建议（如固定、手术、转诊等）
5. 注意事项：患者应该注意的事项
6. 免责声明：提示此为AI辅助诊断，最终诊断需由专业医生确定

请用中文回复，结构化输出。`

  patientInfo.value = {
    age: '',
    gender: '',
    symptoms: ''
  }
  interpretDialogVisible.value = true
}

/* 将文件转换为base64 */
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.readAsDataURL(file)
    reader.onload = () => resolve(reader.result.split(',')[1]) // 去掉data:image前缀
    reader.onerror = error => reject(error)
  })
}

/* 提交医疗分析请求 */
async function submitInterpret() {
  if (!customPrompt.value.trim()) {
    ElMessage.warning('请输入分析提示')
    return
  }

  interpretLoading.value = true

  let promptWithPatient = customPrompt.value
  if (patientInfo.value.age || patientInfo.value.gender || patientInfo.value.symptoms) {
    const patientText = `\n患者信息：年龄=${patientInfo.value.age || '未提供'}, 性别=${patientInfo.value.gender || '未提供'}, 症状=${patientInfo.value.symptoms || '未提供'}`
    promptWithPatient = customPrompt.value + patientText
  }

  try {
    // 准备请求数据
    const requestData = {
      detections: result.value.predictions,
      prompt: promptWithPatient
    }

    // 如果有原始图片文件，转换为base64传递
    if (file.value) {
      try {
        const imageBase64 = await fileToBase64(file.value)
        requestData.image_base64 = imageBase64
      } catch (imgErr) {
        console.warn('图片转换失败，继续发送文本:', imgErr)
      }
    }

    const res = await axios.post('/api/interpret', requestData, {
      timeout: 180000
    })

    if (res.data.success) {
      interpretResult.value = res.data.interpretation
      resultDialogVisible.value = true
      interpretDialogVisible.value = false
      
      // 保存医疗建议到历史记录
      if (currentHistoryId.value) {
        try {
          await axios.post(`/api/history/${currentHistoryId.value}/advice`, {
            interpretation: res.data.interpretation,
            patient_info: patientInfo.value,
            prompt: customPrompt.value
          })
          ElMessage.success('医疗建议已保存到历史记录')
        } catch (saveErr) {
          console.error('保存医疗建议失败:', saveErr)
        }
      }
    } else {
      ElMessage.error(res.data.error || '分析失败')
    }
  } catch (err) {
    console.error('医疗建议请求失败:', err)
    const errorMsg = err.response?.data?.error || err.response?.data?.hint || err.message
    ElMessage.error('获取医疗建议失败: ' + errorMsg)
  } finally {
    interpretLoading.value = false
  }
}

/* 复制结果到剪贴板 */
function copyResult() {
  navigator.clipboard.writeText(interpretResult.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

/* 初始化模型列表 */
/* 根据置信度获取标签类型 */
function getConfidenceTag(confidence) {
  if (confidence >= 0.8) return 'success'
  if (confidence >= 0.6) return 'warning'
  return 'danger'
}

/* 根据置信度获取进度条颜色 */
function getConfidenceColor(confidence) {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

onMounted(async () => {
  try {
    const res = await axios.get('/api/settings')
    const modelsData = res.data.available_models || []
    
    // 分离系统模型和自定义模型
    systemModels.value = modelsData.filter(m => m.type === 'system')
    customModels.value = modelsData.filter(m => m.type === 'custom')
    allModels.value = modelsData
    
    // 设置默认模型
    const defaultModel = res.data.default_model
    if (defaultModel && allModels.value.find(m => m.key === defaultModel)) {
      model.value = defaultModel
    } else if (systemModels.value.length > 0) {
      model.value = systemModels.value[0].key
    }
  } catch (err) {
    console.error('加载模型列表失败:', err)
    // 使用默认数据
    systemModels.value = [
      { key: 'yolov8', name: 'YOLOv8' },
      { key: 'yolo12', name: 'YOLOv12' }
    ]
    model.value = 'yolov8'
  }
})
</script>

<style scoped>
.upload-card  { padding: 16px; }
.uploader-row { display: flex; justify-content: space-between; align-items: center; }
.btn-group    { display: flex; gap: 8px; }
.btn          { width: 100px; }

/* 缩略图区域 */
.thumb-area   { margin-top: 12px; }
.thumb-img    { max-height: 120px; max-width: 100%; border: 1px solid #dcdfe6; border-radius: 4px; }

.result-area  { margin-top: 16px; text-align: left; }

.action-buttons {
  margin-top: 20px;
  text-align: center;
}

.interpret-result {
  max-height: 500px;
  overflow-y: auto;
}

.result-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Microsoft YaHei', sans-serif;
  line-height: 1.6;
  color: #303133;
  background-color: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
}

/* 图片对比区域样式 */
.image-comparison {
  margin-bottom: 20px;
}

.image-card {
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  overflow: hidden;
  background-color: #fafafa;
  transition: box-shadow 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.image-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.image-title {
  padding: 16px 20px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 600;
  font-size: 16px;
  color: #303133;
  text-align: center;
}

.image-wrapper {
  flex: 1;
  padding: 20px;
  background-color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 500px;
}

.image-wrapper :deep(.el-image) {
  width: 100%;
  height: 100%;
  max-height: 550px;
}

.image-wrapper :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 550px;
  object-fit: contain;
}

/* 置信度显示样式 */
.confidence-display {
  width: 100%;
  padding: 8px 0;
}

.confidence-progress {
  width: 100%;
}

.confidence-progress :deep(.el-progress__text) {
  font-size: 14px;
  font-weight: 600;
  min-width: 45px;
}

/* 暗色模式下的图片对比 */
html.dark .image-card {
  border-color: #334155;
  background-color: #1e293b;
}

html.dark .image-title {
  background-color: #0f172a;
  border-bottom-color: #334155;
  color: #e2e8f0;
}

html.dark .image-wrapper {
  background-color: #1e293b;
}

/* ==================== 暗色模式适配 ==================== */

/* 暗色模式下的结果内容 */
html.dark .result-content {
  color: #e2e8f0;
  background-color: #0f172a;
}

/* 暗色模式下的缩略图边框 */
html.dark .thumb-img {
  border-color: #334155;
}

/* 暗色模式下的 h3 标题 */
html.dark h3 {
  color: #f1f5f9;
}

/* 暗色模式下的 Alert */
html.dark .el-alert--info.is-light {
  background-color: rgba(96, 165, 250, 0.1);
  border-color: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}

html.dark .el-alert__title {
  color: #60a5fa;
}

html.dark .el-alert__description {
  color: #94a3b8;
}

/* ==================== Markdown 渲染样式 ==================== */

/* Markdown 内容区域 */
.markdown-body {
  padding: 16px;
  background-color: #ffffff;
  border-radius: 8px;
  border: 1px solid #e1e4e8;
  max-height: 600px;
  overflow-y: auto;
}

/* 暗色模式下的 Markdown */
html.dark .markdown-body {
  background-color: #0d1117;
  border-color: #30363d;
  color: #c9d1d9;
}

/* 调整对话框内的 Markdown 样式 */
.interpret-result-dialog :deep(.el-dialog__body) {
  padding: 20px;
}

/* Markdown 标题样式优化 */
.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body h1 {
  font-size: 1.5em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-body h2 {
  font-size: 1.25em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-body h3 {
  font-size: 1.125em;
}

/* 暗色模式下的标题 */
html.dark .markdown-body h1,
html.dark .markdown-body h2 {
  border-bottom-color: #30363d;
}

/* 列表样式优化 */
.markdown-body ul,
.markdown-body ol {
  padding-left: 2em;
  margin-bottom: 16px;
}

.markdown-body li {
  margin-bottom: 0.25em;
}

/* 强调文字 */
.markdown-body strong {
  font-weight: 600;
  color: #d73a49;
}

html.dark .markdown-body strong {
  color: #f85149;
}

/* 引用块样式 */
.markdown-body blockquote {
  padding: 0 1em;
  color: #6a737d;
  border-left: 0.25em solid #dfe2e5;
  margin: 0 0 16px 0;
}

html.dark .markdown-body blockquote {
  color: #8b949e;
  border-left-color: #30363d;
}

/* 代码块样式 */
.markdown-body code {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  background-color: rgba(27, 31, 35, 0.05);
  border-radius: 3px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.markdown-body pre {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: #f6f8fa;
  border-radius: 6px;
  margin-bottom: 16px;
}

.markdown-body pre code {
  background-color: transparent;
  padding: 0;
}

html.dark .markdown-body code {
  background-color: rgba(110, 118, 129, 0.4);
}

html.dark .markdown-body pre {
  background-color: #161b22;
}

/* 表格样式 */
.markdown-body table {
  border-spacing: 0;
  border-collapse: collapse;
  margin-bottom: 16px;
  width: 100%;
  overflow: auto;
  display: block;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid #dfe2e5;
}

.markdown-body table th {
  font-weight: 600;
  background-color: #f6f8fa;
}

.markdown-body table tr:nth-child(2n) {
  background-color: #f6f8fa;
}

html.dark .markdown-body table th,
html.dark .markdown-body table td {
  border-color: #30363d;
}

html.dark .markdown-body table th,
html.dark .markdown-body table tr:nth-child(2n) {
  background-color: #161b22;
}

/* 水平线 */
.markdown-body hr {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: #e1e4e8;
  border: 0;
}

html.dark .markdown-body hr {
  background-color: #30363d;
}

/* 链接样式 */
.markdown-body a {
  color: #0366d6;
  text-decoration: none;
}

.markdown-body a:hover {
  text-decoration: underline;
}

html.dark .markdown-body a {
  color: #58a6ff;
}
</style>