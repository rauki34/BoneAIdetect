<template>
  <div class="register-page">
    <!-- 背景层：与登录页完全同逻辑 -->
    <div class="bg-layer" :style="bgStyle" />

    <el-card class="register-card">
      <div class="register-header">
        <h1>骨折检测系统</h1>
        <p>创建新账号</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="register-form"
        label-position="left"
        label-width="90px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="3-20个字符" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少6个字符"
            show-password
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="password_confirm">
          <el-input
            v-model="form.password_confirm"
            type="password"
            placeholder="再次输入密码"
            show-password
          />
        </el-form-item>

        <el-form-item label="验证码" prop="captcha">
          <el-row :gutter="12">
            <el-col :span="16">
              <el-input
                v-model="form.captcha"
                placeholder="请输入验证码"
                maxlength="4"
                show-word-limit
              />
            </el-col>
            <el-col :span="8">
              <div class="captcha-image">
                <img
                  :src="captchaUrl"
                  @click="refreshCaptcha"
                  alt="验证码"
                  style="cursor: pointer; width: 100%; height: 40px; object-fit: cover;"
                />
              </div>
            </el-col>
          </el-row>
        </el-form-item>

        <el-button
          type="primary"
          class="register-btn"
          :loading="loading"
          @click="register"
        >
          注册
        </el-button>
      </el-form>

      <div class="register-footer">
        <p>已有账号？<router-link to="/login">返回登录</router-link></p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/* -------------------- 背景配置（与登录页完全一致） -------------------- */
import { ref, reactive, computed } from 'vue'

/** 按需要改这里 **/
const bgType = ref('image') // 'gradient' | 'image' | 'url'
const bgGradient = ref('linear-gradient(135deg, #667eea 0%, #764ba2 100%)')
const bgImage = ref('../signup.png') // 本地 public/img 目录
const bgUrl = ref('https://images.unsplash.com/photo-1506744038136-46273834b3fb')

const bgStyle = computed(() => {
  if (bgType.value === 'gradient') return { background: bgGradient.value }
  if (bgType.value === 'image') return { backgroundImage: `url(${bgImage.value})` }
  if (bgType.value === 'url') return { backgroundImage: `url(${bgUrl.value})` }
  return {}
})
/* -------------------- 背景配置结束 -------------------- */

/* -------------------- 注册逻辑（你原来的一样） -------------------- */
import { useRouter } from 'vue-router'
import axios from '../utils/axios'
import { ElMessage } from 'element-plus'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  password_confirm: '',
  captcha: ''
})

const validatePassword = (rule, value, callback) => {
  if (value === '') callback(new Error('请输入密码'))
  else if (value.length < 6) callback(new Error('密码长度至少6个字符'))
  else callback()
}
const validatePassword2 = (rule, value, callback) => {
  if (value === '') callback(new Error('请再次输入密码'))
  else if (value !== form.password) callback(new Error('两次输入密码不一致!'))
  else callback()
}
const validateCaptcha = (rule, value, callback) => {
  if (value === '') callback(new Error('请输入验证码'))
  else if (value.length !== 4) callback(new Error('验证码长度为4个字符'))
  else callback()
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度3-20个字符', trigger: 'blur' }
  ],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  password_confirm: [{ validator: validatePassword2, trigger: 'blur' }],
  captcha: [{ validator: validateCaptcha, trigger: 'blur' }]
}

// 验证码图片 URL - 使用完整路径
const captchaUrl = ref('http://127.0.0.1:5000/api/captcha?' + Date.now())

// 刷新验证码
const refreshCaptcha = () => {
  captchaUrl.value = 'http://127.0.0.1:5000/api/captcha?' + Date.now()
  form.captcha = ''
}

// 页面加载时自动获取验证码
refreshCaptcha()

const register = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await axios.post('/api/register', {
        username: form.username,
        password: form.password,
        password_confirm: form.password_confirm,
        captcha: form.captcha
      })
      if (res.data.success) {
        ElMessage.success('注册成功，请登录')
        setTimeout(() => router.push('/login'), 1000)
      }
    } catch (err) {
      const msg = err.response?.data?.error || err.message || '注册失败'
      ElMessage.error(msg)
      // 验证码错误时刷新验证码
      if (msg.includes('验证码')) {
        refreshCaptcha()
      }
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.register-page {
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

.register-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 40px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
  border-radius: 12px;
}

.register-header {
  text-align: center;
  margin-bottom: 30px;
}

.register-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  background: linear-gradient(to right, #667eea, #764ba2);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.register-header p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

.register-form {
  margin-bottom: 16px;
}

.register-form ::v-deep(.el-form-item) {
  margin-bottom: 12px;
}

.register-btn {
  width: 100%;
  height: 40px;
  font-size: 16px;
  margin-top: 12px;
}

.register-footer {
  text-align: center;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.register-footer p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

.register-footer a {
  color: #667eea;
  text-decoration: none;
}

.register-footer a:hover {
  color: #764ba2;
}

.captcha-image {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid #dcdfe6;
}

.captcha-image img {
  transition: filter 0.3s;
}

.captcha-image img:hover {
  filter: brightness(0.9);
}
</style>