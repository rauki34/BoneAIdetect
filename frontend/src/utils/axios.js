import axios from 'axios'

// 创建 axios 实例
const instance = axios.create({
  baseURL: 'http://127.0.0.1:5000',
  timeout: 30000,
  withCredentials: true  // 启用 session 支持
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
    return Promise.reject(error)
  }
)

export const axiosInstance = instance
export default axiosInstance
