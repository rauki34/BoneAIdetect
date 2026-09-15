<template>
  <div class="smart-ortho-login">
    <!-- 背景动画 -->
    <div class="bg-animation">
      <div class="bone-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <!-- 主容器 -->
    <div class="main-container">
      <!-- 左侧品牌区 -->
      <div class="brand-section">
        <div class="brand-content">
          <div class="logo">
            <el-icon size="64" color="#fff"><FirstAidKit /></el-icon>
          </div>
          <h1 class="system-title">智慧骨科云平台</h1>
          <p class="system-subtitle">Smart Orthopedics Cloud Platform</p>
          <div class="features">
            <div class="feature-item">
              <el-icon><Check /></el-icon>
              <span>AI智能诊断</span>
            </div>
            <div class="feature-item">
              <el-icon><Check /></el-icon>
              <span>精准骨折检测</span>
            </div>
            <div class="feature-item">
              <el-icon><Check /></el-icon>
              <span>全流程病历管理</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧登录区 -->
      <div class="login-section">
        <!-- 入口选择 -->
        <div v-if="!selectedPortal" class="portal-selection">
          <h2 class="portal-title">请选择登录入口</h2>
          <p class="portal-subtitle">请选择您的身份以进入相应的服务平台</p>
          
          <div class="portal-cards">
            <!-- 患者入口 -->
            <div class="portal-card patient" @click="selectPortal('patient')">
              <div class="card-icon">
                <el-icon size="48"><User /></el-icon>
              </div>
              <h3>就诊入口</h3>
              <p>Patient Portal</p>
              <div class="card-features">
                <span>查看病历</span>
                <span>主治医师</span>
                <span>检查报告</span>
              </div>
              <el-button type="primary" size="large" class="enter-btn">
                进入 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>

            <!-- 医生入口 -->
            <div class="portal-card doctor" @click="selectPortal('doctor')">
              <div class="card-icon">
                <el-icon size="48"><FirstAidKit /></el-icon>
              </div>
              <h3>诊疗工作台</h3>
              <p>Doctor Workstation</p>
              <div class="card-features">
                <span>患者管理</span>
                <span>AI辅助诊断</span>
                <span>病历管理</span>
              </div>
              <el-button type="success" size="large" class="enter-btn">
                进入 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </div>

          <!-- 医生注册申请 -->
          <div class="doctor-register-link">
            <span>是医生？</span>
            <el-link type="primary" @click="showDoctorRegister = true">
              申请入驻诊疗工作台
            </el-link>
          </div>
        </div>

        <!-- 登录表单 -->
        <div v-else class="login-form-container">
          <div class="form-header">
            <el-button text @click="selectedPortal = null" class="back-btn">
              <el-icon><ArrowLeft /></el-icon> 返回
            </el-button>
            <h2>{{ portalTitle }}</h2>
          </div>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            class="login-form"
            @keyup.enter="handleLogin"
          >
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="用户名"
                size="large"
                :prefix-icon="User"
              />
            </el-form-item>

            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="密码"
                size="large"
                :prefix-icon="Lock"
                show-password
              />
            </el-form-item>

            <!-- 三个入口均需验证码：后端已强制校验 -->
            <el-form-item prop="captcha">
              <div class="captcha-row">
                <el-input
                  v-model="form.captcha"
                  placeholder="验证码"
                  size="large"
                  maxlength="4"
                  style="flex: 1"
                />
                <div class="captcha-image" @click="refreshCaptcha">
                  <img v-if="captchaImage" :src="captchaImage" alt="验证码" />
                </div>
              </div>
            </el-form-item>

            <div class="form-options">
              <el-checkbox v-model="rememberMe">记住我</el-checkbox>
              <el-link type="primary" @click="showForgotPassword = true">忘记密码？</el-link>
            </div>

            <el-button
              type="primary"
              size="large"
              class="login-btn"
              :loading="loading"
              @click="handleLogin"
            >
              登录
            </el-button>

            <div class="register-link" v-if="selectedPortal === 'patient'">
              <span>还没有账号？</span>
              <el-link type="primary" @click="showPatientRegister = true">立即注册</el-link>
            </div>
          </el-form>
        </div>
      </div>
    </div>

    <!-- 隐藏的管理员入口 - 连续点击logo 5次触发 -->
    <div 
      class="admin-trigger" 
      @click="handleAdminTrigger"
      title=""
    ></div>

    <!-- 管理员登录弹窗 -->
    <el-dialog
      v-model="showAdminLogin"
      title="管理员登录"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="adminFormRef"
        :model="adminForm"
        :rules="adminRules"
        @keyup.enter="handleAdminLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="adminForm.username"
            placeholder="管理员账号"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="adminForm.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item prop="captcha">
          <div class="captcha-row">
            <el-input
              v-model="adminForm.captcha"
              placeholder="验证码"
              maxlength="4"
              style="flex: 1"
            />
            <div class="captcha-image" @click="refreshAdminCaptcha">
              <img v-if="adminCaptchaImage" :src="adminCaptchaImage" alt="验证码" />
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdminLogin = false">取消</el-button>
        <el-button type="primary" :loading="adminLoading" @click="handleAdminLogin">
          登录
        </el-button>
      </template>
    </el-dialog>

    <!-- 患者注册弹窗 -->
    <PatientRegisterDialog
      v-model="showPatientRegister"
      @success="handlePatientRegisterSuccess"
    />

    <!-- 医生注册申请弹窗 -->
    <DoctorRegisterDialog
      v-model="showDoctorRegister"
      @success="handleDoctorRegisterSuccess"
    />

    <!-- 忘记密码弹窗 -->
    <el-dialog
      v-model="showForgotPassword"
      title="重置密码"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-steps :active="forgotStep" finish-status="success" simple>
        <el-step title="验证身份" />
        <el-step title="重置密码" />
        <el-step title="完成" />
      </el-steps>

      <!-- 步骤1: 验证身份 -->
      <el-form
        v-if="forgotStep === 0"
        ref="forgotFormRef"
        :model="forgotForm"
        :rules="forgotRules"
        label-width="100px"
        style="margin-top: 20px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="forgotForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="forgotForm.phone" placeholder="请输入注册时的手机号" />
        </el-form-item>
        <el-form-item label="验证码" prop="captcha">
          <div class="captcha-row">
            <el-input
              v-model="forgotForm.captcha"
              placeholder="请输入验证码"
              maxlength="4"
              style="flex: 1"
            />
            <div class="captcha-image" @click="refreshForgotCaptcha">
              <img v-if="forgotCaptchaImage" :src="forgotCaptchaImage" alt="验证码" />
            </div>
          </div>
        </el-form-item>
      </el-form>

      <!-- 步骤2: 重置密码 -->
      <el-form
        v-if="forgotStep === 1"
        ref="resetFormRef"
        :model="resetForm"
        :rules="resetRules"
        label-width="100px"
        style="margin-top: 20px"
      >
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="resetForm.newPassword"
            type="password"
            placeholder="请输入新密码（至少6位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="resetForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>

      <!-- 步骤3: 完成 -->
      <div v-if="forgotStep === 2" class="success-step">
        <el-result
          icon="success"
          title="密码重置成功"
          sub-title="请使用新密码登录"
        />
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button v-if="forgotStep === 0" @click="showForgotPassword = false">取消</el-button>
          <el-button v-if="forgotStep === 0" type="primary" :loading="forgotLoading" @click="verifyIdentity">
            下一步
          </el-button>
          <el-button v-if="forgotStep === 1" @click="forgotStep--">上一步</el-button>
          <el-button v-if="forgotStep === 1" type="primary" :loading="resetLoading" @click="resetPassword">
            确认重置
          </el-button>
          <el-button v-if="forgotStep === 2" type="primary" @click="closeForgotDialog">
            确定
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 页脚 -->
    <div class="footer">
      <p>© 2026 智慧骨科云平台 | 让骨科诊疗更智能</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  User, Lock, FirstAidKit, Check, ArrowRight, ArrowLeft
} from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { saveAuth } from '../utils/auth'
import PatientRegisterDialog from '../components/PatientRegisterDialog.vue'
import DoctorRegisterDialog from '../components/DoctorRegisterDialog.vue'

