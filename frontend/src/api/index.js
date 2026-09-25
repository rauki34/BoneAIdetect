/**
 * 接口层（阶段 12）
 *
 * 改造前有 115 处 `axios.get('/api/xxx')` 散落在 13 个组件里。集中到这里的收益
 * 不是"好看"，而是三件具体的事：
 *
 *   1. **改地址只改一处**。接口路径写散之后，后端改个路由要在十几个文件里找。
 *   2. **每个接口的超时/头部有单一出处**。AI 对话要 180s、Agent 要 300s、
 *      其余 30s —— 这些差异现在只写在函数里，调用点不必再各自记得传 timeout。
 *      （真实事故：客户端默认 30s 把一次已成功的 RAG 回答判成了失败。）
 *   3. **参数形状有名字**。`{session_id, message}` 这种匿名对象，改成
 *      `chatAgent({ sessionId, message })` 之后，调用点错传参数会更容易被发现。
 *
 * **分域拆分**：api/ai.js、api/knowledge.js、api/detection.js、api/patient.js。
 * 每个模块只管一域，导出具名函数 —— 不用 `api.get('/api/xxx')` 这种薄封装，
 * 因为那样只是把字符串换个地方写，收益为零。
 *
 * 底层的 axios 实例、JWT 注入、401 跳转仍在 `src/utils/axios.js`：那是**传输层**
 * 的关注点（认证、错误码映射），本层是**接口契约**的关注点（哪个接口、什么参数）。
 * 两层的边界不要混。
 */
export * as ai from './ai'
export * as knowledge from './knowledge'
export * as detection from './detection'
export * as patient from './patient'
