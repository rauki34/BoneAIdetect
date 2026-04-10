<template>
  <div class="report-detail">
    <el-card v-if="report" shadow="never">
      <template #header>
        <div class="card-header">
          <span>报告详情</span>
          <el-button type="text" @click="handleBack">
            <el-icon><ArrowLeft /></el-icon>
            返回列表
          </el-button>
        </div>
      </template>
      
      <div class="detail-content">
        <!-- 基本信息 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item label="报告ID">
            {{ report.id }}
          </el-descriptions-item>
          <el-descriptions-item label="医生姓名">
            {{ report.doctor_name || '未指定' }}
          </el-descriptions-item>
          <el-descriptions-item label="检测时间">
            {{ formatDateTime(report.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="检测模型">
            {{ report.model }}
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 检测结果 -->
        <el-divider content-position="left">检测结果</el-divider>
        <div class="detection-results">
          <el-tag
            v-for="(detection, index) in report.detections"
            :key="index"
            size="large"
            style="margin-right: 8px; margin-bottom: 8px;"
          >
            {{ detection.class }} - 置信度: {{ (detection.confidence * 100).toFixed(1) }}%
          </el-tag>
        </div>
        
        <!-- 医生诊断 -->
        <el-divider content-position="left">医生诊断</el-divider>
        <div class="diagnosis-content">
          {{ report.diagnosis || '医生暂未填写诊断结论' }}
        </div>
        
        <!-- 医疗建议 -->
        <el-divider content-position="left">医疗建议</el-divider>
        <div class="medical-advice-content">
          <div v-if="report.medical_advice">
            <div v-if="report.medical_advice.severity" class="advice-item">
              <strong>严重程度:</strong> {{ report.medical_advice.severity }}
            </div>
            <div v-if="report.medical_advice.recommendation" class="advice-item">
              <strong>建议:</strong> {{ report.medical_advice.recommendation }}
            </div>
            <div v-if="report.medical_advice.follow_up" class="advice-item">
              <strong>随访建议:</strong> {{ report.medical_advice.follow_up }}
            </div>
          </div>
          <div v-else class="no-advice">
            暂无医疗建议
          </div>
        </div>
        
        <!-- 检测图像 -->
        <el-divider content-position="left">检测图像</el-divider>
        <div class="image-preview">
          <el-image
            v-if="report.result_image"
            :src="report.result_image"
            fit="contain"
            :preview-src-list="[report.result_image]"
            style="max-width: 100%; max-height: 500px;"
          />
          <el-empty v-else description="暂无图像" />
        </div>
      </div>
    </el-card>
    
    <!-- 加载状态 -->
    <el-card v-else-if="loading" shadow="never" v-loading="loading">
      <div style="height: 400px;"></div>
    </el-card>
    
    <!-- 空状态 -->
    <el-card v-else shadow="never">
      <el-empty description="请从列表中选择一个报告查看详情" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from '../utils/axios'
import { formatDateTime } from '../utils/datetime'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

const props = defineProps({
  reportId: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['back'])

const loading = ref(false)
const report = ref(null)

// 加载报告详情
const loadReportDetail = async (id) => {
  if (!id) {
    report.value = null
    return
  }
  
  loading.value = true
  try {
    const response = await axios.get(`/api/patient/reports/${id}`)
    report.value = response.data.report || null
  } catch (error) {
    console.error('加载报告详情失败:', error)
    ElMessage.error('加载报告详情失败')
    report.value = null
  } finally {
    loading.value = false
  }
}

// 返回列表
const handleBack = () => {
  emit('back')
}

// 监听 reportId 变化
watch(() => props.reportId, (newId) => {
  loadReportDetail(newId)
}, { immediate: true })

// 暴露方法供父组件调用
defineExpose({
  loadReportDetail
})
</script>

<style scoped>
.report-detail {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-content {
  padding: 10px;
}

.detection-results {
  padding: 10px 0;
}

.diagnosis-content,
.medical-advice-content {
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
  min-height: 60px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.advice-item {
  margin-bottom: 12px;
  line-height: 1.6;
}

.advice-item:last-child {
  margin-bottom: 0;
}

.no-advice {
  color: #909399;
  font-style: italic;
}

.image-preview {
  text-align: center;
  padding: 20px;
}

html.dark .diagnosis-content,
html.dark .medical-advice-content {
  background-color: #1e293b;
  color: #e2e8f0;
}
</style>
