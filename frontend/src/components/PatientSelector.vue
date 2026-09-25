<template>
  <div class="patient-selector">
    <el-select
      v-model="selectedPatientId"
      filterable
      remote
      reserve-keyword
      placeholder="搜索患者(姓名或ID)"
      :remote-method="searchPatients"
      :loading="loading"
      @change="handleChange"
      style="width: 100%"
    >
      <el-option
        v-for="patient in patients"
        :key="patient.id"
        :label="`${patient.full_name || patient.username} (ID: ${patient.id})`"
        :value="patient.id"
      >
        <div class="patient-option">
          <span class="patient-name">{{ patient.full_name || patient.username }}</span>
          <span class="patient-info">ID: {{ patient.id }} | 电话: {{ patient.phone || '未提供' }}</span>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as patientApi from '../api/patient'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const selectedPatientId = ref(props.modelValue)
const patients = ref([])
const loading = ref(false)

// 搜索患者
const searchPatients = async (query) => {
  if (query === '') {
    loadPatients()
    return
  }
  
  loading.value = true
  try {
    const response = await patientApi.doctorPatients({
      params: { search: query }
    })
    patients.value = response.data.data || []
  } catch (error) {
    console.error('搜索患者失败:', error)
    ElMessage.error('搜索患者失败')
  } finally {
    loading.value = false
  }
}

// 加载所有患者
const loadPatients = async () => {
  loading.value = true
  try {
    const response = await patientApi.doctorPatients()
    patients.value = response.data.data || []
  } catch (error) {
    console.error('加载患者列表失败:', error)
    ElMessage.error('加载患者列表失败')
  } finally {
    loading.value = false
  }
}

// 处理选择变化
const handleChange = (value) => {
  emit('update:modelValue', value)
  const patient = patients.value.find(p => p.id === value)
  emit('change', patient)
}

// 初始化加载患者列表
onMounted(() => {
  loadPatients()
})
</script>

<style scoped>
.patient-selector {
  width: 100%;
}

.patient-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.patient-name {
  font-weight: 600;
  color: #303133;
}

.patient-info {
  font-size: 12px;
  color: #909399;
}

html.dark .patient-name {
  color: #e2e8f0;
}

html.dark .patient-info {
  color: #94a3b8;
}
</style>
