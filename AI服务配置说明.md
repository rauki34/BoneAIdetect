# AI服务配置说明

## 功能概述

系统支持四种AI服务提供商，用于生成医疗建议：
1. **本地部署** - 使用本地Qwen3-VL-4B模型
2. **OpenAI API** - 使用OpenAI的GPT模型
3. **ModelScope API** - 使用阿里ModelScope平台的多模态大模型
4. **自定义API** - 使用其他兼容OpenAI格式的API

## 配置方法

### 1. 本地部署（默认）

**特点：**
- 无需网络连接（除首次下载模型）
- 数据隐私性好，图片不上传到云端
- 需要6GB+显存
- 响应速度取决于本地硬件

**配置步骤：**
1. 确保AI服务已启动：
   ```bash
   cd AI
   python app.py
   ```
2. 在系统设置中选择"本地部署 (Qwen3-VL)"
3. 点击"测试连接"验证

**适用场景：**
- 对数据隐私要求高的场景
- 有本地GPU资源的场景
- 网络不稳定的场景

---

### 2. OpenAI API

**特点：**
- 需要OpenAI账号和API密钥
- 需要网络连接
- 按使用量付费
- 响应速度快
- 模型能力强

**配置步骤：**
1. 获取OpenAI API密钥：
   - 访问 https://platform.openai.com/
   - 注册/登录账号
   - 在API Keys页面创建新密钥

2. 在系统设置中：
   - 选择"OpenAI API"
   - 输入API密钥（格式：sk-xxxxxxxx）
   - 选择模型（推荐GPT-4或GPT-4 Turbo）

3. 点击"测试连接"验证

**模型选择：**
| 模型 | 特点 | 适用场景 |
|------|------|----------|
| GPT-4 | 最强能力，价格较高 | 复杂诊断场景 |
| GPT-4 Turbo | 能力接近GPT-4，更快更便宜 | 推荐日常使用 |
| GPT-3.5 Turbo | 价格便宜，能力较弱 | 简单场景，成本控制 |

**费用参考：**
- GPT-4: ~$0.03/1K tokens
- GPT-4 Turbo: ~$0.01/1K tokens
- GPT-3.5 Turbo: ~$0.001/1K tokens

---

### 3. ModelScope API

**特点：**
- 阿里达摩院推出的模型服务平台
- 支持多模态大模型（图文理解）
- 国内访问速度快
- 支持Qwen系列等开源模型

**配置步骤：**
1. 获取ModelScope Token：
   - 访问 https://www.modelscope.cn/
   - 注册/登录账号
   - 进入"我的" -> "访问令牌"创建Token

2. 在系统设置中：
   - 选择"ModelScope API"
   - 输入Token
   - 选择或输入模型ID

3. 点击"测试连接"验证

**推荐模型：**
| 模型ID | 说明 | 特点 |
|--------|------|------|
| Qwen/Qwen3.5-397B-A17B | 通义千问3.5 | 最新版本，能力强 |
| Qwen/Qwen2-VL-72B-Instruct | 多模态大模型 | 支持图文理解 |
| Qwen/Qwen2-VL-7B-Instruct | 轻量多模态 | 速度快，显存需求低 |
| OpenGVLab/InternVL2-Llama3-76B | 多模态大模型 | 视觉理解能力强 |

**费用：**
- 新用户有免费额度
- 超出后按调用量计费
- 具体价格参考ModelScope官网

---

### 4. 自定义API

**特点：**
- 支持任何兼容OpenAI API格式的服务
- 包括：文心一言、通义千问、智谱AI等
- 需要配置API地址和密钥

**配置步骤：**
1. 选择"自定义API"
2. 填写以下信息：
   - **API地址**：完整的API端点URL
   - **API密钥**：服务提供商的密钥
   - **模型名称**：使用的模型标识

3. 点击"测试连接"验证

**常见服务商配置示例：**

#### 百度文心一言
```
API地址: https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions
API密钥: 通过百度AI平台获取
模型名称: ernie-bot-4
```

#### 阿里通义千问
```
API地址: https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation
API密钥: 通过阿里云获取
模型名称: qwen-turbo
```

#### 智谱AI (GLM)
```
API地址: https://open.bigmodel.cn/api/paas/v4/chat/completions
API密钥: 通过智谱AI平台获取
模型名称: glm-4
```

#### 本地Ollama
```
API地址: http://localhost:11434/v1/chat/completions
API密钥: ollama（或任意字符串）
模型名称: llama2/qwen/等
```

---

## 切换AI服务

1. 进入系统设置页面
2. 在"AI服务设置"部分选择提供商
3. 填写相应配置
4. 点击"保存设置"
5. 点击"测试连接"验证配置

**注意：**
- 切换后新的检测将使用新的AI服务
- 历史记录中的AI建议不会自动更新

---

## 故障排查

### 问题1：测试连接失败

**可能原因：**
- API密钥错误
- 网络连接问题
- API服务不可用
- 余额不足（付费API）

**解决方法：**
1. 检查API密钥是否正确
2. 检查网络连接
3. 查看API服务商状态页面
4. 检查账户余额

### 问题2：响应超时

**可能原因：**
- 网络延迟高
- AI服务负载高
- 提示词太长

**解决方法：**
1. 检查网络连接
2. 稍后重试
3. 简化提示词

### 问题3：返回内容质量差

**可能原因：**
- 使用的模型能力较弱
- 提示词不够清晰

**解决方法：**
1. 切换到更强的模型（如GPT-4）
2. 在检测时提供自定义提示词

---

## 安全建议

1. **API密钥保护**
   - 不要将密钥硬编码在代码中
   - 定期更换密钥
   - 使用环境变量存储密钥

2. **数据隐私**
   - 敏感数据建议使用本地部署
   - 使用API时注意服务商的数据使用政策

3. **成本控制**
   - 设置使用限额
   - 监控API调用量
   - 选择合适的模型

---

## 技术实现

### 后端代码位置
- 配置管理：`backend/app.py` - `get_settings()` 和 `update_settings()`
- AI调用：`backend/app.py` - `interpret_detection()`
- AI服务封装：`backend/app.py` - `call_local_ai()`, `call_openai_api()`, `call_custom_api()`

### 前端代码位置
- 设置界面：`frontend/src/views/Home.vue` - 系统设置部分

### 数据存储
- 配置存储在 `system_settings` 表中
- 字段：`ai_provider`, `ai_api_key`, `ai_api_url`, `ai_model`

---

## 更新日志

### 2024-03-12
- 添加AI服务提供商选择功能
- 支持本地部署、OpenAI API、ModelScope API、自定义API四种模式
- 添加ModelScope API支持，支持多模态图文理解
- 添加连接测试功能
- 添加配置保存和读取功能
