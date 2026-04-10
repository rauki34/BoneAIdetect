<template>
  <div v-if="visible" class="ai-assistant" :class="{ minimized, maximized }">
    <!-- Header -->
    <div class="ai-header">
      <div class="ai-title">
        <el-icon><ChatDotRound /></el-icon>
        <span>AI助手</span>
      </div>
      <div class="ai-controls">
        <el-button
          text
          circle
          size="small"
          @click="toggleMinimize"
          :icon="minimized ? Expand : Minus"
        />
        <el-button
          v-if="!minimized"
          text
          circle
          size="small"
          @click="toggleMaximize"
          :icon="maximized ? CopyDocument : FullScreen"
        />
        <el-button
          text
          circle
          size="small"
          @click="closeAssistant"
          :icon="Close"
        />
      </div>
    </div>

    <!-- Content (hidden when minimized) -->
    <div v-if="!minimized" class="ai-content">
      <!-- Disclaimer -->
      <div v-if="showDisclaimer" class="ai-disclaimer">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <div class="disclaimer-title">免责声明</div>
          </template>
          <div class="disclaimer-text">
            本AI助手提供的信息仅供参考,不能替代专业医生的诊断和建议。
            如有疑问,请及时咨询您的主治医生。
          </div>
          <el-button
            type="primary"
            size="small"
            style="margin-top: 8px;"
            @click="acceptDisclaimer"
          >
            我已了解
          </el-button>
        </el-alert>
      </div>

      <!-- Context Info -->
      <div v-if="contextReport && !showDisclaimer" class="ai-context-info">
        <el-tag size="small" type="info">
          <el-icon><Document /></el-icon>
          当前上下文: 报告 #{{ contextReport.id }}
        </el-tag>
      </div>

      <!-- Messages -->
      <div ref="messagesContainer" class="ai-messages">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['ai-message', msg.type]"
        >
          <div class="message-avatar">
            <el-icon v-if="msg.type === 'user'"><User /></el-icon>
            <el-icon v-else><Cpu /></el-icon>
          </div>
          <div class="message-content">
            <div class="message-text">{{ msg.content }}</div>
            <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
        </div>

        <!-- Loading indicator -->
        <div v-if="loading" class="ai-message assistant">
          <div class="message-avatar">
            <el-icon><Cpu /></el-icon>
          </div>
          <div class="message-content">
            <div class="message-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              AI思考中...
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="messages.length === 0 && !loading && !showDisclaimer" class="ai-empty">
          <el-icon><ChatDotRound /></el-icon>
          <p>您好!我是AI助手,有什么可以帮您的吗?</p>
        </div>
      </div>

      <!-- Input -->
      <div v-if="!showDisclaimer" class="ai-input">
        <el-input
          v-model="userInput"
          type="textarea"
          :rows="2"
          placeholder="输入您的问题..."
          :disabled="loading"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <el-button
          type="primary"
          :disabled="!userInput.trim() || loading"
          :loading="loading"
          @click="sendMessage"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import axios from '../utils/axios'
import { formatDateTime } from '../utils/datetime'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Minus,
  Expand,
  FullScreen,
  CopyDocument,
  Close,
  Document,
  User,
  Cpu,
  Loading,
  Promotion
} from '@element-plus/icons-vue'
// Simple UUID generator
const generateUUID = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

const props = defineProps({
  reportId: {
    type: Number,
    default: null
  }
})

const visible = ref(true)
const minimized = ref(false)
const maximized = ref(false)
const showDisclaimer = ref(true)
const loading = ref(false)
const userInput = ref('')
const messages = ref([])
const messagesContainer = ref(null)
const sessionId = ref(null)
const contextReport = ref(null)

// Toggle minimize
const toggleMinimize = () => {
  minimized.value = !minimized.value
  if (!minimized.value) {
    nextTick(() => scrollToBottom())
  }
}

// Toggle maximize
const toggleMaximize = () => {
  maximized.value = !maximized.value
  nextTick(() => scrollToBottom())
}

// Close assistant
const closeAssistant = () => {
  visible.value = false
}

// Accept disclaimer
const acceptDisclaimer = () => {
  showDisclaimer.value = false
  nextTick(() => scrollToBottom())
}

// Initialize session
const initializeSession = () => {
  // Try to load session from localStorage
  const savedSessionId = localStorage.getItem('ai_session_id')
  const savedSessionTime = localStorage.getItem('ai_session_time')
  
  // Check if session is still valid (30 minutes)
  const now = Date.now()
  if (savedSessionId && savedSessionTime) {
    const elapsed = now - parseInt(savedSessionTime)
    if (elapsed < 30 * 60 * 1000) {
      sessionId.value = savedSessionId
      return
    }
  }
  
  // Create new session
  sessionId.value = generateUUID()
  localStorage.setItem('ai_session_id', sessionId.value)
  localStorage.setItem('ai_session_time', now.toString())
}

// Load conversation history
const loadHistory = async () => {
  if (!sessionId.value) return
  
  try {
    const params = {
      session_id: sessionId.value
    }
    
    if (props.reportId) {
      params.report_id = props.reportId
    }
    
    const response = await axios.get('/api/patient/ai/history', { params })
    
    if (response.data.success && response.data.data) {
      messages.value = response.data.data.map(msg => ({
        type: msg.message_type === 'user' ? 'user' : 'assistant',
        content: msg.message_content,
        timestamp: new Date(msg.created_at)
      }))
      
      nextTick(() => scrollToBottom())
    }
  } catch (error) {
    console.error('加载对话历史失败:', error)
    // Don't show error message for history loading failure
  }
}

