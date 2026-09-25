<template>
  <div class="floating-ai-assistant">
    <!-- 悬浮按钮 -->
    <div
      class="floating-btn"
      :class="{ active: isOpen }"
      @click="toggleChat"
    >
      <el-icon v-if="!isOpen" size="26"><ChatDotRound /></el-icon>
      <el-icon v-else size="26"><Close /></el-icon>
      <div v-if="unreadCount > 0" class="unread-badge">{{ unreadCount }}</div>
    </div>

    <!-- 对话窗口 -->
    <transition name="chat-window">
      <div v-if="isOpen" class="chat-window" :class="{ maximized: isMaximized }">
        <!-- 头部 -->
        <div class="chat-header">
          <div class="header-left">
            <div class="header-icon">
              <el-icon size="18"><ChatDotRound /></el-icon>
            </div>
            <span class="header-title">健康助手</span>
            <span class="status-dot"></span>
          </div>
          <div class="header-actions">
            <button class="action-btn" @click="toggleMaximize" :title="isMaximized ? '还原' : '最大化'">
              <el-icon size="16"><component :is="isMaximized ? CopyDocument : FullScreen" /></el-icon>
            </button>
            <button class="action-btn" @click="clearChat" title="清空对话">
              <el-icon size="16"><Delete /></el-icon>
            </button>
            <button class="action-btn close" @click="toggleChat" title="关闭">
              <el-icon size="16"><Close /></el-icon>
            </button>
          </div>
        </div>

        <!-- 免责声明 -->
        <div v-if="showDisclaimer" class="disclaimer-section">
          <div class="disclaimer-box">
            <div class="disclaimer-icon">
              <el-icon size="20" color="#f59e0b"><Warning /></el-icon>
            </div>
            <div class="disclaimer-content">
              <h4>医疗免责声明</h4>
              <p>本助手提供的信息仅供参考，不能替代专业医生的诊断和治疗建议。</p>
              <p>如有紧急医疗问题，请立即联系您的主治医生或前往医院就诊。</p>
            </div>
            <button class="disclaimer-btn" @click="acceptDisclaimer">
              我已了解并同意
            </button>
          </div>
        </div>

        <!-- 消息区域 -->
        <div v-else ref="messagesContainer" class="messages-container" @click="onMessageClick">
          <!-- 欢迎消息 -->
          <div v-if="messages.length === 0" class="welcome-section">
            <div class="welcome-card">
              <div class="welcome-icon">
                <el-icon size="36" color="#0d9488"><FirstAidKit /></el-icon>
              </div>
              <h3 class="welcome-title">您好！我是您的健康助手</h3>
              <p class="welcome-desc">我可以帮您解答关于骨折康复、日常护理等方面的问题</p>
            </div>
            <div class="quick-questions">
              <div class="quick-label">您可能想了解</div>
              <div class="quick-chips">
                <button
                  v-for="(item, index) in quickQuestions"
                  :key="item.text"
                  class="quick-chip"
                  :class="`chip-${index % 5}`"
                  @click="sendQuickQuestion(item.text)"
                >
                  <span class="chip-dot"></span>
                  {{ item.text }}
                </button>
              </div>
            </div>
          </div>

          <!-- 消息列表 -->
          <template v-else>
            <div
              v-for="(msg, index) in messages"
              :key="msg.timestamp?.getTime?.() || index"
              :class="['message-item', msg.role]"
              :data-index="index"
            >
              <div class="message-avatar">
                <div v-if="msg.role === 'user'" class="user-avatar">
                  <el-icon size="16"><UserFilled /></el-icon>
                </div>
                <div v-else class="ai-avatar">
                  <el-icon size="16"><FirstAidKit /></el-icon>
                </div>
              </div>
              <div class="message-content">
                <!-- Agent 执行轨迹：让"模型自己决定了查什么"这件事可见。
                     放在回答上方，因为用户关心的是结论怎么来的 -->
                <div
                  v-if="msg.role === 'assistant' && msg.trace?.length"
                  class="agent-trace"
                >
                  <div
                    class="agent-trace-head"
                    @click="toggleTrace(index)"
                  >
                    <el-icon size="12"><Compass /></el-icon>
                    <span>分析过程（{{ msg.trace.filter(t => t.type === 'tool_result').length }} 步工具调用）</span>
                    <span class="agent-trace-toggle">{{ expandedTraces.has(index) ? '收起' : '展开' }}</span>
                  </div>
                  <div v-show="expandedTraces.has(index)" class="agent-trace-body">
                    <div
                      v-for="step in msg.trace"
                      :key="step.step"
                      :class="['agent-step', `is-${stepTone(step)}`]"
                    >
                      <span class="agent-step-dot"></span>
                      <span class="agent-step-text">{{ stepText(step) }}</span>
                      <span v-if="step.elapsed_ms >= 500" class="agent-step-time">
                        {{ (step.elapsed_ms / 1000).toFixed(1) }}s
                      </span>
                    </div>
                  </div>
                </div>
                <div class="message-bubble">
                  <div v-if="msg.role === 'assistant' && msg.isStreaming" class="streaming-text">
                    <span v-for="(char, i) in msg.content" :key="i" :style="{ animationDelay: `${i * 0.03}s` }">{{ char }}</span>
                    <span class="cursor">|</span>
                  </div>
                  <div v-else class="message-text" v-html="formatMessage(msg.content)"></div>
                  <!-- 引用溯源：回答里的 [1][2] 角标点击后在这里查到原文 -->
                  <CitationList
                    v-if="msg.role === 'assistant' && msg.references?.length"
                    :references="msg.references"
                    compact
                  />
                </div>
                <div class="message-meta">
                  <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                  <button
                    v-if="msg.role === 'assistant'"
                    class="copy-btn"
                    @click="copyMessage(msg.content)"
                  >
                    <el-icon size="12"><CopyDocument /></el-icon>
                    复制
                  </button>
                </div>
              </div>
            </div>
          </template>

          <!-- 加载中 -->
          <div v-if="isLoading" class="message-item assistant">
            <div class="message-avatar">
              <div class="ai-avatar">
                <el-icon size="16"><FirstAidKit /></el-icon>
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
            <div class="input-box">
              <textarea
                v-model="inputMessage"
                :rows="2"
                placeholder="请输入您的问题..."
                :disabled="isLoading"
                maxlength="500"
                @keydown.enter.exact.prevent="sendMessage"
              ></textarea>
            </div>
            <div class="input-toolbar">
              <label class="agent-toggle" :title="'开启后 AI 会自行查阅你的病历、检测报告与指南，多步分析后作答（较慢）'">
                <input v-model="agentMode" type="checkbox" :disabled="isLoading" />
                <span>深度分析</span>
              </label>
              <span v-if="agentMode" class="agent-toggle-hint">多步分析约需 30-90 秒</span>
              <span class="input-hint">
                <el-icon size="12"><InfoFilled /></el-icon>
                <template v-if="quotaDaily !== null">今日剩余 {{ quotaDaily }} 次 · </template>
                按 Enter 发送
              </span>
              <button
                class="send-btn"
                :disabled="!inputMessage.trim() || isLoading"
                :class="{ loading: isLoading }"
                @click="sendMessage"
              >
                <span v-if="!isLoading" class="send-text">发送</span>
                <span v-else class="loading-spinner"></span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 点击回答里的 [1] 角标后展示该条引用的原文片段 -->
    <el-dialog
      v-model="citationDialogVisible"
      :title="activeCitation ? `引用 [${activeCitation.index}]` : '引用'"
      width="620px"
      append-to-body
    >
      <div v-if="activeCitation" class="citation-detail">
        <div class="citation-detail-row">
          <span class="citation-detail-label">来源</span>
          <span>《{{ activeCitation.doc }}》</span>
        </div>
        <div v-if="activeCitation.section" class="citation-detail-row">
          <span class="citation-detail-label">章节</span>
          <span>{{ activeCitation.section }}</span>
        </div>
        <div v-if="activeCitation.page" class="citation-detail-row">
          <span class="citation-detail-label">页码</span>
          <span>第 {{ activeCitation.page }} 页</span>
        </div>
        <div class="citation-detail-row">
          <span class="citation-detail-label">性质</span>
          <span>{{ activeCitation.origin_label || activeCitation.origin }}</span>
        </div>
        <div v-if="activeCitation.source" class="citation-detail-row">
          <span class="citation-detail-label">出处</span>
          <span class="citation-detail-source">{{ activeCitation.source }}</span>
        </div>
        <div class="citation-detail-snippet">
          {{ activeCitation.snippet || activeCitation.content }}
        </div>
      </div>
    </el-dialog>
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
  UserFilled,
  FirstAidKit,
  Warning,
  InfoFilled,
  Clock,
  Food,
  QuestionFilled,
  TrendCharts,
  ArrowRight,
  Compass
} from '@element-plus/icons-vue'
import * as aiApi from '../api/ai'
import CitationList from './CitationList.vue'

