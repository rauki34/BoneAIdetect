<template>
  <div class="floating-ai-assistant">
    <!-- 悬浮按钮 -->
    <div
      class="floating-btn"
      :class="{ active: isOpen }"
      @click="toggleChat"
    >
      <el-icon v-if="!isOpen" size="28"><ChatDotRound /></el-icon>
      <el-icon v-else size="28"><Close /></el-icon>
      <div v-if="unreadCount > 0" class="unread-badge">{{ unreadCount }}</div>
    </div>

    <!-- 对话窗口 -->
    <transition name="chat-window">
      <div v-if="isOpen" class="chat-window" :class="{ maximized: isMaximized }">
        <!-- 头部 -->
        <div class="chat-header">
          <div class="header-left">
            <el-icon size="20"><ChatDotRound /></el-icon>
            <span class="header-title">AI健康助手</span>
            <el-tag size="small" type="success" effect="light">在线</el-tag>
          </div>
          <div class="header-actions">
            <el-button
              text
              circle
              size="small"
              @click="toggleMaximize"
              :icon="isMaximized ? CopyDocument : FullScreen"
            />
            <el-button
              text
              circle
              size="small"
              @click="clearChat"
              :icon="Delete"
              title="清空对话"
            />
            <el-button
              text
              circle
              size="small"
              @click="toggleChat"
              :icon="Close"
            />
          </div>
        </div>

        <!-- 免责声明 -->
        <div v-if="showDisclaimer" class="disclaimer-section">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
          >
            <template #title>
              <span class="disclaimer-title">医疗免责声明</span>
            </template>
            <div class="disclaimer-content">
              <p>本AI助手提供的信息仅供参考，不能替代专业医生的诊断和治疗建议。</p>
              <p>如有紧急医疗问题，请立即联系您的主治医生或前往医院就诊。</p>
            </div>
            <div class="disclaimer-actions">
              <el-button type="primary" size="small" @click="acceptDisclaimer">
                我已了解并同意
              </el-button>
            </div>
          </el-alert>
        </div>

        <!-- 消息区域 -->
        <div v-else ref="messagesContainer" class="messages-container">
          <!-- 欢迎消息 -->
          <div v-if="messages.length === 0" class="welcome-section">
            <div class="welcome-icon">
              <el-icon size="48" color="#3b82f6"><FirstAidKit /></el-icon>
            </div>
            <h3 class="welcome-title">您好！我是您的AI健康助手</h3>
            <p class="welcome-desc">我可以帮您解答关于骨折康复、日常护理等方面的问题</p>
            <div class="quick-questions">
              <div class="quick-title">常见问题：</div>
              <div class="quick-tags">
                <el-tag
                  v-for="question in quickQuestions"
                  :key="question"
                  class="quick-tag"
                  effect="light"
                  @click="sendQuickQuestion(question)"
                >
                  {{ question }}
                </el-tag>
              </div>
            </div>
          </div>

          <!-- 消息列表 -->
          <template v-else>
            <div
              v-for="(msg, index) in messages"
              :key="index"
              :class="['message-item', msg.role]"
            >
              <div class="message-avatar">
                <el-avatar
                  v-if="msg.role === 'user'"
                  :size="36"
                  :icon="UserFilled"
                  class="user-avatar"
                />
                <div v-else class="ai-avatar">
                  <el-icon size="20"><Cpu /></el-icon>
                </div>
              </div>
              <div class="message-content">
                <div class="message-bubble">
                  <div v-if="msg.role === 'assistant' && msg.isStreaming" class="streaming-text">
                    <span v-for="(char, i) in msg.content" :key="i" :style="{ animationDelay: `${i * 0.03}s` }">{{ char }}</span>
                    <span class="cursor">|</span>
                  </div>
                  <div v-else class="message-text" v-html="formatMessage(msg.content)"></div>
                </div>
                <div class="message-meta">
                  <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                  <el-button
                    v-if="msg.role === 'assistant'"
                    link
                    type="primary"
                    size="small"
                    :icon="CopyDocument"
                    @click="copyMessage(msg.content)"
                  >
                    复制
                  </el-button>
                </div>
              </div>
            </div>
          </template>

          <!-- 加载中 -->
          <div v-if="isLoading" class="message-item assistant">
            <div class="message-avatar">
              <div class="ai-avatar">
                <el-icon size="20"><Cpu /></el-icon>
              </div>
            </div>
            <div class="message-content">
              <div class="message-bubble loading-bubble">
                <div class="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区域 -->
        <div v-if="!showDisclaimer" class="input-section">
          <div class="input-wrapper">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="2"
              placeholder="请输入您的问题..."
              :disabled="isLoading"
              maxlength="500"
              show-word-limit
              @keydown.enter.exact.prevent="sendMessage"
            />
            <div class="input-actions">
              <span class="input-hint">按 Enter 发送，Shift + Enter 换行</span>
              <el-button
                type="primary"
                :disabled="!inputMessage.trim() || isLoading"
                :loading="isLoading"
                @click="sendMessage"
              >
                <el-icon><Promotion /></el-icon>
                发送
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Close,
  FullScreen,
  CopyDocument,
  Delete,
  Promotion,
  UserFilled,
  Cpu,
  FirstAidKit
} from '@element-plus/icons-vue'
import axios from '../utils/axios'

