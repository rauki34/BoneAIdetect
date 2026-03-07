import axios from 'axios'

// 创建axios实例
const instance = axios.create({
  baseURL: 'http://127.0.0.1:5000',
  timeout: 30000
})

// 请求拦截器：添加用户名到请求头
instance.interceptors.request.use(
  config => {
    const username = localStorage.getItem('username')
    if (username) {
      config.headers['X-Username'] = username
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理错误
instance.interceptors.response.use(
  response => {
    return response
  },
  error => {
    if (error.response?.status === 401) {
      // 未授权，清除登录信息并跳转到登录页
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('role')
      // 使用 replace 并强制刷新，确保状态完全重置
      window.location.replace('/login?t=' + Date.now())
    }
    return Promise.reject(error)
  }
)

export default instance
