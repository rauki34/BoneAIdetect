<template>
  <div class="doctor-report-list">
    <!-- 筛选区域 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="filters">
        <el-form-item label="患者">
          <PatientSelector
            v-model="filters.patient_id"
            style="width: 250px"
            @change="handleFilterChange"
          />
        </el-form-item>
        
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateRangeChange"
            style="width: 300px"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="loadReports">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 报告列表 -->
    <el-card class="list-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>报告列表</span>
          <el-button type="text" @click="loadReports">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      
      <el-table
        v-loading="loading"
        :data="reports"
        style="width: 100%"
        stripe
      >
        <el-table-column prop="id" label="报告ID" width="80" />
        
        <el-table-column label="患者姓名" width="120">
          <template #default="{ row }">
            {{ row.patient_name || '未关联' }}
          </template>
        </el-table-column>
        
        <el-table-column label="检测时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.timestamp) }}
          </template>
        </el-table-column>
        
        <el-table-column label="检测结果" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="(detection, index) in row.detections.slice(0, 3)"
              :key="index"
              size="small"
              style="margin-right: 4px;"
            >
              {{ detection.class }}
            </el-tag>
            <el-tag v-if="row.detections.length > 3" size="small" type="info">
              +{{ row.detections.length - 3 }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="诊断" min-width="200">
          <template #default="{ row }">
            <el-text v-if="row.diagnosis" line-clamp="2">
              {{ row.diagnosis }}
            </el-text>
            <el-text v-else type="info">未填写</el-text>
          </template>
        </el-table-column>
        
        <el-table-column label="最后修改" width="180">
          <template #default="{ row }">
            {{ row.updated_at ? formatDateTime(row.updated_at) : '-' }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              type="info"
              size="small"
              @click="handleView(row)"
            >
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-empty v-if="!loading && reports.length === 0" description="暂无报告数据" />
    </el-card>

    <!-- 报告编辑对话框 -->
    <ReportEditor
      v-model="editorVisible"
      :report="currentReport"
      @success="handleEditSuccess"
    />

    <!-- 报告详情对话框 -->
    <el-dialog
      v-model="viewDialogVisible"
      title="报告详情"
      width="900px"
    >
      <div v-if="currentReport" class="report-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="报告ID">
            {{ currentReport.id }}
          </el-descriptions-item>
          <el-descriptions-item label="患者姓名">
            {{ currentReport.patient_name || '未关联' }}
          </el-descriptions-item>
          <el-descriptions-item label="检测时间">
            {{ formatDateTime(currentReport.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="医生">
            {{ currentReport.username }}
          </el-descriptions-item>
          <el-descriptions-item label="检测模型">
            {{ currentReport.model }}
          </el-descriptions-item>
          <el-descriptions-item label="最后修改">
            {{ currentReport.updated_at ? formatDateTime(currentReport.updated_at) : '-' }}
          </el-descriptions-item>
        </el-descriptions>
        
        <el-divider content-position="left">检测结果</el-divider>
        <div class="detection-results">
          <el-tag
            v-for="(detection, index) in currentReport.detections"
            :key="index"
            size="large"
            style="margin-right: 8px; margin-bottom: 8px;"
          >
            {{ detection.class }} - 置信度: {{ (detection.confidence * 100).toFixed(1) }}%
          </el-tag>
        </div>
        
        <el-divider content-position="left">诊断结论</el-divider>
        <div class="diagnosis-content">
          {{ currentReport.diagnosis || '未填写' }}
        </div>
        
        <el-divider content-position="left">随访备注</el-divider>
        <div class="follow-up-content">
          {{ currentReport.follow_up_notes || '未填写' }}
        </div>
        
        <el-divider content-position="left">检测图像</el-divider>
        <div class="image-preview">
          <el-image
            v-if="currentReport.result_image"
            :src="currentReport.result_image"
            fit="contain"
            :preview-src-list="[currentReport.result_image]"
            style="max-width: 100%; max-height: 500px;"
          />
        </div>
      </div>
      
      <template #footer>
        <el-button @click="viewDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="handleEditFromView">编辑报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as doctorApi from '../api/doctor'
import { formatDateTime } from '../utils/datetime'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PatientSelector from './PatientSelector.vue'
import ReportEditor from './ReportEditor.vue'

const loading = ref(false)
const reports = ref([])
const filters = ref({
  patient_id: null,
  date_from: null,
  date_to: null
})
const dateRange = ref([])

const editorVisible = ref(false)
const viewDialogVisible = ref(false)
const currentReport = ref(null)

// 加载报告列表
const loadReports = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.patient_id) {
      params.patient_id = filters.value.patient_id
    }
    if (filters.value.date_from) {
      params.date_from = filters.value.date_from
    }
    if (filters.value.date_to) {
      params.date_to = filters.value.date_to
    }
    
    const response = await doctorApi.reports(params)
    reports.value = response.data.data || []
  } catch (error) {
    console.error('加载报告列表失败:', error)
    ElMessage.error('加载报告列表失败')
  } finally {
    loading.value = false
  }
}

// 处理筛选变化
const handleFilterChange = () => {
  // 自动触发查询可以在这里实现
}

// 处理日期范围变化
const handleDateRangeChange = (value) => {
  if (value && value.length === 2) {
    filters.value.date_from = value[0]
    filters.value.date_to = value[1]
  } else {
    filters.value.date_from = null
    filters.value.date_to = null
  }
}

// 重置筛选
const resetFilters = () => {
  filters.value = {
    patient_id: null,
    date_from: null,
    date_to: null
  }
  dateRange.value = []
  loadReports()
}

// 编辑报告
const handleEdit = (report) => {
  currentReport.value = report
  editorVisible.value = true
}

// 查看报告
const handleView = (report) => {
  currentReport.value = report
  viewDialogVisible.value = true
}

// 从查看对话框打开编辑
const handleEditFromView = () => {
  viewDialogVisible.value = false
  editorVisible.value = true
}

// 编辑成功回调
const handleEditSuccess = () => {
  loadReports()
}

// 初始化加载
onMounted(() => {
  loadReports()
})
</script>

<style scoped>
.doctor-report-list {
  padding: var(--spacing-xl);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-base);
}

.list-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-base);
  transition: box-shadow var(--transition-base);
}

.list-card:hover {
  box-shadow: var(--shadow-lg);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.report-detail {
  padding: var(--spacing-md);
}

.detection-results {
  padding: var(--spacing-md) 0;
}

.diagnosis-content,
.follow-up-content {
  padding: var(--spacing-md);
  background-color: var(--bg-secondary);
  border-radius: var(--radius-sm);
  min-height: 60px;
  white-space: pre-wrap;
  word-wrap: break-word;
  transition: background-color var(--transition-base);
}

.image-preview {
  text-align: center;
  padding: var(--spacing-xl);
}

html.dark .diagnosis-content,
html.dark .follow-up-content {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
}
</style>
