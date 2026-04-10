# 智慧骨科云平台 - 后端API文档

## 文档信息
- **版本**: 1.0.0
- **更新时间**: 2025年
- **文件位置**: `backend/app.py`
- **总行数**: 约6500行

---

## 目录
1. [用户认证模块](#1-用户认证模块)
2. [检测分析模块](#2-检测分析模块)
3. [患者管理模块](#4-患者管理模块)
4. [医生管理模块](#5-医生管理模块)
5. [管理员功能模块](#6-管理员功能模块)
6. [AI模型管理模块](#7-ai模型管理模块)
7. [系统监控模块](#8-系统监控模块)
8. [消息通知模块](#9-消息通知模块)
9. [公告管理模块](#10-公告管理模块)

---

## 1. 用户认证模块

### 1.1 用户登录
- **URL**: `/api/login`
- **方法**: `POST`
- **权限**: 无需登录
- **功能**: 用户登录验证，支持多种角色
- **请求参数**:
  - `username`: 用户名
  - `password`: 密码
  - `captcha_id`: 验证码ID
  - `captcha_code`: 验证码

### 1.2 用户注册
- **URL**: `/api/register`
- **方法**: `POST`
- **权限**: 无需登录
- **功能**: 新用户注册
- **请求参数**:
  - `username`: 用户名
  - `password`: 密码
  - `full_name`: 真实姓名
  - `email`: 邮箱
  - `phone`: 电话
  - `role`: 角色（patient/doctor）
  - `captcha_id`: 验证码ID
  - `captcha_code`: 验证码

### 1.3 用户登出
- **URL**: `/api/logout`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 用户登出，清除session

### 1.4 获取验证码
- **URL**: `/api/captcha`
- **方法**: `GET`
- **权限**: 无需登录
- **功能**: 生成图形验证码
- **响应**: 验证码图片

### 1.5 验证验证码
- **URL**: `/api/captcha/verify`
- **方法**: `POST`
- **权限**: 无需登录
- **功能**: 验证用户输入的验证码

---

## 2. 检测分析模块

### 2.1 图片检测
- **URL**: `/api/predict`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 上传图片进行骨折检测
- **请求参数**:
  - `image`: 图片文件（base64或文件上传）
  - `model`: 使用的模型名称

### 2.2 视频检测
- **URL**: `/api/video/detect`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 上传视频进行骨折检测

### 2.3 摄像头实时检测
- **URL**: `/api/camera/detect`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 摄像头实时帧检测

### 2.4 获取检测历史
- **URL**: `/api/history`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取当前用户的检测历史记录

### 2.5 获取检测详情
- **URL**: `/api/history/<int:history_id>`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取单条检测记录的详细信息

### 2.6 删除检测记录
- **URL**: `/api/history/<int:history_id>`
- **方法**: `DELETE`
- **权限**: `@require_auth`
- **功能**: 删除指定检测记录

### 2.7 清空检测历史
- **URL**: `/api/history/clear/all`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 清空所有检测历史（仅管理员）

### 2.8 保存医学建议
- **URL**: `/api/history/<int:history_id>/advice`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 为检测记录添加医学建议

### 2.9 AI解读检测
- **URL**: `/api/interpret`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 使用AI解读检测结果

---

## 3. 数据统计模块

### 3.1 全局统计分析
- **URL**: `/api/analysis`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取系统全局统计数据

### 3.2 置信度趋势（全局）
- **URL**: `/api/analysis/confidence_series`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取检测置信度变化趋势

### 3.3 置信度趋势（个人）
- **URL**: `/api/analysis/user_confidence_series`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取当前用户的检测置信度趋势

### 3.4 用户统计
- **URL**: `/api/analysis/user_stats`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取当前用户的统计数据

---

## 4. 患者管理模块

### 4.1 获取患者列表
- **URL**: `/api/patients`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取患者列表

### 4.2 创建患者
- **URL**: `/api/patients`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 创建新患者档案

### 4.3 获取患者详情
- **URL**: `/api/patients/<int:patient_id>`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取指定患者的详细信息

### 4.4 更新患者信息
- **URL**: `/api/patients/<int:patient_id>`
- **方法**: `PUT`
- **权限**: `@require_auth`
- **功能**: 更新患者信息

### 4.5 删除患者
- **URL**: `/api/patients/<int:patient_id>`
- **方法**: `DELETE`
- **权限**: `@require_auth`
- **功能**: 删除患者档案

### 4.6 获取检查记录
- **URL**: `/api/examinations`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取检查记录列表

### 4.7 创建检查记录
- **URL**: `/api/examinations`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 创建新的检查记录

### 4.8 获取患者端医生列表
- **URL**: `/api/patient/doctors`
- **方法**: `GET`
- **权限**: `@require_role('patient')`
- **功能**: 患者获取自己的主治医师列表

### 4.9 获取患者检测记录
- **URL**: `/api/patient/detection-reports`
- **方法**: `GET`
- **权限**: `@require_role('patient')`
- **功能**: 患者获取自己的AI检测报告

### 4.10 获取患者病历
- **URL**: `/api/patient/medical-records`
- **方法**: `GET`
- **权限**: `@require_role('patient')`
- **功能**: 患者获取自己的病历记录

---

## 5. 医生管理模块

### 5.1 医生获取患者列表
- **URL**: `/api/doctor/patients`
- **方法**: `GET`
- **权限**: `@require_role('doctor')`
- **功能**: 医生获取关联的患者列表

### 5.2 医生添加患者
- **URL**: `/api/doctor/patients`
- **方法**: `POST`
- **权限**: `@require_role('doctor')`
- **功能**: 医生添加新患者

### 5.3 归档/恢复患者
- **URL**: `/api/doctor/patients/<int:patient_id>/archive`
- **方法**: `PUT`
- **权限**: `@require_role('doctor')`
- **功能**: 归档或恢复患者关系
- **参数**: `status` ('archived' 或 'active')

### 5.4 获取所有患者（用于选择）
- **URL**: `/api/doctor/all-patients`
- **方法**: `GET`
- **权限**: `@require_role('doctor')`
- **功能**: 获取所有患者列表（用于创建病历时选择）

### 5.5 创建病历
- **URL**: `/api/doctor/medical-records`
- **方法**: `POST`
- **权限**: `@require_role('doctor')`
- **功能**: 医生创建病历记录

### 5.6 获取病历列表
- **URL**: `/api/doctor/medical-records`
- **方法**: `GET`
- **权限**: `@require_role('doctor')`
- **功能**: 医生获取自己创建的病历列表

### 5.7 更新病历
- **URL**: `/api/doctor/medical-records/<int:record_id>`
- **方法**: `PUT`
- **权限**: `@require_role('doctor')`
- **功能**: 更新病历信息

### 5.8 删除病历
- **URL**: `/api/doctor/medical-records/<int:record_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('doctor')`
- **功能**: 删除病历记录

### 5.9 获取医生工作台数据
- **URL**: `/api/doctor/dashboard`
- **方法**: `GET`
- **权限**: `@require_role('doctor')`
- **功能**: 获取医生工作台统计数据

### 5.10 医生注册申请
- **URL**: `/api/doctor/register`
- **方法**: `POST`
- **权限**: 无需登录
- **功能**: 提交医生入驻申请

---

## 6. 管理员功能模块

### 6.1 获取用户列表
- **URL**: `/api/users`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取所有用户列表

### 6.2 创建用户
- **URL**: `/api/users`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 管理员创建新用户

### 6.3 更新用户
- **URL**: `/api/users/<int:user_id>`
- **方法**: `PUT`
- **权限**: `@require_role('admin')`
- **功能**: 更新用户信息

### 6.4 删除用户
- **URL**: `/api/users/<int:user_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 删除用户

### 6.5 获取医生注册审核列表
- **URL**: `/api/admin/doctor-registrations`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取待审核的医生注册申请

### 6.6 审核医生注册
- **URL**: `/api/admin/doctor-registrations/<int:registration_id>/review`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 审核通过或拒绝医生注册

### 6.7 获取管理员仪表盘数据
- **URL**: `/api/admin/dashboard`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取管理员仪表盘统计数据

### 6.8 获取系统统计
- **URL**: `/api/admin/statistics`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取系统详细统计数据

### 6.9 获取操作日志
- **URL**: `/api/admin/logs`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取系统操作日志

### 6.10 删除日志
- **URL**: `/api/logs/<int:log_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 删除单条日志

### 6.11 清空日志
- **URL**: `/api/logs/clear`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 清空所有日志

---

## 7. AI模型管理模块

### 7.1 获取模型列表
- **URL**: `/api/models`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取所有可用的AI模型

### 7.2 获取已发布模型
- **URL**: `/api/models/published`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取已发布的模型列表

### 7.3 发布模型
- **URL**: `/api/models/<int:model_id>/publish`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 发布模型供用户使用

### 7.4 禁用模型
- **URL**: `/api/models/<int:model_id>/disable`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 禁用模型

### 7.5 启用模型
- **URL**: `/api/models/<int:model_id>/enable`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 启用模型

### 7.6 删除模型
- **URL**: `/api/models/<int:model_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 删除模型

### 7.7 训练模型
- **URL**: `/api/models/train`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 提交模型训练任务

### 7.8 获取训练任务列表
- **URL**: `/api/training/tasks`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取模型训练任务列表

### 7.9 获取训练任务详情
- **URL**: `/api/training/tasks/<int:task_id>`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取训练任务详细信息

### 7.10 获取训练进度
- **URL**: `/api/training/tasks/<int:task_id>/progress`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取训练任务的实时进度

### 7.11 获取训练日志
- **URL**: `/api/training/tasks/<int:task_id>/logs`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取训练任务的日志

### 7.12 停止训练任务
- **URL**: `/api/training/tasks/<int:task_id>/stop`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 停止正在进行的训练任务

---

## 8. 系统监控模块

### 8.1 获取系统信息
- **URL**: `/api/monitor/system`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取系统运行信息（CPU、内存、磁盘等）

### 8.2 获取系统统计
- **URL**: `/api/monitor/stats`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 获取系统使用统计数据

### 8.3 获取系统设置
- **URL**: `/api/settings`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取系统配置信息

### 8.4 更新系统设置
- **URL**: `/api/settings`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 更新系统配置

### 8.5 获取AI设置
- **URL**: `/api/ai-settings`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取AI相关配置

---

## 9. 消息通知模块

### 9.1 获取消息联系人
- **URL**: `/api/messages/contacts`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取可发送消息的联系人列表

### 9.2 获取聊天记录
- **URL**: `/api/messages/conversation/<int:user_id>`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取与指定用户的聊天记录

### 9.3 发送消息
- **URL**: `/api/messages/send`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 发送消息给指定用户

### 9.4 标记消息已读
- **URL**: `/api/messages/mark-read`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 标记消息为已读状态

### 9.5 获取未读消息数
- **URL**: `/api/messages/unread-count`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取未读消息数量

### 9.6 获取公告列表
- **URL**: `/api/announcements`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取当前用户的公告列表

### 9.7 标记公告已读
- **URL**: `/api/announcements/<int:announcement_id>/read`
- **方法**: `POST`
- **权限**: `@require_auth`
- **功能**: 标记公告为已读

---

## 10. 公告管理模块

### 10.1 获取公告列表（管理员）
- **URL**: `/api/admin/announcements`
- **方法**: `GET`
- **权限**: `@require_role('admin')`
- **功能**: 管理员获取所有公告

### 10.2 创建公告
- **URL**: `/api/admin/announcements`
- **方法**: `POST`
- **权限**: `@require_role('admin')`
- **功能**: 创建新公告

### 10.3 更新公告
- **URL**: `/api/admin/announcements/<int:announcement_id>`
- **方法**: `PUT`
- **权限**: `@require_role('admin')`
- **功能**: 更新公告内容

### 10.4 删除公告
- **URL**: `/api/admin/announcements/<int:announcement_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('admin')`
- **功能**: 删除公告

---

## 11. 数据集管理模块

### 11.1 获取数据集列表
- **URL**: `/api/datasets`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取数据集列表

### 11.2 上传数据集
- **URL**: `/api/datasets`
- **方法**: `POST`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 上传新的数据集

### 11.3 更新数据集
- **URL**: `/api/datasets/<int:dataset_id>`
- **方法**: `PUT`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 更新数据集信息

### 11.4 删除数据集
- **URL**: `/api/datasets/<int:dataset_id>`
- **方法**: `DELETE`
- **权限**: `@require_role('admin', 'doctor')`
- **功能**: 删除数据集

### 11.5 获取所有数据集
- **URL**: `/api/datasets/all`
- **方法**: `GET`
- **权限**: `@require_auth`
- **功能**: 获取所有可用数据集

---

## 12. 文件服务

### 12.1 获取结果图片
- **URL**: `/results/<path:filename>`
- **方法**: `GET`
- **权限**: 无需登录
- **功能**: 获取检测结果的图片文件

### 12.2 获取上传图片
- **URL**: `/uploads/<path:filename>`
- **方法**: `GET`
- **权限**: 无需登录
- **功能**: 获取用户上传的图片文件

---

## 权限说明

### 装饰器说明
- `@require_auth`: 需要登录（验证token）
- `@require_role('admin')`: 仅管理员可访问
- `@require_role('doctor')`: 仅医生可访问
- `@require_role('patient')`: 仅患者可访问
- `@require_role('admin', 'doctor')`: 管理员或医生可访问

### 角色权限
| 角色 | 权限范围 |
|------|----------|
| admin | 系统管理、用户管理、模型管理、数据统计、公告管理等 |
| doctor | 患者管理、病历管理、检测分析、AI解读等 |
| patient | 查看自己的病历、检测报告、主治医师信息等 |

---

## 技术栈

- **框架**: Flask
- **数据库**: SQLite + SQLAlchemy
- **AI模型**: YOLOv8 (Ultralytics)
- **深度学习**: PyTorch
- **图像处理**: OpenCV, PIL
- **认证**: Session + Token
- **跨域**: Flask-CORS

---

## 备注

1. 所有API返回格式统一为JSON
2. 错误返回格式: `{"error": "错误信息"}`
3. 成功返回格式: `{"success": true, "data": ...}`
4. 需要认证的接口需在请求头中携带token
