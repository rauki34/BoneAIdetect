<template>
  <div class="content-section">
    <h2>系统监控</h2>
    
    <!-- 统计卡片 -->
    <el-row :gutter="20" style="margin-bottom: 24px">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-value stat-blue">{{ stats.users?.total || 0 }}</div>
            <div class="stat-label">总用户数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-value stat-green">{{ stats.detections?.total || 0 }}</div>
            <div class="stat-label">总检测次数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-value stat-purple">{{ stats.detections?.today || 0 }}</div>
            <div class="stat-label">今日检测</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-value stat-orange">{{ stats.files?.count || 0 }}</div>
            <div class="stat-label">文件数量</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统资源监控 -->
    <el-row :gutter="20">
      <!-- CPU -->
      <el-col :xs="24" :md="8">
        <el-card class="monitor-card">
          <template #header>
            <div class="monitor-header">
              <span><el-icon><Cpu /></el-icon> CPU</span>
              <el-tag :type="systemInfo.cpu?.percent > 80 ? 'danger' : 'success'">
                {{ systemInfo.cpu?.percent?.toFixed(1) || 0 }}%
              </el-tag>
            </div>
          </template>
          <div class="monitor-content">
            <el-progress
              :percentage="systemInfo.cpu?.percent || 0"
              :color="getProgressColor"
              :stroke-width="12"
              striped
              striped-flow
            />
            <div class="monitor-info">
              <p>核心数: {{ systemInfo.cpu?.count || '-' }}</p>
              <p>频率: {{ systemInfo.cpu?.freq || '-' }}</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 内存 -->
      <el-col :xs="24" :md="8">
        <el-card class="monitor-card">
          <template #header>
            <div class="monitor-header">
              <span><el-icon><Memo /></el-icon> 内存</span>
              <el-tag :type="systemInfo.memory?.percent > 80 ? 'danger' : 'success'">
                {{ systemInfo.memory?.percent || 0 }}%
              </el-tag>
            </div>
          </template>
          <div class="monitor-content">
            <el-progress
              :percentage="systemInfo.memory?.percent || 0"
              :color="getProgressColor"
              :stroke-width="12"
              striped
              striped-flow
            />
            <div class="monitor-info">
              <p>总计: {{ systemInfo.memory?.total || '-' }}</p>
              <p>已用: {{ systemInfo.memory?.used || '-' }}</p>
              <p>可用: {{ systemInfo.memory?.available || '-' }}</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 磁盘 -->
      <el-col :xs="24" :md="8">
        <el-card class="monitor-card">
          <template #header>
            <div class="monitor-header">
              <span><el-icon><Histogram /></el-icon> 磁盘</span>
              <el-tag :type="systemInfo.disk?.percent > 80 ? 'danger' : 'success'">
                {{ systemInfo.disk?.percent || 0 }}%
              </el-tag>
            </div>
          </template>
          <div class="monitor-content">
            <el-progress
              :percentage="systemInfo.disk?.percent || 0"
              :color="getProgressColor"
              :stroke-width="12"
              striped
              striped-flow
            />
            <div class="monitor-info">
              <p>总计: {{ systemInfo.disk?.total || '-' }}</p>
              <p>已用: {{ systemInfo.disk?.used || '-' }}</p>
              <p>可用: {{ systemInfo.disk?.free || '-' }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统信息 -->
    <el-row style="margin-top: 24px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span><el-icon><InfoFilled /></el-icon> 系统信息</span>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="操作系统">{{ systemInfo.system?.platform || '-' }}</el-descriptions-item>
            <el-descriptions-item label="处理器">{{ systemInfo.system?.processor || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Python版本">{{ systemInfo.system?.python_version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="系统启动时间">{{ systemInfo.system?.boot_time || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <!-- 刷新按钮 -->
    <div class="refresh-bar">
      <el-button type="primary" @click="refreshData" :loading="loading">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
      <span class="refresh-hint">数据每30秒自动刷新</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from '../utils/axios'
import { ElMessage } from 'element-plus'
import { Cpu, Memo, Histogram, InfoFilled, Refresh } from '@element-plus/icons-vue'

const loading = ref(false)
const systemInfo = ref({})
const stats = ref({})
let refreshTimer = null

// 获取系统信息
const loadSystemInfo = async () => {
  try {
    const res = await axios.get('/api/monitor/system')
    systemInfo.value = res.data
  } catch (err) {
    console.error('加载系统信息失败:', err)
  }
}

// 获取统计数据
const loadStats = async () => {
  try {
    const res = await axios.get('/api/monitor/stats')
    stats.value = res.data
  } catch (err) {
    console.error('加载统计数据失败:', err)
  }
}

// 刷新所有数据
const refreshData = async () => {
  loading.value = true
  try {
    await Promise.all([loadSystemInfo(), loadStats()])
    ElMessage.success('数据已刷新')
  } catch (err) {
    ElMessage.error('刷新失败')
  } finally {
    loading.value = false
  }
}

// 进度条颜色
const getProgressColor = (percentage) => {
  if (percentage < 50) return '#67c23a'
  if (percentage < 80) return '#e6a23c'
  return '#f56c6c'
}

// 自动刷新
const startAutoRefresh = () => {
  refreshTimer = setInterval(() => {
    loadSystemInfo()
    loadStats()
  }, 30000) // 30秒
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  refreshData()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.content-section {
  animation: fadeIn 0.3s ease-in;
}

.content-section h2 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 24px;
  color: var(--medical-text-primary, #1a202c);
}

/* 统计卡片 */
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
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 8px;
}

.stat-blue { color: #409eff; }
.stat-green { color: #67c23a; }
.stat-purple { color: #9254de; }
.stat-orange { color: #e6a23c; }

.stat-label {
  color: #909399;
  font-size: 14px;
}

/* 监控卡片 */
.monitor-card {
  margin-bottom: 16px;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.monitor-header span {
  display: flex;
  align-items: center;
  gap: 8px;
}

.monitor-content {
  padding: 16px 0;
}

.monitor-info {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.monitor-info p {
  margin: 8px 0;
  color: #606266;
  font-size: 14px;
}

/* 刷新栏 */
.refresh-bar {
  margin-top: 24px;
  text-align: center;
}

.refresh-hint {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
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

/* 暗色模式适配 */
html.dark .monitor-info p {
  color: #a6aeb8;
}

html.dark .stat-label {
  color: #a6aeb8;
}
</style>
