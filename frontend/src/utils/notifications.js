import { ElMessage, ElNotification } from 'element-plus'

/**
 * 创建消息提示函数工厂
 * @param {string} type - 消息类型: success/warning/info/error
 * @returns {Function} 消息提示函数
 */
const createMessage = (type) => (message, duration = 3000) => {
  ElMessage({
    message,
    type,
    duration,
    showClose: true
  })
}

/**
 * 显示成功消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showSuccess = createMessage('success')

/**
 * 显示错误消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showError = createMessage('error')

/**
 * 显示警告消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showWarning = createMessage('warning')

/**
 * 显示信息消息
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长(毫秒)
 */
export const showInfo = createMessage('info')

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
