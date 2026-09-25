"""AI 助手对话接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import func

from core.auth import get_current_user, require_auth, require_role
from core.helpers import can_access_patient
from core.ratelimit import limit
from database import db, AIConversation, safe_json_loads
from services.ai_service import (
    _build_assistant_messages, build_rag_context, call_ai_assistant_api,
    get_llm_client,
)
from services.llm_client import LLMError
from utils.logger import logger

bp = Blueprint('ai', __name__)


def _resolve_request_patient(user, data):
    """解析请求里的 patient_id，返回 (patient_id, include_personal, error)

    error 非 None 时调用方原样返回它（已含状态码）。

    此前本文件 9 处一律写死 `patient_id=user.id`，而那一列的语义是
    **会话归属人**；于是医生登录时医生 id 被当成患者 id 用来检索"个人病历"，
    医生永远看不到绑定患者的病历，而 `can_access_patient` 在本文件从未被调用。
    现在把「会话归属人」与「本次检索的主体患者」分开：

    - 患者：不传 → 自己 + 含个人切片（**与改造前逐字一致**）；传别人 → 403
    - 医生/管理员：不传 → (None, False)，只查共享库（不再拿自身 id 当患者 id，
      也不强制必填 —— 纯医学知识问题本就无需患者上下文）；传了 → 必须过
      can_access_patient
    """
    raw = (data or {}).get('patient_id')
    if raw in (None, '', 0):
        if user.role == 'patient':
            return user.id, True, None
        return None, False, None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None, False, (jsonify({
            'success': False,
            'error': 'patient_id 必须是整数',
            'error_code': 'VALIDATION_001',
        }), 400)
    if not can_access_patient(user, pid):
        # 角色合法但无权访问该患者的数据，与 AUTH_002（角色门禁）区分开
        logger.warning('用户 %s(%s) 尝试访问无权查看的患者 %s 的对话上下文',
                       user.username, user.role, pid)
        return None, False, (jsonify({
            'success': False,
            'error': '无权访问该患者的数据',
            'error_code': 'AUTH_003',
        }), 403)
    return pid, True, None

@bp.route("/api/ai-assistant/chat/stream", methods=["POST"])
@limit('ai_chat', key='user')   # AI 调用按用户限流：token 计费，成本归属需清晰
@require_role('patient', 'doctor', 'admin')
def ai_assistant_chat_stream():
    """AI助手流式对话（SSE）

    事件格式：
        data: {"delta": "增量文本"}
        data: {"error": "错误信息"}
        data: [DONE]

    注意：SSE 一旦开始发送就无法再更改 HTTP 状态码，
    因此错误也以 200 + error 事件返回，由前端统一处理。
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400

    session_id = data.get('session_id', '')
    message = data.get('message', '').strip()
    if not session_id:
        return jsonify({"success": False, "error": "会话ID不能为空"}), 400
    if not message:
        return jsonify({"success": False, "error": "消息内容不能为空"}), 400

    user = get_current_user()
    user_id = user.id                 # 会话归属人，不是检索主体

    subject_id, include_personal, err = _resolve_request_patient(user, data)
    if err:
        return err

    # 用户消息先落库，保证即使流式中断也不丢失提问
    db.session.add(AIConversation(
        patient_id=user_id,
        session_id=session_id,
        message_type='user',
        message_content=message,
    ))
    db.session.commit()

    # RAG 检索必须在视图内完成：生成器在请求上下文之外执行
    rag_context, references = build_rag_context(
        message, patient_id=subject_id, include_personal=include_personal,
    )
    messages = _build_assistant_messages(
        user_id, session_id, rag_context=rag_context, question=message,
    )

    # 必须在视图内构造客户端：生成器在请求上下文之外执行，
    # 此时 get_llm_client() 内部的数据库查询会抛
    # "Working outside of application context"
    client = get_llm_client()
    # 超时用 Provider 默认值（modelscope 120s）。此前对远端固定 60s，
    # 注入参考资料后实测单次回答需 38-45s，余量过小，
    # 稍有波动就会超时并静默降级为预设话术。
    timeout = None

    def generate():
        collected = []
        try:
            for chunk in client.chat(messages, stream=True,
                                     timeout=timeout, max_tokens=500):
                collected.append(chunk)
                yield f'data: {json.dumps({"delta": chunk}, ensure_ascii=False)}\n\n'
        except LLMError as e:
            logger.warning('流式对话失败: %s', e)
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
        except Exception as e:
            logger.error('流式对话异常: %s', e, exc_info=True)
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
        finally:
            # 合并完整回复落库，否则下轮对话拿不到上下文。
            # 生成器在请求上下文之外执行，需自带 app context。
            if collected:
                try:
                    with current_app.app_context():
                        db.session.add(AIConversation(
                            patient_id=user_id,
                            session_id=session_id,
                            message_type='assistant',
                            message_content=''.join(collected),
                            references=(json.dumps(references, ensure_ascii=False)
                                        if references else None),
                        ))
                        db.session.commit()
                except Exception as e:
                    logger.error('保存流式回复失败: %s', e, exc_info=True)
            # 引用先于 [DONE] 送出。前端目前未使用本流式接口，
            # 这里只为契约完整（前端若改用 SSE，引用已经就位）。
            if references:
                yield f'data: {json.dumps({"references": references}, ensure_ascii=False)}\n\n'
            yield 'data: [DONE]\n\n'

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )

@bp.route("/api/ai-assistant/chat", methods=["POST"])
@limit('ai_chat', key='user')   # AI 调用按用户限流
@require_role('patient', 'doctor', 'admin')
def ai_assistant_chat():
    """AI助手对话接口 - 使用系统配置的AI服务"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400
    
    session_id = data.get('session_id', '')
    message = data.get('message', '').strip()
    
    if not session_id:
        return jsonify({"success": False, "error": "会话ID不能为空"}), 400
    
    if not message:
        return jsonify({"success": False, "error": "消息内容不能为空"}), 400
    
    user = get_current_user()

    subject_id, include_personal, err = _resolve_request_patient(user, data)
    if err:
        return err

    try:
        # 保存用户消息到数据库
        user_msg = AIConversation(
            patient_id=user.id,
            session_id=session_id,
            message_type='user',
            message_content=message
        )
        db.session.add(user_msg)
        db.session.commit()

        # RAG：检索共享知识库 + 主体患者的个人病历。
        # 检索失败返回 ('', [])，对话退回无参考资料的回答，不会因此不可用。
        rag_context, references = build_rag_context(
            message, patient_id=subject_id, include_personal=include_personal,
        )

        # 构建消息历史（系统提示词 + RAG 参考资料 + 最近 10 条上下文）
        messages = _build_assistant_messages(
            user.id, session_id, rag_context=rag_context, question=message,
        )

        # 使用系统配置的AI服务
        reply = call_ai_assistant_api(messages)

        # 保存AI回复到数据库（引用一并落库，刷新页面后引用卡片才不丢）
        ai_msg = AIConversation(
            patient_id=user.id,
            session_id=session_id,
            message_type='assistant',
            message_content=reply,
            references=json.dumps(references, ensure_ascii=False) if references else None,
        )
        db.session.add(ai_msg)
        db.session.commit()

        return jsonify({
            "success": True,
            "reply": reply,
            "references": references,
            "session_id": session_id
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"AI助手对话失败: {e}")
        return jsonify({"success": False, "error": "AI服务暂时不可用，请稍后再试"}), 503

@bp.route("/api/ai-assistant/history", methods=["GET"])
@require_role('patient', 'doctor', 'admin')
def ai_assistant_history():
    """获取AI助手对话历史"""
    session_id = request.args.get('session_id', '')
    
    if not session_id:
        return jsonify({"success": False, "error": "会话ID不能为空"}), 400
    
    user = get_current_user()
    
    try:
        # 获取该会话的所有消息
        conversations = AIConversation.query.filter_by(
            patient_id=user.id,
            session_id=session_id
        ).order_by(AIConversation.created_at.asc()).all()
        
        messages = []
        for conv in conversations:
            messages.append({
                "role": conv.message_type,
                "content": conv.message_content,
                # 引用随消息一并返回，否则刷新页面后引用卡片就没了
                "references": safe_json_loads(conv.references, []),
                "timestamp": conv.created_at.isoformat() if conv.created_at else None
            })
        
        return jsonify({
            "success": True,
            "messages": messages,
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return jsonify({"success": False, "error": "获取历史记录失败"}), 500

@bp.route("/api/ai-assistant/sessions", methods=["GET"])
@require_role('patient', 'doctor', 'admin')
def ai_assistant_sessions():
    """获取用户的所有会话列表"""
    user = get_current_user()
    
    try:
        # 获取用户的所有会话（按最后消息时间排序）
        sessions = db.session.query(
            AIConversation.session_id,
            func.max(AIConversation.created_at).label('last_time'),
            func.count(AIConversation.id).label('message_count')
        ).filter_by(
            patient_id=user.id
        ).group_by(
            AIConversation.session_id
        ).order_by(
            func.max(AIConversation.created_at).desc()
        ).limit(20).all()
        
        result = []
        for s in sessions:
            # 获取每条会话的最后一条消息
            last_msg = AIConversation.query.filter_by(
                patient_id=user.id,
                session_id=s.session_id
            ).order_by(AIConversation.created_at.desc()).first()
            
            result.append({
                "session_id": s.session_id,
                "last_message": last_msg.message_content if last_msg else "",
                "last_time": s.last_time.isoformat() if s.last_time else None,
                "message_count": s.message_count
            })
        
        return jsonify({
            "success": True,
            "sessions": result
        })
        
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return jsonify({"success": False, "error": "获取会话列表失败"}), 500