const router = useRouter()

// 状态
const selectedPortal = ref(null)
const loading = ref(false)
const rememberMe = ref(false)
const captchaImage = ref('')
const captchaId = ref('')

// 表单
const formRef = ref(null)
const form = reactive({
  username: '',
  password: '',
  captcha: ''
})

// 验证规则
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

// 计算属性
const portalTitle = computed(() => {
  return selectedPortal.value === 'patient' ? '患者登录' : '医生登录'
})

// 选择入口
const selectPortal = (portal) => {
  selectedPortal.value = portal
  // 三个入口现在都需要验证码，切换时重新加载
  refreshCaptcha()
}

// 加载验证码（登录表单与管理员弹窗共用）
const loadCaptcha = async (idRef, imageRef, formObj) => {
  try {
    const res = await axios.get('/api/captcha', {
      responseType: 'blob'
    })
    idRef.value = res.headers['x-captcha-id'] || ''
    const reader = new FileReader()
    reader.onload = () => {
      imageRef.value = reader.result
    }
    reader.readAsDataURL(res.data)
    if (formObj) formObj.captcha = ''
  } catch (err) {
    console.error('获取验证码失败:', err)
  }
}

// 刷新主登录表单的验证码
const refreshCaptcha = () => loadCaptcha(captchaId, captchaImage, form)

