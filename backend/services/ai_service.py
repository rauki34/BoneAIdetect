"""AI 服务层

从 app.py 抽出：AI 配置读取、统一 LLM 客户端构造、医疗建议生成、
助手对话调用与降级回复。被 api/ai.py 与 api/detection.py 共用。
"""
import json
import threading
from datetime import datetime

from flask import current_app

from database import db, AIConversation, DetectionHistory, SystemSettings
from services.llm_client import LLMClient, LLMError
from utils.logger import logger

# ==================== AI助手接口 ====================

# AI助手系统提示词
AI_SYSTEM_PROMPT = """你是一位专业的骨科医疗AI助手，专门为骨折患者提供康复指导和健康咨询。

你的职责：
1. 解答骨折康复期的常见问题（如饮食、运动、护理等）
2. 提供骨折愈合过程的一般性知识
3. 解释医学术语，帮助患者理解诊断报告
4. 提醒患者按时复查和遵循医嘱

重要限制：
1. 你提供的信息仅供参考，不能替代专业医生的诊断和治疗建议
2. 对于紧急医疗情况，必须建议患者立即就医
3. 不要给出具体的药物剂量或治疗方案
4. 不要诊断疾病，只能提供一般性健康信息
5. 如果患者症状严重或异常，建议立即联系主治医生

回答风格：
- 使用通俗易懂的语言
- 保持友善、耐心的态度
- 回答简洁明了，避免过于专业的术语
- 适当使用表情符号增加亲和力
- 回答控制在300字以内"""

# ==================== AI 解读接口 ====================
# 本地 AI 服务地址改由 config.py 的 AI_SERVICE_URL 提供（见 get_llm_client）

def get_ai_settings():
    """获取AI服务配置"""
    ai_provider_setting = SystemSettings.query.filter_by(key='ai_provider').first()
    ai_provider = ai_provider_setting.value if ai_provider_setting else 'local'
    
    ai_api_key_setting = SystemSettings.query.filter_by(key='ai_api_key').first()
    ai_api_key = ai_api_key_setting.value if ai_api_key_setting else ''
    
    ai_api_url_setting = SystemSettings.query.filter_by(key='ai_api_url').first()
    ai_api_url = ai_api_url_setting.value if ai_api_url_setting else ''
    
    ai_model_setting = SystemSettings.query.filter_by(key='ai_model').first()
    ai_model = ai_model_setting.value if ai_model_setting else 'gpt-4'
    
    return {
        'provider': ai_provider,
        'api_key': ai_api_key,
        'api_url': ai_api_url,
        'model': ai_model
    }

def get_llm_client():
    """由系统 AI 配置构造统一 LLM 客户端

    替代原先在各处重复的 if provider == ... 分支。
    各 Provider 的默认 timeout / max_tokens 已按原 call_* 函数设定，
    因此建议生成类调用无需显式传参即可保持原行为。
    """
    ai_config = get_ai_settings()
    # 本地服务地址来自 config.py（环境变量 AI_SERVICE_URL），
    # 仅当数据库中未单独配置 ai_api_url 时生效
    if ai_config.get('provider') == 'local' and not ai_config.get('api_url'):
        # 原实现引用裸 app（本模块从未导入它）→ 一旦走到这个分支就 NameError。
        # 而默认配置恰恰是 provider=local 且数据库未配置 api_url，
        # 也就是这个分支一旦被执行就是崩溃。
        ai_config['api_url'] = current_app.config.get('AI_SERVICE_URL', '')
    return LLMClient.from_settings(ai_config)