// Load report context
const loadReportContext = async (reportId) => {
  if (!reportId) {
    contextReport.value = null
    return
  }
  
  try {
    const response = await axios.get(`/api/patient/reports/${reportId}`)
    if (response.data.report) {
      contextReport.value = response.data.report
    }
  } catch (error) {
    console.error('加载报告上下文失败:', error)
    contextReport.value = null
  }
}

// Send message
const sendMessage = async () => {
  if (!userInput.value.trim() || loading.value) return
  
  const message = userInput.value.trim()
  userInput.value = ''
  
  // Add user message to UI
  messages.value.push({
    type: 'user',
    content: message,
    timestamp: new Date()
  })
  
  nextTick(() => scrollToBottom())
  
  // Update session time
  localStorage.setItem('ai_session_time', Date.now().toString())
  
  loading.value = true
  
  try {
    const requestData = {
      session_id: sessionId.value,
      message: message
    }
    
    if (props.reportId) {
      requestData.report_id = props.reportId
    }
    
    const response = await axios.post('/api/patient/ai/chat', requestData)
    
    if (response.data.success) {
      // Add AI response to UI
      messages.value.push({
        type: 'assistant',
        content: response.data.reply,
        timestamp: new Date()
      })
      
      nextTick(() => scrollToBottom())
    } else {
      throw new Error(response.data.error || 'AI服务响应失败')
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    
    let errorMessage = 'AI服务暂时不可用,请稍后再试'
    
    if (error.response?.status === 503) {
      errorMessage = 'AI服务暂时不可用,请稍后再试'
    } else if (error.response?.status === 504) {
      errorMessage = 'AI服务响应超时,请稍后再试'
    } else if (error.response?.data?.error) {
      errorMessage = error.response.data.error
    }
    
    ElMessage.error(errorMessage)
    
    // Add error message to chat
    messages.value.push({
      type: 'assistant',
      content: `抱歉,${errorMessage}`,
      timestamp: new Date()
    })
    
    nextTick(() => scrollToBottom())
  } finally {
    loading.value = false
  }
}

// Scroll to bottom
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// Watch reportId changes
watch(() => props.reportId, (newReportId) => {
  loadReportContext(newReportId)
  
  // Reload history when report changes
  if (newReportId && sessionId.value) {
    loadHistory()
  }
})

// Initialize on mount
onMounted(() => {
  initializeSession()
  loadReportContext(props.reportId)
  loadHistory()
})

// Expose methods
defineExpose({
  show: () => { visible.value = true },
  hide: () => { visible.value = false },
  toggle: () => { visible.value = !visible.value }
})
</script>

<style scoped>
.ai-assistant {
  position: fixed;
  bottom: 30px;
  right: 30px;
  width: 380px;
  height: 600px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 2000;
  transition: all 0.3s ease;
}

.ai-assistant.minimized {
  height: 56px;
}

.ai-assistant.maximized {
  width: 600px;
  height: 80vh;
  bottom: 20px;
  right: 20px;
}

.ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 12px 12px 0 0;
  cursor: move;
}

.ai-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 16px;
}

.ai-controls {
  display: flex;
  gap: 4px;
}

.ai-controls .el-button {
  color: #fff;
}

.ai-controls .el-button:hover {
  background: rgba(255, 255, 255, 0.2);
}

.ai-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.ai-disclaimer {
  padding: 16px;
  background: #fff9e6;
}

.disclaimer-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.disclaimer-text {
  font-size: 13px;
  line-height: 1.6;
  color: #666;
}

.ai-context-info {
  padding: 8px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.ai-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f5f7fa;
}

.ai-message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.ai-message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
}

.ai-message.user .message-avatar {
  background: #409eff;
  color: #fff;
}

.ai-message.assistant .message-avatar {
  background: #667eea;
  color: #fff;
}

.message-content {
  flex: 1;
  max-width: 70%;
}

.ai-message.user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-text {
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.ai-message.user .message-text {
  background: #409eff;
  color: #fff;
  border-radius: 12px 12px 0 12px;
}

.ai-message.assistant .message-text {
  background: #fff;
  color: #303133;
  border-radius: 12px 12px 12px 0;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.message-time {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
  padding: 0 4px;
}

.message-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fff;
  border-radius: 12px 12px 12px 0;
  color: #909399;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.ai-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  font-size: 14px;
}

.ai-empty .el-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.ai-input {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  border-radius: 0 0 12px 12px;
}

.ai-input .el-textarea {
  flex: 1;
}

.ai-input .el-button {
  align-self: flex-end;
}

/* Dark mode support */
html.dark .ai-assistant {
  background: #1e293b;
}

html.dark .ai-messages {
  background: #0f172a;
}

html.dark .ai-message.assistant .message-text {
  background: #1e293b;
  color: #e2e8f0;
}

html.dark .message-loading {
  background: #1e293b;
  color: #94a3b8;
}

html.dark .ai-input {
  background: #1e293b;
  border-top-color: #334155;
}

html.dark .ai-context-info {
  background: #1e293b;
  border-bottom-color: #334155;
}

/* Scrollbar styling */
.ai-messages::-webkit-scrollbar {
  width: 6px;
}

.ai-messages::-webkit-scrollbar-track {
  background: transparent;
}

.ai-messages::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 3px;
}

.ai-messages::-webkit-scrollbar-thumb:hover {
  background: #c0c4cc;
}
</style>
