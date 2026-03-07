<template>
  <div class="camera-detection-container">
    <el-card class="control-card">
      <div class="control-row">
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

        <el-select v-model="selectedCamera" placeholder="选择摄像头" style="width:180px; margin-left: 12px;">
          <el-option
            v-for="camera in cameras"
            :key="camera.deviceId"
            :label="camera.label || `摄像头 ${camera.deviceId.slice(0, 8)}...`"
            :value="camera.deviceId"
          />
        </el-select>

        <el-button @click="getCameras" :loading="isLoadingCameras" style="margin-left: 8px;">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>

        <div class="btn-group">
          <el-button
            type="success"
            class="btn"
            :disabled="!selectedCamera || isStreaming"
            @click="startCamera"
          >
            <el-icon><VideoCamera /></el-icon>
            开启摄像头
          </el-button>

          <el-button
            type="primary"
            class="btn"
            :disabled="!isStreaming || isDetecting"
            :loading="isDetecting"
            @click="startDetection"
          >
            {{ isDetecting ? '检测中...' : '开始检测' }}
          </el-button>

          <el-button
            type="danger"
            class="btn"
            :disabled="!isStreaming"
            @click="stopCamera"
          >
            <el-icon><VideoCameraFilled /></el-icon>
            关闭摄像头
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="!hasCameraPermission"
        title="请允许摄像头权限以使用实时检测功能"
        type="warning"
        show-icon
        :closable="false"
        style="margin-top: 12px;"
      />
    </el-card>

    <!-- 视频显示区域 -->
    <el-row :gutter="20" class="video-row" v-show="showVideoArea">
      <el-col :span="12">
        <el-card class="video-card">
          <template #header>
            <div class="card-header">
              <span>摄像头画面</span>
              <el-tag v-if="isStreaming" type="success">直播中</el-tag>
            </div>
          </template>
          <div class="video-container">
            <video
              ref="videoElement"
              class="video-player"
              autoplay
              playsinline
              muted
            ></video>
            <canvas ref="captureCanvas" style="display: none;"></canvas>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="video-card">
          <template #header>
            <div class="card-header">
              <span>实时检测结果</span>
              <el-tag v-if="isDetecting" type="success">检测中</el-tag>
            </div>
          </template>
          <div class="result-container">
            <img
              v-if="resultImage"
              :src="resultImage"
              class="result-image"
              alt="检测结果"
            />
            <div v-else-if="isDetecting" class="processing-status">
              <el-icon class="loading-icon"><Loading /></el-icon>
              <p>等待检测结果...</p>
            </div>
            <el-empty v-else description="等待检测"></el-empty>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 实时检测结果 -->
    <el-card class="results-card" v-if="isDetecting || detectionHistory.length > 0">
      <template #header>
        <div class="card-header">
          <span>实时检测结果</span>
          <el-button type="primary" size="small" text @click="clearHistory">
            清空记录
          </el-button>
        </div>
      </template>

      <!-- 当前检测结果 -->
      <div v-if="currentDetections.length > 0" class="current-detections">
        <h4>当前帧检测到 {{ currentDetections.length }} 个目标</h4>
        <el-row :gutter="10">
          <el-col :span="6" v-for="(det, index) in currentDetections" :key="index">
            <el-card class="detection-item" shadow="hover">
              <div class="detection-class">{{ det.class }}</div>
              <el-progress
                :percentage="Math.round(det.confidence * 100)"
                :color="getConfidenceColor(det.confidence)"
                :stroke-width="10"
              />
            </el-card>
          </el-col>
        </el-row>
      </div>

      <!-- 检测历史 -->
      <el-timeline style="margin-top: 20px;" v-if="detectionHistory.length > 0">
        <el-timeline-item
          v-for="(record, index) in detectionHistory.slice(0, 10)"
          :key="index"
          :timestamp="record.time"
          :type="record.detections.length > 0 ? 'success' : 'info'"
        >
          <p>检测到 {{ record.detections.length }} 个目标</p>
          <el-tag
            v-for="cls in [...new Set(record.detections.map(d => d.class))]"
            :key="cls"
            size="small"
            style="margin-right: 4px; margin-top: 4px;"
          >
            {{ cls }}
          </el-tag>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 检测统计 -->
    <el-card class="stats-card" v-if="detectionHistory.length > 0">
      <template #header>
        <div class="card-header">
          <span>检测统计</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ stats.totalFrames }}</div>
            <div class="stat-label">总检测帧</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ stats.detectedFrames }}</div>
            <div class="stat-label">有目标帧</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ stats.totalDetections }}</div>
            <div class="stat-label">总检测数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-value">{{ stats.avgConfidence }}%</div>
            <div class="stat-label">平均置信度</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import axios from '../utils/axios'
