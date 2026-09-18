# 智慧骨科云平台

基于深度学习的医学影像骨折智能检测系统，集成YOLO目标检测、AI辅助诊断、患者管理、病历管理等功能，为骨科医生提供全流程诊疗支持。

***

## 项目概述

本项目是一个面向医疗场景的骨折检测与诊疗管理系统，采用前后端分离架构，支持三种角色（管理员/医生/患者）的协同工作。系统通过YOLO计算机视觉技术自动识别X光片中的骨折部位，并结合多模态大语言模型生成专业的医疗建议。

### 核心功能

- **AI骨折检测**：支持图片、视频、摄像头三种检测方式
- **多模型支持**：YOLOv8、YOLOv11、YOLOv26及自定义训练模型
- **患者管理**：完整的患者档案、病历、检查记录管理
- **医生工作站**：患者管理、病历管理、AI辅助诊断一体化
- **AI医疗建议**：基于检测结果生成专业诊断建议
- **消息通知**：医患之间即时通讯
- **系统公告**：管理员发布公告，定向推送给医生或患者
- **模型训练管理**：自定义模型训练、超参数优化、模型发布
- **数据统计分析**：检测趋势、患者统计、工作量统计
- **操作日志**：完整的操作审计记录
- **医生入驻审核**：医生注册需管理员审核

***

## 技术栈

### 前端技术栈

| 技术                  | 版本      | 用途                   |
| ------------------- | ------- | -------------------- |
| Vue 3               | ^3.4.31 | 前端框架，Composition API |
| Element Plus        | ^2.7.6  | UI组件库                |
| Vite                | ^5.3.3  | 构建工具                 |
| Vue Router          | ^4.4.0  | 路由管理                 |
| Axios               | ^1.7.2  | HTTP请求               |
| ECharts             | ^6.0.0  | 数据可视化图表              |
| @antv/g2plot        | ^2.4.31 | 高级图表组件               |
| vue-markdown-render | ^2.3.0  | Markdown渲染           |
| html2canvas         | ^1.4.1  | 页面截图生成               |
| jspdf               | ^4.2.1  | PDF文档生成              |
| html2pdf.js         | ^0.14.0 | HTML转PDF             |

### 后端技术栈

| 技术                 | 版本      | 用途            |
| ------------------ | ------- | ------------- |
| Flask              | ^3.1.2  | Web框架         |
| Flask-SQLAlchemy   | ^3.1.1  | ORM数据库操作      |
| Flask-Migrate      | ^4.1.0  | 数据库迁移         |
| Flask-CORS         | ^6.0.2  | 跨域处理          |
| Flask-JWT-Extended | ^4.7.1  | JWT认证         |
| Werkzeug           | ^3.1.4  | 密码加密、WSGI工具   |
| Ultralytics        | ^8.4.31 | YOLO模型推理和训练   |
| PyTorch            | ^2.7.1  | 深度学习框架        |
| OpenCV             | ^4.12.0 | 图像处理          |
| Pillow             | ^12.1.0 | 图像处理          |
| SQLite             | 3.x     | 轻量级数据库        |
| Optuna             | ^4.8.0  | 超参数优化         |
| Transformers       | ^4.57.3 | 大模型加载         |
| Accelerate         | ^1.12.0 | 模型加速          |
| bitsandbytes       | ^0.49.2 | 4-bit量化        |

### AI服务技术栈

| 技术           | 版本      | 用途       |
| ------------ | ------- | -------- |
| Flask        | ^3.1.2  | Web框架    |
| Transformers | ^4.57.3 | 大模型加载与推理 |
| PyTorch      | ^2.7.1  | 深度学习框架   |
| bitsandbytes | ^0.49.2 | 4-bit量化  |
| Pillow       | ^12.1.0 | 图像处理     |

***

## 项目结构

