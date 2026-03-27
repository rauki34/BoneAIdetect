# 医学骨折检测分析系统

基于深度学习的医学影像骨折智能检测平台，集成多模型目标检测、模型训练管理、视频流检测、摄像头实时检测与多模态AI医疗建议生成，为骨科医生提供辅助诊断支持。

---

## 项目概述

本项目是一个面向医疗场景的骨折检测系统，通过计算机视觉技术自动识别X光片中的骨折部位，并结合大语言模型生成专业的医疗建议。系统采用前后端分离架构，支持多模型切换、自定义模型训练、视频流检测、摄像头实时检测、检测历史管理、数据可视化分析和用户权限控制。

### 核心功能

- **多模型骨折检测**：支持YOLOv8、YOLOv11、YOLOv12等多个检测模型
- **CBAM注意力机制**：支持CBAM优化的YOLO模型训练，提升特征提取能力
- **自定义模型训练**：支持上传数据集训练自定义模型，支持模型续训
- **视频流检测分析**：支持上传视频文件进行批量检测分析
- **摄像头实时检测**：支持连接摄像头进行实时检测
- **AI医疗建议**：基于多模态大模型生成专业诊断建议
- **检测历史管理**：完整的检测记录存储、查询、删除功能
- **数据可视化**：置信度趋势分析、模型使用统计、检测类别分布、个人数据统计
- **用户权限控制**：管理员/普通用户双角色权限体系
- **亮暗主题切换**：支持亮色/暗色双主题，适配不同使用环境
- **注册验证码保护**：4位验证码防恶意注册
- **系统监控**：CPU、内存、磁盘实时监控
- **文件管理**：上传、下载、删除文件
- **操作日志**：完整操作审计记录

---

## 技术栈

### 前端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.4.x | 前端框架，Composition API |
| Element Plus | ^2.x | UI组件库 |
| Vite | ^5.x | 构建工具 |
| Vue Router | ^4.x | 路由管理 |
| Axios | ^1.x | HTTP请求 |
| @antv/g2plot | ^2.x | 数据可视化图表 |
| vue-markdown-render | ^2.x | Markdown渲染 |

### 后端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Flask | ^3.x | Web框架 |
| Flask-SQLAlchemy | ^3.x | ORM数据库操作 |
| Flask-Migrate | ^4.x | 数据库迁移 |
| Flask-CORS | ^4.x | 跨域处理 |
| Flask-Sock | ^0.7.x | WebSocket支持 |
| Werkzeug | ^3.x | 密码加密、WSGI工具 |
| Ultralytics | ^8.x | YOLO模型推理和训练 |
| OpenCV | ^4.x | 图像处理 |
| Pillow | ^10.x | 验证码图像生成 |
| SQLite | 3.x | 轻量级数据库 |

### AI服务技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Transformers | ^4.x | 大模型加载与推理 |
| PyTorch | ^2.x | 深度学习框架 |
| BitsAndBytes | ^0.x | 4-bit模型量化 |

---

## 项目结构

