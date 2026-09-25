<template>
  <el-dialog
    v-model="visible"
    title="编辑报告"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form :model="form" label-width="120px">
      <el-form-item label="患者姓名">
        <el-input v-model="reportData.patient_name" disabled />
      </el-form-item>
      
      <el-form-item label="检测时间">
        <el-input v-model="reportData.timestamp" disabled />
      </el-form-item>
      
      <el-form-item label="检测结果">
        <el-tag
          v-for="(detection, index) in reportData.detections"
          :key="index"
          style="margin-right: 8px; margin-bottom: 8px;"
        >
          {{ detection.class }} ({{ (detection.confidence * 100).toFixed(1) }}%)
        </el-tag>
      </el-form-item>
      
      <el-divider />
      
      <el-form-item label="诊断结论" required>
        <el-input
          v-model="form.diagnosis"
          type="textarea"
          :rows="6"
          placeholder="请输入诊断结论..."
        />
      </el-form-item>
      
      <el-form-item label="随访备注">
        <el-input
          v-model="form.follow_up_notes"
          type="textarea"
          :rows="6"
          placeholder="请输入随访备注..."
        />
      </el-form-item>
      
      <el-form-item label="最后修改时间" v-if="reportData.updated_at">
        <el-text type="info">{{ formatDateTime(reportData.updated_at) }}</el-text>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSubmit"
      >
        保存修改
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import * as doctorApi from '../api/doctor'
import { ElMessage } from 'element-plus'
import { formatDateTime } from '../utils/datetime'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  report: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = ref(props.modelValue)
const loading = ref(false)
const reportData = ref({})
const form = ref({
  diagnosis: '',
  follow_up_notes: ''
})

// 监听 modelValue 变化
watch(() => props.modelValue, (newVal) => {
  visible.value = newVal
  if (newVal && props.report) {
    loadReportData()
  }
})

// 监听 visible 变化
watch(visible, (newVal) => {
  emit('update:modelValue', newVal)
})

// 加载报告数据
const loadReportData = () => {
  reportData.value = { ...props.report }
  form.value = {
    diagnosis: props.report.diagnosis || '',
    follow_up_notes: props.report.follow_up_notes || ''
  }
}

// 提交修改
const handleSubmit = async () => {
  if (!form.value.diagnosis && !form.value.follow_up_notes) {
    ElMessage.warning('请至少填写诊断结论或随访备注')
    return
  }
  
  loading.value = true
  try {
    await doctorApi.updateReport(props.report.id, {
      diagnosis: form.value.diagnosis,
      follow_up_notes: form.value.follow_up_notes
    })
    
    ElMessage.success('报告更新成功')
    emit('success')
    handleClose()
  } catch (error) {
    console.error('更新报告失败:', error)
    const errorMsg = error.response?.data?.error || '更新报告失败'
    ElMessage.error(errorMsg)
  } finally {
    loading.value = false
  }
}

// 关闭对话框
const handleClose = () => {
  visible.value = false
  form.value = {
    diagnosis: '',
    follow_up_notes: ''
  }
}
</script>

<style scoped>
.el-form-item {
  margin-bottom: 20px;
}
</style>
