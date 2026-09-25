/**
 * 知识库接口
 *
 * 上传与入库是**异步**的（阶段 8 起入库跑在 Celery worker 里）：
 * 上传接口返回 202 受理，文档状态从 pending → processing → ready/failed。
 * 所以这里的 `uploadDoc` **不**返回切片结果 —— 改造前前端硬依赖
 * `res.data.chunks`，异步化之后那个字段永远为空，页面会一直弹"入库失败"。
 * 需要切片请看 `docChunks(docId)`。
 */
import axios from '../utils/axios'

// 入库异步化之后上传不该再等 5 分钟（原来 300s 是给同步入库留的）
const UPLOAD_TIMEOUT = 60000

/** 文档列表（医生/管理员；患者访问返回 403） */
export const listDocs = (params = {}, options = {}) =>
  axios.get('/api/knowledge/docs', { params, ...options })

/** 知识库统计（文档数、切片数、按类型分布） */
export const stats = (options = {}) =>
  axios.get('/api/knowledge/stats', options)

/** 某文档的切片（用于核对入库结果） */
export const docChunks = (docId, options = {}) =>
  axios.get(`/api/knowledge/docs/${docId}/chunks`, options)

/** 删除文档（共享文档仅管理员可删） */
export const removeDoc = (docId, options = {}) =>
  axios.delete(`/api/knowledge/docs/${docId}`, options)

/** 重新入库（异步，返回受理状态） */
export const reingestDoc = (docId, options = {}) =>
  axios.post(`/api/knowledge/docs/${docId}/reingest`, {}, options)

/** 上传文档（FormData；带 onUploadProgress 时用 options 传入） */
export const uploadDoc = (formData, options = {}) =>
  axios.post('/api/knowledge/docs', formData,
    { timeout: UPLOAD_TIMEOUT, ...options })

/** 检索预览（医生/管理员） */
export const search = (payload, options = {}) =>
  axios.post('/api/knowledge/search', payload, options)
