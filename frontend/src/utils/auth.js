/**
 * 认证状态管理
 *
 * 集中定义登录态相关的 localStorage key，避免各处登出逻辑遗漏字段。
 * 历史上 PatientPortal / DoctorWorkstation 各写了一份 removeItem 列表，
 * 新增 access_token 时容易漏改，故统一到此处。
 */

export const AUTH_KEYS = ['access_token', 'token', 'username', 'userRole']

/** 保存登录信息 */
export function saveAuth({ accessToken, username, role }) {
  if (accessToken) localStorage.setItem('access_token', accessToken)
  localStorage.setItem('token', 'ok')   // 登录态标记，供路由守卫判断
  localStorage.setItem('username', username)
  localStorage.setItem('userRole', role)
}

/** 清除登录信息 */
export function clearAuth() {
  AUTH_KEYS.forEach((k) => localStorage.removeItem(k))
}
