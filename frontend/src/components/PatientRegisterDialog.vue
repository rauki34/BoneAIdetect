<template>
  <el-dialog
    v-model="visible"
    title="患者注册"
    width="500px"
    :close-on-click-modal="false"
    class="patient-register-dialog"
  >
    <el-steps :active="currentStep" finish-status="success" simple class="register-steps">
      <el-step title="基本信息" />
      <el-step title="详细信息" />
      <el-step title="完成" />
    </el-steps>

    <!-- 步骤1: 基本信息 -->
    <el-form
      v-if="currentStep === 0"
      ref="step1FormRef"
      :model="form"
      :rules="step1Rules"
      label-width="100px"
      class="register-form"
    >
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" placeholder="请输入用户名（用于登录）" />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          placeholder="请输入密码（至少6位）"
          show-password
        />
      </el-form-item>

      <el-form-item label="确认密码" prop="passwordConfirm">
        <el-input
          v-model="form.passwordConfirm"
          type="password"
          placeholder="请再次输入密码"
          show-password
        />
      </el-form-item>

      <el-form-item label="真实姓名" prop="fullName">
        <el-input v-model="form.fullName" placeholder="请输入真实姓名" />
      </el-form-item>

      <el-form-item label="身份证号" prop="idCard">
        <el-input v-model="form.idCard" placeholder="请输入身份证号" maxlength="18" />
      </el-form-item>
    </el-form>

    <!-- 步骤2: 详细信息 -->
    <el-form
      v-if="currentStep === 1"
      ref="step2FormRef"
      :model="form"
      :rules="step2Rules"
      label-width="100px"
      class="register-form"
    >
      <el-form-item label="性别" prop="gender">
        <el-radio-group v-model="form.gender">
          <el-radio value="男">男</el-radio>
          <el-radio value="女">女</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="出生日期" prop="birthDate">
        <el-date-picker
          v-model="form.birthDate"
          type="date"
          placeholder="选择出生日期"
          style="width: 100%"
          value-format="YYYY-MM-DD"
        />
      </el-form-item>

      <el-form-item label="手机号码" prop="phone">
        <el-input v-model="form.phone" placeholder="请输入手机号码" maxlength="11" />
      </el-form-item>

      <el-form-item label="邮箱" prop="email">
        <el-input v-model="form.email" placeholder="请输入邮箱（选填）" />
      </el-form-item>

      <el-form-item label="家庭住址" prop="address">
        <el-input
          v-model="form.address"
          type="textarea"
          :rows="2"
          placeholder="请输入家庭住址"
        />
      </el-form-item>

      <el-form-item label="紧急联系人" prop="emergencyContact">
        <el-input v-model="form.emergencyContact" placeholder="请输入紧急联系人姓名" />
      </el-form-item>

      <el-form-item label="紧急电话" prop="emergencyPhone">
        <el-input v-model="form.emergencyPhone" placeholder="请输入紧急联系人电话" />
      </el-form-item>

      <el-form-item label="过敏史" prop="allergies">
        <el-input
          v-model="form.allergies"
          type="textarea"
          :rows="2"
          placeholder="请填写过敏史（没有请填'无'）"
        />
      </el-form-item>

      <el-form-item label="既往病史" prop="medicalHistory">
        <el-input
          v-model="form.medicalHistory"
          type="textarea"
          :rows="3"
          placeholder="请填写既往病史（没有请填'无'）"
        />
      </el-form-item>

      <el-form-item label="验证码" prop="captcha">
        <div class="captcha-row">
          <el-input
            v-model="form.captcha"
            placeholder="请输入验证码"
            maxlength="4"
            style="flex: 1"
          />
          <div class="captcha-image" @click="refreshCaptcha">
            <img v-if="captchaImage" :src="captchaImage" alt="验证码" />
          </div>
        </div>
      </el-form-item>
    </el-form>

    <!-- 步骤3: 完成 -->
    <div v-if="currentStep === 2" class="success-step">
      <el-result
        icon="success"
        title="注册成功"
        sub-title="请牢记您的用户名和密码，即将返回登录页面"
      >
        <template #extra>
          <p class="account-info">
            <strong>用户名：</strong>{{ form.username }}
          </p>
        </template>
      </el-result>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button v-if="currentStep === 0" type="warning" @click="autoFillTestData">
          <el-icon><MagicStick /></el-icon> 自动填充测试数据
        </el-button>
        <el-button v-if="currentStep > 0 && currentStep < 2" @click="currentStep--">
          上一步
        </el-button>
        <el-button v-if="currentStep < 1" type="primary" @click="nextStep">
          下一步
        </el-button>
        <el-button v-if="currentStep === 1" type="primary" :loading="loading" @click="submitRegister">
          提交注册
        </el-button>
        <el-button v-if="currentStep === 2" type="primary" @click="closeDialog">
          确定
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import * as authApi from '../api/auth'
import * as patientApi from '../api/patient'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const currentStep = ref(0)
const loading = ref(false)
const step1FormRef = ref(null)
const step2FormRef = ref(null)

