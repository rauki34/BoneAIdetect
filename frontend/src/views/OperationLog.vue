<template>
  <div class="content-section">
    <h2>操作日志</h2>
    
    <!-- 搜索栏 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6">
        <el-input
          v-model="searchForm.username"
          placeholder="用户名"
          clearable
          @keyup.enter="handleSearch"
        />
      </el-col>
      <el-col :span="4">
        <el-select v-model="searchForm.method" placeholder="请求方法" clearable style="width: 100%">
          <el-option label="GET" value="GET" />
          <el-option label="POST" value="POST" />
          <el-option label="PUT" value="PUT" />
          <el-option label="DELETE" value="DELETE" />
        </el-select>
      </el-col>
      <el-col :span="6">
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="resetSearch">重置</el-button>
      </el-col>
      <el-col :span="8" style="text-align: right">
        <el-button type="danger" @click="handleClearAll">清空所有日志</el-button>
      </el-col>
    </el-row>

    <!-- 日志表格 -->
    <el-table :data="logList" style="width: 100%" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="method" label="方法" width="80">
        <template #default="{ row }">
          <el-tag :type="getMethodType(row.method)" size="small">
            {{ row.method }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="url" label="请求路径" min-width="200" show-overflow-tooltip />
      <el-table-column prop="description" label="操作描述" min-width="150" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP地址" width="130" />
      <el-table-column prop="success" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.success ? 'success' : 'danger'" size="small">
            {{ row.success ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.timestamp) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="danger" size="small" class="table-btn" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model="pagination.page"
      :page-size="pagination.per_page"
      :total="pagination.total"
      :page-sizes="[10, 20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      style="margin-top: 16px; justify-content: flex-end"
      @size-change="handleSizeChange"
      @current-change="handlePageChange"
    />

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="日志详情" width="600px">
      <el-descriptions :column="1" border v-if="currentLog">
        <el-descriptions-item label="ID">{{ currentLog.id }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ currentLog.username }}</el-descriptions-item>
        <el-descriptions-item label="请求方法">
          <el-tag :type="getMethodType(currentLog.method)">{{ currentLog.method }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="请求路径">{{ currentLog.url }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ currentLog.ip }}</el-descriptions-item>
        <el-descriptions-item label="User-Agent">{{ currentLog.user_agent }}</el-descriptions-item>
        <el-descriptions-item label="操作描述">{{ currentLog.description || '-' }}</el-descriptions-item>
        <el-descriptions-item label="执行状态">
          <el-tag :type="currentLog.success ? 'success' : 'danger'">
            {{ currentLog.success ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="!currentLog.success && currentLog.error_msg">
          <span style="color: #f56c6c">{{ currentLog.error_msg }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="操作时间">{{ formatTime(currentLog.timestamp) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from '../utils/axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const logList = ref([])
const detailVisible = ref(false)
const currentLog = ref(null)

const searchForm = reactive({
  username: '',
  method: ''
})

const pagination = reactive({
  page: 1,
  per_page: 20,
  total: 0
})

// 获取日志列表
const loadLogs = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      per_page: pagination.per_page,
      ...searchForm
    }
    const res = await axios.get('/api/logs', { params })
    logList.value = res.data.data
    pagination.total = res.data.total
  } catch (err) {
    ElMessage.error('加载日志失败: ' + (err.response?.data?.error || err.message))
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadLogs()
}

// 重置搜索
const resetSearch = () => {
  searchForm.username = ''
  searchForm.method = ''
  pagination.page = 1
  loadLogs()
}

// 删除单条日志
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这条日志吗？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await axios.delete(`/api/logs/${row.id}`)
    ElMessage.success('日志已删除')
    loadLogs()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.error || '删除失败')
    }
  }
}

// 清空所有日志
const handleClearAll = async () => {
  try {
    await ElMessageBox.confirm('确定要清空所有日志吗？此操作不可恢复！', '确认清空', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'danger'
    })
    
    const res = await axios.delete('/api/logs/clear')
    ElMessage.success(res.data.message)
    loadLogs()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.error || '清空失败')
    }
  }
}

// 查看详情
const showDetail = (row) => {
  currentLog.value = row
  detailVisible.value = true
}

// 分页大小变化
const handleSizeChange = (size) => {
  pagination.per_page = size
  loadLogs()
}

// 页码变化
const handlePageChange = (page) => {
  pagination.page = page
  loadLogs()
}

// 获取请求方法对应的标签类型
const getMethodType = (method) => {
  const types = {
    'GET': 'info',
    'POST': 'success',
    'PUT': 'warning',
    'DELETE': 'danger'
  }
  return types[method] || 'info'
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
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

onMounted(() => {
  loadLogs()
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

</style>
