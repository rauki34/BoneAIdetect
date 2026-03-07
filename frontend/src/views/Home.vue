<template>
  <el-container class="home-container">
    <!-- 左侧菜单栏：可收起 + 医疗蓝 -->
    <el-aside :width="sideWidth" class="sidebar">
      <!-- 收起/展开按钮 -->
      <div class="sidebar-toggle" @click="collapse = !collapse">
        <el-icon size="18">
          <Expand v-if="collapse" />
          <Fold v-else />
        </el-icon>
      </div>

      <!-- 菜单 -->
      <el-menu
        :default-active="activeMenu"
        :collapse="collapse"
        :collapse-transition="false"
        @select="handleMenuSelect"
        :router="false"
      >
        <el-menu-item index="detect">
          <el-icon><Picture /></el-icon>
          <template #title>开始检测</template>
        </el-menu-item>

        <el-menu-item index="video">
          <el-icon><VideoCamera /></el-icon>
          <template #title>视频流检测</template>
        </el-menu-item>

        <el-menu-item index="camera">
          <el-icon><Camera /></el-icon>
          <template #title>摄像头检测</template>
        </el-menu-item>

        <el-menu-item index="training" v-if="isAdmin">
          <el-icon><MagicStick /></el-icon>
          <template #title>模型训练</template>
        </el-menu-item>

        <el-menu-item index="history">
          <el-icon><Clock /></el-icon>
          <template #title>检测历史</template>
        </el-menu-item>

        <el-menu-item index="analysis" v-if="isAdmin">
          <el-icon><TrendCharts /></el-icon>
          <template #title>数据分析</template>
        </el-menu-item>

        <el-menu-item index="settings" v-if="isAdmin">
          <el-icon><Setting /></el-icon>
          <template #title>系统设置</template>
        </el-menu-item>

        <el-menu-item index="users" v-if="isAdmin">
          <el-icon><User /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>

        <el-menu-item index="logs" v-if="isAdmin">
          <el-icon><Document /></el-icon>
          <template #title>操作日志</template>
        </el-menu-item>

        <el-menu-item index="files" v-if="isAdmin">
          <el-icon><Folder /></el-icon>
          <template #title>文件管理</template>
        </el-menu-item>

        <el-menu-item index="monitor" v-if="isAdmin">
          <el-icon><Monitor /></el-icon>
          <template #title>系统监控</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧主内容区 -->
    <el-container class="main-container" direction="vertical">
      <!-- 顶部栏 -->
      <el-header class="top-header">
        <div class="header-left">
          <span class="system-title">骨折检测系统</span>
          <el-tag size="small" type="success" effect="light" class="version-tag">v1.0</el-tag>
        </div>
        <div class="header-right">
          <!-- 亮暗模式切换按钮 -->
          <el-switch
            v-model="isDarkMode"
            class="theme-switch"
            inline-prompt
            :active-icon="Moon"
            :inactive-icon="Sunny"
            active-text=""
            inactive-text=""
            @change="toggleTheme"
          />
          <el-divider direction="vertical" />
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-icon class="user-icon"><UserFilled /></el-icon>
              <span class="username-text">{{ username }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容主体 -->
      <el-main class="main-content">
        <!-- 检测页面 -->
        <div v-if="activeMenu === 'detect'" class="content-section">
          <h2>多模型骨折检测</h2>
          <Detection />
        </div>

        <!-- 视频流检测 -->
        <div v-if="activeMenu === 'video'" class="content-section">
          <h2>视频流检测分析</h2>
          <VideoStreamDetection />
        </div>

        <!-- 摄像头检测 -->
        <div v-if="activeMenu === 'camera'" class="content-section">
          <h2>摄像头实时检测</h2>
          <CameraDetection />
        </div>

        <!-- 模型训练 -->
        <div v-if="activeMenu === 'training'" class="content-section" v-show="isAdmin">
          <h2>模型训练管理</h2>
          <ModelTraining :isAdmin="isAdmin" />
        </div>

        <!-- 检测历史 -->
        <div v-if="activeMenu === 'history'" class="content-section">
          <h2>检测历史</h2>
          <div style="margin-bottom: 16px" v-if="isAdmin">
            <el-button type="danger" @click="clearHistory">清空所有</el-button>
          </div>
          <el-table :data="historyList" style="width: 100%" v-if="historyList.length > 0" border>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column label="时间" width="160">
              <template #default="{ row }">
                {{ formatTime(row.timestamp) }}
              </template>
            </el-table-column>
            <el-table-column prop="username" label="检测用户" width="120" v-if="isAdmin" />
            <el-table-column label="模型" width="120">
              <template #default="{ row }">
                {{ getModelDisplayName(row.model) }}
              </template>
            </el-table-column>
            <el-table-column label="骨折类型" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="type in row.fracture_types" :key="type" size="small" style="margin-right: 4px; margin-bottom: 2px;">
                  {{ type }}
                </el-tag>
                <span v-if="!row.fracture_types || row.fracture_types.length === 0">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="检测数" width="80" align="center" />
            <el-table-column label="医疗建议" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.has_medical_advice ? 'success' : 'info'" size="small">
                  {{ row.has_medical_advice ? '有' : '无' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right" align="center">
              <template #default="{ row }">
                <div class="action-btn-group">
                  <el-button 
                    type="primary" 
                    size="small" 
                    @click="viewHistoryDetail(row)"
                    class="table-btn"
                  >
                    <el-icon class="btn-icon"><View /></el-icon>
                    <span class="btn-text">详情</span>
                  </el-button>
                  <el-button 
                    type="success" 
                    size="small" 
                    @click="viewResult(row)"
                    class="table-btn"
                  >
                    <el-icon class="btn-icon"><Picture /></el-icon>
                    <span class="btn-text">图片</span>
                  </el-button>
                  <el-button 
                    type="danger" 
                    size="small" 
                    @click="deleteHistory(row.id)"
                    class="table-btn"
                  >
                    <el-icon class="btn-icon"><Delete /></el-icon>
                    <span class="btn-text">删除</span>
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无检测记录" />
        </div>

        <!-- 数据分析 -->
        <div v-if="activeMenu === 'analysis'" class="content-section">
          <h2>数据分析</h2>
          <el-row :gutter="20">
            <el-col :xs="24" :sm="12" :md="6">
              <el-card class="stat-card">
                <div class="stat-item">
                  <div class="stat-value stat-blue">{{ analysis.total_detections }}</div>
                  <div class="stat-label">总检测次数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="6">
              <el-card class="stat-card">
                <div class="stat-item">
                  <div class="stat-value stat-purple">{{ Object.keys(analysis.models_used).length }}</div>
                  <div class="stat-label">已用模型数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="6">
              <el-card class="stat-card">
                <div class="stat-item">
                  <div class="stat-value stat-indigo">{{ Object.keys(analysis.classes_detected).length }}</div>
                  <div class="stat-label">检测类别数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="6">
              <el-card class="stat-card">
                <div class="stat-item">
                  <div class="stat-value stat-orange">{{ (analysis.avg_confidence * 100).toFixed(1) }}%</div>
                  <div class="stat-label">平均置信度</div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <el-row :gutter="20" style="margin-top: 24px">
            <el-col :xs="24" :md="12">
              <el-card title="模型使用统计" class="data-card">
                <el-table :data="modelsData">
                  <el-table-column prop="name" label="模型" />
                  <el-table-column prop="count" label="使用次数" />
                </el-table>
              </el-card>
            </el-col>
            <el-col :xs="24" :md="12">
              <el-card title="检测类别统计" class="data-card">
                <el-table :data="classesData">
                  <el-table-column prop="name" label="类别" />
                  <el-table-column prop="count" label="检测次数" />
                </el-table>
              </el-card>
            </el-col>
          </el-row>
          <!-- 置信度趋势折线 -->
          <el-row style="margin-top: 24px">
            <el-col :span="24">
              <el-card title="置信度趋势" class="data-card">
                <div v-if="!lineData.length" class="no-data">暂无检测记录</div>
                <div v-show="lineData.length" ref="confidenceLineRef" style="height:320px"></div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- 系统设置 -->
        <div v-if="activeMenu === 'settings'" class="content-section">
          <h2>系统设置</h2>
          <el-form label-width="120px" style="max-width:500px">
            <el-form-item label="默认模型">
              <el-select v-model="settings.default_model" placeholder="选择默认模型" style="width: 200px">
                <el-option-group label="系统模型">
                  <el-option
                    v-for="m in systemModelsForSettings"
                    :key="m.key"
                    :label="m.name"
                    :value="m.key"
                  />
                </el-option-group>
                <el-option-group label="自定义模型" v-if="customModelsForSettings.length > 0">
                  <el-option
                    v-for="m in customModelsForSettings"
                    :key="m.key"
                    :label="m.name"
                    :value="m.key"
                  />
                </el-option-group>
              </el-select>
            </el-form-item>
            <el-form-item label="置信度阈值">
              <el-input-number v-model="settings.confidence_threshold" :min="0" :max="1" :step="0.01" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveSettings">保存设置</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 用户管理 -->
        <div v-if="activeMenu === 'users'" class="content-section">
          <UserManagement />
        </div>

        <!-- 操作日志 -->
        <div v-if="activeMenu === 'logs'" class="content-section">
          <OperationLog />
        </div>

        <!-- 文件管理 -->
        <div v-if="activeMenu === 'files'" class="content-section">
          <FileManager />
        </div>

        <!-- 系统监控 -->
        <div v-if="activeMenu === 'monitor'" class="content-section">
          <SystemMonitor />
        </div>
      </el-main>
    </el-container>

    <!-- 历史记录详情对话框 -->
    <el-dialog
      v-model="historyDetailVisible"
      title="检测记录详情"
      width="900px"
      :close-on-click-modal="false"
    >
      <div v-if="currentHistory" class="history-detail">
        <!-- 基本信息 -->
        <el-descriptions :column="3" border style="margin-bottom: 20px;">
          <el-descriptions-item label="记录ID">{{ currentHistory.id }}</el-descriptions-item>
          <el-descriptions-item label="检测用户">{{ currentHistory.username || '-' }}</el-descriptions-item>
          <el-descriptions-item label="检测时间">{{ formatTime(currentHistory.timestamp) }}</el-descriptions-item>
          <el-descriptions-item label="使用模型">{{ getModelDisplayName(currentHistory.model) }}</el-descriptions-item>
          <el-descriptions-item label="检测数量">{{ currentHistory.count }} 个</el-descriptions-item>
          <el-descriptions-item label="平均置信度">
            <span v-if="currentHistory.confidence">{{ (currentHistory.confidence * 100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 图片对比 -->
        <h4 style="margin-bottom: 12px;">图片对比</h4>
        <el-row :gutter="20" style="margin-bottom: 20px;">
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">原始图片</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="currentHistory.original_image"
                  :src="currentHistory.original_image"
                  fit="contain"
                  :preview-src-list="[currentHistory.original_image, currentHistory.result_image]"
                />
                <el-empty v-else description="原图未保存" />
              </div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">检测结果</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="currentHistory.result_image"
                  :src="currentHistory.result_image"
                  fit="contain"
                  :preview-src-list="[currentHistory.result_image, currentHistory.original_image]"
                />
                <el-empty v-else description="结果图未保存" />
              </div>
            </div>
          </el-col>
        </el-row>

        <!-- 检测详情 -->
        <h4 style="margin-bottom: 12px;">检测详情</h4>
        <el-table :data="currentHistory.detections" border size="small" style="margin-bottom: 20px;">
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="class" label="类别" width="120" />
          <el-table-column label="置信度" width="150">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.confidence * 100)"
                :color="getConfidenceColor(row.confidence)"
                :stroke-width="12"
              />
            </template>
          </el-table-column>
          <el-table-column prop="bbox" label="检测框坐标" />
        </el-table>

        <!-- 医疗建议 -->
        <div v-if="currentHistory.has_medical_advice && currentHistory.medical_advice">
          <h4 style="margin-bottom: 12px;">医疗建议</h4>
          <el-alert
            title="AI 辅助诊断建议"
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
          >
            此为AI辅助诊断结果仅供参考，具体诊断请咨询专业医生
          </el-alert>
          <div class="medical-advice-content">
            <pre>{{ currentHistory.medical_advice.interpretation }}</pre>
          </div>
          <el-descriptions v-if="currentHistory.medical_advice.patient_info" :column="3" size="small" border style="margin-top: 12px;">
            <el-descriptions-item label="患者年龄">{{ currentHistory.medical_advice.patient_info.age || '未提供' }}</el-descriptions-item>
            <el-descriptions-item label="患者性别">{{ currentHistory.medical_advice.patient_info.gender || '未提供' }}</el-descriptions-item>
            <el-descriptions-item label="症状描述">{{ currentHistory.medical_advice.patient_info.symptoms || '未提供' }}</el-descriptions-item>
          </el-descriptions>
        </div>
        <el-empty v-else description="暂无医疗建议" style="margin: 20px 0;" />
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="historyDetailVisible = false">
            <el-icon><Close /></el-icon>
            关闭
          </el-button>
          <el-button type="success" @click="downloadImage(currentHistory?.original_image)">
            <el-icon><Download /></el-icon>
            下载原图
          </el-button>
          <el-button type="primary" @click="downloadImage(currentHistory?.result_image)">
            <el-icon><Download /></el-icon>
            下载结果图
          </el-button>
        </div>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
/* -------------------- 收起菜单 -------------------- */
import { ref, computed, reactive, onMounted, onUnmounted, nextTick, watch, toRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from '../utils/axios'
import Detection from './Detection.vue'
import UserManagement from './UserManagement.vue'
import OperationLog from './OperationLog.vue'
import FileManager from './FileManager.vue'
import SystemMonitor from './SystemMonitor.vue'
import VideoStreamDetection from './VideoStreamDetection.vue'
import CameraDetection from './CameraDetection.vue'
import ModelTraining from './ModelTraining.vue'
import { Line } from '@antv/g2plot'
import { ArrowDown, Fold, Expand, Picture, Clock, TrendCharts, Setting, User, Moon, Sunny, UserFilled, SwitchButton, Document, Folder, Monitor, Close, Download, View, Delete, VideoCamera, Camera, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'


const collapse = ref(false)
const sideWidth = computed(() => (collapse.value ? 64 : 220) + 'px')

// 亮暗模式切换
const isDarkMode = ref(localStorage.getItem('theme') === 'dark')

// 应用主题
const applyTheme = (dark) => {
  const html = document.documentElement
  if (dark) {
    html.classList.add('dark')
  } else {
    html.classList.remove('dark')
  }
}

// 切换主题
const toggleTheme = (val) => {
  isDarkMode.value = val
  localStorage.setItem('theme', val ? 'dark' : 'light')
  applyTheme(val)
  ElMessage.success(val ? '已切换到暗色模式' : '已切换到亮色模式')
}

// 初始化主题
applyTheme(isDarkMode.value)

/* -------------------------------------------------- */

const router = useRouter()
const route = useRoute()
const activeMenu = ref('detect')

// 格式化时间显示
const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).replace(/\//g, '-')
  } catch (e) {
    return timestamp
  }
}

// 模型名称映射（用于显示可读名称）
const modelNameMap = ref(new Map())

// 获取模型显示名称
const getModelDisplayName = (modelKey) => {
  if (!modelKey) return '-'
  // 系统模型
  if (modelKey === 'yolov8') return 'YOLOv8'
  if (modelKey === 'yolo11') return 'YOLOv11'
  if (modelKey === 'yolo12') return 'YOLOv12'
  // 从映射中获取自定义模型名称
  const customName = modelNameMap.value.get(modelKey)
  if (customName) return customName
  // 如果找不到映射，返回简化后的key
  if (modelKey.startsWith('custom_')) {
    return modelKey.replace('custom_', '').replace(/_\d+$/, '')
  }
  return modelKey
}

// 加载模型名称映射
const loadModelNameMap = async () => {
  try {
    const res = await axios.get('/api/models')
    const map = new Map()
    // 系统模型
    res.data.system_models.forEach(m => {
      map.set(m.model_key || m.key, m.name)
    })
    // 自定义模型
    res.data.custom_models.forEach(m => {
      map.set(m.model_key, m.name)
    })
    modelNameMap.value = map
  } catch (err) {
    console.error('加载模型名称映射失败', err)
  }
}

// 使用计算属性实时获取用户信息，确保切换用户后自动更新
const username = computed(() => localStorage.getItem('username') || 'User')
const userRole = computed(() => localStorage.getItem('role') || 'user')
const isAdmin = computed(() => userRole.value === 'admin')

// 设置页面的模型列表（从 settings.available_models 转换）
const systemModelsForSettings = computed(() => {
  if (!settings.available_models) return []
  return settings.available_models.filter(m => m.type === 'system')
})

const customModelsForSettings = computed(() => {
  if (!settings.available_models) return []
  return settings.available_models.filter(m => m.type === 'custom')
})

// 历史记录
const historyList = ref([])
const historyDetailVisible = ref(false)
const currentHistory = ref(null)

// 分析数据
const analysis = reactive({
  total_detections: 0,
  models_used: {},
  classes_detected: {},
  avg_confidence: 0
})
const modelsData = ref([])
const classesData = ref([])

// 设置数据
const settings = reactive({
  default_model: 'yolov8',
  available_models: [],
  confidence_threshold: 0.25
})

// 加载历史
const loadHistory = async () => {
  try {
    const res = await axios.get('/api/history')
    historyList.value = res.data.data
  } catch (err) {
    console.error('加载历史失败', err)
  }
}

// 删除历史
const deleteHistory = async (id) => {
  try {
    await axios.delete(`http://127.0.0.1:5000/api/history/ ${id}`)
    loadHistory()
  } catch (err) {
    console.error('删除失败', err)
  }
}

// 清空历史
const clearHistory = async () => {
  try {
    await axios.delete('http://127.0.0.1:5000/api/history/clear/all ')
    loadHistory()
  } catch (err) {
    console.error('清空失败', err)
  }
}

// 查看结果
const viewResult = (row) => {
  window.open(row.result_image)
}

// 根据置信度获取颜色
const getConfidenceColor = (confidence) => {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

// 查看历史记录详情
const viewHistoryDetail = async (row) => {
  try {
    const res = await axios.get(`/api/history/${row.id}`)
    currentHistory.value = res.data
    historyDetailVisible.value = true
  } catch (err) {
    console.error('加载详情失败', err)
    ElMessage.error('加载详情失败')
  }
}

// 下载图片
const downloadImage = (url) => {
  if (!url) {
    ElMessage.warning('图片链接不存在')
    return
  }
  const link = document.createElement('a')
  link.href = url
  link.download = url.split('/').pop() || 'image.jpg'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 加载分析
const loadAnalysis = async () => {
  try {
    const res = await axios.get('/api/analysis')
    Object.assign(analysis, res.data)
    // 使用模型名称映射转换 key 为可读名称
    modelsData.value = Object.entries(analysis.models_used).map(([key, count]) => ({
      name: getModelDisplayName(key),
      count
    }))
    classesData.value = Object.entries(analysis.classes_detected).map(([name, count]) => ({ name, count }))
  } catch (err) {
    console.error('加载分析失败', err)
  }
}

// 加载设置
const loadSettings = async () => {
  try {
    const res = await axios.get('/api/settings')
    Object.assign(settings, res.data)
  } catch (err) {
    console.error('加载设置失败', err)
  }
}

// 保存设置
const saveSettings = async () => {
  try {
    await axios.post('/api/settings', settings)
    ElMessage.success('设置已保存')
  } catch (err) {
    console.error('保存设置失败', err)
  }
}

// 退出 - 使用 window.location.replace 强制刷新，确保状态完全重置
const logout = () => {
  // 清除所有登录状态
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('role')
  
  ElMessage.success('已退出登录')
  
  // 使用 replace 并强制刷新页面，避免浏览器历史记录问题
  window.location.replace('/login?t=' + Date.now())
}

// 置信度趋势折线图
const lineData = ref([])           // 原始数据
const confidenceLineRef = ref(null)   // dom 容器
const lineRendered = ref(false)
let linePlot = null                   // 图表实例

const reloadLineData = async () => {
  try {
    const res = await axios.get('/api/analysis/confidence_series')
    lineData.value = res.data ?? []   // 兜底空数组
  } catch (e) {
    console.error('拉取折线数据失败', e)
    lineData.value = []               // 出错也清空，避免旧脏数据
  }
}

const destroyChart = () => {
  if (linePlot) {
    linePlot.destroy()
    linePlot = null
    lineRendered.value = false
  }
}

const drawConfidenceLine = async (force = false) => {
  // 如果不是管理员或不在分析页面，不绘制（除非强制刷新）
  if (!isAdmin.value) return
  if (activeMenu.value !== 'analysis' && !force) return
  
  // 强制刷新时，先销毁旧图表
  if (force) {
    destroyChart()
  }
  
  await reloadLineData()
  await nextTick()
  
  // 再次检查DOM元素是否存在（切换菜单后可能DOM还未准备好）
  if (!confidenceLineRef.value) {
    console.log('【折线】DOM容器未准备好，延迟重试')
    // 延迟100ms后重试
    setTimeout(() => {
      if (activeMenu.value === 'analysis' && confidenceLineRef.value) {
        drawConfidenceLine(true)
      }
    }, 100)
    return
  }

  const rawData = toRaw(lineData.value)   // 脱响应式代理
  console.log('【折线】数据条数:', rawData.length, '强制刷新:', force)

  // 如果图表已存在，销毁并重新创建（确保数据完全刷新）
  if (lineRendered.value && linePlot) {
    destroyChart()
  }
  
  // 如果没有数据，显示空状态
  if (!rawData || rawData.length === 0) {
    console.log('【折线】暂无数据')
    return
  }
  
  // 创建新图表
  try {
    linePlot = new Line(confidenceLineRef.value, {
      data: rawData,
      xField: 'timestamp',
      yField: 'confidence',
      smooth: true,
      color: '#2b6cb0',
      animation: { appear: { animation: 'fade-in' } },
      xAxis: { 
        title: { text: '检测时间', style: { fill: '#666' } }, 
        label: { rotate: 0 }
      },
      yAxis: { 
        title: { text: '置信度', style: { fill: '#666' } }, 
        min: 0, 
        max: 1, 
        tickCount: 6, 
        label: { formatter: (v) => `${(v * 100).toFixed(0)}%` } 
      },
      tooltip: { 
        showMarkers: true,
        fields: ['timestamp', 'confidence'],
        formatter: (data) => {
          const timestamp = data?.timestamp || '-'
          const confidence = data?.confidence || 0
          return {
            name: '置信度',
            value: `${(confidence * 100).toFixed(1)}%`
          }
        },
        customContent: (title, items) => {
          const data = items?.[0]?.data || {}
          const timestamp = data.timestamp || '-'
          const confidence = data.confidence || 0
          return `
            <div style="padding: 8px 12px;">
              <div style="margin-bottom: 4px; color: #666;">时间：${timestamp}</div>
              <div style="color: #2b6cb0; font-weight: bold;">置信度：${(confidence * 100).toFixed(1)}%</div>
            </div>
          `
        }
      },
      interactions: [{ type: 'tooltip' }]
    })
    linePlot.render()
    lineRendered.value = true
    console.log('【折线】图表渲染成功')
  } catch (e) {
    console.error('【折线】图表渲染失败:', e)
  }
}

// 菜单切换处理
const handleMenuSelect = (index) => {
  // 如果离开analysis页面，销毁图表避免内存泄漏和渲染问题
  if (activeMenu.value === 'analysis' && index !== 'analysis') {
    destroyChart()
  }
  
  activeMenu.value = index
  if (index === 'history') loadHistory()
  if (index === 'analysis' && isAdmin.value) {
    loadAnalysis(); loadSettings()
    // 延迟执行，确保DOM已更新
    setTimeout(() => {
      // 强制刷新图表（因为DOM是新创建的）
      needRefreshChart.value = false
      drawConfidenceLine(true) // 强制刷新
    }, 150)
  }
  if (index === 'settings' && isAdmin.value) loadSettings()
}

// 标记是否有新数据需要刷新图表
const needRefreshChart = ref(false)

// 处理检测完成事件 - 更新数据并刷新图表
const handlePredictionComplete = async () => {
  console.log('【折线】收到检测完成事件')
  // 重新加载数据
  await reloadLineData()
  // 如果在analysis页面，立即刷新图表
  if (isAdmin.value && activeMenu.value === 'analysis') {
    await nextTick()
    drawConfidenceLine()
  } else {
    // 如果不在analysis页面，标记需要刷新
    needRefreshChart.value = true
    console.log('【折线】标记需要刷新')
  }
}

onMounted(() => {
  // 让 Detection 上传完后能通知我们重画折线
  window.addEventListener('predictionComplete', handlePredictionComplete)

  // 加载模型名称映射
  loadModelNameMap()

  // 原有的首次加载
  loadHistory()
  if (isAdmin.value) {
    loadAnalysis()
    loadSettings()
    if (activeMenu.value === 'analysis') {
      setTimeout(() => drawConfidenceLine(), 100)
    }
  }
})

watch(activeMenu, (val) => {
  if (val === 'analysis' && isAdmin.value) {
    // 延迟执行，确保DOM已更新
    setTimeout(() => {
      // 如果有新数据或图表未渲染，则强制刷新
      if (needRefreshChart.value || !lineRendered.value) {
        needRefreshChart.value = false
        drawConfidenceLine(true) // 强制刷新
      }
    }, 100)
  }
})

// 卸载时销毁图表实例
onUnmounted(() => {
  window.removeEventListener('predictionComplete', handlePredictionComplete)
  destroyChart()
})
</script>

<!-- 全局：变量 + ElementPlus 覆盖 -->
<style>
/* 医疗感变量 - 亮色模式 */
:root {
  --medical-bg: #f5f9ff;            /* 主背景 */
  --medical-menu-bg: #ffffff;       /* 侧边栏 */
  --medical-primary: #2b6cb0;       /* 主色 */
  --medical-primary-light: #e6f2ff;
  --medical-menu-text: #4a5568;
  --medical-menu-active: #2b6cb0;
  --medical-menu-hover: #ebf8ff;
  --medical-header-bg: #f3fee7;
  --medical-text-primary: #1a202c;
  --medical-text-secondary: #4a5568;
  --medical-border-color: #e2e8f0;
  --medical-card-bg: #ffffff;
}

/* 暗色模式变量 */
html.dark {
  --medical-bg: #0f172a;            /* 主背景 */
  --medical-menu-bg: #1e293b;       /* 侧边栏 */
  --medical-primary: #60a5fa;       /* 主色 */
  --medical-primary-light: #1e3a5f;
  --medical-menu-text: #94a3b8;
  --medical-menu-active: #60a5fa;
  --medical-menu-hover: #334155;
  --medical-header-bg: #1e293b;
  --medical-text-primary: #f1f5f9;
  --medical-text-secondary: #94a3b8;
  --medical-border-color: #334155;
  --medical-card-bg: #1e293b;
}

/* ElementPlus 顶栏 & 主内容区 */
.el-header {
  background-color: var(--medical-menu-bg) !important;
  border-bottom: 1px solid var(--medical-border-color) !important;
}
.el-main {
  background-color: var(--medical-bg) !important;
}

/* ==================== 暗色模式全局样式优化 ==================== */

/* 暗色模式下的基础文字颜色 */
html.dark {
  color: #e2e8f0;
}

/* 暗色模式下的表格样式 */
html.dark .el-table {
  background-color: var(--medical-card-bg);
  color: #e2e8f0;
}

html.dark .el-table th {
  background-color: #252f47;
  color: #f1f5f9;
  font-weight: 600;
  border-bottom-color: var(--medical-border-color);
}

html.dark .el-table td {
  background-color: var(--medical-card-bg);
  color: #e2e8f0;
  border-bottom-color: var(--medical-border-color);
}

html.dark .el-table--striped .el-table__body tr.el-table__row--striped td {
  background-color: #252f47;
}

html.dark .el-table__body tr:hover > td {
  background-color: #334155 !important;
}

html.dark .el-table__empty-text {
  color: #94a3b8;
}

/* 暗色模式下的卡片样式 */
html.dark .el-card {
  background-color: var(--medical-card-bg);
  border-color: var(--medical-border-color);
  color: #e2e8f0;
}

html.dark .el-card__header {
  border-bottom-color: var(--medical-border-color);
  color: #f1f5f9;
}

/* 暗色模式下的表单 */
html.dark .el-form-item__label {
  color: #e2e8f0;
}

/* 暗色模式下的输入框 */
html.dark .el-input__wrapper {
  background-color: #0f172a;
  box-shadow: 0 0 0 1px #475569 inset;
}

html.dark .el-input__inner {
  color: #e2e8f0;
}

html.dark .el-input__inner::placeholder {
  color: #64748b;
}

/* 暗色模式下的选择器 */
html.dark .el-select-dropdown {
  background-color: #1e293b;
  border-color: #334155;
}

html.dark .el-select-dropdown__item {
  color: #e2e8f0;
}

html.dark .el-select-dropdown__item:hover,
html.dark .el-select-dropdown__item.selected {
  background-color: #334155;
  color: #60a5fa;
}

/* 暗色模式下的按钮 */
html.dark .el-button--default {
  background-color: #334155;
  border-color: #475569;
  color: #e2e8f0;
}

html.dark .el-button--default:hover {
  background-color: #475569;
  border-color: #64748b;
  color: #f1f5f9;
}

/* 暗色模式下的标签 */
html.dark .el-tag {
  background-color: #334155;
  border-color: #475569;
  color: #e2e8f0;
}

html.dark .el-tag--success {
  background-color: rgba(16, 185, 129, 0.2);
  border-color: rgba(16, 185, 129, 0.3);
  color: #34d399;
}

html.dark .el-tag--info {
  background-color: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.3);
  color: #60a5fa;
}

html.dark .el-tag--danger {
  background-color: rgba(248, 113, 113, 0.2);
  border-color: rgba(248, 113, 113, 0.3);
  color: #f87171;
}

/* 暗色模式下的对话框 */
html.dark .el-dialog {
  background-color: #1e293b;
}

html.dark .el-dialog__title {
  color: #f1f5f9;
}

html.dark .el-dialog__body {
  color: #e2e8f0;
}

/* 暗色模式下的下拉菜单 */
html.dark .el-dropdown-menu {
  background-color: #1e293b;
  border-color: #334155;
}

html.dark .el-dropdown-menu__item {
  color: #e2e8f0;
}

html.dark .el-dropdown-menu__item:hover {
  background-color: #334155;
  color: #60a5fa;
}

/* 暗色模式下的分割线 */
html.dark .el-divider {
  background-color: #334155;
}

/* 暗色模式下的空状态 */
html.dark .el-empty__description {
  color: #94a3b8;
}

/* 暗色模式下的菜单 */
html.dark .el-menu {
  background-color: var(--medical-menu-bg);
}

html.dark .el-menu-item {
  color: #94a3b8;
}

html.dark .el-menu-item:hover {
  background-color: #334155;
  color: #e2e8f0;
}

html.dark .el-menu-item.is-active {
  background-color: rgba(96, 165, 250, 0.15);
  color: #60a5fa;
}

/* 暗色模式下的分页 */
html.dark .el-pagination {
  color: #e2e8f0;
}

html.dark .el-pagination button {
  background-color: transparent;
  color: #94a3b8;
}

html.dark .el-pagination button:hover {
  color: #60a5fa;
}

html.dark .el-pager li {
  background-color: transparent;
  color: #94a3b8;
}

html.dark .el-pager li.active {
  color: #60a5fa;
}

html.dark .el-pager li:hover {
  color: #60a5fa;
}
</style>

<!-- 组件内：侧边栏 + 动画 -->
<style scoped>
.home-container {
  min-height: 100vh;
  height: auto;
  background: var(--medical-bg);
}

.sidebar {
  background: var(--medical-menu-bg);
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.25s;
}

.sidebar-toggle {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--medical-menu-text);
}
.sidebar-toggle:hover {
  background: var(--medical-menu-hover);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--medical-menu-active);
  white-space: nowrap;
}
.sidebar-header img {
  width: 28px;
  height: 28px;
}

.el-menu {
  border-right: none;
  background: var(--medical-menu-bg);
}
.el-menu-item {
  color: var(--medical-menu-text);
  border-radius: 6px;
  margin: 0 6px 4px 6px;
}
.el-menu-item:hover {
  background: var(--medical-menu-hover) !important;
}
.el-menu-item.is-active {
  background: var(--medical-primary-light) !important;
  color: var(--medical-menu-active) !important;
}
.el-menu-item.is-active .el-icon {
  color: var(--medical-menu-active);
}

/* ==================== 顶栏样式 ==================== */

/* 亮色模式 - 蓝白主题 */
.top-header {
  background: #ffffff !important;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.header-left {
  display: flex;
  align-items: center;
}

.system-title {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  letter-spacing: 0.5px;
}

.version-tag {
  margin-left: 8px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 主题切换开关样式 - 亮色模式 */
.theme-switch {
  --el-switch-on-color: #334155;
  --el-switch-off-color: #3b82f6;
}

.theme-switch :deep(.el-switch__core) {
  border-radius: 12px;
  border: 1px solid #d1d5db;
}

.theme-switch :deep(.el-switch__inner) {
  padding: 0 4px;
}

.header-right .el-divider {
  background-color: #d1d5db;
  height: 20px;
}

.user-info {
  cursor: pointer;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 20px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  transition: all 0.3s ease;
}

.user-info:hover {
  background: #e2e8f0;
  color: #1e293b;
}

.user-icon {
  font-size: 16px;
  color: #3b82f6;
}

.username-text {
  font-weight: 500;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ==================== 暗色模式 - 暗夜黑风格 ==================== */

html.dark .top-header {
  background: #0f172a !important;
  border-bottom: 1px solid #1e293b;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

html.dark .system-title {
  color: #f1f5f9;
}

html.dark .version-tag {
  background-color: rgba(16, 185, 129, 0.2) !important;
  border-color: rgba(16, 185, 129, 0.3) !important;
  color: #34d399 !important;
}

/* 暗色模式 - 主题切换开关 */
html.dark .theme-switch {
  --el-switch-on-color: #60a5fa;
  --el-switch-off-color: #475569;
}

html.dark .theme-switch :deep(.el-switch__core) {
  border-color: #475569;
}

html.dark .header-right .el-divider {
  background-color: #334155;
}

html.dark .user-info {
  color: #94a3b8;
  background: #1e293b;
  border-color: #334155;
}

html.dark .user-info:hover {
  background: #334155;
  color: #f1f5f9;
}

html.dark .user-icon {
  color: #60a5fa;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: var(--medical-bg);
}

.content-section {
  animation: fadeIn 0.3s ease-in;
}
.content-section h2 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 24px;
  color: var(--medical-text-primary);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ==================== 历史记录详情对话框样式 ==================== */
.history-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.detail-image-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  background-color: #fafafa;
}

.detail-image-title {
  padding: 10px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 500;
  text-align: center;
  color: #606266;
}

.detail-image-wrapper {
  padding: 16px;
  background-color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  height: 300px;
}

.detail-image-wrapper .el-image {
  width: 100%;
  height: 100%;
}

.detail-image-wrapper .el-image :deep(img) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.medical-advice-content {
  background-color: #f5f7fa;
  border-radius: 4px;
  padding: 16px;
  max-height: 300px;
  overflow-y: auto;
}

.medical-advice-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Microsoft YaHei', sans-serif;
  line-height: 1.6;
  color: #303133;
}

/* 表格操作按钮样式 - 紧凑布局 */
.action-btn-group {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
}

.action-btn-group .table-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  height: 28px;
  line-height: 1;
}

.action-btn-group .table-btn .btn-icon {
  font-size: 13px;
  margin-right: 3px;
}

.action-btn-group .table-btn .btn-text {
  font-size: 12px;
}

/* 对话框底部按钮样式 */
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 12px 0;
}

.dialog-footer .el-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  font-size: 14px;
}

.dialog-footer .el-icon {
  font-size: 16px;
}

/* ==================== 数据分析统计卡片样式 ==================== */

.stat-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
}

.stat-blue { color: #4f6ef7; }
.stat-purple { color: #764ba2; }
.stat-indigo { color: #667eea; }
.stat-orange { color: #f29d04; }

.stat-label {
  color: #64748b;
  margin-top: 8px;
  font-size: 14px;
}

/* 暗色模式下的统计卡片 */
html.dark .stat-blue { color: #60a5fa; }
html.dark .stat-purple { color: #a78bfa; }
html.dark .stat-indigo { color: #818cf8; }
html.dark .stat-orange { color: #fbbf24; }

html.dark .stat-label {
  color: #94a3b8;
}

/* 数据卡片标题 */
.data-card :deep(.el-card__header) {
  font-weight: 600;
  color: var(--medical-text-primary);
}

/* 无数据提示 */
.no-data {
  text-align: center;
  color: #909399;
  padding: 40px 0;
}

html.dark .no-data {
  color: #64748b;
}

.action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}
.action-buttons .el-button {
  border-radius: 12px;
}

.cell-model {
  font-size: 13px;
}
</style>
