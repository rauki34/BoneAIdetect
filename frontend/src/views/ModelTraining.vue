<template>
  <div class="model-training-container">
    <!-- 训练新模型 -->
    <el-card class="training-card">
      <template #header>
        <div class="card-header">
          <span>训练新模型</span>
        </div>
      </template>

      <el-form :model="trainingForm" label-width="120px" ref="trainingFormRef">
        <el-form-item label="模型名称" required>
          <el-input v-model="trainingForm.name" placeholder="输入模型名称" />
        </el-form-item>

        <el-form-item label="模型描述">
          <el-input v-model="trainingForm.description" type="textarea" :rows="2" placeholder="输入模型描述" />
        </el-form-item>

        <el-form-item label="基础模型" required>
          <el-select v-model="trainingForm.base_model" placeholder="选择基础模型" style="width: 350px">
            <el-option-group label="预训练模型">
              <el-option label="YOLOv8" value="yolov8" />
              <el-option label="YOLOv11" value="yolo11" />
              <el-option label="YOLOv12" value="yolo12" />
            </el-option-group>
            <el-option-group label="CBAM优化模型 (推荐用于骨折检测)">
              <el-option label="YOLOv8-CBAM (注意力优化)" value="yolov8-cbam">
                <span style="display: flex; align-items: center; gap: 8px;">
                  <el-tag size="small" type="success" effect="dark">NEW</el-tag>
                  <span>YOLOv8-CBAM (注意力优化)</span>
                  <el-tooltip content="集成CBAM注意力机制，提升骨折区域检测精度">
                    <el-icon><Info-Filled /></el-icon>
                  </el-tooltip>
                </span>
              </el-option>
              <el-option label="YOLO11-CBAM (注意力优化)" value="yolo11-cbam">
                <span style="display: flex; align-items: center; gap: 8px;">
                  <el-tag size="small" type="success" effect="dark">NEW</el-tag>
                  <span>YOLO11-CBAM (注意力优化)</span>
                  <el-tooltip content="集成CBAM注意力机制，提升骨折区域检测精度">
                    <el-icon><Info-Filled /></el-icon>
                  </el-tooltip>
                </span>
              </el-option>
            </el-option-group>
            <el-option-group label="自定义模型" v-if="availableCustomModels.length > 0">
              <el-option
                v-for="m in availableCustomModels"
                :key="m.model_key"
                :label="`${m.name} (${m.base_model}, mAP50: ${(m.map50 * 100).toFixed(1)}%)`"
                :value="m.model_key"
              />
            </el-option-group>
          </el-select>
          <div class="el-form-item__tip" v-if="isContinuedTraining">
            已选择自定义模型进行续训，将在已有模型基础上继续训练
          </div>
          <div class="el-form-item__tip" v-else-if="isCBAMModel" style="color: #67c23a;">
            <el-icon><Circle-Check /></el-icon>
            使用CBAM注意力机制优化，可提升骨折检测精度 2-3%
          </div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="训练轮数">
              <el-input-number v-model="trainingForm.epochs" :min="10" :max="500" :step="10" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="批次大小">
              <el-input-number v-model="trainingForm.batch_size" :min="1" :max="64" :step="1" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="图像尺寸">
              <el-select v-model="trainingForm.img_size">
                <el-option label="640x640" :value="640" />
                <el-option label="416x416" :value="416" />
                <el-option label="320x320" :value="320" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="数据集" required>
          <el-upload
            ref="uploadRef"
            action=""
            :auto-upload="false"
            :on-change="onDatasetChange"
            :limit="1"
            accept=".zip"
          >
            <el-button type="primary">
              <el-icon><Upload /></el-icon>
              选择数据集(.zip)
            </el-button>
            <template #tip>
              <div class="el-upload__tip">
                请上传包含 data.yaml 的 ZIP 格式数据集，文件大小不超过 500MB
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item>
          <el-button type="success" @click="startTraining" :loading="isTraining" :disabled="!canStartTraining">
            <el-icon><VideoPlay /></el-icon>
            开始训练
          </el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 训练任务列表 -->
    <el-card class="tasks-card">
      <template #header>
        <div class="card-header">
          <span>训练任务</span>
          <el-button type="primary" text @click="loadTasks">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="trainingTasks" style="width: 100%">
        <el-table-column prop="task_name" label="任务名称" min-width="150" />
        <el-table-column prop="model_name" label="模型" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round(row.progress)"
              :status="row.status === 'failed' ? 'exception' : ''"
            />
          </template>
        </el-table-column>
        <el-table-column prop="current_epoch" label="轮数" width="100">
          <template #default="{ row }">
            {{ row.current_epoch }} / {{ row.total_epochs }}
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建者" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click="viewTaskDetail(row)">
              详情
            </el-button>
            <el-button type="info" size="small" text @click="viewLogs(row)" v-if="row.log_file">
              日志
            </el-button>
            <el-button
              type="danger"
              size="small"
              text
              @click="stopTraining(row)"
              v-if="row.status === 'running'"
            >
              终止
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 模型列表 -->
    <el-card class="models-card">
      <template #header>
        <div class="card-header">
          <span>模型管理</span>
          <div>
            <el-radio-group v-model="modelFilter" size="small">
              <el-radio-button label="all">全部</el-radio-button>
              <el-radio-button label="system">系统模型</el-radio-button>
              <el-radio-button label="custom">自定义模型</el-radio-button>
            </el-radio-group>
            <el-button type="primary" text @click="loadModels" style="margin-left: 12px;">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="filteredModels" style="width: 100%">
        <el-table-column prop="name" label="模型名称" min-width="150" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type === 'system' ? 'info' : 'success'">
              {{ row.type === 'system' ? '系统' : '自定义' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="base_model" label="基础模型" width="100" v-if="modelFilter !== 'system'" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getModelStatusType(row.status)">
              {{ getModelStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="map50" label="mAP@0.5" width="100">
          <template #default="{ row }">
            {{ row.map50 ? (row.map50 * 100).toFixed(2) + '%' : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建者" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              text
              @click="viewModelDetail(row)"
            >
              详情
            </el-button>
            <template v-if="row.type === 'custom' && isAdmin">
              <el-button
                v-if="row.status === 'trained'"
                type="success"
                size="small"
                text
                @click="publishModel(row)"
              >
                发布
              </el-button>
              <el-button
                v-if="row.status === 'published'"
                type="warning"
                size="small"
                text
                @click="disableModel(row)"
              >
                禁用
              </el-button>
              <el-button
                v-if="row.status === 'disabled'"
                type="primary"
                size="small"
                text
                @click="enableModel(row)"
              >
                启用
              </el-button>
              <el-button
                v-if="row.status !== 'training'"
                type="danger"
                size="small"
                text
                @click="deleteModel(row)"
              >
                删除
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="taskDetailVisible" title="训练任务详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedTask">
        <el-descriptions-item label="任务名称">{{ selectedTask.task_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedTask.status)">
            {{ getStatusText(selectedTask.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="当前轮数">{{ selectedTask.current_epoch }} / {{ selectedTask.total_epochs }}</el-descriptions-item>
        <el-descriptions-item label="进度">{{ selectedTask.progress?.toFixed(2) }}%</el-descriptions-item>
        <el-descriptions-item label="损失">{{ selectedTask.loss?.toFixed(4) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="验证损失">{{ selectedTask.val_loss?.toFixed(4) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建者">{{ selectedTask.created_by }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ selectedTask.created_at }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ selectedTask.started_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ selectedTask.completed_at || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="selectedTask?.error_message" class="error-message">
        <el-alert :title="selectedTask.error_message" type="error" :closable="false" />
      </div>
    </el-dialog>

    <!-- 训练日志对话框 -->
    <el-dialog v-model="logsVisible" title="训练日志" width="800px">
      <pre class="log-content">{{ trainingLogs }}</pre>
    </el-dialog>

    <!-- 模型详情对话框 -->
    <el-dialog v-model="modelDetailVisible" title="模型性能详情" width="700px">
      <el-descriptions :column="2" border v-if="selectedModel">
        <el-descriptions-item label="模型名称">{{ selectedModel.name }}</el-descriptions-item>
        <el-descriptions-item label="模型标识">{{ selectedModel.model_key }}</el-descriptions-item>
        <el-descriptions-item label="基础模型">{{ selectedModel.base_model }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getModelStatusType(selectedModel.status)">
            {{ getModelStatusText(selectedModel.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="训练轮数">{{ selectedModel.epochs }}</el-descriptions-item>
        <el-descriptions-item label="批次大小">{{ selectedModel.batch_size }}</el-descriptions-item>
        <el-descriptions-item label="图像尺寸">{{ selectedModel.img_size }}x{{ selectedModel.img_size }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">性能指标</el-divider>

      <el-row :gutter="20" v-if="selectedModel && (selectedModel.map50 || selectedModel.map50_95)">
        <el-col :span="8">
          <el-card class="metric-card">
            <div class="metric-value">{{ selectedModel.map50 ? (selectedModel.map50 * 100).toFixed(2) + '%' : '-' }}</div>
            <div class="metric-label">mAP@0.5</div>
            <el-progress
              :percentage="selectedModel.map50 ? selectedModel.map50 * 100 : 0"
              :color="getMetricColor(selectedModel.map50)"
              :stroke-width="8"
            />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card class="metric-card">
            <div class="metric-value">{{ selectedModel.map50_95 ? (selectedModel.map50_95 * 100).toFixed(2) + '%' : '-' }}</div>
            <div class="metric-label">mAP@0.5:0.95</div>
            <el-progress
              :percentage="selectedModel.map50_95 ? selectedModel.map50_95 * 100 : 0"
              :color="getMetricColor(selectedModel.map50_95)"
              :stroke-width="8"
            />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card class="metric-card">
            <div class="metric-value">{{ selectedModel.accuracy ? (selectedModel.accuracy * 100).toFixed(2) + '%' : '-' }}</div>
            <div class="metric-label">准确率</div>
            <el-progress
              :percentage="selectedModel.accuracy ? selectedModel.accuracy * 100 : 0"
              :color="getMetricColor(selectedModel.accuracy)"
              :stroke-width="8"
            />
          </el-card>
        </el-col>
      </el-row>

      <el-empty v-else description="暂无性能指标数据" />

      <el-divider content-position="left">模型说明</el-divider>
      <p>{{ selectedModel?.description || '无描述' }}</p>

      <template #footer>
        <el-button @click="modelDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import axios from '../utils/axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, VideoPlay, Refresh, InfoFilled, CircleCheck } from '@element-plus/icons-vue'

const props = defineProps({
  isAdmin: Boolean
})

/* 响应式变量 */
const trainingFormRef = ref(null)
const uploadRef = ref(null)
const isTraining = ref(false)
const modelFilter = ref('all')
const trainingTasks = ref([])
const models = ref({ system_models: [], custom_models: [] })
const trainingLogs = ref('')
const taskDetailVisible = ref(false)
const logsVisible = ref(false)
const modelDetailVisible = ref(false)
const selectedTask = ref(null)
const selectedModel = ref(null)
const progressTimer = ref(null)

/* 训练表单 */
const trainingForm = reactive({
  name: '',
  description: '',
  base_model: 'yolov8',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  dataset: null
})

/* 计算属性 */
const canStartTraining = computed(() => {
  return trainingForm.name && trainingForm.dataset && !isTraining.value
})

// 可用于续训的自定义模型（已训练或已发布的模型）
const availableCustomModels = computed(() => {
  return models.value.custom_models?.filter(m =>
    m.status === 'trained' || m.status === 'published'
  ) || []
})

// 判断是否选择了续训
const isContinuedTraining = computed(() => {
  const baseModels = ['yolov8', 'yolo11', 'yolo12', 'yolov8-cbam', 'yolo11-cbam']
  return trainingForm.base_model && !baseModels.includes(trainingForm.base_model)
})

// 判断是否选择了CBAM模型
const isCBAMModel = computed(() => {
  return trainingForm.base_model && trainingForm.base_model.includes('cbam')
})

const filteredModels = computed(() => {
  let result = []
  if (modelFilter.value === 'all' || modelFilter.value === 'system') {
    result = [...result, ...models.value.system_models]
  }
  if (modelFilter.value === 'all' || modelFilter.value === 'custom') {
    result = [...result, ...models.value.custom_models]
  }
  return result
})

/* 加载数据 */
onMounted(() => {
  loadModels()
  loadTasks()
  // 启动定时刷新
  startProgressTimer()
})

onUnmounted(() => {
  // 清除定时器
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
  }
})

/* 启动进度定时刷新 */
function startProgressTimer() {
  // 每 3 秒刷新一次训练进度
  progressTimer.value = setInterval(async () => {
    const runningTasks = trainingTasks.value.filter(t => t.status === 'running')
    if (runningTasks.length > 0) {
      await refreshTasksProgress(runningTasks)
    }
  }, 3000)
}

/* 刷新任务进度 */
async function refreshTasksProgress(tasks) {
  try {
    for (const task of tasks) {
      const res = await axios.get(`/api/training/tasks/${task.id}/progress`)
      const progressData = res.data
      
      // 更新任务数据
      const index = trainingTasks.value.findIndex(t => t.id === task.id)
      if (index !== -1) {
        trainingTasks.value[index] = {
          ...trainingTasks.value[index],
          ...progressData
        }
      }
    }
  } catch (err) {
    console.error('刷新进度失败:', err)
  }
}

async function loadModels() {
  try {
    const res = await axios.get('/api/models')
    models.value = res.data
  } catch (err) {
    ElMessage.error('加载模型列表失败')
  }
}

async function loadTasks() {
  try {
    const res = await axios.get('/api/training/tasks')
    trainingTasks.value = res.data.tasks
  } catch (err) {
    ElMessage.error('加载训练任务失败')
  }
}

/* 数据集上传 */
function onDatasetChange(file) {
  trainingForm.dataset = file.raw
}

/* 开始训练 */
async function startTraining() {
  if (!trainingForm.name) {
    ElMessage.warning('请输入模型名称')
    return
  }
  if (!trainingForm.dataset) {
    ElMessage.warning('请上传数据集')
    return
  }

  isTraining.value = true

  try {
    const formData = new FormData()
    formData.append('dataset', trainingForm.dataset)
    formData.append('name', trainingForm.name)
    formData.append('description', trainingForm.description)
    formData.append('base_model', trainingForm.base_model)
    formData.append('epochs', trainingForm.epochs)
    formData.append('batch_size', trainingForm.batch_size)
    formData.append('img_size', trainingForm.img_size)

    const res = await axios.post('/api/models/train', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.data.success) {
      ElMessage.success('训练任务已启动')
      resetForm()
      loadTasks()
    }
  } catch (err) {
    ElMessage.error('启动训练失败: ' + (err.response?.data?.error || err.message))
  } finally {
    isTraining.value = false
  }
}

/* 重置表单 */
function resetForm() {
  trainingForm.name = ''
  trainingForm.description = ''
  trainingForm.base_model = 'yolov8'
  trainingForm.epochs = 100
  trainingForm.batch_size = 16
  trainingForm.img_size = 640
  trainingForm.dataset = null
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

/* 查看任务详情 */
function viewTaskDetail(task) {
  selectedTask.value = task
  taskDetailVisible.value = true
}

/* 查看日志 */
async function viewLogs(task) {
  try {
    const res = await axios.get(`/api/training/tasks/${task.id}/logs`)
    trainingLogs.value = res.data.logs || '暂无日志'
    logsVisible.value = true
  } catch (err) {
    ElMessage.error('加载日志失败')
  }
}

/* 终止训练 */
async function stopTraining(task) {
  try {
    await ElMessageBox.confirm(
      '确定要终止此训练任务吗？终止后无法恢复',
      '确认终止',
      {
        confirmButtonText: '确定终止',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await axios.post(`/api/training/tasks/${task.id}/stop`)
    ElMessage.success('训练任务已终止')
    loadTasks()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('终止失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

/* 发布模型 */
async function publishModel(model) {
  try {
    await ElMessageBox.confirm('确定要发布此模型吗？发布后可用于检测', '确认发布', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await axios.post(`/api/models/${model.id}/publish`)
    ElMessage.success('模型已发布')
    loadModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('发布失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

/* 禁用模型 */
async function disableModel(model) {
  try {
    await ElMessageBox.confirm('确定要禁用此模型吗？禁用后无法用于检测', '确认禁用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await axios.post(`/api/models/${model.id}/disable`)
    ElMessage.success('模型已禁用')
    loadModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('禁用失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

/* 启用模型 */
async function enableModel(model) {
  try {
    await ElMessageBox.confirm('确定要启用此模型吗？启用后可用于检测', '确认启用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'primary'
    })

    await axios.post(`/api/models/${model.id}/enable`)
    ElMessage.success('模型已启用')
    loadModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('启用失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

/* 删除模型 */
async function deleteModel(model) {
  try {
    await ElMessageBox.confirm('确定要删除此模型吗？此操作不可恢复', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'danger'
    })

    await axios.delete(`/api/models/${model.id}`)
    ElMessage.success('模型已删除')
    loadModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

/* 查看模型详情 */
function viewModelDetail(model) {
  selectedModel.value = model
  modelDetailVisible.value = true
}

/* 根据指标值获取颜色 */
function getMetricColor(value) {
  if (!value) return '#909399'
  if (value >= 0.8) return '#67c23a'
  if (value >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

/* 状态转换函数 */
function getStatusType(status) {
  const map = {
    'pending': 'info',
    'running': 'primary',
    'completed': 'success',
    'failed': 'danger',
    'stopped': 'warning'
  }
  return map[status] || 'info'
}

function getStatusText(status) {
  const map = {
    'pending': '等待中',
    'running': '训练中',
    'completed': '已完成',
    'failed': '失败',
    'stopped': '已终止'
  }
  return map[status] || status
}

function getModelStatusType(status) {
  const map = {
    'training': 'warning',
    'trained': 'success',
    'published': 'primary',
    'disabled': 'info'
  }
  return map[status] || 'info'
}

function getModelStatusText(status) {
  const map = {
    'training': '训练中',
    'trained': '已训练',
    'published': '已发布',
    'disabled': '已禁用'
  }
  return map[status] || status
}
</script>

<style scoped>
.model-training-container {
  padding: 16px;
}

.training-card,
.tasks-card,
.models-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.el-upload__tip {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}

.error-message {
  margin-top: 16px;
}

.log-content {
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 4px;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.metric-card {
  text-align: center;
  padding: 16px;
}

.metric-value {
  font-size: 28px;
  font-weight: bold;
  color: #4f6ef7;
  margin-bottom: 8px;
}

.metric-label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 12px;
}
</style>
