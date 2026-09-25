/**
 * 认证与账号接口
 *
 * 这些接口在**未登录**状态下调用，所以 `utils/axios.js` 的 401 拦截器对它们
 * 有特殊处理：这里的 401 表示"凭据错误"，而不是"登录态失效" —— 否则在登录页
 * 输错密码会被跳转到登录页并提示"登录已过期"（既有逻辑见 AUTH_ENDPOINTS）。
 */
import axios from '../utils/axios'

/** 图形验证码（图片二进制；验证码 id 在响应头 X-Captcha-ID） */
export const captcha = (options = {}) =>
  axios.get('/api/captcha', options)

/** 登录（返回 access_token / role / redirect_url） */
export const login = (credentials, options = {}) =>
  axios.post('/api/login', credentials, options)

/** 找回密码第一步：校验身份（手机号 + 验证码） */
export const verifyReset = (payload, options = {}) =>
  axios.post('/api/forgot-password/verify', payload, options)

/** 找回密码第二步：设置新密码 */
export const resetPassword = (payload, options = {}) =>
  axios.post('/api/forgot-password/reset', payload, options)
