<template>
  <div class="content-section">
    <h2>文件管理</h2>
    
    <!-- 操作栏 -->
    <el-row style="margin-bottom: 16px">
      <el-col :span="12">
        <el-upload
          ref="uploadRef"
          action="http://127.0.0.1:5000/api/files/upload"
          :headers="uploadHeaders"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          :show-file-list="false"
          :with-credentials="false"
        >
          <el-button type="primary">
            <el-icon><Upload /></el-icon>
            上传文件
          </el-button>
        </el-upload>
        <span style="margin-left: 12px; color: #909399; font-size: 12px">
          支持: jpg, png, gif, pdf, doc, docx, txt (最大10MB)
        </span>
      </el-col>
    </el-row>

    <!-- 文件列表 -->
    <el-table :data="fileList" style="width: 100%" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="original_name" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column prop="extension" label="类型" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="getFileTypeTag(row.extension)">
            {{ row.extension?.toUpperCase() || 'UNKNOWN' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="size_str" label="大小" width="100" />
      <el-table-column prop="uploader" label="上传者" width="120" />
      <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      <el-table-column label="上传时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" class="table-btn" @click="handleDownload(row)">下载</el-button>
          <el-button type="danger" size="small" class="table-btn" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model="pagination.page"
      :page-size="pagination.per_page"
      :total="pagination.total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next, jumper"
      style="margin-top: 16px; justify-content: flex-end"
      @size-change="handleSizeChange"
      @current-change="handlePageChange"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import axios from '../utils/axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'

const loading = ref(false)
const fileList = ref([])
const uploadRef = ref(null)

const pagination = reactive({
  page: 1,
  per_page: 20,
  total: 0
})

// 上传请求头
const uploadHeaders = computed(() => {
  return {
    'X-Username': localStorage.getItem('username') || ''
  }
})

// 加载文件列表
const loadFiles = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/files', {
      params: {
        page: pagination.page,
        per_page: pagination.per_page
      }
    })
    fileList.value = res.data.data
    pagination.total = res.data.total
  } catch (err) {
    ElMessage.error('加载文件列表失败: ' + (err.response?.data?.error || err.message))
  } finally {
    loading.value = false
  }
}

// 上传前检查
const beforeUpload = (file) => {
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  return true
}

// 上传成功
const handleUploadSuccess = (response) => {
  if (response.success) {
    ElMessage.success('上传成功')
    loadFiles()
  } else {
    ElMessage.error(response.error || '上传失败')
  }
}

// 上传失败
const handleUploadError = (error) => {
  ElMessage.error('上传失败: ' + (error.response?.data?.error || '网络错误'))
}

// 下载文件
const handleDownload = (row) => {
  // 使用a标签下载
  const link = document.createElement('a')
  link.href = `/api/files/download/${row.id}`
  link.download = row.original_name
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 删除文件
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件 "${row.original_name}" 吗？`,
      '确认删除',
      { type: 'warning' }
    )
    
    await axios.delete(`/api/files/${row.id}`)
    ElMessage.success('文件已删除')
    loadFiles()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.error || '删除失败')
    }
  }
}

// 分页大小变化
const handleSizeChange = (size) => {
  pagination.per_page = size
  loadFiles()
}

// 页码变化
const handlePageChange = (page) => {
  pagination.page = page
  loadFiles()
}

// 获取文件类型标签样式
const getFileTypeTag = (ext) => {
  const typeMap = {
    'jpg': 'success',
    'jpeg': 'success',
    'png': 'success',
    'gif': 'success',
    'pdf': 'warning',
    'doc': 'primary',
    'docx': 'primary',
    'txt': 'info'
  }
  return typeMap[ext?.toLowerCase()] || 'info'
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
  loadFiles()
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

/* 暗色模式下的按钮样式 */
html.dark .table-btn.el-button--primary {
  background-color: #1d4ed8 !important;
  border-color: #3b82f6 !important;
  color: #ffffff !important;
}

html.dark .table-btn.el-button--primary:hover {
  background-color: #2563eb !important;
  border-color: #60a5fa !important;
}

html.dark .table-btn.el-button--danger {
  background-color: #b91c1c !important;
  border-color: #ef4444 !important;
  color: #ffffff !important;
}

</style>