// 刷新管理员弹窗的验证码
const refreshAdminCaptcha = () => loadCaptcha(adminCaptchaId, adminCaptchaImage, adminForm)

// 登录
const handleLogin = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const loginData = {
        username: form.username,
        password: form.password,
        role: selectedPortal.value,
        captcha: form.captcha,
        captcha_id: captchaId.value
      }

      const res = await axios.post('/api/login', loginData)
      
      if (res.data.success) {
        // 存储登录信息（access_token 为真实 JWT，由 utils/axios.js 注入请求头）
        saveAuth({
          accessToken: res.data.access_token,
          username: res.data.username,
          role: res.data.role
        })

        if (rememberMe.value) {
          localStorage.setItem('rememberedUsername', form.username)
        }
        
        ElMessage.success('登录成功')
        
        // 根据角色跳转
        console.log('[DEBUG] 登录成功，角色:', res.data.role)
        let targetPath = '/login'
        if (res.data.role === 'patient') {
          targetPath = '/patient-portal'
        } else if (res.data.role === 'doctor') {
          targetPath = '/doctor-workstation'
        } else if (res.data.role === 'admin') {
          targetPath = '/admin'
        }
        console.log('[DEBUG] 准备跳转到:', targetPath)
        
        // 使用 window.location 强制跳转
        window.location.href = targetPath
      }
    } catch (err) {
      const msg = err.response?.data?.error || '登录失败'
      ElMessage.error(msg)
      // 验证码为一次性使用，无论哪个入口失败都要换一张
      refreshCaptcha()
    } finally {
      loading.value = false
    }
  })
}

// 管理员登录
const adminClickCount = ref(0)
const adminClickTimer = ref(null)
const showAdminLogin = ref(false)
const adminLoading = ref(false)
const adminFormRef = ref(null)
const adminCaptchaId = ref('')
const adminCaptchaImage = ref('')
const adminForm = reactive({
  username: '',
  password: '',
  captcha: ''
})
const adminRules = {
  username: [{ required: true, message: '请输入管理员账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

const handleAdminTrigger = () => {
  adminClickCount.value++
  
  if (adminClickTimer.value) {
    clearTimeout(adminClickTimer.value)
  }
  
  adminClickTimer.value = setTimeout(() => {
    adminClickCount.value = 0
  }, 3000)
  
  if (adminClickCount.value >= 5) {
    adminClickCount.value = 0
    showAdminLogin.value = true
    refreshAdminCaptcha()   // 打开弹窗即加载验证码
  }
}

const handleAdminLogin = async () => {
  if (!adminFormRef.value) return
  
  await adminFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    adminLoading.value = true
    try {
      const res = await axios.post('/api/login', {
        username: adminForm.username,
        password: adminForm.password,
        role: 'admin',
        captcha: adminForm.captcha,
        captcha_id: adminCaptchaId.value
      })

      if (res.data.success && res.data.role === 'admin') {
        saveAuth({
          accessToken: res.data.access_token,
          username: res.data.username,
          role: 'admin'
        })
        ElMessage.success('管理员登录成功')
        router.push('/admin')
      } else {
        ElMessage.error('非管理员账号')
      }
    } catch (err) {
      const msg = err.response?.data?.error || '登录失败'
      ElMessage.error(msg)
      // 验证码为一次性使用，失败后必须换一张
      refreshAdminCaptcha()
    } finally {
      adminLoading.value = false
    }
  })
}

// 注册弹窗
const showPatientRegister = ref(false)
const showDoctorRegister = ref(false)

const handlePatientRegisterSuccess = () => {
  showPatientRegister.value = false
  ElMessage.success('注册成功，请登录')
}

const handleDoctorRegisterSuccess = () => {
  showDoctorRegister.value = false
  ElMessage.success('申请已提交，请等待审核')
}

// 忘记密码
const showForgotPassword = ref(false)
const forgotStep = ref(0)
const forgotLoading = ref(false)
const resetLoading = ref(false)
const forgotFormRef = ref(null)
const resetFormRef = ref(null)
const forgotCaptchaImage = ref('')
const forgotCaptchaId = ref('')

const forgotForm = reactive({
  username: '',
  phone: '',
  captcha: ''
})

const resetForm = reactive({
  newPassword: '',
  confirmPassword: ''
})

const forgotRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

const resetRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== resetForm.newPassword) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