```
grauateDesign/
├── frontend/                 # 前端项目
│   ├── src/
│   │   ├── components/      # 公共组件
│   │   │   ├── FloatingAIAssistant.vue   # 悬浮AI助手组件
│   │   │   ├── DoctorRegisterDialog.vue  # 医生注册对话框
│   │   │   ├── DoctorReportList.vue      # 医生报告列表
│   │   │   ├── PatientRegisterDialog.vue # 患者注册对话框
│   │   │   ├── PatientReportList.vue     # 患者报告列表
│   │   │   ├── PatientSelector.vue       # 患者选择器
│   │   │   ├── ReportDetail.vue          # 报告详情组件
│   │   │   └── ReportEditor.vue          # 报告编辑器组件
│   │   ├── views/           # 页面视图
│   │   │   ├── SmartOrthopedicsLogin.vue # 统一登录入口
│   │   │   ├── PatientPortal.vue         # 患者端门户
│   │   │   ├── DoctorWorkstation.vue     # 医生工作站
│   │   │   ├── AdminApproval.vue         # 管理员后台
│   │   │   ├── ModelTraining.vue         # 模型训练页面
│   │   │   ├── Detection.vue             # 图像检测
│   │   │   ├── VideoStreamDetection.vue  # 视频流检测
│   │   │   └── CameraDetection.vue       # 摄像头检测
│   │   ├── router/          # 路由配置
│   │   │   └── index.js
│   │   ├── utils/           # 工具函数
│   │   │   ├── axios.js     # Axios配置和拦截器
│   │   │   ├── datetime.js  # 日期时间工具
│   │   │   └── notifications.js  # 通知工具
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── style.css
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
│
├── backend/                  # 后端项目
│   ├── app.py               # 主应用入口
│   ├── database.py          # 数据库模型定义
│   ├── train_and_update.py  # 模型训练脚本
│   ├── hyperparameter_optimization.py  # 超参数优化
│   ├── reset_admin.py       # 管理员重置工具
│   ├── requirements.txt     # Python依赖
│   ├── migrations/          # 数据库迁移
│   │   ├── versions/
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── models/              # YOLO模型文件
│   ├── uploads/             # 上传文件存储
│   ├── results/             # 检测结果存储
│   └── instance/            # SQLite数据库文件
│
├── AI/                       # AI服务
│   ├── app.py               # AI服务入口（Qwen3-VL-4B多模态模型）
│   └── requirements.txt
│
├── requirements-all.txt     # 完整依赖清单
│
└── venv/                     # Python虚拟环境
```

***

## 快速开始

### 环境要求

- **操作系统**：Windows 10/11 或 Linux
- **Python**：3.11+
- **Node.js**：16+
- **CUDA**：11.8+ (推荐，用于GPU加速)
- **内存**：16GB+ (推荐)
- **存储空间**：20GB+ (包含模型文件)

### 安装步骤

#### 1. 克隆项目

```bash
git clone <repository-url>
cd grauateDesign
```

#### 2. 创建虚拟环境

```bash
# Windows PowerShell
python -m venv venv
venv\Scripts\Activate.ps1

# Windows CMD
python -m venv venv
venv\Scripts\activate.bat

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

#### 3. 安装后端依赖

```bash
# 安装主后端依赖
pip install -r backend/requirements.txt

# 安装AI服务依赖
pip install -r AI/requirements.txt

# 或者一次性安装所有依赖
pip install -r requirements-all.txt
```

**注意**：PyTorch建议根据CUDA版本单独安装：
```bash
# CUDA 11.8
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu121

