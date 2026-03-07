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
- **数据可视化**：置信度趋势分析、模型使用统计、检测类别分布
- **用户权限控制**：管理员/普通用户双角色权限体系
- **亮暗主题切换**：支持亮色/暗色双主题，适配不同使用环境

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
| SQLite | 3.x | 轻量级数据库 |

### AI服务技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Transformers | ^4.x | 大模型加载与推理 |
| PyTorch | ^2.x | 深度学习框架 |
| BitsAndBytes | ^0.x | 4-bit模型量化 |
| Pillow | ^10.x | 图像处理 |

---

## 项目结构

```
d:\grauateDesign
├── frontend/                    # 前端项目
│   ├── src/
│   │   ├── views/              # 页面组件
│   │   │   ├── Home.vue        # 主布局页面
│   │   │   ├── Detection.vue   # 图片检测页面
│   │   │   ├── VideoStreamDetection.vue  # 视频流检测页面
│   │   │   ├── CameraDetection.vue       # 摄像头实时检测页面
│   │   │   ├── ModelTraining.vue         # 模型训练管理页面
│   │   │   ├── UserManagement.vue        # 用户管理页面
│   │   │   ├── Login.vue       # 登录页面
│   │   │   └── Register.vue    # 注册页面
│   │   ├── router/
│   │   │   └── index.js        # 路由配置
│   │   ├── utils/
│   │   │   └── axios.js        # Axios封装
│   │   ├── App.vue             # 根组件
│   │   ├── main.js             # 入口文件
│   │   └── style.css           # 全局样式
│   ├── package.json
│   └── vite.config.js
│
├── backend/                     # 后端项目
│   ├── app.py                  # Flask主应用
│   ├── database.py             # 数据库模型定义
│   ├── requirements.txt        # Python依赖
│   ├── models/                 # YOLO模型权重文件
│   │   ├── yolov8.pt          # YOLOv8权重
│   │   ├── yolo11n.pt         # YOLOv11权重
│   │   ├── yolo12n.pt         # YOLOv12权重
│   │   └── custom_*.pt        # 自定义训练模型
│   ├── uploads/               # 上传文件存储
│   │   ├── datasets/          # 训练数据集
│   │   └── training_runs/     # 训练结果
│   ├── results/               # 检测结果图片存储
│   └── instance/
│       └── bone_detection.db  # SQLite数据库
│
├── AI/                         # AI服务
│   ├── app.py                 # AI服务Flask应用
│   └── Qwen3-VL-4B-Instruct/  # 多模态大模型文件
│
├── dataset/                    # 数据集
│   └── break-bone/            # 骨折检测数据集
│       ├── train/
│       ├── valid/
│       └── data.yaml
│
└── README.md                   # 项目说明文档
```

---

## 核心功能模块

### 1. 图片检测 (Detection.vue)
- 支持图片上传和预览
- 多模型选择（系统模型+自定义模型）
- 实时检测结果显示
- AI医疗建议生成

### 2. 视频流检测 (VideoStreamDetection.vue)
- 上传视频文件进行检测
- WebSocket实时推送检测结果
- 检测统计和帧级别详情

### 3. 摄像头实时检测 (CameraDetection.vue)
- 摄像头设备选择和预览
- 实时检测和结果展示
- 检测历史时间线

### 4. 模型训练管理 (ModelTraining.vue)
- 上传数据集训练新模型
- 支持YOLOv8/11/12作为基础模型
- **CBAM注意力机制**：支持YOLOv8-CBAM、YOLO11-CBAM优化模型训练
- **支持模型续训**：在已有模型基础上继续训练
- 训练任务实时监控
- 模型性能指标展示（mAP50、mAP50-95、Fitness）
- **模型状态管理**：发布/禁用/启用/删除完整生命周期管理
- **彻底删除**：删除模型时自动清理.pt文件、数据集、训练记录等

### 5. 数据分析 (Home.vue)
- 检测统计概览
- 模型使用统计
- 检测类别分布
- 置信度趋势折线图

---

## API 接口说明

### 用户认证
- `POST /api/login` - 用户登录
- `POST /api/register` - 用户注册

### 检测功能
- `POST /api/predict` - 图片检测
- `POST /api/video/detect` - 视频检测
- `POST /api/camera/detect` - 摄像头单帧检测
- `WS /ws/video/<task_id>` - 视频检测WebSocket

### 模型训练
- `GET /api/models` - 获取所有模型（支持分页和状态筛选）
- `GET /api/models/published` - 获取已发布模型
- `POST /api/models/train` - 开始训练（支持常规训练和CBAM训练）
- `POST /api/models/<id>/publish` - 发布模型
- `POST /api/models/<id>/disable` - 禁用模型
- `POST /api/models/<id>/enable` - 启用已禁用模型
- `DELETE /api/models/<id>` - 删除模型（自动清理相关文件）
- `GET /api/training/tasks` - 获取训练任务
- `GET /api/training/tasks/<id>/progress` - 获取训练进度

### 历史管理
- `GET /api/history` - 获取检测历史
- `DELETE /api/history/<id>` - 删除历史记录
- `DELETE /api/history/clear/all` - 清空历史

### 数据分析
- `GET /api/analysis` - 获取统计数据
- `GET /api/analysis/confidence_series` - 置信度趋势

### 系统设置
- `GET /api/settings` - 获取设置
- `POST /api/settings` - 更新设置

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

### 续训功能
选择已训练的自定义模型作为基础模型，系统会加载已有权重继续训练，适用于：
- 增加新数据微调模型
- 延长训练轮数优化性能

### 模型状态流转
```
训练中 → 训练完成 → 发布 → 禁用 → 启用 → 发布
              ↓       ↓      ↓
           可删除   可检测  可删除/启用
```

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
9. **权限管理**：基于角色的访问控制
10. **数据可视化**：置信度趋势、模型统计、类别分布

---

## 未来展望

1. **模型优化**：引入更轻量级的检测模型，支持移动端部署
2. **多模态融合**：结合文本病历信息，提供更精准的诊断建议
3. **分布式部署**：支持多GPU并行推理，提升并发处理能力
4. **数据增强**：集成在线数据标注工具，持续优化模型效果
5. **报告生成**：自动生成标准化诊断报告，支持PDF导出
