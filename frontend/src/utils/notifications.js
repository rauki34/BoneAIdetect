import { ElMessage, ElNotification } from 'element-plus'

/**
 * 显示成功消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showSuccess = (message, duration = 3000) => {
  ElMessage({
    message,
    type: 'success',
    duration,
    showClose: true
  })
}

/**
 * 显示错误消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showError = (message, duration = 3000) => {
  ElMessage({
    message,
    type: 'error',
    duration,
    showClose: true
  })
}

/**
 * 显示警告消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showWarning = (message, duration = 3000) => {
  ElMessage({
    message,
    type: 'warning',
    duration,
    showClose: true
  })
}

/**
 * 显示信息消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showInfo = (message, duration = 3000) => {
  ElMessage({
    message,
    type: 'info',
    duration,
    showClose: true
  })
}

/**
 * 显示通知
 * @param {string} title - 标题
 * @param {string} message - 消息内容
 * @param {string} type - 类型: success/warning/info/error
 * @param {number} duration - 显示时长(毫秒)
 */
export const showNotification = (title, message, type = 'info', duration = 4500) => {
  ElNotification({
    title,
    message,
    type,
    duration,
    position: 'top-right'
  })
}

/**
 * 显示加载消息
 * @param {string} message - 消息内容
 * @returns {Function} 关闭函数
 */
export const showLoading = (message = '加载中...') => {
  const loadingMessage = ElMessage({
    message,
    type: 'info',
    duration: 0,
    icon: 'Loading'
  })
  
  return () => loadingMessage.close()
}