const form = reactive({
  username: '',
  password: '',
  passwordConfirm: '',
  fullName: '',
  idCard: '',
  gender: '男',
  birthDate: '',
  phone: '',
  email: '',
  address: '',
  emergencyContact: '',
  emergencyPhone: '',
  allergies: '',
  medicalHistory: '',
  captcha: ''
})

// 验证码
const captchaId = ref('')
const captchaImage = ref('')

const refreshCaptcha = async () => {
  try {
    const res = await authApi.captcha({ responseType: 'blob' })
    captchaId.value = res.headers['x-captcha-id'] || ''
    const reader = new FileReader()
    reader.onload = () => { captchaImage.value = reader.result }
    reader.readAsDataURL(res.data)
    form.captcha = ''
  } catch (err) {
    console.error('获取验证码失败:', err)
  }
}

// 验证身份证号
const validateIdCard = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入身份证号'))
    return
  }
  const reg = /^[1-9]\d{5}(18|19|20)\d{2}((0[1-9])|(1[0-2]))(([0-2][1-9])|10|20|30|31)\d{3}[0-9Xx]$/
  if (!reg.test(value)) {
    callback(new Error('身份证号格式不正确'))
  } else {
    callback()
  }
}

// 验证手机号
const validatePhone = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入手机号码'))
    return
  }
  const reg = /^1[3-9]\d{9}$/
  if (!reg.test(value)) {
    callback(new Error('手机号格式不正确'))
  } else {
    callback()
  }
}

// 验证确认密码
const validatePasswordConfirm = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请再次输入密码'))
  } else if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

// 生成随机身份证号
const generateIdCard = () => {
  const prefix = '110101' // 北京市东城区
  const year = Math.floor(Math.random() * (2000 - 1960 + 1)) + 1960 // 1960-2000
  const month = String(Math.floor(Math.random() * 12) + 1).padStart(2, '0')
  const day = String(Math.floor(Math.random() * 28) + 1).padStart(2, '0')
  const random = String(Math.floor(Math.random() * 999) + 1).padStart(3, '0')
  const base = prefix + year + month + day + random
  // 计算校验码
  const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
  const checkCodes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
  let sum = 0
  for (let i = 0; i < 17; i++) {
    sum += parseInt(base[i]) * weights[i]
  }
  return base + checkCodes[sum % 11]
}