// 刷新忘记密码验证码
const refreshForgotCaptcha = async () => {
  try {
    const res = await axios.get('/api/captcha', {
      responseType: 'blob'
    })
    forgotCaptchaId.value = res.headers['x-captcha-id'] || ''
    const reader = new FileReader()
    reader.onload = () => {
      forgotCaptchaImage.value = reader.result
    }
    reader.readAsDataURL(res.data)
    forgotForm.captcha = ''
  } catch (err) {
    console.error('获取验证码失败:', err)
  }
}

// 验证身份
const verifyIdentity = async () => {
  if (!forgotFormRef.value) return
  await forgotFormRef.value.validate(async (valid) => {
    if (!valid) return
    forgotLoading.value = true
    try {
      const res = await axios.post('/api/forgot-password/verify', {
        username: forgotForm.username,
        phone: forgotForm.phone,
        captcha: forgotForm.captcha,
        captcha_id: forgotCaptchaId.value
      })
      if (res.data.success) {
        forgotStep.value = 1
      }
    } catch (err) {
      const msg = err.response?.data?.error || '验证失败'
      ElMessage.error(msg)
      refreshForgotCaptcha()
    } finally {
      forgotLoading.value = false
    }
  })
}

// 重置密码
const resetPassword = async () => {
  if (!resetFormRef.value) return
  await resetFormRef.value.validate(async (valid) => {
    if (!valid) return
    resetLoading.value = true
    try {
      const res = await axios.post('/api/forgot-password/reset', {
        username: forgotForm.username,
        new_password: resetForm.newPassword
      })
      if (res.data.success) {
        forgotStep.value = 2
      }
    } catch (err) {
      const msg = err.response?.data?.error || '重置失败'
      ElMessage.error(msg)
    } finally {
      resetLoading.value = false
    }
  })
}

// 关闭忘记密码弹窗
const closeForgotDialog = () => {
  showForgotPassword.value = false
  forgotStep.value = 0
  forgotForm.username = ''
  forgotForm.phone = ''
  forgotForm.captcha = ''
  resetForm.newPassword = ''
  resetForm.confirmPassword = ''
}

// 监听弹窗打开，自动获取验证码
watch(showForgotPassword, (val) => {
  if (val) {
    refreshForgotCaptcha()
  }
})

onMounted(() => {
  // 检查是否有记住的用户名
  const remembered = localStorage.getItem('rememberedUsername')
  if (remembered) {
    form.username = remembered
    rememberMe.value = true
  }
})
</script>

<style scoped>
.smart-ortho-login {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

/* 背景动画 */
.bg-animation {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
}

.bone-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(circle at 20% 80%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(16, 185, 129, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 40% 40%, rgba(99, 102, 241, 0.05) 0%, transparent 50%);
  animation: pulse 8s ease-in-out infinite;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #f0fdf4 100%);
}

@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

/* 主容器 */
.main-container {
  flex: 1;
  display: flex;
  position: relative;
  z-index: 1;
}

/* 左侧品牌区 */
.brand-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px;
  background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #0ea5e9 100%);
  color: white;
  position: relative;
  overflow: hidden;
}