import { ElMessage } from 'element-plus'
import { VideoCamera, VideoCameraFilled, Loading, Refresh } from '@element-plus/icons-vue'

/* 响应式变量 */
const model = ref('')
const systemModels = ref([])
const customModels = ref([])
const allModels = ref([])
const cameras = ref([])
const selectedCamera = ref('')
const isStreaming = ref(false)
const isDetecting = ref(false)
const isLoadingCameras = ref(false)
const hasCameraPermission = ref(true)
const resultImage = ref('')
const currentDetections = ref([])
const detectionHistory = ref([])
const showVideoArea = ref(false)

/* DOM 引用 */
const videoElement = ref(null)
const captureCanvas = ref(null)

/* 检测间隔 */
let detectionInterval = null
let frameCount = 0

/* 计算统计 */
const stats = computed(() => {
  const totalFrames = detectionHistory.value.length
  const detectedFrames = detectionHistory.value.filter(h => h.detections.length > 0).length
  const totalDetections = detectionHistory.value.reduce((sum, h) => sum + h.detections.length, 0)
  const avgConfidence = totalFrames > 0
    ? Math.round(detectionHistory.value.reduce((sum, h) => {
        return sum + h.detections.reduce((dSum, d) => dSum + d.confidence, 0) / (h.detections.length || 1)
      }, 0) / totalFrames * 100)
    : 0

  return {
    totalFrames,
    detectedFrames,
    totalDetections,
    avgConfidence
  }
})

/* 加载可用模型和摄像头 */
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
  } catch {
    systemModels.value = [
      { key: 'yolov8', name: 'YOLOv8' },
      { key: 'yolo12', name: 'YOLOv12' }
    ]
    model.value = 'yolov8'
  }

  // 获取摄像头列表
  await getCameras()
})

onUnmounted(() => {
  stopCamera()
})

/* 获取摄像头列表 */
async function getCameras() {
  isLoadingCameras.value = true
  try {
    // 先请求摄像头权限，否则 enumerateDevices 返回的设备名称为空
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
    stream.getTracks().forEach(track => track.stop()) // 立即关闭测试流

    hasCameraPermission.value = true

    // 获取设备列表
    const devices = await navigator.mediaDevices.enumerateDevices()
    cameras.value = devices.filter(device => device.kind === 'videoinput')

    console.log('检测到的摄像头:', cameras.value)

    if (cameras.value.length > 0 && !selectedCamera.value) {
      selectedCamera.value = cameras.value[0].deviceId
    }

    if (cameras.value.length === 0) {
      ElMessage.warning('未检测到摄像头设备')
    } else {
      ElMessage.success(`检测到 ${cameras.value.length} 个摄像头`)
    }
  } catch (err) {
    console.error('获取摄像头失败:', err)
    hasCameraPermission.value = false
    if (err.name === 'NotAllowedError') {
      ElMessage.error('请允许摄像头权限以使用此功能')
    } else if (err.name === 'NotFoundError') {
      ElMessage.error('未找到摄像头设备')
    } else {
      ElMessage.error('获取摄像头失败: ' + err.message)
    }
  } finally {
    isLoadingCameras.value = false
  }
}

