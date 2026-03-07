<template>
  <div class="login-page">
    <!-- 背景层：三种模式随时换 -->
    <div class="bg-layer" :style="bgStyle" />

    <el-card class="login-card">
      <div class="login-header">
        <h1>骨折检测系统</h1>
        <p>医学影像智能分析平台</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        label-position="left"
        label-width="90px"
        @keyup.enter="login"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
            @keyup.enter="login"
          />
        </el-form-item>

        <el-button
          type="primary"
          class="login-btn"
          :loading="loading"
          @click="login"
        >
          登录
        </el-button>
      </el-form>

      <div class="login-tip">
        <p style="margin-bottom: 8px">演示账号：admin / 123456</p>
        <p>
          还没有账号？
          <router-link to="/register">立即注册</router-link>
        </p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/* -------------------- 背景配置 start -------------------- */
import { ref, reactive, computed, onMounted } from 'vue'

/** 想换背景？改这里即可 **/
const bgType = ref('url') // 'gradient' | 'image' | 'url'
const bgGradient = ref('linear-gradient(black, #434343)') // 渐变色
const bgImage = ref('../phebe.png') // 放在 public下的本地图片
const bgUrl = ref('https://gbres.dfcfw.com/Files/iimage/20230526/158094EACFCCA2A0100F941E683BE27A_w2688h1792.jpg') // 网络图
//测试图片 https://images.unsplash.com/photo-1506744038136-46273834b3fb
//https://gbres.dfcfw.com/Files/iimage/20230526/158094EACFCCA2A0100F941E683BE27A_w2688h1792.jpg 医疗效果图

/* 计算属性：根据类型返回对应样式 */
const bgStyle = computed(() => {
  if (bgType.value === 'gradient') return { background: bgGradient.value }
  if (bgType.value === 'image') return { backgroundImage: `url(${bgImage.value})` }
  if (bgType.value === 'url') return { backgroundImage: `url(${bgUrl.value})` }
  return {}
})
/* -------------------- 背景配置 end -------------------- */

/* -------------------- 登录逻辑 start -------------------- */
import { useRouter } from 'vue-router'
import axios from '../utils/axios'
import { ElMessage } from 'element-plus'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

// 页面加载时清除旧登录状态，确保切换用户时状态干净
onMounted(() => {
  const token = localStorage.getItem('token')
  if (token) {
    // 如果已有登录状态，清除它（切换用户场景）
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }
})

const login = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await axios.post('/api/login', {
        username: form.username,
        password: form.password
      })
      if (res.data.success) {
        // 先存储用户信息
        localStorage.setItem('token', 'ok')
        localStorage.setItem('username', res.data.username)
        localStorage.setItem('role', res.data.role || 'user')
        
        ElMessage.success('登录成功')
        
        // 使用 replace 而不是 push，避免浏览器历史记录问题
        // 添加时间戳强制刷新页面，确保状态完全重置
        window.location.replace('/home?t=' + Date.now())
      }
    } catch (err) {
      const msg = err.response?.data?.error || err.message || '登录失败'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  })
}
/* -------------------- 登录逻辑 end -------------------- */
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  overflow: hidden;
}

.bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  background-size: cover;
  background-position: center;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 40px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
  border-radius: 12px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  background: linear-gradient(to right, #667eea, #764ba2);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-header p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

.login-form {
  margin-bottom: 16px;
}

.login-form ::v-deep(.el-form-item) {
  margin-bottom: 12px;
}

.login-btn {
  width: 100%;
  height: 40px;
  font-size: 16px;
  margin-top: 12px;
}

.login-tip {
  text-align: center;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.login-tip p {
  margin: 0;
  color: #999;
  font-size: 12px;
}

.login-tip a {
  color: #667eea;
  text-decoration: none;
}

.login-tip a:hover {
  color: #764ba2;
}
</style>
