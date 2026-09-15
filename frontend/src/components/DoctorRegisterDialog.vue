<template>
  <el-dialog
    v-model="visible"
    title="医生入驻申请"
    width="600px"
    :close-on-click-modal="false"
    class="doctor-register-dialog"
  >
    <div class="dialog-header">
      <el-alert
        title="申请须知"
        description="请如实填写以下信息，提交后需等待管理员审核通过方可使用。审核结果将通过短信或邮件通知您。"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      class="register-form"
    >
      <h4 class="section-title">账户信息</h4>
      
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

      <h4 class="section-title">个人信息</h4>

      <el-form-item label="真实姓名" prop="fullName">
        <el-input v-model="form.fullName" placeholder="请输入真实姓名" />
      </el-form-item>

      <el-form-item label="所属医院" prop="hospital">
        <el-input v-model="form.hospital" placeholder="请输入所属医院名称" />
      </el-form-item>

      <el-form-item label="科室" prop="department">
        <el-select v-model="form.department" placeholder="请选择科室" style="width: 100%">
          <el-option label="骨科" value="骨科" />
          <el-option label="创伤骨科" value="创伤骨科" />
          <el-option label="脊柱外科" value="脊柱外科" />
          <el-option label="关节外科" value="关节外科" />
          <el-option label="运动医学科" value="运动医学科" />
          <el-option label="骨肿瘤科" value="骨肿瘤科" />
          <el-option label="小儿骨科" value="小儿骨科" />
          <el-option label="手足外科" value="手足外科" />
          <el-option label="康复医学科" value="康复医学科" />
          <el-option label="放射科" value="放射科" />
          <el-option label="其他" value="其他" />
        </el-select>
      </el-form-item>

      <el-form-item label="职称" prop="title">
        <el-select v-model="form.title" placeholder="请选择职称" style="width: 100%">
          <el-option label="主任医师" value="主任医师" />
          <el-option label="副主任医师" value="副主任医师" />
          <el-option label="主治医师" value="主治医师" />
          <el-option label="住院医师" value="住院医师" />
          <el-option label="实习医师" value="实习医师" />
        </el-select>
      </el-form-item>

      <el-form-item label="执业证号" prop="licenseNumber">
        <el-input v-model="form.licenseNumber" placeholder="请输入医师执业证书编号">
          <template #append>
            <el-button @click="form.licenseNumber = generateLicenseNumber()">
              <el-icon><MagicStick /></el-icon> 自动生成
            </el-button>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="专业特长" prop="specialty">
        <el-input
          v-model="form.specialty"
          type="textarea"
          :rows="3"
          placeholder="请简述您的专业特长和研究方向"
        />
      </el-form-item>

      <h4 class="section-title">联系方式</h4>

      <el-form-item label="手机号码" prop="phone">
        <el-input v-model="form.phone" placeholder="请输入手机号码" maxlength="11" />
      </el-form-item>

      <el-form-item label="邮箱" prop="email">
        <el-input v-model="form.email" placeholder="请输入邮箱地址" />
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

    <template #footer>
      <div class="dialog-footer">
        <el-button type="warning" @click="autoFillTestData">
          <el-icon><MagicStick /></el-icon> 自动填充测试数据
        </el-button>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitApplication">
          提交申请
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import axios from '../utils/axios'

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

const loading = ref(false)
const formRef = ref(null)

const form = reactive({
  username: '',
  password: '',
  passwordConfirm: '',
  fullName: '',
  hospital: '',
  department: '',
  title: '',
  licenseNumber: '',
  specialty: '',
  phone: '',
  email: '',
  captcha: ''
})

// 验证码
const captchaId = ref('')
const captchaImage = ref('')

const refreshCaptcha = async () => {
  try {
    const res = await axios.get('/api/captcha', { responseType: 'blob' })
    captchaId.value = res.headers['x-captcha-id'] || ''
    const reader = new FileReader()
    reader.onload = () => { captchaImage.value = reader.result }
    reader.readAsDataURL(res.data)
    form.captcha = ''
  } catch (err) {
    console.error('获取验证码失败:', err)
  }
}

// 弹窗打开时加载验证码
watch(visible, (val) => {
  if (val) refreshCaptcha()
})

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