const isOpen = ref(false)
const isMaximized = ref(false)
const showDisclaimer = ref(false)
const isLoading = ref(false)
const inputMessage = ref('')
const messages = ref([])
const messagesContainer = ref(null)
const unreadCount = ref(0)
const sessionId = ref('')

// 常见问题
const quickQuestions = [
  '骨折后多久可以恢复？',
  '骨折康复期需要注意什么？',
  '骨折后饮食有什么建议？',
  '如何判断骨折愈合情况？',
  '骨折后可以做哪些康复运动？'
]

// 切换聊天窗口
const toggleChat = () => {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    unreadCount.value = 0
    nextTick(() => {
      scrollToBottom()
    })
  }
}

// 切换最大化
const toggleMaximize = () => {
  isMaximized.value = !isMaximized.value
  nextTick(() => {
    scrollToBottom()
  })
}

// 接受免责声明
const acceptDisclaimer = () => {
  showDisclaimer.value = false
  localStorage.setItem('ai_assistant_disclaimer_accepted', 'true')
  nextTick(() => {
    scrollToBottom()
  })
}

// 生成会话ID
const generateSessionId = () => {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
}

// 初始化会话
const initSession = () => {
  const savedSessionId = localStorage.getItem('ai_assistant_session_id')
  const savedSessionTime = localStorage.getItem('ai_assistant_session_time')
  const disclaimerAccepted = localStorage.getItem('ai_assistant_disclaimer_accepted')
  
  // 检查免责声明
  showDisclaimer.value = disclaimerAccepted !== 'true'
  
  // 检查会话是否过期（24小时）
  const now = Date.now()
  if (savedSessionId && savedSessionTime) {
    const elapsed = now - parseInt(savedSessionTime)
    if (elapsed < 24 * 60 * 60 * 1000) {
      sessionId.value = savedSessionId
      loadChatHistory()
      return
    }
  }
  
  // 创建新会话
  sessionId.value = generateSessionId()
  localStorage.setItem('ai_assistant_session_id', sessionId.value)
  localStorage.setItem('ai_assistant_session_time', now.toString())
}

// 加载聊天历史
const loadChatHistory = async () => {
  try {
    const response = await axios.get('/api/ai-assistant/history', {
      params: { session_id: sessionId.value }
    })
    if (response.data.success && response.data.messages) {
      messages.value = response.data.messages.map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp)
      }))
      nextTick(() => scrollToBottom())
    }
  } catch (error) {
    console.error('加载历史记录失败:', error)
  }
}

// 发送消息
const sendMessage = async () => {
  const message = inputMessage.value.trim()
  if (!message || isLoading.value) return
  
  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: message,
    timestamp: new Date()
  })
  
  inputMessage.value = ''
  isLoading.value = true
  
  nextTick(() => scrollToBottom())
  
  try {
    const response = await axios.post('/api/ai-assistant/chat', {
      session_id: sessionId.value,
      message: message
    })
    
    if (response.data.success) {
      // 添加AI回复
      messages.value.push({
        role: 'assistant',
        content: response.data.reply,
        timestamp: new Date()
      })
    } else {
      throw new Error(response.data.error || 'AI服务响应失败')
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    let errorMsg = '抱歉，服务暂时不可用，请稍后再试'
    if (error.response?.data?.error) {
      errorMsg = error.response.data.error
    }
    messages.value.push({
      role: 'assistant',
      content: errorMsg,
      timestamp: new Date()
    })
  } finally {
    isLoading.value = false
    nextTick(() => scrollToBottom())
  }
}

// 发送快捷问题
const sendQuickQuestion = (question) => {
  inputMessage.value = question
  sendMessage()
}

// 清空对话
const clearChat = () => {
  messages.value = []
  // 创建新会话
  sessionId.value = generateSessionId()
  localStorage.setItem('ai_assistant_session_id', sessionId.value)
  localStorage.setItem('ai_assistant_session_time', Date.now().toString())
  ElMessage.success('对话已清空')
}

// 复制消息
const copyMessage = async (content) => {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('已复制到剪贴板')
  } catch (err) {
    ElMessage.error('复制失败')
  }
}