def generate_ai_advice_async(history_id, detections):
    """异步生成AI医疗建议
    
    Args:
        history_id: 检测历史记录ID
        detections: 检测结果列表
    """
    # 在**请求线程里**取出真实 app 对象再进后台线程。
    # 线程内没有请求上下文，原实现直接调 current_app 会抛
    # "Working outside of application context"——包括它自己的
    # get_ai_settings() 数据库查询，也就是说这个函数此前根本跑不起来。
    app = current_app._get_current_object()

    def generate_advice():
      # 整个线程体都在应用上下文里跑：get_ai_settings() / get_llm_client()
      # 都要查 SystemSettings 表，只包住最后的保存是不够的
      with app.app_context():
        try:
            # 构建提示词
            detection_summary = []
            for i, det in enumerate(detections, 1):
                cls = det.get("class", "未知")
                conf = det.get("confidence", 0)
                bbox = det.get("bbox", [])
                detection_summary.append(f"检测{i}: 类别={cls}, 置信度={conf:.2f}, 位置={bbox}")
            
            detection_text = "\n".join(detection_summary)
            
            prompt = f"""你是一位专业的骨科医生助手。我将提供骨折检测的X光片检测结果，请根据检测信息进行专业分析。

检测结果：
{detection_text}

请提供以下信息：
1. 影像分析：根据检测到的骨折类型和位置进行分析
2. 风险评估：评估病情的严重程度
3. 进一步检查建议：建议进行哪些进一步检查（如CT、MRI等）
4. 处置建议：初步的处置建议（如固定、手术、转诊等）
5. 注意事项：患者应该注意的事项
6. 免责声明：提示此为AI辅助诊断，最终诊断需由专业医生确定

请用中文回复，结构化输出。"""
            
            # 获取AI配置并构造统一客户端
            # 不显式传 timeout / max_tokens：各 Provider 的默认值与
            # 原 call_* 函数保持一致（openai 60s/1000, modelscope 120s/2000,
            # custom 60s/不限制, local 180s/不限制）
            ai_config = get_ai_settings()
            provider = ai_config['provider']

            client = get_llm_client()
            reply = client.chat_text(prompt)

            # 构建医疗建议数据
            medical_advice = {
                'interpretation': reply,
                'diagnosis': '',
                'treatment': '',
                'precautions': '',
                'generated_at': datetime.utcnow().isoformat(),
                'ai_provider': provider
            }
            
            # 尝试从回复中提取结构化信息
            lines = reply.split('\n')
            current_section = ''
            
            for line in lines:
                lower_line = line.lower()
                if '诊断' in lower_line or '分析' in lower_line:
                    current_section = 'diagnosis'
                elif '治疗' in lower_line or '处置' in lower_line:
                    current_section = 'treatment'
                elif '注意' in lower_line or '建议' in lower_line:
                    current_section = 'precautions'
                elif line.strip() and current_section:
                    medical_advice[current_section] += line + '\n'
            
            # 保存到数据库
            history = db.session.get(DetectionHistory, history_id)
            if history:
                history.medical_advice = json.dumps(medical_advice, ensure_ascii=False)
                db.session.commit()
                logger.info("AI建议生成成功: history_id=%s", history_id)
            else:
                logger.info("历史记录不存在: history_id=%s", history_id)

        except Exception as e:
            logger.error("生成AI建议失败: history_id=%s, error=%s", history_id, e)
    
    # 启动后台线程
    thread = threading.Thread(target=generate_advice)
    thread.daemon = True
    thread.start()

def _build_assistant_messages(user_id, session_id):
    """拼装助手对话上下文（系统提示词 + 最近 10 条历史）"""
    history = AIConversation.query.filter_by(
        patient_id=user_id,
        session_id=session_id
    ).order_by(AIConversation.created_at.desc()).limit(10).all()

    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    # 查询是倒序的，需反转回时间正序
    for h in reversed(history):
        role = "user" if h.message_type == "user" else "assistant"
        messages.append({"role": role, "content": h.message_content})
    return messages

def call_ai_assistant_api(messages):
    """调用系统配置的AI服务进行对话

    失败时降级为本地模拟回复（保持原有容错行为）。
    注意：降级是静默的 —— 用户拿到的是预设话术而非真实模型输出，
    因此以 WARNING 记录失败原因，避免"服务其实一直不可用"被掩盖。
    """
    try:
        client = get_llm_client()

        # max_tokens 保持原值 500。
        # 超时：远端服务沿用原有的 60s；本地模型生成较慢（实测约 90s），
        # 原实现给本地设的 30s 必然超时并静默降级为模拟回复，故改为
        # 使用 Provider 默认值（local=180s）。
        timeout = None if client.provider_name == 'local' else 60
        return client.chat(messages, timeout=timeout, max_tokens=500)

    except LLMError as e:
        logger.warning('AI 服务不可用，已降级为模拟回复: %s', e)
        return get_mock_reply(messages)
    except Exception as e:
        logger.error('AI 服务调用异常，已降级为模拟回复: %s', e, exc_info=True)
        return get_mock_reply(messages)

