/**
 * 日期时间工具函数
 * 统一处理UTC时间到本地时间（中国时区 UTC+8）的转换
 */

/**
 * 将UTC时间转换为本地时间并格式化为时间字符串（简化版）
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期时间字符串
 */
export const formatTime = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  // 加上8小时（中国时区 UTC+8）
  const localDate = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return localDate.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * 将UTC时间转换为本地时间并格式化为日期字符串
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期字符串
 */
export const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  // 加上8小时（中国时区 UTC+8）
  const localDate = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return localDate.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

/**
 * 将UTC时间转换为本地时间并格式化为日期时间字符串
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期时间字符串
 */
export const formatDateTime = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  // 加上8小时（中国时区 UTC+8）
  const localDate = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return localDate.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * 将UTC时间转换为本地时间并格式化为完整日期时间字符串（带秒）
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期时间字符串
 */
export const formatDateTimeFull = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  // 加上8小时（中国时区 UTC+8）
  const localDate = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  return localDate.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}
