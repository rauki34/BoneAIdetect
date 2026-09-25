# 前端镜像：构建静态产物后用 nginx 托管
#
# ⚠️ **本文件未经实跑验证**：本机 Docker 引擎起不来（缺 WSL2 所需的 Windows 功能，
# 诊断与启用步骤见 docker-compose.yml 顶部）。
#
# 构建时用的是 .env.production —— 其中 VITE_API_BASE 为空，即前端走**相对路径**
# `/api`，由 nginx.conf 反向代理到后端容器。这是这套部署的既定设计
# （见 .env.production 里的注释），所以镜像里不需要注入后端地址。

FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