# CPU only
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu
```

#### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 启动服务

#### 方式一：手动启动（开发模式）

**终端1 - 启动Flask后端：**

```bash
# 确保虚拟环境已激活
cd backend
python app.py
# 服务运行在 http://localhost:5000
```

**终端2 - 启动AI服务：**

```bash
# 确保虚拟环境已激活
cd AI
python app.py
# 服务运行在 http://localhost:8000
```

**终端3 - 启动前端：**

```bash
cd frontend
npm run dev
# 服务运行在 http://localhost:5173
```

**终端4 - 启动Celery worker（训练与知识库入库）：**

```bash
cd backend
bash scripts/celery.sh start
# 日志: logs/celery.log
```

> **worker 必须单独起。** 训练与文档入库都在 worker 里执行，只起后端的话
> 这两类任务会一直躺在队列里不动（接口会返回 202 已受理，但永远停在"处理中"）。
> 队列依赖 Redis，所以要先 `bash scripts/redis.sh start` —— 脚本会替你检查。

#### 启停脚本速查

三个长驻组件（PostgreSQL / Redis / worker）都不是 Windows 服务，
重启电脑后需要手动拉起。脚本都在 `backend/scripts/`：

```bash
bash scripts/pg.sh start        # PostgreSQL（含 pgvector）
bash scripts/redis.sh start     # Redis（缓存 + 消息队列 broker）
bash scripts/flask.sh start     # 后端（加 debug 参数可开 DEBUG 日志并放宽限流）
bash scripts/celery.sh start    # Celery worker
```

各自的 `status` / `stop` / `log` 子命令同理；`celery.sh status` 会列出已注册的任务。

#### 方式二：生产部署

```bash
# 构建前端
cd frontend
npm run build

