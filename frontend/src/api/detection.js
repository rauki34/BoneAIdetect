/**
 * 检测相关接口
 *
 * 检测的模型列表来自 `/api/settings` 的 available_models（**只含已发布模型**）：
 * 医生不能选用训练完但未发布的模型，这是阶段 8 收紧的发布门禁。所以这里
 * 不提供"列出全部模型"的函数 —— 前端任何检测入口都该走 settings。
 */
import axios from '../utils/axios'

// 上传图片/视频做检测：推理在服务端，大图慢些但远不到 5 分钟
const DETECT_TIMEOUT = 120000

/** 系统设置（含可用模型列表、默认模型） */
export const settings = (options = {}) =>
  axios.get('/api/settings', options)

/** 图片检测（医生的自定义模型由后端按已发布列表校验） */
export const predict = (formData, options = {}) =>
  axios.post('/api/predict', formData, { timeout: DETECT_TIMEOUT, ...options })

/** 摄像头单帧检测 */
export const cameraDetect = (formData, options = {}) =>
  axios.post('/api/camera/detect', formData, { timeout: DETECT_TIMEOUT, ...options })

/** 视频检测（返回任务 id，进度经 WebSocket 推送） */
export const videoDetect = (formData, options = {}) =>
  axios.post('/api/video/detect', formData, { timeout: DETECT_TIMEOUT, ...options })

/** AI 解读某条检测记录（会落库 medical_advice 与引用） */
export const interpret = (payload, options = {}) =>
  axios.post('/api/interpret', payload, { timeout: 300000, ...options })

/** 医生把检测记录归属到患者（并把诊断写进病历） */
export const createReport = (payload, options = {}) =>
  axios.post('/api/doctor/reports', payload, options)

/** 保存医疗建议（编辑后回写） */
export const saveAdvice = (historyId, payload, options = {}) =>
  axios.post(`/api/history/${historyId}/advice`, payload, options)