// 格式化消息（简单的文本格式化）
const formatMessage = (content) => {
  if (!content) return ''
  // 转义HTML
  let formatted = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 处理换行
  formatted = formatted.replace(/\n/g, '<br>')
  
  // 处理粗体 **text**
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  
  // 处理斜体 *text*
  formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>')
  
  return formatted
}

// 格式化时间
const formatTime = (date) => {
  if (!date) return ''
  const now = new Date()
  const msgDate = new Date(date)
  const diff = now - msgDate
  
  // 今天内显示时间
  if (diff < 24 * 60 * 60 * 1000 && now.getDate() === msgDate.getDate()) {
    return msgDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  // 昨天显示昨天
  if (diff < 48 * 60 * 60 * 1000 && now.getDate() - msgDate.getDate() === 1) {
    return '昨天 ' + msgDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  // 其他显示日期时间
  return msgDate.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// 滚动到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 监听消息变化
watch(messages, () => {
  nextTick(() => scrollToBottom())
}, { deep: true })

onMounted(() => {
  initSession()
})

// 暴露方法给父组件
defineExpose({
  open: () => { isOpen.value = true },
  close: () => { isOpen.value = false },
  toggle: () => { isOpen.value = !isOpen.value }
})
</script>

<style scoped>
.floating-ai-assistant {
  position: fixed;
  bottom: 30px;
  right: 30px;
  z-index: 9999;
}

/* 悬浮按钮 */
.floating-btn {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
  transition: all 0.3s ease;
  color: white;
  position: relative;
}

.floating-btn:hover {
  transform: scale(1.1) rotate(5deg);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
}

.floating-btn.active {
  background: linear-gradient(135deg, #ef4444 0%, #f97316 100%);
  box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
}

.unread-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 20px;
  height: 20px;
  background: #ef4444;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  color: white;
  border: 2px solid white;
}

/* 对话窗口 */
.chat-window {
  position: absolute;
  bottom: 80px;
  right: 0;
  width: 400px;
  height: 600px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.3s ease;
}

.chat-window.maximized {
  width: 700px;
  height: 80vh;
}

/* 窗口动画 */
.chat-window-enter-active,
.chat-window-leave-active {
  transition: all 0.3s ease;
}

.chat-window-enter-from,
.chat-window-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

/* 头部 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  color: white;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 4px;
}

.header-actions .el-button {
  color: white;
}

.header-actions .el-button:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* 免责声明 */
.disclaimer-section {
  padding: 20px;
  background: #fffbeb;
  border-bottom: 1px solid #fcd34d;
}

.disclaimer-title {
  font-weight: 600;
  color: #92400e;
}

.disclaimer-content {
  margin: 12px 0;
  font-size: 13px;
  color: #78350f;
  line-height: 1.6;
}

.disclaimer-content p {
  margin: 4px 0;
}

.disclaimer-actions {
  margin-top: 12px;
}

/* 消息区域 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f8fafc;
}

/* 欢迎区域 */
.welcome-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 40px 20px;
}

.welcome-icon {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #dbeafe 0%, #e0e7ff 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.welcome-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 8px 0;
}

.welcome-desc {
  font-size: 14px;
  color: #64748b;
  margin: 0 0 24px 0;
}

.quick-questions {
  width: 100%;
}

.quick-title {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
}

.quick-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.quick-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.quick-tag:hover {
  background: #3b82f6;
  color: white;
}

/* 消息项 */
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.user-avatar {
  background: #3b82f6;
}

.ai-avatar {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.message-content {
  flex: 1;
  max-width: 75%;
}

.message-item.user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.6;
  word-wrap: break-word;
}

.message-item.user .message-bubble {
  background: #3b82f6;
  color: white;
  border-radius: 16px 16px 4px 16px;
}

.message-item.assistant .message-bubble {
  background: white;
  color: #1e293b;
  border-radius: 16px 16px 16px 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.loading-bubble {
  padding: 16px 20px;
}

.message-text {
  white-space: pre-wrap;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding: 0 4px;
}

.message-time {
  font-size: 11px;
  color: #94a3b8;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 4px;
  align-items: center;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #cbd5e1;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-indicator span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes typing {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* 输入区域 */
.input-section {
  padding: 16px 20px;
  background: white;
  border-top: 1px solid #e2e8f0;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.input-hint {
  font-size: 12px;
  color: #94a3b8;
}

/* 滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 6px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chat-window {
    position: fixed;
    bottom: 0;
    right: 0;
    left: 0;
    width: 100%;
    height: 80vh;
    border-radius: 16px 16px 0 0;
  }
  
  .chat-window.maximized {
    width: 100%;
    height: 100vh;
    border-radius: 0;
  }
  
  .floating-btn {
    bottom: 20px;
    right: 20px;
  }
}
</style>
