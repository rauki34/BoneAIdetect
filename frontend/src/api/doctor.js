/**
 * 医生工作台接口
 */
import axios from '../utils/axios'

/** 医生名下患者的检测报告列表 */
export const reports = (params = {}, options = {}) =>
  axios.get('/api/doctor/reports', { params, ...options })

/** 编辑报告（诊断 / 随访备注 / 医疗建议） */
export const updateReport = (id, payload, options = {}) =>
  axios.put(`/api/doctor/reports/${id}`, payload, options)