/* 开启摄像头 */
async function startCamera() {
  try {
    // 先显示视频区域，确保 DOM 元素存在
    showVideoArea.value = true
    
    // 等待 DOM 更新
    await nextTick()
    
    let constraints

    if (selectedCamera.value) {
      // 使用选定的摄像头
      constraints = {
        video: {
          deviceId: { exact: selectedCamera.value },
          width: { ideal: 640 },
          height: { ideal: 480 }
        },
        audio: false
      }
    } else {
      // 使用默认摄像头
      constraints = {
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 }
        },
        audio: false
      }
    }

    console.log('正在请求摄像头权限...', constraints)
    const stream = await navigator.mediaDevices.getUserMedia(constraints)
    console.log('获取到视频流:', stream)

    if (videoElement.value) {
      videoElement.value.srcObject = stream
      
      // 等待视频加载完成
      videoElement.value.onloadedmetadata = () => {
        console.log('视频元数据加载完成')
        videoElement.value.play().then(() => {
          console.log('视频开始播放')
          isStreaming.value = true
          hasCameraPermission.value = true
          ElMessage.success('摄像头已开启')
        }).catch(err => {
          console.error('视频播放失败:', err)
          ElMessage.error('视频播放失败: ' + err.message)
        })
      }
      
      // 添加错误处理
      videoElement.value.onerror = (err) => {
        console.error('视频元素错误:', err)
        ElMessage.error('视频加载错误')
      }
    } else {
      console.error('视频元素未找到')
      ElMessage.error('页面元素错误')
    }
  } catch (err) {
    console.error('开启摄像头失败:', err)
    hasCameraPermission.value = false
    showVideoArea.value = false
    if (err.name === 'NotAllowedError') {
      ElMessage.error('请允许摄像头权限')
    } else if (err.name === 'NotFoundError') {
      ElMessage.error('未找到摄像头设备')
    } else if (err.name === 'DevicesNotFoundError') {
      ElMessage.error('未找到摄像头设备')
    } else {
      ElMessage.error('开启摄像头失败: ' + err.message)
    }
  }
}

/* 关闭摄像头 */
function stopCamera() {
  // 停止检测
  if (detectionInterval) {
    clearInterval(detectionInterval)
    detectionInterval = null
  }
  isDetecting.value = false

  // 停止视频流
  if (videoElement.value && videoElement.value.srcObject) {
    const tracks = videoElement.value.srcObject.getTracks()
    tracks.forEach(track => track.stop())
    videoElement.value.srcObject = null
  }

  isStreaming.value = false
  showVideoArea.value = false
  resultImage.value = ''
  currentDetections.value = []
  ElMessage.info('摄像头已关闭')
}

/* 开始检测 */
function startDetection() {
  if (!isStreaming.value) {
    ElMessage.warning('请先开启摄像头')
    return
  }

  isDetecting.value = true
  frameCount = 0

  // 每 200ms 检测一帧
  detectionInterval = setInterval(async () => {
    await detectFrame()
  }, 200)

  ElMessage.success('开始实时检测')
}

/* 检测单帧 */
async function detectFrame() {
  if (!videoElement.value || !captureCanvas.value) return

  const video = videoElement.value
  const canvas = captureCanvas.value
  const ctx = canvas.getContext('2d')

  // 设置画布尺寸
  canvas.width = video.videoWidth || 640
  canvas.height = video.videoHeight || 480

  // 绘制当前帧
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

  // 转换为 base64
  const imageData = canvas.toDataURL('image/jpeg', 0.8)

  try {
    const res = await axios.post('/api/camera/detect', {
      image: imageData,
      model: model.value
    })

    if (res.data.success) {
      // 更新结果图像
      resultImage.value = res.data.result_image

      // 更新当前检测结果
      currentDetections.value = res.data.detections || []

      // 添加到历史记录
      frameCount++
      if (frameCount % 5 === 0) { // 每5帧记录一次
        detectionHistory.value.unshift({
          time: new Date().toLocaleTimeString('zh-CN'),
          detections: res.data.detections || []
        })

        // 限制历史记录长度
        if (detectionHistory.value.length > 50) {
          detectionHistory.value = detectionHistory.value.slice(0, 50)
        }
      }
    }
  } catch (err) {
    console.error('检测失败:', err)
  }
}

/* 清空历史 */
function clearHistory() {
  detectionHistory.value = []
  ElMessage.success('已清空记录')
}

/* 根据置信度获取颜色 */
function getConfidenceColor(confidence) {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}
</script>

<style scoped>
.camera-detection-container {
  padding: 16px;
}

.control-card {
  margin-bottom: 20px;
}

.control-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-group {
  display: flex;
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
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

.video-container {
  width: 100%;
  height: 360px;
  background-color: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-player {
  max-width: 100%;
  max-height: 100%;
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

.results-card {
  margin-bottom: 20px;
}

.current-detections {
  margin-bottom: 20px;
}

.current-detections h4 {
  margin-bottom: 12px;
  color: #303133;
}

.detection-item {
  text-align: center;
  margin-bottom: 10px;
}

.detection-class {
  font-weight: 500;
  margin-bottom: 8px;
  color: #303133;
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