def get_mock_reply(messages):
    """获取模拟回复（当AI服务不可用时使用）"""
    # 获取最后一条用户消息
    user_message = ""
    for msg in reversed(messages):
        if msg.get('role') == 'user':
            user_message = msg.get('content', '')
            break
    
    user_message_lower = user_message.lower()
    
    # 根据关键词返回预设回复
    if any(kw in user_message_lower for kw in ['恢复', '愈合', '多久', '时间']):
        return """骨折的恢复时间因人而异，主要取决于：

📌 **影响因素**：
• 骨折类型和严重程度
• 年龄和身体状况
• 治疗方式（手术/保守）
• 康复配合度

⏱️ **一般时间参考**：
• 简单骨折：6-8周初步愈合
• 复杂骨折：3-6个月或更长
• 完全恢复功能：可能需要6-12个月

💡 **建议**：定期复查X光，遵医嘱进行康复训练。如有异常请及时联系您的主治医生！"""
    
    elif any(kw in user_message_lower for kw in ['饮食', '吃', '营养', '补钙']):
        return """骨折康复期的饮食建议：

🥛 **推荐食物**：
• 高钙食物：牛奶、酸奶、豆腐、深绿色蔬菜
• 优质蛋白：鸡蛋、鱼肉、瘦肉、豆类
• 维生素C：柑橘、猕猴桃、西红柿（促进胶原合成）
• 维生素D：鱼类、蛋黄、适当晒太阳

⚠️ **注意事项**：
• 避免过量饮酒和吸烟
• 控制盐分摄入
• 不要盲目大量补钙，遵医嘱

💊 **提醒**：如需服用钙片或其他营养品，请先咨询医生。"""
    
    elif any(kw in user_message_lower for kw in ['运动', '锻炼', '康复', '活动']):
        return """骨折后的康复运动要循序渐进：

📋 **康复阶段**：

**早期（骨折后1-2周）**：
• 主要休息，抬高患肢
• 可做未固定关节的轻微活动
• 肌肉等长收缩练习

**中期（骨折后2-6周）**：
• 在医生允许下开始轻度活动
• 逐步增加关节活动范围
• 轻度肌肉力量训练

**后期（骨折愈合后）**：
• 逐步恢复正常活动
• 加强肌肉力量训练
• 恢复关节灵活性

⚠️ **重要提醒**：所有康复运动都应在医生指导下进行，切勿自行盲目锻炼！"""
    
    elif any(kw in user_message_lower for kw in ['注意', '护理', '照顾', '保养']):
        return """骨折康复期护理要点：

🏠 **日常护理**：
• 保持石膏/支具干燥清洁
• 观察患肢血液循环（颜色、温度）
• 抬高患肢，减轻肿胀
• 按医嘱定期换药/复查

🚨 **异常情况需立即就医**：
• 患肢剧烈疼痛或麻木
• 手指/脚趾发紫、发凉
• 石膏内异味或渗液
• 发热（可能感染）

💊 **用药提醒**：
• 按时服用医生开的药物
• 不要自行停药或增减剂量
• 如有不适及时告知医生

有任何疑问，建议及时联系您的主治医生！"""
    
    elif any(kw in user_message_lower for kw in ['疼痛', '疼', '痛', '不舒服']):
        return """关于骨折后疼痛的管理：

✅ **正常情况**：
• 骨折后前几天疼痛较明显是正常的
• 抬高患肢可减轻肿胀和疼痛
• 按医嘱服用止痛药

⚠️ **需警惕的情况**：
• 疼痛突然加重
• 止痛药无法缓解的剧烈疼痛
• 伴有发热、红肿
• 石膏/支具过紧导致的疼痛

💡 **缓解方法**：
• 冰敷（骨折初期，每次15-20分钟）
• 抬高患肢
• 保持舒适体位
• 分散注意力

🚨 **提醒**：如果疼痛持续不缓解或加重，请立即联系医生！"""
    
    else:
        return """感谢您的提问！😊

作为您的AI健康助手，我可以帮您解答：
• 骨折康复期的饮食建议
• 康复运动和锻炼指导
• 日常护理注意事项
• 骨折愈合的一般知识
• 诊断报告的解释

⚠️ **重要提醒**：我提供的信息仅供参考，不能替代专业医生的诊断和治疗建议。如有紧急情况或症状加重，请立即联系您的主治医生或前往医院就诊。

您还有什么想了解的吗？"""