# 使用Gunicorn启动后端（Linux）
cd ../backend
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Windows可使用 waitress
waitress-serve --port=5000 app:app
```

### 访问系统

- **前端界面**：<http://localhost:5173> (开发) / <http://localhost:80> (生产)
- **后端API**：<http://localhost:5000>
- **AI服务**：<http://localhost:8000>

### 默认账号

- **管理员**：用户名: `admin`，密码: `123456`

***

## 功能模块详解

### 1. 统一登录入口

- 支持患者、医生、管理员三种角色
- 图形验证码保护
- 医生可申请入驻，需管理员审核
- 自动根据角色跳转对应首页

### 2. 患者端功能

- **个人概览**：查看基本信息、主治医生、最新病历
- **我的病历**：查看所有病历记录
- **主治医师**：查看主治医生信息
- **检查报告**：查看AI检测报告
- **消息通知**：接收医生消息和系统公告
- **AI健康助手**：悬浮按钮式AI助手，支持骨折康复咨询和常见问题解答

### 3. 医生工作站

- **工作台首页**：统计数据、待办事项、快捷入口
- **患者管理**：我的患者列表、添加患者、患者详情
- **病历管理**：创建病历、编辑病历、病历列表
- **AI辅助诊断**：图片检测、视频检测、摄像头检测
- **检查报告**：查看所有检测报告
- **检测历史**：历史检测记录查询
- **消息通知**：与患者沟通、接收系统消息

### 4. 管理员后台

- **仪表盘**：系统统计数据、趋势图表
- **用户管理**：创建/编辑/删除用户、重置密码
- **医生审核**：审核医生入驻申请
- **模型管理**：发布/禁用/删除模型
- **训练任务**：查看训练进度、停止任务
- **操作日志**：查看系统操作记录
- **公告管理**：发布公告、定向推送

### 5. AI检测模块

- **图片检测**：上传单张或多张图片检测
- **视频检测**：上传视频文件逐帧检测
- **摄像头检测**：实时摄像头检测
- **多模型切换**：支持YOLOv8/11/26及自定义模型
- **患者关联**：检测结果可关联到患者档案
- **AI解读**：基于检测结果生成医疗建议

### 6. 模型训练模块

- **数据集管理**：上传YOLO格式数据集
- **训练配置**：设置轮数、批次大小、图像尺寸
- **超参数优化**：基于Optuna自动优化超参数
- **训练监控**：实时查看训练进度和损失曲线
- **模型评估**：自动计算mAP、Precision、Recall、F1
- **模型发布**：训练完成后发布供使用

### 7. 数据统计分析

- **检测趋势**：按日/周/月统计检测数量
- **置信度趋势**：检测置信度变化曲线
- **患者统计**：年龄段分布、性别分布
- **工作量统计**：医生工作量统计
- **模型使用统计**：各模型使用频率

***

## 数据库表结构

| 表名                         | 说明     | 主要字段                                                                               |
| -------------------------- | ------ | ---------------------------------------------------------------------------------- |
| users                      | 用户表    | username, password, role, full_name, email, phone                                 |
| doctor_profiles            | 医生资料   | user_id, department, title, license_number, hospital, status                     |
| patient_profiles           | 患者资料   | user_id, patient_number, gender, birth_date, address, allergies                 |
| doctor_patient_relations   | 医患关系   | doctor_id, patient_id, is_primary, status                                       |
| detection_history          | 检测历史   | username, patient_id, filename, model, detections, confidence, medical_advice    |
| medical_records            | 病历记录   | record_number, patient_id, doctor_id, diagnosis, treatment, prescription        |
| custom_models              | 自定义模型  | name, model_key, status, accuracy, map50, map50_95, precision, recall, f1_score |
| training_tasks             | 训练任务   | model_id, epochs, progress, status, loss, val_loss                               |
| doctor_registrations       | 医生注册申请 | username, full_name, department, title, license_number, status                   |
| announcements              | 系统公告   | title, content, target_role, priority, is_active                                 |
| messages                   | 消息通知   | sender_id, receiver_id, title, content, message_type, is_read                  |
| operation_logs             | 操作日志   | username, method, url, description, success, ip                                  |
| ai_conversations           | AI对话   | patient_id, session_id, message_type, message_content                          |
| datasets                   | 数据集    | name, dataset_path, num_images, num_classes, class_names                         |

***

## API接口概览

### 认证接口

- `POST /api/login` - 用户登录
- `POST /api/register` - 用户注册
- `POST /api/logout` - 用户登出
- `GET /api/captcha` - 获取验证码

### 检测接口

- `POST /api/predict` - 图像检测
- `POST /api/video/detect` - 视频检测
- `POST /api/camera/detect` - 摄像头检测
- `GET /api/history` - 检测历史

### 患者管理接口

- `GET/POST /api/doctor/patients` - 患者列表/创建
- `GET /api/patient/profile` - 患者资料
- `GET /api/patient/medical-records` - 患者病历

### 医生管理接口

- `GET /api/doctor/dashboard` - 医生工作台数据
- `GET /api/doctor/reports` - 医生报告列表
- `POST /api/doctor/register` - 医生入驻申请

### 管理员接口

- `GET/POST /api/users` - 用户列表/创建
- `GET /api/admin/dashboard` - 管理员仪表盘
- `GET /api/admin/statistics` - 系统统计
- `POST /api/admin/approve-doctor/{id}` - 审核医生注册

### 模型管理接口

- `GET /api/models` - 模型列表
- `POST /api/models/train` - 创建训练任务
- `POST /api/models/{id}/publish` - 发布模型
- `GET /api/training/tasks` - 训练任务列表

### 消息通知接口

- `GET /api/messages/contacts` - 消息联系人
- `POST /api/messages/send` - 发送消息
- `GET /api/announcements` - 公告列表

### AI助手接口

- `POST /api/ai-assistant/chat` - AI助手对话
- `GET /api/ai-assistant/history` - 对话历史
- `GET /api/ai-assistant/sessions` - 会话列表

***

## 技术亮点

1. **三端分离架构**：患者端、医生端、管理员端独立设计，权限严格分离
2. **医患关系管理**：支持主治医生与患者的绑定关系
3. **医生入驻审核**：医生注册需管理员审核，确保资质合规
4. **多模型支持**：支持YOLOv8/11/26及自定义模型，动态加载
5. **AI辅助诊断**：集成多模态大模型生成专业医疗建议
6. **实时通讯**：医患之间即时消息通知
7. **模型生命周期管理**：训练→评估→发布→禁用完整流程
8. **超参数优化**：基于Optuna的贝叶斯自动优化
9. **操作审计**：完整的操作日志记录
10. **数据可视化**：ECharts图表展示统计数据

***

## 相关文档

- [项目大纲.md](项目大纲.md) - 项目架构详细说明
- [AI服务配置说明.md](AI服务配置说明.md) - AI服务配置详细说明
- [改进方案文档.md](改进方案文档.md) - 项目改进方案

***

## 许可说明

本项目仅供学习参考，不可用于商业用途