```
d:\grauateDesign
├── frontend/                    # 前端项目 (Vue 3 + Vite)
│   ├── src/
│   │   ├── views/              # 页面组件
│   │   │   ├── Home.vue        # 首页（数据分析仪表盘）
│   │   │   ├── Detection.vue   # 图片检测页面
│   │   │   ├── VideoStreamDetection.vue  # 视频流检测页面
│   │   │   ├── CameraDetection.vue       # 摄像头实时检测页面
│   │   │   ├── ModelTraining.vue        # 模型训练管理页面
│   │   │   ├── UserManagement.vue        # 用户管理页面
│   │   │   ├── OperationLog.vue          # 操作日志页面
│   │   │   ├── FileManager.vue           # 文件管理页面
│   │   │   ├── SystemMonitor.vue         # 系统监控页面
│   │   │   ├── Login.vue                 # 登录页面
│   │   │   └── Register.vue              # 注册页面（含验证码）
│   │   ├── router/                       # 路由配置
│   │   ├── utils/                        # 工具函数（axios封装）
│   │   ├── App.vue                       # 根组件
│   │   ├── main.js                       # 入口文件
│   │   └── style.css                     # 全局样式（亮暗主题）
│   ├── package.json
│   └── vite.config.js
│
├── backend/                     # 后端项目 (Flask)
│   ├── app.py                  # Flask主应用（50+ API接口）
│   ├── database.py             # 数据库模型定义
│   ├── reset_admin.py          # 重置管理员账号脚本
│   ├── train_and_update.py     # 训练更新脚本
│   ├── requirements.txt        # Python依赖
│   ├── models/                 # YOLO模型权重文件
│   │   ├── yolov8.pt          # YOLOv8预训练权重
│   │   ├── yolo11n.pt         # YOLOv11预训练权重
│   │   ├── yolo12n.pt         # YOLOv12预训练权重
│   │   └── cbam_temp_*.pt     # CBAM临时模型文件
│   ├── yolo_modules/           # 自定义YOLO模块
│   │   ├── cbam.py            # CBAM注意力机制实现
│   │   └── cbam_utils.py      # CBAM工具函数和模型创建
│   ├── uploads/                # 上传文件存储
│   │   ├── datasets/          # 训练数据集
│   │   └── training_runs/     # 训练结果
│   ├── results/                # 检测结果图片存储
│   ├── files/                  # 用户上传文件
│   ├── runs/                   # 模型运行结果
│   └── instance/
│       └── bone_detection.db   # SQLite数据库
│
├── AI/                         # AI服务 (Qwen3-VL多模态大模型)
│   ├── app.py                 # Flask AI服务应用
│   ├── requirements.txt        # Python依赖
│   └── Qwen3-VL-4B-Instruct/   # 多模态大模型文件
│       ├── config.json
│       ├── tokenizer.json
│       └── ...
│
├── dataset/                    # 数据集
│   └── break-bone/            # 骨折检测数据集
│       ├── train/             # 训练集
│       ├── valid/             # 验证集
│       └── data.yaml          # 数据集配置
│
├── venv/                       # Python虚拟环境
│
├── instance/                   # 实例目录（数据库）
│   └── bone_detection.db
│
├── 项目大纲.md                 # 项目详细大纲文档
├── README.md                   # 项目说明文档
├── CBAM使用说明.md            # CBAM注意力机制说明
├── AI服务配置说明.md          # AI服务配置说明
├── 权限管理功能说明.md        # 权限管理说明
├── 验证码功能实现总结.md      # 验证码功能说明
├── 验证码功能测试说明.md      # 验证码测试说明
├── database_export.sql         # 数据库SQL导出
└── requirements-all.txt        # 全部依赖汇总
```

---

## 核心功能模块

### 1. 图片检测 (Detection.vue)
- 支持图片上传和预览
- 多模型选择（系统模型+自定义模型）
- 实时检测结果显示（原图与结果图对比）
- 检测详情表格展示（类别、置信度、检测框坐标）
- AI医疗建议生成与保存

### 2. 视频流检测 (VideoStreamDetection.vue)
- 上传视频文件进行检测
- WebSocket实时推送检测结果
- 逐帧检测与结果展示
- 检测统计和进度显示

### 3. 摄像头实时检测 (CameraDetection.vue)
- 摄像头设备选择和预览
- 实时检测和结果展示
- 检测框实时绘制

### 4. 模型训练管理 (ModelTraining.vue)
- 上传数据集训练新模型
- 支持YOLOv8/11/12作为基础模型
- **CBAM注意力机制**：支持YOLOv8-CBAM、YOLO11-CBAM优化模型训练
- **支持模型续训**：在已有模型基础上继续训练
- 训练任务实时监控（进度、损失、轮数）
- 模型性能指标展示（mAP50、mAP50-95、Fitness）
- **模型状态管理**：发布/禁用/启用/删除完整生命周期管理

