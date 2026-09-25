/**
 * 患者与账号相关接口
 */
import axios from '../utils/axios'

/** 医生名下绑定的患者（医生工作台用） */
export const doctorPatients = (params = {}, options = {}) =>
  axios.get('/api/doctor/patients', { params, ...options })

// 验证码属于认证域，见 api/auth.js（此处不再重复定义，避免两处漂移）

/**
 * 注册
 *
 * 两者都是**公开**接口（注册时还没有登录态），且失败原因各不相同：
 * 用户名已存在、验证码错误/过期、密码强度不足…… 调用点应把后端返回的
 * `error` 原样展示，而不是自己编一句"注册失败"。
 */
export const registerPatient = (payload, options = {}) =>
  axios.post('/api/patient/register', payload, options)

export const registerDoctor = (payload, options = {}) =>
  axios.post('/api/doctor/register', payload, options)

/** 患者自己的检测报告列表 */
export const patientReports = (params = {}, options = {}) =>
  axios.get('/api/patient/reports', { params, ...options })

/** 报告详情 */
export const patientReportDetail = (id, options = {}) =>
  axios.get(`/api/patient/reports/${id}`, options)
