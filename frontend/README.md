# 智慧骨科云平台 — 前端

基于 Vue 3 + Vite + Element Plus 的医学影像骨折检测与诊疗管理系统前端。

## 技术栈

| 技术 | 版本 | 用途 |
|---|---|---|
| Vue 3 | ^3.4.31 | 前端框架（Composition API + `<script setup>`） |
| Vite | ^5.3.3 | 构建工具 |
| Vue Router | ^4.4.0 | 路由（懒加载 + 角色守卫） |
| Element Plus | ^2.7.6 | UI 组件库 |
| Axios | ^1.7.2 | HTTP 请求（统一拦截器） |
| ECharts | ^6.0.0 | 数据可视化 |
| jspdf / html2canvas | — | PDF 报告导出 |
| vue-markdown-render | ^2.3.0 | Markdown 渲染（AI 回答） |

## 目录结构

```
src/
├── views/                  # 页面级组件
│   ├── SmartOrthopedicsLogin.vue    # 统一登录入口
│   ├── PatientPortal.vue            # 患者端门户
│   ├── DoctorWorkstation.vue        # 医生工作站
│   ├── AdminApproval.vue            # 管理员后台
│   ├── Detection.vue                # 图像检测
│   ├── VideoStreamDetection.vue     # 视频流检测
│   └── CameraDetection.vue          # 摄像头检测
├── components/             # 公共组件（8 个）
├── router/index.js         # 路由配置 + 角色守卫
├── utils/
│   ├── axios.js            # Axios 实例与拦截器
│   ├── datetime.js         # 日期格式化
│   └── notifications.js    # ElMessage 封装
├── App.vue
└── main.js
```

## 开发

```bash
npm install
npm run dev          # 开发服务器 http://localhost:5173
```

后端需同时运行在 `http://127.0.0.1:5000`（见 `backend/app.py`）。

## 构建

```bash
npm run build        # 产物输出到 dist/
npm run preview      # 本地预览构建产物
```

## 环境变量

复制 `.env.development` 并按需修改：

```
VITE_API_BASE=http://127.0.0.1:5000
VITE_WS_BASE=ws://127.0.0.1:5000
```

## 角色与路由

| 路由 | 角色 | 说明 |
|---|---|---|
| `/login` | 公开 | 统一登录入口，含图形验证码 |
| `/patient-portal` | patient | 患者端 |
| `/doctor-workstation` | doctor | 医生工作站 |
| `/admin` | admin | 管理后台 |
| `/detect` | admin / doctor | 图像检测 |
| `/video` | admin / doctor | 视频流检测 |
| `/camera` | admin / doctor | 摄像头检测 |

路由守卫在 `src/router/index.js`，未登录跳转 `/login`，角色不匹配跳转对应首页。

## 部署

```bash
npm run build
# 将 dist/ 交给 Nginx 托管，并将 /api 反向代理到后端 5000 端口
```
