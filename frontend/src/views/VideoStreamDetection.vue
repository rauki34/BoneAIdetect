<template>
  <div class="video-stream-container">
    <!-- 返回按钮 - 仅医生端显示 -->
    <div v-if="userRole === 'doctor'" class="back-button" style="margin-bottom: 16px;">
      <el-button @click="router.push('/doctor-workstation')">
        <el-icon><ArrowLeft /></el-icon>
        返回工作台
      </el-button>
    </div>
    
    <el-card class="upload-card">
      <div class="uploader-row">
        <el-select v-model="model" placeholder="选择模型" style="width:200px" :disabled="allModels.length === 0">
          <el-option-group label="可用模型" v-if="allModels.length > 0">
            <el-option
              v-for="m in allModels"
              :key="m.key"
              :label="m.name"
              :value="m.key"
            />
          </el-option-group>
          <template #empty>
            <div style="padding: 10px; text-align: center; color: #999;">
              暂无可用模型<br>
              <span style="font-size: 12px;">请联系管理员发布模型</span>
            </div>
          </template>
        </el-select>

        <div class="btn-group">
          <el-upload
            ref="uploader"
            action=""
            :auto-upload="false"
            :show-file-list="false"
            accept="video/*"
            :on-change="onFileChange"
            class="upload-demo"
          >
            <el-button type="primary" class="btn">选择视频</el-button>
          </el-upload>

          <el-button
            type="success"
            class="btn"
            :disabled="!file || processing"
            :loading="processing"
            @click="startDetection"
          >
            {{ processing ? '检测中...' : '开始检测' }}
          </el-button>

          <el-button
            type="danger"
            class="btn"
            :disabled="!processing"
            @click="stopDetection"
          >
            停止检测
          </el-button>
        </div>
      </div>

      <div v-if="file" class="file-info">
        <el-tag type="info">{{ file.name }}</el-tag>
        <el-tag type="success" v-if="duration">时长: {{ formatDuration(duration) }}</el-tag>
      </div>
    </el-card>

    <!-- 视频显示区域 -->
    <el-row :gutter="20" class="video-row" v-if="resultImage || processing">
      <el-col :span="12">
        <el-card class="video-card">
          <template #header>
            <div class="card-header">
              <span>原始视频</span>
            </div>
          </template>
          <video
            ref="originalVideo"
            class="video-player"
            controls
            :src="originalVideoUrl"
            @loadedmetadata="onVideoLoaded"
          ></video>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="video-card">
          <template #header>
            <div class="card-header">
              <span>检测结果</span>
              <el-tag v-if="currentFrame" type="success">帧: {{ currentFrame }}</el-tag>
            </div>
          </template>
          <div class="result-container">
            <img
              v-if="resultImage"
              :src="resultImage"
              class="result-image"
              alt="检测结果"
            />
            <div v-else-if="processing" class="processing-status">
              <el-icon class="loading-icon"><Loading /></el-icon>
              <p>正在检测中...</p>
            </div>
            <el-empty v-else description="等待检测"></el-empty>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 检测结果统计 -->
    <el-card class="stats-card" v-if="detectionStats.total_frames > 0">
      <template #header>
        <div class="card-header">
          <span>检测统计</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ detectionStats.total_frames }}</div>
            <div class="stat-label">总帧数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ detectionStats.detected_frames }}</div>
            <div class="stat-label">检测到目标帧</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ detectionStats.total_detections }}</div>
            <div class="stat-label">总检测数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ detectionStats.avg_confidence }}%</div>
            <div class="stat-label">平均置信度</div>
          </div>
        </el-col>
      </el-row>

      <!-- 检测详情表格 -->
      <el-table :data="frameResults" style="margin-top: 20px" max-height="300" v-if="frameResults.length > 0">
        <el-table-column prop="frame" label="帧号" width="80" />
        <el-table-column prop="timestamp" label="时间戳" width="100">
          <template #default="{ row }">
            {{ formatDuration(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="count" label="检测数" width="80" />
        <el-table-column label="置信度" min-width="150">
          <template #default="{ row }">
            <el-progress
              v-if="row.avg_confidence > 0"
              :percentage="Math.round(row.avg_confidence * 100)"
              :color="getConfidenceColor(row.avg_confidence)"
              :stroke-width="8"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="检测类型" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="cls in row.classes" :key="cls" size="small" style="margin-right: 4px;">
              {{ cls }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from '../utils/axios'
import { ElMessage } from 'element-plus'
import { Loading, ArrowLeft } from '@element-plus/icons-vue'

const router = useRouter()

/* 响应式变量 */
const userRole = ref(localStorage.getItem('userRole') || '')
const file = ref(null)
const model = ref('')
const allModels = ref([])
const processing = ref(false)
const originalVideoUrl = ref('')
const resultImage = ref('')
const currentFrame = ref(0)
const duration = ref(0)
const originalVideo = ref(null)

/* 检测统计 */
const detectionStats = ref({
  total_frames: 0,
  detected_frames: 0,
  total_detections: 0,
  avg_confidence: 0
})
const frameResults = ref([])

/* WebSocket 连接 */
let ws = null
let wsReconnectTimer = null

/* 加载可用模型 */
onMounted(async () => {
  try {
    const res = await axios.get('/api/settings')
    const modelsData = res.data.available_models || []

    // 只使用已发布的自定义模型（管理员发布的）
    allModels.value = modelsData

    // 设置默认模型
    const defaultModel = res.data.default_model
    if (defaultModel && allModels.value.find(m => m.key === defaultModel)) {
      model.value = defaultModel
    } else if (allModels.value.length > 0) {
      model.value = allModels.value[0].key
    }
  } catch {
    allModels.value = []
    model.value = ''
  }
})

onUnmounted(() => {
  stopDetection()
  if (ws) {
    ws.close()
  }
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
  }
})

/* 文件选择回调 */
function onFileChange(uploadFile) {
  const rawFile = uploadFile.raw
  if (!rawFile) return

  // 检查文件类型
  if (!rawFile.type.startsWith('video/')) {
    ElMessage.error('请选择视频文件')
    return
  }

  file.value = rawFile
  originalVideoUrl.value = URL.createObjectURL(rawFile)
  resultImage.value = ''
  frameResults.value = []
  detectionStats.value = {
    total_frames: 0,
    detected_frames: 0,
    total_detections: 0,
    avg_confidence: 0
  }
}

/* 视频加载完成 */
function onVideoLoaded() {
  if (originalVideo.value) {
    duration.value = originalVideo.value.duration
  }
}

/* 开始检测 */
async function startDetection() {
  if (!file.value) {
    ElMessage.warning('请先选择视频文件')
    return
  }

  processing.value = true
  frameResults.value = []

  try {
    // 创建 FormData
    const formData = new FormData()
    formData.append('video', file.value)
    formData.append('model', model.value)

    // 发送视频文件到后端
    const res = await axios.post('/api/video/detect', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.data.success) {
      const taskId = res.data.task_id
      // 建立 WebSocket 连接接收实时结果
      connectWebSocket(taskId)
    } else {
      ElMessage.error(res.data.error || '检测失败')
      processing.value = false
    }
  } catch (err) {
    console.error('检测失败:', err)
    ElMessage.error('检测失败: ' + (err.response?.data?.error || err.message))
    processing.value = false
  }
}

/* 建立 WebSocket 连接 */
function connectWebSocket(taskId) {
  // 开发环境走 .env.development 配置；生产环境留空则按当前页面协议/主机推导
  const wsBase = import.meta.env.VITE_WS_BASE
    || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`
  const wsUrl = `${wsBase}/ws/video/${taskId}`
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    console.log('WebSocket 连接成功')
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleWebSocketMessage(data)
  }

  ws.onerror = (error) => {
    console.error('WebSocket 错误:', error)
    ElMessage.error('实时连接错误')
  }

  ws.onclose = () => {
    console.log('WebSocket 连接关闭')
    processing.value = false
  }
}

/* 处理 WebSocket 消息 */
function handleWebSocketMessage(data) {
  if (data.type === 'frame') {
    // 更新当前帧图像
    resultImage.value = `data:image/jpeg;base64,${data.image}`
    currentFrame.value = data.frame

    // 添加到帧结果列表
    if (data.detections && data.detections.length > 0) {
      frameResults.value.unshift({
        frame: data.frame,
        timestamp: data.timestamp,
        count: data.detections.length,
        avg_confidence: data.avg_confidence,
        classes: [...new Set(data.detections.map(d => d.class))]
      })

      // 限制列表长度
      if (frameResults.value.length > 50) {
        frameResults.value = frameResults.value.slice(0, 50)
      }
    }
  } else if (data.type === 'stats') {
    // 更新统计信息
    detectionStats.value = data.stats
  } else if (data.type === 'complete') {
    ElMessage.success('视频检测完成')
    processing.value = false
    if (ws) {
      ws.close()
      ws = null
    }
  } else if (data.type === 'error') {
    ElMessage.error(data.message)
    processing.value = false
    if (ws) {
      ws.close()
      ws = null
    }
  }
}

/* 停止检测 */
function stopDetection() {
  if (ws) {
    ws.close()
    ws = null
  }
  processing.value = false
  ElMessage.info('已停止检测')
}

/* 格式化时长 */
function formatDuration(seconds) {
  if (!seconds) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

/* 根据置信度获取颜色 */
function getConfidenceColor(confidence) {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}
</script>

<style scoped>
.video-stream-container {
  padding: 16px;
}

.upload-card {
  margin-bottom: 20px;
}

.uploader-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-group {
  display: flex;
  gap: 8px;
}

.btn {
  width: 100px;
}

.file-info {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.video-row {
  margin-bottom: 20px;
}

.video-card {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.video-player {
  width: 100%;
  height: 360px;
  background-color: #000;
}

.result-container {
  width: 100%;
  height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
  overflow: hidden;
}

.result-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.processing-status {
  text-align: center;
  color: #909399;
}

.loading-icon {
  font-size: 48px;
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.stats-card {
  margin-top: 20px;
}

.stat-item {
  text-align: center;
  padding: 16px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #4f6ef7;
}

.stat-label {
  margin-top: 8px;
  color: #606266;
  font-size: 14px;
}
</style>
