/**
 * 日期时间工具函数
 * 统一处理UTC时间到本地时间（中国时区 UTC+8）的转换
 */

// 中国时区偏移量（毫秒）
const TIMEZONE_OFFSET = 8 * 60 * 60 * 1000

/**
 * 将UTC时间转换为本地时间
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {Date|null} 本地时间Date对象或null
 */
const parseToLocalDate = (dateStr) => {
  if (!dateStr) return null
  const date = new Date(dateStr)
  return new Date(date.getTime() + TIMEZONE_OFFSET)
}

/**
 * 格式化日期时间
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @param {Object} options - 格式化选项
 * @param {boolean} options.dateOnly - 仅显示日期
 * @param {boolean} options.includeSeconds - 包含秒数
 * @param {boolean} options.includeTime - 包含时间（默认true）
 * @returns {string} 格式化后的本地时间字符串
 */
export const formatDateTime = (dateStr, options = {}) => {
  const { dateOnly = false, includeSeconds = false, includeTime = true } = options
  
  const localDate = parseToLocalDate(dateStr)
  if (!localDate) return '-'
  
  if (dateOnly) {
    return localDate.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    })
  }
  
  const formatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }
  
  if (includeSeconds) {
    formatOptions.second = '2-digit'
    formatOptions.hour12 = false
  }
  
  if (!includeTime) {
    return localDate.toLocaleDateString('zh-CN', formatOptions)
  }
  
  return localDate.toLocaleString('zh-CN', formatOptions)
}

/**
 * 格式化日期（仅日期部分）
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期字符串
 */
export const formatDate = (dateStr) => formatDateTime(dateStr, { dateOnly: true })

/**
 * 格式化时间（简化版，包含日期和时间）
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期时间字符串
 */
export const formatTime = (dateStr) => formatDateTime(dateStr)

/**
 * 格式化完整日期时间（带秒）
 * @param {string} dateStr - ISO格式的UTC时间字符串
 * @returns {string} 格式化后的本地日期时间字符串
 */
export const formatDateTimeFull = (dateStr) => formatDateTime(dateStr, { includeSeconds: true })