.brand-section::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: 
    radial-gradient(circle at 30% 70%, rgba(255,255,255,0.1) 0%, transparent 40%),
    radial-gradient(circle at 70% 30%, rgba(255,255,255,0.1) 0%, transparent 40%);
  animation: rotate 30s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.brand-content {
  text-align: center;
  position: relative;
  z-index: 1;
}

.logo {
  margin-bottom: 30px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.system-title {
  font-size: 42px;
  font-weight: 700;
  margin-bottom: 10px;
  text-shadow: 0 2px 10px rgba(0,0,0,0.2);
}

.system-subtitle {
  font-size: 18px;
  opacity: 0.9;
  margin-bottom: 50px;
  letter-spacing: 2px;
}

.features {
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: center;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
  padding: 12px 24px;
  background: rgba(255,255,255,0.15);
  border-radius: 30px;
  backdrop-filter: blur(10px);
}

/* 右侧登录区 */
.login-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(20px);
}

/* 入口选择 */
.portal-selection {
  width: 100%;
  max-width: 700px;
  text-align: center;
}

.portal-title {
  font-size: 32px;
  color: #1e293b;
  margin-bottom: 10px;
  font-weight: 600;
}

.portal-subtitle {
  color: #64748b;
  margin-bottom: 50px;
  font-size: 16px;
}

.portal-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 30px;
  margin-bottom: 40px;
}

.portal-card {
  background: white;
  border-radius: 20px;
  padding: 40px 30px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 2px solid transparent;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}

.portal-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.15);
}

.portal-card.patient:hover {
  border-color: #3b82f6;
}

.portal-card.doctor:hover {
  border-color: #10b981;
}

.card-icon {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
}

.portal-card.patient .card-icon {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
}

.portal-card.doctor .card-icon {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
}

.portal-card h3 {
  font-size: 24px;
  color: #1e293b;
  margin-bottom: 5px;
}

.portal-card > p {
  color: #94a3b8;
  font-size: 14px;
  margin-bottom: 20px;
}

.card-features {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-bottom: 25px;
}

.card-features span {
  padding: 6px 14px;
  background: #f1f5f9;
  border-radius: 20px;
  font-size: 13px;
  color: #64748b;
}

.enter-btn {
  width: 100%;
  font-size: 16px;
  border-radius: 10px;
}

.doctor-register-link {
  color: #64748b;
  font-size: 14px;
}

.doctor-register-link span {
  margin-right: 8px;
}

/* 登录表单 */
.login-form-container {
  width: 100%;
  max-width: 400px;
}

.form-header {
  text-align: center;
  margin-bottom: 40px;
  position: relative;
}

.back-btn {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
}

.form-header h2 {
  font-size: 28px;
  color: #1e293b;
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 8px 15px;
}

.captcha-row {
  display: flex;
  gap: 12px;
}

.captcha-image {
  width: 120px;
  height: 46px;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid #dcdfe6;
}

.captcha-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 25px;
}

.login-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  border-radius: 10px;
  margin-bottom: 20px;
}

.register-link {
  text-align: center;
  color: #64748b;
  font-size: 14px;
}

.register-link span {
  margin-right: 8px;
}

/* 隐藏的管理员触发器 */
.admin-trigger {
  position: fixed;
  top: 20px;
  right: 20px;
  width: 30px;
  height: 30px;
  cursor: pointer;
  z-index: 100;
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.3s;
}

.admin-trigger:hover {
  opacity: 0.1;
  background: #3b82f6;
}

/* 页脚 */
.footer {
  text-align: center;
  padding: 20px;
  color: #94a3b8;
  font-size: 13px;
  position: relative;
  z-index: 1;
}

/* 响应式 */
@media (max-width: 1024px) {
  .brand-section {
    display: none;
  }
  
  .login-section {
    flex: 1;
  }
}

@media (max-width: 640px) {
  .portal-cards {
    grid-template-columns: 1fr;
  }
  
  .login-section {
    padding: 30px;
  }
}
</style>