const isOpen = ref(false)
const isMaximized = ref(false)
const showDisclaimer = ref(false)
const isLoading = ref(false)
const inputMessage = ref('')
const messages = ref([])
const messagesContainer = ref(null)
const unreadCount = ref(0)
const sessionId = ref('')
// 深度分析（Agent）：开启后走 /api/agent/chat，AI 自行决定查阅哪些资料。
// 默认关闭 —— 它比普通问答慢得多（多轮 LLM 调用），不该是默认体验。
const agentMode = ref(false)
// 展开的轨迹（按消息下标记录，避免给每条消息都塞一个展开态字段）
const expandedTraces = ref(new Set())
// 额度：优先读响应头（后端在成功响应里给），拿不到就不显示
const quotaDaily = ref(null)

// 常量定义
const STORAGE_KEYS = {
  SESSION_ID: 'ai_assistant_session_id',
  SESSION_TIME: 'ai_assistant_session_time',
  DISCLAIMER_ACCEPTED: 'ai_assistant_disclaimer_accepted'
}

const SESSION_DURATION = 24 * 60 * 60 * 1000 // 24小时

// 常见问题
const quickQuestions = [
  { text: '骨折后多久可以恢复？' },
  { text: '骨折康复期需要注意什么？' },
  { text: '骨折后饮食有什么建议？' },
  { text: '如何判断骨折愈合情况？' },
  { text: '骨折后可以做哪些康复运动？' }
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
  try {
    localStorage.setItem(STORAGE_KEYS.DISCLAIMER_ACCEPTED, 'true')
  } catch (e) {
    console.warn('localStorage 不可用:', e)
  }
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
  let savedSessionId = null
  let savedSessionTime = null
  let disclaimerAccepted = null

  try {
    savedSessionId = localStorage.getItem(STORAGE_KEYS.SESSION_ID)
    savedSessionTime = localStorage.getItem(STORAGE_KEYS.SESSION_TIME)
    disclaimerAccepted = localStorage.getItem(STORAGE_KEYS.DISCLAIMER_ACCEPTED)
  } catch (e) {
    console.warn('localStorage 不可用:', e)
  }

  // 检查免责声明
  showDisclaimer.value = disclaimerAccepted !== 'true'

  // 检查会话是否过期
  const now = Date.now()
  if (savedSessionId && savedSessionTime) {
    const elapsed = now - parseInt(savedSessionTime)
    if (elapsed < SESSION_DURATION) {
      sessionId.value = savedSessionId
      loadChatHistory()
      return
    }
  }

  // 创建新会话
  sessionId.value = generateSessionId()
  try {
    localStorage.setItem(STORAGE_KEYS.SESSION_ID, sessionId.value)
    localStorage.setItem(STORAGE_KEYS.SESSION_TIME, now.toString())
  } catch (e) {
    console.warn('localStorage 不可用:', e)
  }
}

