<template>
  <div class="content-section">
    <h2>用户管理</h2>
    
    <div style="margin-bottom: 16px">
      <el-button type="primary" @click="showCreateDialog">创建用户</el-button>
    </div>

    <el-table :data="userList" style="width: 100%" v-loading="loading">
      <el-table-column prop="id" label="ID" width="60"></el-table-column>
      <el-table-column prop="username" label="用户名" width="150"></el-table-column>
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
            {{ row.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" align="center">
        <template #default="{ row }">
          <div class="action-buttons">
            <el-button type="primary" size="small" class="table-btn" @click="showEditDialog(row)">编辑</el-button>
            <el-button type="danger" size="small" class="table-btn" @click="handleDelete(row)" :disabled="row.username === currentUsername">
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑用户对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="500px"
      @close="resetForm"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="3-20个字符"
            :disabled="isEdit"
          ></el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password" v-if="!isEdit">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少6个字符"
          ></el-input>
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword" v-if="isEdit">
          <el-input
            v-model="form.newPassword"
            type="password"
            placeholder="留空则不修改密码"
          ></el-input>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" placeholder="选择角色">
            <el-option label="普通用户" value="user"></el-option>
            <el-option label="管理员" value="admin"></el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from '../utils/axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const userList = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const currentUsername = ref(localStorage.getItem('username') || '')

const form = reactive({
  id: null,
  username: '',
  password: '',
  newPassword: '',
  role: 'user'
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度3-20个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少6个字符', trigger: 'blur' }
  ],
  role: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

const dialogTitle = ref('创建用户')

// 格式化时间显示
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

// 加载用户列表
const loadUsers = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/users')
    userList.value = res.data.data
  } catch (err) {
    ElMessage.error('加载用户列表失败: ' + (err.response?.data?.error || err.message))
  } finally {
    loading.value = false
  }
}

// 显示创建对话框
const showCreateDialog = () => {
  isEdit.value = false
  dialogTitle.value = '创建用户'
  dialogVisible.value = true
}

// 显示编辑对话框
const showEditDialog = (row) => {
  isEdit.value = true
  dialogTitle.value = '编辑用户'
  form.id = row.id
  form.username = row.username
  form.role = row.role
  form.password = ''
  form.newPassword = ''
  dialogVisible.value = true
}

// 重置表单
const resetForm = () => {
  if (formRef.value) {
    formRef.value.resetFields()
  }
  form.id = null
  form.username = ''
  form.password = ''
  form.newPassword = ''
  form.role = 'user'
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      if (isEdit.value) {
        // 更新用户
        const updateData = {
          role: form.role
        }
        if (form.newPassword) {
          updateData.password = form.newPassword
        }
        await axios.put(`/api/users/${form.id}`, updateData)
        ElMessage.success('用户更新成功')
      } else {
        // 创建用户
        await axios.post('/api/users', {
          username: form.username,
          password: form.password,
          role: form.role
        })
        ElMessage.success('用户创建成功')
      }
      dialogVisible.value = false
      loadUsers()
    } catch (err) {
      ElMessage.error(err.response?.data?.error || '操作失败')
    } finally {
      submitting.value = false
    }
  })
}

// 删除用户
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${row.username}" 吗？此操作将同时删除该用户的所有检测历史。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await axios.delete(`/api/users/${row.id}`)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.error || '删除失败')
    }
  }
}

onMounted(() => {
  loadUsers()
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

.action-buttons {
  display: flex;
  gap: 8px;
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
