<template>
  <div class="patient-report-list">
    <!-- 筛选和视图切换 -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-header">
        <h3>我的检测报告</h3>
        <div class="filter-actions">
          <el-radio-group v-model="viewMode" size="small">
            <el-radio-button label="card">
              <el-icon><Grid /></el-icon>
              卡片
            </el-radio-button>
            <el-radio-button label="table">
              <el-icon><List /></el-icon>
              列表
            </el-radio-button>
          </el-radio-group>
          <el-button type="text" @click="loadReports" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 卡片视图 -->
    <div v-if="viewMode === 'card'" class="card-view">
      <el-row :gutter="20" v-loading="loading">
        <el-col
          v-for="report in reports"
          :key="report.id"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <el-card class="report-card" shadow="hover" @click="handleViewDetail(report)">
            <div class="report-card-header">
              <el-tag type="primary" size="small">报告 #{{ report.id }}</el-tag>
              <el-icon class="view-icon"><View /></el-icon>
            </div>
            
            <div class="report-card-body">
              <div class="report-info-item">
                <el-icon class="info-icon"><UserFilled /></el-icon>
                <span class="info-label">医生:</span>
                <span class="info-value">{{ report.doctor_name || '未指定' }}</span>
              </div>
              
              <div class="report-info-item">
                <el-icon class="info-icon"><Clock /></el-icon>
                <span class="info-label">时间:</span>
                <span class="info-value">{{ formatDate(report.timestamp) }}</span>
              </div>
              
              <div class="report-detections">
                <el-tag
                  v-for="(detection, index) in report.detections.slice(0, 2)"
                  :key="index"
                  size="small"
                  type="warning"
                  effect="plain"
                >
                  {{ detection.class }}
                </el-tag>
                <el-tag v-if="report.detections.length > 2" size="small" type="info">
                  +{{ report.detections.length - 2 }}
                </el-tag>
              </div>
              
              <div v-if="report.diagnosis" class="report-diagnosis">
                <el-text line-clamp="2" class="diagnosis-text">
                  {{ report.diagnosis }}
                </el-text>
              </div>
              <div v-else class="report-diagnosis empty">
                <el-text type="info">暂无诊断</el-text>
              </div>
            </div>
            
            <div class="report-card-footer">
              <el-button
                type="primary"
                size="small"
                :loading="loadingReportId === report.id"
                @click.stop="handleViewDetail(report)"
              >
                查看详情
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
      
      <el-empty v-if="!loading && reports.length === 0" description="暂无报告数据" />
    </div>

    <!-- 表格视图 (原有的) -->
    <el-card v-else class="list-card" shadow="never">
      <el-table
        v-loading="loading"
        :data="reports"
        style="width: 100%"
        stripe
      >
        <el-table-column prop="id" label="报告ID" width="80" />
        
        <el-table-column label="医生姓名" width="150">
          <template #default="{ row }">
            {{ row.doctor_name || '未指定' }}
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
        
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              :loading="loadingReportId === row.id"
              @click="handleViewDetail(row)"
            >
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-empty v-if="!loading && reports.length === 0" description="暂无报告数据" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from '../utils/axios'
import { formatDate, formatDateTime } from '../utils/datetime'
import { ElMessage } from 'element-plus'
import { Refresh, Grid, List, View, UserFilled, Clock } from '@element-plus/icons-vue'

const emit = defineEmits(['view-detail'])

const loading = ref(false)
const reports = ref([])
const loadingReportId = ref(null)
const viewMode = ref('card') // 'card' or 'table'

// 加载报告列表
const loadReports = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/patient/reports')
    reports.value = response.data.data || []
  } catch (error) {
    console.error('加载报告列表失败:', error)
    ElMessage.error('加载报告列表失败')
  } finally {
    loading.value = false
  }
}

// 查看报告详情
const handleViewDetail = (report) => {
  loadingReportId.value = report.id
  // 模拟加载延迟以显示反馈
  setTimeout(() => {
    loadingReportId.value = null
    emit('view-detail', report)
  }, 100)
}

// 初始化加载
onMounted(() => {
  loadReports()
})

// 暴露方法供父组件调用
defineExpose({
  loadReports
})
</script>

<style scoped>
.patient-report-list {
  padding: var(--spacing-xl);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-base);
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.filter-actions {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
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

/* 卡片视图样式 */
.card-view {
  margin-top: var(--spacing-xl);
}

.report-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-fast);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.report-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.report-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.view-icon {
  font-size: 20px;
  color: var(--text-secondary);
  transition: color var(--transition-fast);
}

.report-card:hover .view-icon {
  color: var(--primary);
}

.report-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.report-info-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 14px;
}

.info-icon {
  color: var(--primary);
  font-size: 16px;
}

.info-label {
  color: var(--text-secondary);
  min-width: 40px;
}

.info-value {
  color: var(--text-primary);
  font-weight: 500;
}

.report-detections {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) 0;
}

.report-diagnosis {
  padding: var(--spacing-sm);
  background-color: var(--bg-secondary);
  border-radius: var(--radius-sm);
  min-height: 50px;
  display: flex;
  align-items: center;
}

.report-diagnosis.empty {
  justify-content: center;
}

.diagnosis-text {
  font-size: 13px;
  color: var(--text-regular);
  line-height: 1.6;
}

.report-card-footer {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-lighter);
  display: flex;
  justify-content: flex-end;
}

/* 响应式 */
@media (max-width: 768px) {
  .patient-report-list {
    padding: var(--spacing-md);
  }
  
  .filter-header {
    flex-direction: column;
    gap: var(--spacing-md);
    align-items: flex-start;
  }
  
  .report-card {
    margin-bottom: var(--spacing-md);
  }
}
</style>