### 5. 数据分析 (Home.vue)
- 数字化智能仪表盘
- 检测统计概览（总检测次数、已用模型数、检测类别数、平均置信度）
- 模型使用统计与性能对比
- 检测类别分布统计
- 置信度趋势折线图
- **用户个性化数据**：普通用户查看个人检测统计

### 6. 用户管理 (UserManagement.vue)
- 用户列表展示
- 创建/编辑/删除用户
- 角色分配（管理员/普通用户）
- 密码重置

### 7. 操作日志 (OperationLog.vue)
- 完整操作记录（用户、方法、URL、描述、结果）
- 日志查询和筛选
- 日志清除

### 8. 文件管理 (FileManager.vue)
- 文件上传和存储
- 文件下载
- 文件删除
- 文件大小格式化显示

### 9. 系统监控 (SystemMonitor.vue)
- CPU使用率实时监控
- 内存使用情况
- 磁盘空间监控
- 系统信息展示

---

## API 接口说明

### 用户认证
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/login | POST | 用户登录 |
| /api/register | POST | 用户注册（含验证码） |
| /api/captcha | GET | 获取验证码图片 |
| /api/captcha/verify | POST | 验证验证码 |

### 检测功能
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/predict | POST | 图片检测 |
| /api/video/detect | POST | 视频检测启动 |
| /api/camera/detect | POST | 摄像头单帧检测 |
| /ws/video/<task_id> | WebSocket | 视频检测实时推送 |

### 模型训练
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/models | GET | 获取所有模型 |
| /api/models/published | GET | 获取已发布模型 |
| /api/models/train | POST | 开始训练 |
| /api/models/<id>/publish | POST | 发布模型 |
| /api/models/<id>/disable | POST | 禁用模型 |
| /api/models/<id>/enable | POST | 启用模型 |
| /api/models/<id> | DELETE | 删除模型 |
| /api/training/tasks | GET | 获取训练任务列表 |
| /api/training/tasks/<id>/progress | GET | 获取训练进度 |
| /api/training/tasks/<id>/stop | POST | 终止训练任务 |

### 历史管理
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/history | GET | 获取检测历史 |
| /api/history/<id> | GET | 获取历史详情 |
| /api/history/<id> | DELETE | 删除历史记录 |
| /api/history/clear/all | DELETE | 清空所有历史 |
| /api/history/<id>/advice | POST | 保存医疗建议 |

### 数据分析
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/analysis | GET | 获取统计数据（管理员） |
| /api/analysis/confidence_series | GET | 置信度趋势（管理员） |
| /api/analysis/user_confidence_series | GET | 个人置信度趋势 |
| /api/analysis/user_stats | GET | 个人检测统计 |
| /api/interpret | POST | AI解读生成 |

### 用户管理
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/users | GET | 获取用户列表 |
| /api/users | POST | 创建用户 |
| /api/users/<id> | PUT | 更新用户 |
| /api/users/<id> | DELETE | 删除用户 |

### 系统管理
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/settings | GET | 获取设置 |
| /api/settings | POST | 更新设置 |
| /api/logs | GET | 获取操作日志 |
| /api/logs/<id> | DELETE | 删除日志 |
| /api/logs/clear | DELETE | 清空日志 |
| /api/monitor/system | GET | 系统监控信息 |
| /api/monitor/stats | GET | 系统统计 |

### 文件管理
| 接口 | 方法 | 说明 |
|------|------|------|
| /api/files | GET | 获取文件列表 |
| /api/files/upload | POST | 上传文件 |
| /api/files/download/<id> | GET | 下载文件 |
| /api/files/<id> | DELETE | 删除文件 |

---

## 模型训练说明

### 数据集格式
上传的ZIP文件需要包含YOLO格式的数据集：
```
dataset.zip
├── train/
│   ├── images/
│   └── labels/
├── valid/
│   ├── images/
│   └── labels/
└── data.yaml
```

### 训练参数
- **基础模型**：YOLOv8/11/12、YOLOv8-CBAM、YOLO11-CBAM 或已训练的自定义模型（续训）
- **训练轮数**：10-500
- **批次大小**：1-64
- **图像尺寸**：320/416/640