// 自动填充测试数据
const autoFillTestData = () => {
  const timestamp = Date.now().toString().slice(-6)
  form.username = `patient${timestamp}`
  form.password = '123456'
  form.passwordConfirm = '123456'
  form.fullName = '张' + ['伟', '芳', '娜', '敏', '静', '丽', '强', '磊', '军', '洋'][Math.floor(Math.random() * 10)]
  form.idCard = generateIdCard()
  
  // 填充第二步数据
  form.gender = Math.random() > 0.5 ? '男' : '女'
  const birthYear = Math.floor(Math.random() * (1995 - 1970 + 1)) + 1970
  const birthMonth = String(Math.floor(Math.random() * 12) + 1).padStart(2, '0')
  const birthDay = String(Math.floor(Math.random() * 28) + 1).padStart(2, '0')
  form.birthDate = `${birthYear}-${birthMonth}-${birthDay}`
  // 生成11位手机号：1 + 第二位(3-9) + 9位随机数
  const secondDigit = [3, 4, 5, 6, 7, 8, 9][Math.floor(Math.random() * 7)]
  const remaining9Digits = Math.floor(Math.random() * 1000000000).toString().padStart(9, '0')
  form.phone = '1' + secondDigit + remaining9Digits
  form.email = `${form.username}@test.com`
  form.address = '北京市朝阳区测试路' + Math.floor(Math.random() * 100) + '号'
  form.emergencyContact = '李' + ['明', '华', '强', '军'][Math.floor(Math.random() * 4)]
  form.emergencyPhone = form.phone
  form.allergies = '无'
  form.medicalHistory = '无'
  
  ElMessage.success('测试数据已自动填充')
}

const step1Rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度3-20个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  passwordConfirm: [
    { required: true, validator: validatePasswordConfirm, trigger: 'blur' }
  ],
  fullName: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { min: 2, max: 20, message: '姓名长度2-20个字符', trigger: 'blur' }
  ],
  idCard: [
    { required: true, validator: validateIdCard, trigger: 'blur' }
  ]
}

const step2Rules = {
  gender: [{ required: true, message: '请选择性别', trigger: 'change' }],
  birthDate: [{ required: true, message: '请选择出生日期', trigger: 'change' }],
  phone: [
    { required: true, validator: validatePhone, trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  address: [{ required: true, message: '请输入家庭住址', trigger: 'blur' }],
  emergencyContact: [{ required: true, message: '请输入紧急联系人', trigger: 'blur' }],
  emergencyPhone: [{ required: true, validator: validatePhone, trigger: 'blur' }],
  allergies: [{ required: true, message: '请填写过敏史', trigger: 'blur' }],
  medicalHistory: [{ required: true, message: '请填写既往病史', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

const nextStep = async () => {
  if (!step1FormRef.value) return

  await step1FormRef.value.validate((valid) => {
    if (valid) {
      currentStep.value++
      refreshCaptcha()   // 进入第 2 步即加载验证码
    }
  })
}

const submitRegister = async () => {
  if (!step2FormRef.value) return
  
  await step2FormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const res = await patientApi.registerPatient({
        username: form.username,
        password: form.password,
        full_name: form.fullName,
        id_card: form.idCard,
        gender: form.gender,
        birth_date: form.birthDate,
        phone: form.phone,
        email: form.email,
        address: form.address,
        emergency_contact: form.emergencyContact,
        emergency_phone: form.emergencyPhone,
        allergies: form.allergies,
        medical_history: form.medicalHistory,
        captcha: form.captcha,
        captcha_id: captchaId.value
      })

      if (res.data.success) {
        currentStep.value = 2
        emit('success')
      }
    } catch (err) {
      const msg = err.response?.data?.error || '注册失败'
      ElMessage.error(msg)
      // 验证码一次性使用，失败后需要换一张
      refreshCaptcha()
    } finally {
      loading.value = false
    }
  })
}

const closeDialog = () => {
  visible.value = false
  resetForm()
}

const resetForm = () => {
  currentStep.value = 0
  Object.keys(form).forEach(key => {
    if (key === 'gender') {
      form[key] = '男'
    } else {
      form[key] = ''
    }
  })
}

watch(() => props.modelValue, (val) => {
  if (!val) {
    resetForm()
  }
})
</script>

<style scoped>
.patient-register-dialog :deep(.el-dialog__body) {
  padding: 20px 30px;
}

.register-steps {
  margin-bottom: 30px;
}

.register-form :deep(.el-input__wrapper),
.register-form :deep(.el-textarea__inner) {
  border-radius: 8px;
}

/* 验证码 */
.captcha-row {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
}

.captcha-image {
  flex-shrink: 0;
  width: 110px;
  height: 38px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
}

.captcha-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.success-step {
  padding: 20px 0;
}

.account-info {
  margin-top: 20px;
  padding: 15px;
  background: #f0f9ff;
  border-radius: 8px;
  color: #1e293b;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