// 加载聊天历史
const loadChatHistory = async () => {
  try {
    const response = await aiApi.history(sessionId.value)
    if (response.data.success && response.data.messages) {
      messages.value = response.data.messages.map(msg => ({
        role: msg.role,
        content: msg.content,
        // 引用随历史一起返回，刷新页面后引用卡片仍在
        references: msg.references || [],
        // 深度分析的执行轨迹也要能恢复，否则刷新后"分析过程"就没了
        trace: msg.agent_trace || [],
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
    // 必须显式放宽超时：axios 实例默认 30s，而接入 RAG 后
    // 一次回答实测需 30-45s（检索约 2s + 模型生成 30-45s），
    // 用默认值会在服务端已经成功返回 200 的情况下由浏览器先中断，
    // 用户看到的是"服务暂时不可用"，日志里却是一条成功的请求。
    // 深度分析更慢（多轮工具调用，实测 2 轮约 37-90s），所以再放宽一档。
    // 超时由 api 层按接口给（普通问答 180s / Agent 300s），
    // 调用点不必再各自记得传 —— 这正是收敛到接口层的收益之一
    const useAgent = agentMode.value
    const response = useAgent
      ? await aiApi.chatAgent(sessionId.value, message)
      : await aiApi.chat(sessionId.value, message)

    readQuota(response)

    if (response.data.success) {
      // 添加AI回复（含引用溯源；深度分析另有执行轨迹）
      messages.value.push({
        role: 'assistant',
        content: useAgent ? response.data.answer : response.data.reply,
        references: response.data.references || [],
        trace: useAgent ? (response.data.trace || []) : [],
        timestamp: new Date()
      })
      if (useAgent && response.data.trace?.length) {
        expandedTraces.value.add(messages.value.length - 1)
      }
      if (useAgent && response.data.degraded) {
        // 编排降级了（总开关关闭 / provider 不支持工具 / 模型失败后回退）——
        // 如实告知，否则用户以为得到的是多步分析的结论
        ElMessage.warning('本次未能完成多步分析，已按普通问答回答')
      }
    } else {
      throw new Error(response.data.error || 'AI服务响应失败')
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    let errorMsg = '抱歉，服务暂时不可用，请稍后再试'
    const data = error.response?.data
    if (data?.error) {
      errorMsg = quotaHint(data) || data.error
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

// 额度响应头 → 界面显示（后端只在成功响应里给，拿不到就保持上一次的值）
const readQuota = (response) => {
  const left = response.headers?.['x-quota-daily-remaining']
  if (left !== undefined && left !== null && left !== '') {
    quotaDaily.value = Number(left)
  }
}

// 额度用尽的提示与"请求过于频繁"语义不同，该分开说：
// 一个是"用完了"（新建会话 / 明日重置），一个是"太快了"（等一会）
const quotaHint = (data) => {
  // QUOTA_001 的文案后端已经写清楚了（"本次会话已达上限（30 次），新建会话可继续"），
  // 直接用它，别再拼一遍
  if (data.error_code === 'QUOTA_001') return data.error
  if (data.error_code === 'QUOTA_002') {
    const hours = data.retry_after
      ? Math.max(1, Math.round(data.retry_after / 3600))
      : null
    return `今日对话额度已用完${hours ? `，约 ${hours} 小时后（本地 00:00）重置` : '，明日 00:00 重置'}。`
  }
  return ''   // 其他错误（含 RATE_LIMIT_EXCEEDED）走原有文案
}

// 轨迹文案：工具名 → 用户看得懂的说法（后端返回的是给模型看的英文名）
const TOOL_LABELS = {
  search_guideline: '检索诊疗指南',
  query_medical_records: '查阅我的病历',
  get_patient_profile: '查阅我的健康档案',
  list_detection_reports: '查阅我的检测报告',
  get_followup_schedule: '查阅复诊安排'
}

const stepTone = (step) => {
  if (step.type === 'error' || step.status === 'llm_error') return 'error'
  if (step.type === 'guard') return 'warn'
  if (step.type === 'tool_result') {
    if (step.status === 'ok') return 'ok'
    if (step.status === 'permission_denied') return 'error'
    if (step.status === 'not_found' || step.status === 'unsupported') return 'warn'
    return 'warn'
  }
  return 'info'
}

const stepText = (step) => {
  if (step.type === 'tool_result') {
    const label = TOOL_LABELS[step.name] || step.name
    return `${label}：${step.summary}`
  }
  const head = {
    planner: '理解问题并决定下一步',
    guard: '到达上限，收尾',
    answer: '生成最终结论',
    error: '出错了'
  }[step.type] || step.type
  return step.summary ? `${head} —— ${step.summary}` : head
}

const toggleTrace = (index) => {
  const next = new Set(expandedTraces.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  expandedTraces.value = next
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
  const now = Date.now()
  try {
    localStorage.setItem(STORAGE_KEYS.SESSION_ID, sessionId.value)
    localStorage.setItem(STORAGE_KEYS.SESSION_TIME, now.toString())
  } catch (e) {
    console.warn('localStorage 不可用:', e)
  }
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

  // 使用 DOM API 进行安全的 HTML 转义
  const div = document.createElement('div')
  div.textContent = content
  let formatted = div.innerHTML

  // 处理换行
  formatted = formatted.replace(/\n/g, '<br>')

  // 处理粗体 **text**（在转义后替换，确保安全）
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // 处理斜体 *text*
  formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // 引用角标：把 [1] [2] 渲染成可点击的 <sup>
  // 放在**最后**一趟：前面的粗体/斜体规则先跑完，不会破坏这里插入的标签。
  // 此时内容已被 div.textContent 转义，插入的是固定标签，无注入风险。
  formatted = formatted.replace(
    /\[(\d{1,2})\]/g,
    (m, n) => `<sup class="cite-ref" data-cite="${n}">[${n}]</sup>`
  )

  return formatted
}

// 引用角标点击（事件委托）
// v-html 插入的内容不会被 Vue 编译，无法逐节点绑定事件，
// 因此在容器上统一处理，靠 data-index / data-cite 定位。
const onMessageClick = (event) => {
  const target = event.target.closest?.('.cite-ref')
  if (!target) return
  const item = target.closest('.message-item')
  const index = Number(item?.dataset.index)
  const refs = messages.value[index]?.references || []
  const ref = refs.find(r => Number(r.index) === Number(target.dataset.cite))
  if (!ref) return
  activeCitation.value = ref
  citationDialogVisible.value = true
}

const citationDialogVisible = ref(false)
const activeCitation = ref(null)

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
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}

/* 悬浮按钮 - 简约医疗风 */
.floating-btn {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 
    0 4px 20px rgba(13, 148, 136, 0.15),
    0 1px 3px rgba(0, 0, 0, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: #0d9488;
  position: relative;
  border: 1px solid #e2e8f0;
}

.floating-btn:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 
    0 8px 30px rgba(13, 148, 136, 0.2),
    0 2px 8px rgba(0, 0, 0, 0.05);
  background: #f0fdfa;
  border-color: #99f6e4;
}

.floating-btn:active {
  transform: translateY(0) scale(0.98);
}

.floating-btn.active {
  background: #fef2f2;
  color: #ef4444;
  border-color: #fecaca;
  box-shadow: 
    0 4px 20px rgba(239, 68, 68, 0.15),
    0 1px 3px rgba(0, 0, 0, 0.05);
}

.unread-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: #ef4444;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: white;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3);
}

/* 对话窗口 - 明亮大气 */
.chat-window {
  position: absolute;
  bottom: 72px;
  right: 0;
  width: 420px;
  height: 620px;
  background: #ffffff;
  border-radius: 24px;
  box-shadow: 
    0 25px 80px rgba(0, 0, 0, 0.12),
    0 10px 30px rgba(0, 0, 0, 0.08),
    0 0 0 1px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-window.maximized {
  width: 720px;
  height: 80vh;
}

/* 窗口动画 */
.chat-window-enter-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-window-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}

.chat-window-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}

.chat-window-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

/* 头部 - 清新简洁 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #ffffff;
  border-bottom: 1px solid #f1f5f9;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  width: 36px;
  height: 36px;
  background: #f0fdfa;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0d9488;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 0 2px #ffffff, 0 0 0 4px #d1fae5;
}

.header-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.action-btn.close:hover {
  background: #fef2f2;
  color: #ef4444;
}

/* 免责声明 - 温暖警示 */
.disclaimer-section {
  padding: 20px;
  background: #fffbeb;
  border-bottom: 1px solid #fef3c7;
}

.disclaimer-box {
  background: #ffffff;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.08);
  border: 1px solid #fef3c7;
}

.disclaimer-icon {
  width: 44px;
  height: 44px;
  background: #fff7ed;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.disclaimer-content h4 {
  font-size: 15px;
  font-weight: 600;
  color: #92400e;
  margin: 0 0 8px 0;
}

.disclaimer-content p {
  font-size: 13px;
  color: #a16207;
  margin: 4px 0;
  line-height: 1.5;
}

.disclaimer-btn {
  width: 100%;
  margin-top: 16px;
  padding: 10px 20px;
  background: #f59e0b;
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.disclaimer-btn:hover {
  background: #d97706;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

/* 消息区域 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #fafafa;
}

/* 欢迎区域 */
.welcome-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.welcome-card {
  background: #ffffff;
  border-radius: 20px;
  padding: 32px 24px;
  text-align: center;
  box-shadow: 
    0 4px 20px rgba(0, 0, 0, 0.03),
    0 1px 3px rgba(0, 0, 0, 0.02);
  border: 1px solid #f1f5f9;
}

.welcome-icon {
  width: 72px;
  height: 72px;
  background: #f0fdfa;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  border: 1px solid #ccfbf1;
}

.welcome-title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
  margin: 0 0 8px 0;
}

.welcome-desc {
  font-size: 14px;
  color: #64748b;
  margin: 0;
  line-height: 1.5;
}

.quick-questions {
  padding: 8px 4px;
}

.quick-label {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
  font-weight: 500;
}

.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-chip {
  padding: 8px 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: inherit;
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: all 0.2s ease;
}

.quick-chip:hover {
  background: #0d9488;
  border-color: #0d9488;
  color: #ffffff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.25);
}

.quick-chip:hover .chip-dot {
  background: rgba(255, 255, 255, 0.8);
}

/* 交替颜色 */
.quick-chip.chip-1:hover {
  background: #3b82f6;
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
}

.quick-chip.chip-2:hover {
  background: #f59e0b;
  border-color: #f59e0b;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
}

.quick-chip.chip-3:hover {
  background: #8b5cf6;
  border-color: #8b5cf6;
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.25);
}

.quick-chip.chip-4:hover {
  background: #ec4899;
  border-color: #ec4899;
  box-shadow: 0 4px 12px rgba(236, 72, 153, 0.25);
}

/* 消息项 */
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  animation: message-in 0.3s ease;
}

@keyframes message-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.user-avatar {
  width: 36px;
  height: 36px;
  background: #e2e8f0;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
}

.ai-avatar {
  width: 36px;
  height: 36px;
  background: #0d9488;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 2px 8px rgba(13, 148, 136, 0.25);
}

.message-content {
  flex: 1;
  max-width: 78%;
}

.message-item.user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-bubble {
  padding: 14px 18px;
  border-radius: 18px;
  line-height: 1.6;
  word-wrap: break-word;
  font-size: 14px;
}

.message-item.user .message-bubble {
  background: #0d9488;
  color: white;
  border-radius: 18px 18px 4px 18px;
  box-shadow: 0 2px 8px rgba(13, 148, 136, 0.25);
}

.message-item.assistant .message-bubble {
  background: #ffffff;
  color: #0f172a;
  border-radius: 18px 18px 18px 4px;
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.04),
    0 1px 2px rgba(0, 0, 0, 0.02);
  border: 1px solid #f1f5f9;
}

.loading-bubble {
  padding: 18px 22px;
}

.message-text {
  white-space: pre-wrap;
}

/* 回答里的引用角标 [1] —— 由 formatMessage 生成，见 onMessageClick */
.message-text :deep(.cite-ref) {
  color: #0d9488;
  font-weight: 600;
  cursor: pointer;
  padding: 0 1px;
  border-radius: 3px;
}

.message-text :deep(.cite-ref:hover) {
  background: #f0fdfa;
  text-decoration: underline;
}

/* 引用详情弹窗 */
.citation-detail {
  font-size: 13px;
  line-height: 1.7;
}

.citation-detail-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.citation-detail-label {
  flex-shrink: 0;
  width: 44px;
  color: #909399;
}

.citation-detail-source {
  word-break: break-all;
}

.citation-detail-snippet {
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}

html.dark .citation-detail-snippet {
  background: #262727;
  color: #e5eaf3;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  padding: 0 6px;
}

.message-time {
  font-size: 11px;
  color: #94a3b8;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
}

.copy-btn:hover {
  background: #f1f5f9;
  color: #64748b;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 4px;
  align-items: center;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
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
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* 输入区域 */
.input-section {
  padding: 16px 20px 20px;
  background: #ffffff;
  border-top: 1px solid #f1f5f9;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-box {
  background: #f8fafc;
  border-radius: 16px;
  padding: 14px 18px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s ease;
}

.input-box:focus-within {
  background: #ffffff;
  border-color: #99f6e4;
  box-shadow: 0 0 0 3px rgba(153, 246, 228, 0.3);
}

.input-box textarea {
  width: 100%;
  border: none;
  background: transparent;
  resize: none;
  font-size: 15px;
  line-height: 1.6;
  color: #0f172a;
  outline: none;
  font-family: inherit;
  min-height: 44px;
}

.input-box textarea::placeholder {
  color: #94a3b8;
}

.input-box textarea:disabled {
  opacity: 0.6;
}

.input-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.input-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
}

/* 深度分析开关：默认关闭，开启后走 Agent 端点（多轮工具调用，慢但更全面） */
.agent-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #0d9488;
  cursor: pointer;
  user-select: none;
}

.agent-toggle input {
  width: 13px;
  height: 13px;
  accent-color: #0d9488;
  cursor: pointer;
}

.agent-toggle-hint {
  font-size: 11px;
  color: #94a3b8;
}

/* Agent 执行轨迹 */
.agent-trace {
  margin-bottom: 6px;
  border: 1px solid #99f6e4;
  border-radius: 8px;
  background: #f0fdfa;
  overflow: hidden;
}

.agent-trace-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: #0d9488;
  cursor: pointer;
}

.agent-trace-toggle {
  margin-left: auto;
  color: #64748b;
}

.agent-trace-body {
  padding: 2px 10px 8px;
  border-top: 1px dashed #99f6e4;
}

.agent-step {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 3px 0;
  font-size: 12px;
  color: #334155;
  line-height: 1.5;
}

.agent-step-dot {
  flex: none;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.agent-step.is-ok .agent-step-dot { background: #10b981; }
.agent-step.is-warn .agent-step-dot { background: #f59e0b; }
.agent-step.is-error .agent-step-dot { background: #ef4444; }
.agent-step.is-info .agent-step-dot { background: #0d9488; }

.agent-step-text {
  flex: 1;
}

.agent-step-time {
  flex: none;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.send-btn {
  height: 38px;
  padding: 0 20px;
  border-radius: 10px;
  border: none;
  background: #0d9488;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(13, 148, 136, 0.25);
  font-size: 14px;
  font-weight: 500;
}

.send-btn:hover:not(:disabled) {
  background: #0f766e;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.35);
}

.send-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  box-shadow: none;
}

.send-btn.loading {
  background: #cbd5e1;
  padding: 0 16px;
}

.send-text {
  font-weight: 500;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 6px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #e2e8f0;
  border-radius: 3px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #cbd5e1;
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
    border-radius: 20px 20px 0 0;
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