### CBAM注意力机制
CBAM（Convolutional Block Attention Module）注意力机制可提升模型特征提取能力：
- **插入策略**：仅在Backbone深层和Neck部分插入，避免浅层计算开销
- **适用模型**：YOLOv8-CBAM、YOLO11-CBAM
- **优势**：捕获全局上下文，增强多尺度特征融合

---

## 运行说明

### 环境要求
- Python 3.11+
- Node.js 18+
- CUDA 11.8+（如需GPU加速）
- 6GB+ 显存（AI服务）

### 安装依赖

**后端**:
```bash
cd backend
pip install -r requirements.txt
```

**AI服务**:
```bash
cd AI
pip install flask transformers torch pillow bitsandbytes accelerate
```

**前端**:
```bash
cd frontend
npm install
```

### 启动服务

**1. 启动后端服务**:
```bash
cd backend
python app.py
# 服务运行在 http://127.0.0.1:5000
```

**2. 启动AI服务**:
```bash
cd AI
python app.py
# 服务运行在 http://127.0.0.1:8000
```

**3. 启动前端**:
```bash
cd frontend
npm run dev
# 服务运行在 http://localhost:5173
```

### 默认账号
- 用户名: admin
- 密码: 123456

---

## 技术亮点

1. **多模型支持**：支持YOLOv8/11/12及自定义模型，动态加载无需重启
2. **CBAM注意力机制**：集成CBAM模块优化YOLO模型，提升特征提取能力
3. **模型训练与续训**：完整的训练流程，支持常规训练和CBAM优化训练
4. **模型生命周期管理**：支持发布/禁用/启用/删除，删除时自动清理关联文件
5. **实时检测**：WebSocket实现视频流和摄像头的实时检测
6. **AI辅助诊断**：集成多模态大模型生成专业医疗建议
7. **4-bit量化**：大模型量化技术降低显存需求
8. **亮暗双主题**：完整的主题切换适配
9. **权限管理**：基于角色的访问控制（RBAC）
10. **数据可视化**：置信度趋势、模型统计、类别分布、个人数据
11. **注册验证码**：4位验证码保护，防止恶意注册
12. **系统监控**：CPU、内存、磁盘实时监控
13. **操作日志**：完整的操作审计记录

---

## 数据库表结构

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| users | 用户表 | username, password, role, created_at |
| detection_history | 检测历史 | username, filename, model, detections, confidence, medical_advice |
| custom_models | 自定义模型 | name, model_key, status, accuracy, map50, map50_95 |
| training_tasks | 训练任务 | model_id, epochs, progress, status, loss, val_loss |
| system_settings | 系统设置 | key, value, description |
| operation_logs | 操作日志 | username, method, url, description, success, ip |
| file_records | 文件记录 | filename, original_name, file_size, uploader, mime_type |

---

## 相关文档

- [项目大纲](项目大纲.md) - 详细的项目架构和功能说明
- [CBAM使用说明](CBAM使用说明.md) - CBAM注意力机制使用指南
- [AI服务配置说明](AI服务配置说明.md) - AI服务配置详细说明
- [权限管理功能说明](权限管理功能说明.md) - 权限管理详细说明
- [验证码功能实现总结](验证码功能实现总结.md) - 验证码功能实现细节
- [验证码功能测试说明](验证码功能测试说明.md) - 验证码测试指南

---

## 未来展望

1. **模型优化**：引入更轻量级的检测模型，支持移动端部署
2. **多模态融合**：结合文本病历信息，提供更精准的诊断建议
3. **分布式部署**：支持多GPU并行推理，提升并发处理能力
4. **数据增强**：集成在线数据标注工具，持续优化模型效果
5. **报告生成**：自动生成标准化诊断报告，支持PDF导出
6. **多语言支持**：增加英文等多语言界面

---

## 许可证

本项目仅供学习和研究使用。
