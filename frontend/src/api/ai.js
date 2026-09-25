/**
 * AI 助手 / Agent 相关接口
 *
 * 超时值都写在这里，调用点不必再各自传：这是"每个接口的超时只写一处"的落点。
 *
 *   CHAT_TIMEOUT    普通问答：接入 RAG 后实测单次回答 30-45s，默认 30s 会把
 *                   服务端已经成功的请求判成失败（浏览器先中断，日志里却是
 *                   一条 200）
 *   AGENT_TIMEOUT   Agent 编排：实测 2-3 轮、端到端 37-90s，留足余量
 */
import axios from '../utils/axios'

const CHAT_TIMEOUT = 180000
const AGENT_TIMEOUT = 300000

/** 普通问答（非流式） */
export const chat = (sessionId, message, options = {}) =>
  axios.post('/api/ai-assistant/chat',
    { session_id: sessionId, message },
    { timeout: CHAT_TIMEOUT, ...options })

/**
 * 深度分析（Agent）：模型自主决定查哪些资料，返回执行轨迹
 *
 * patientId 可选：患者不传即本人；医生/管理员传了会走 can_access_patient 校验，
 * 越权返回 403 AUTH_003。
 */
export const chatAgent = (sessionId, message, { patientId, ...options } = {}) => {
  const body = { session_id: sessionId, message }
  if (patientId !== undefined && patientId !== null) body.patient_id = patientId
  return axios.post('/api/agent/chat', body, { timeout: AGENT_TIMEOUT, ...options })
}

/** 会话历史（含引用与 Agent 轨迹，用于刷新后恢复） */
export const history = (sessionId, options = {}) =>
  axios.get('/api/ai-assistant/history',
    { params: { session_id: sessionId }, ...options })
