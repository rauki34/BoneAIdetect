import axios from 'axios'
import { ElMessage } from 'element-plus'
import { clearAuth } from './auth'

// 开发环境兜底到本机后端；生产环境留空（''）表示同源，由 Nginx 反向代理 /api
// 注意用 ?? 而非 ||，因为空字符串是生产环境的有效取值
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:5000'

// 创建 axios 实例
const instance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: true  // 启用 session 支持
})

/**
 * 认证类接口
 *
 * 这些接口的 401 表示"凭据错误"（用户名不存在 / 密码错误），
 * 而非"登录态失效"，因此不能触发跳转登录页的逻辑。
 * 例：登录页输错密码返回 401，若不排除会错误提示"登录已过期"。
 */
const AUTH_ENDPOINTS = ['/api/login', '/api/register', '/api/logout', '/api/captcha']

const isAuthEndpoint = (url = '') => AUTH_ENDPOINTS.some(p => url.includes(p))

// 防止并发请求同时 401 时重复跳转
let redirectingToLogin = false

// 请求拦截器：注入认证信息
instance.interceptors.request.use(
  config => {
    // JWT（阶段 3 启用；登录接口返回 access_token 后自动生效）
    const accessToken = localStorage.getItem('access_token')
    if (accessToken) {
      config.headers['Authorization'] = `Bearer ${accessToken}`
    }

    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器：仅处理跨组件的通用错误（当前只有"登录态失效"）
//
// 设计说明：业务错误（4xx/5xx）不在此处统一提示。
// 各组件已有 101 处带业务上下文的提示（如"获取检测历史记录失败"），
// 在拦截器再提示一次会导致每个失败请求弹出两个 toast，且文案更笼统。
instance.interceptors.response.use(
  response => response,
  error => {
    const status = error.response?.status
    const config = error.config || {}

    const shouldHandle401 =
      status === 401 &&
      !config.skipAuthRedirect &&      // 单次请求可通过该标记跳过
      !isAuthEndpoint(config.url)      // 认证接口的 401 是凭据错误

    if (shouldHandle401 && !redirectingToLogin) {
      redirectingToLogin = true
      clearAuth()

      ElMessage.error('登录已过期，请重新登录')

      // 动态导入避免与 router <-> views <-> axios 形成静态循环依赖
      import('../router')
        .then(({ default: router }) => router.push('/login'))
        .catch(() => { window.location.href = '/login' })
        .finally(() => { redirectingToLogin = false })
    }

    return Promise.reject(error)
  }
)

export const axiosInstance = instance
export default axiosInstance