// 生成随机执业证号
const generateLicenseNumber = () => {
  // 格式：110 + 6位行政区划代码 + 4位年份 + 5位随机码 = 15位
  const year = new Date().getFullYear()
  const randomCode = Math.floor(Math.random() * 90000 + 10000) // 10000-99999
  return `110110${year}${randomCode}`
}

// 验证执业证号
const validateLicenseNumber = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入执业证号'))
    return
  }
  // 执业证号格式：110 + 6位行政区划代码 + 4位年份 + 5位随机码 = 15位
  const reg = /^110\d{12}$/
  if (!reg.test(value)) {
    callback(new Error('执业证号格式不正确，应为110开头的15位数字'))
  } else {
    callback()
  }
}

const rules = {
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
  hospital: [
    { required: true, message: '请输入所属医院', trigger: 'blur' }
  ],
  department: [
    { required: true, message: '请选择科室', trigger: 'change' }
  ],
  title: [
    { required: true, message: '请选择职称', trigger: 'change' }
  ],
  licenseNumber: [
    { required: true, validator: validateLicenseNumber, trigger: 'blur' }
  ],
  specialty: [
    { required: true, message: '请填写专业特长', trigger: 'blur' }
  ],
  phone: [
    { required: true, validator: validatePhone, trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

// 自动填充测试数据
const autoFillTestData = () => {
  const timestamp = Date.now().toString().slice(-6)
  form.username = `doctor${timestamp}`
  form.password = '123456'
  form.passwordConfirm = '123456'
  form.fullName = '王' + ['伟', '芳', '娜', '敏', '静', '丽', '强', '磊', '军', '洋'][Math.floor(Math.random() * 10)]
  form.hospital = ['北京协和医院', '北京大学人民医院', '北京积水潭医院', '301医院', '中日友好医院'][Math.floor(Math.random() * 5)]
  form.department = ['骨科', '创伤骨科', '脊柱外科', '关节外科', '运动医学科'][Math.floor(Math.random() * 5)]
  form.title = ['主任医师', '副主任医师', '主治医师'][Math.floor(Math.random() * 3)]
  form.licenseNumber = generateLicenseNumber()
  form.specialty = '擅长骨折诊断、关节置换、脊柱手术等骨科疾病的诊治'
  // 生成11位手机号：1 + 第二位(3-9) + 9位随机数
  const secondDigit = [3, 4, 5, 6, 7, 8, 9][Math.floor(Math.random() * 7)]
  const remaining9Digits = Math.floor(Math.random() * 1000000000).toString().padStart(9, '0')
  form.phone = '1' + secondDigit + remaining9Digits
  form.email = `${form.username}@hospital.com`
  
  ElMessage.success('测试数据已自动填充')
}

const submitApplication = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const res = await axios.post('/api/doctor/register', {
        username: form.username,
        password: form.password,
        full_name: form.fullName,
        hospital: form.hospital,
        department: form.department,
        title: form.title,
        license_number: form.licenseNumber,
        specialty: form.specialty,
        phone: form.phone,
        email: form.email,
        captcha: form.captcha,
        captcha_id: captchaId.value
      })

      if (res.data.success) {
        ElMessage.success('申请已提交，请等待管理员审核')
        emit('success')
        visible.value = false
        resetForm()
      }
    } catch (err) {
      const msg = err.response?.data?.error || '提交失败'
      ElMessage.error(msg)
      // 验证码一次性使用，失败后需要换一张
      refreshCaptcha()
    } finally {
      loading.value = false
    }
  })
}

const resetForm = () => {
  if (formRef.value) {
    formRef.value.resetFields()
  }
  Object.keys(form).forEach(key => {
    form[key] = ''
  })
}
</script>

<style scoped>
.doctor-register-dialog :deep(.el-dialog__body) {
  padding: 20px 30px;
  max-height: 60vh;
  overflow-y: auto;
}

.dialog-header {
  margin-bottom: 20px;
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

.section-title {
  margin: 20px 0 15px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid #e4e7ed;
  color: #1e293b;
  font-size: 16px;
}

.section-title:first-child {
  margin-top: 0;
}

.register-form :deep(.el-input__wrapper),
.register-form :deep(.el-textarea__inner) {
  border-radius: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
