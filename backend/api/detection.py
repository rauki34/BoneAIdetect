"""检测接口：图像/视频/摄像头检测、检测历史、影像解读

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。

注意：WebSocket 推流路由 /ws/video/<task_id> 依赖绑定 app 实例的
flask_sock 扩展，仍保留在 app.py。
"""
import base64
import json
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import requests
from flask import Blueprint, jsonify, request
from ultralytics import YOLO

from core.auth import get_current_user, require_auth, require_role
from core.helpers import can_access_patient, get_filtered_reports, log_operation
from core.paths import MODEL_CANDIDATES, RESULTS, UPLOADS
from core.ratelimit import limit
from core.state import models, video_tasks
from database import CustomModel, DetectionHistory, db
from services.ai_service import (
    build_rag_context, get_ai_settings, get_llm_client,
)
from services.llm_client import (
    LLMConfigError, LLMConnectionError, LLMTimeoutError,
)
from utils.logger import logger

bp = Blueprint('detection', __name__)

# ==================== 检测接口 ====================

@bp.route("/api/predict", methods=["POST"])
@require_role('admin', 'doctor')
def predict():
    user = get_current_user()
    file = request.files["file"]
    model_name = request.form.get("model", "yolov8s")
    username = user.username  # 使用当前登录用户

    filename = f"{int(time.time())}_{file.filename}"
    img_path = os.path.join(UPLOADS, filename)
    file.save(img_path)

    # 如果模型尚未加载，尝试按需加载（避免必须重启服务）
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                logger.info(f"Dynamically loaded system model {model_name} from {candidate_path}")
            except Exception as e:
                logger.error(f"Failed to dynamically load system model {model_name}: {e}")
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型（从数据库加载）
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    logger.info(f"Dynamically loaded custom model {model_name} from {custom_model.model_path}")
                except Exception as e:
                    logger.error(f"Failed to dynamically load custom model {model_name}: {e}")
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                logger.info(f"Requested model '{model_name}' not available. Available: {list(models.keys())}")
                return jsonify({"error": "模型不存在", "available_models": list(models.keys())}), 400
    model = models[model_name]
    logger.info(f"Using model: {model_name}")
    results = model(img_path)
    result = results[0]

    img = result.plot()
    result_path = os.path.join(RESULTS, filename)
    cv2.imwrite(result_path, img)

    # 提取检测信息
    detections = []
    if result.boxes:
        for box, cls, conf in zip(
            result.boxes.xyxy.cpu().numpy(),
            result.boxes.cls.cpu().numpy(),
            result.boxes.conf.cpu().numpy()
        ):
            detections.append({
                "class": result.names[int(cls)],
                "confidence": round(float(conf), 3),
                "bbox": [round(float(x), 1) for x in box]
            })

    avg_conf = sum(d['confidence'] for d in detections) / len(detections) if detections else 0

    # 保存到数据库历史记录
    history_item = DetectionHistory(
        username=username,
        filename=filename,
        model=model_name,
        result_image=f"http://127.0.0.1:5000/results/{filename}",
        original_image=f"http://127.0.0.1:5000/uploads/{filename}",
        detections=json.dumps(detections),
        count=len(detections),
        confidence=avg_conf
    )
    db.session.add(history_item)
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"执行骨折检测:{filename},检测到{len(detections)}个目标")

    return jsonify({
        "result_image": f"http://127.0.0.1:5000/results/{filename}",
        "detections": detections,
        "predictions": detections,
        "model_used": model_name,
        "history_id": history_item.id
    })

# ==================== 检测历史接口 ====================

@bp.route("/api/history", methods=["GET"])
@require_auth
def get_history():
    user = get_current_user()
    # 使用数据隔离过滤函数
    query = get_filtered_reports(user)
    
    # 检查是否只请求图片检测记录
    image_only = request.args.get('image_only', 'false').lower() == 'true'
    if image_only:
        # 只返回有原始图片路径的记录（图片检测）
        query = query.filter(DetectionHistory.original_image.isnot(None))
    
    history_list = query.order_by(DetectionHistory.timestamp.desc()).limit(50).all()
    data = [item.to_dict() for item in history_list]
    return jsonify({"data": data})

@bp.route("/api/history/<int:history_id>", methods=["DELETE"])
@require_auth
def delete_history(history_id):
    user = get_current_user()
    history = db.session.get(DetectionHistory, history_id)
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 权限检查:admin可以删除所有记录,doctor只能删除自己创建的记录,patient不能删除
    if user.role == 'admin':
        # admin可以删除任何记录
        pass
    elif user.role == 'doctor' and history.username == user.username:
        # doctor只能删除自己创建的记录
        pass
    else:
        # patient或其他角色不能删除,或doctor尝试删除其他医生的记录
        return jsonify({"error": "无权删除此记录"}), 403
    
    filename = history.filename
    db.session.delete(history)
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"删除检测记录:ID={history_id},文件={filename}")
    
    return jsonify({"success": True})

@bp.route("/api/history/clear/all", methods=["DELETE"])
@require_role('admin')
def clear_history():
    count = db.session.query(DetectionHistory).count()
    db.session.query(DetectionHistory).delete()
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"清空所有检测历史:共{count}条记录")
    
    return jsonify({"success": True})

@bp.route("/api/history/<int:history_id>/advice", methods=["POST"])
@require_auth
def save_medical_advice(history_id):
    """保存医疗建议到历史记录"""
    user = get_current_user()
    history = db.session.get(DetectionHistory, history_id)
    
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 权限检查:admin可以修改所有记录,doctor只能修改自己创建的记录,patient不能修改
    if user.role == 'admin':
        # admin可以修改任何记录
        pass
    elif user.role == 'doctor' and history.username == user.username:
        # doctor只能修改自己创建的记录
        pass
    else:
        # patient或其他角色不能修改,或doctor尝试修改其他医生的记录
        return jsonify({"error": "无权修改此记录"}), 403
    
    data = request.json
    
    # 保存医疗建议
    # 兼容两种格式：1. {medical_advice: {...}}  2. {interpretation: ..., patient_info: ...}
    medical_advice = data.get('medical_advice')
    
    # 如果没有medical_advice字段，但有interpretation字段（原系统格式）
    if medical_advice is None and data.get('interpretation') is not None:
        # 这里是**白名单**：不在这个字典里的字段会被静默丢弃。
        # references 必须列进来，否则 RAG 引用溯源在"保存解读结果"这一步
        # 就断了——正文留着 [1][2] 角标，却再也找不到对应来源。
        medical_advice = {
            'interpretation': data.get('interpretation'),
            'patient_info': data.get('patient_info', {}),
            'prompt': data.get('prompt', ''),
            'references': data.get('references', []),
            'updated_at': datetime.utcnow().isoformat()
        }
    
    if medical_advice is not None:
        if isinstance(medical_advice, dict):
            advice_data = {
                **medical_advice,
                'updated_at': datetime.utcnow().isoformat()
            }
            history.medical_advice = json.dumps(advice_data, ensure_ascii=False)
        else:
            history.medical_advice = str(medical_advice)
    
    # 保存诊断结论
    if 'diagnosis' in data:
        history.diagnosis = data.get('diagnosis', '')
    
    # 保存随访备注
    if 'follow_up_notes' in data:
        history.follow_up_notes = data.get('follow_up_notes', '')
    
    db.session.commit()
    
    log_operation(f"保存医疗建议:历史记录ID={history_id}")
    return jsonify({"success": True, "message": "医疗建议已保存"})

@bp.route("/api/history/<int:history_id>", methods=["GET"])
@require_auth
def get_history_detail(history_id):
    """获取单条历史记录详情"""
    user = get_current_user()
    history = db.session.get(DetectionHistory, history_id)
    
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 权限检查:admin可以查看所有记录,doctor只能查看自己创建的记录,patient只能查看关联到自己的记录
    if user.role == 'admin':
        # admin可以查看任何记录
        pass
    elif user.role == 'doctor' and history.username == user.username:
        # doctor只能查看自己创建的记录
        pass
    elif user.role == 'patient' and history.patient_id == user.id:
        # patient只能查看关联到自己的记录
        pass
    else:
        # 无权查看此记录
        return jsonify({"error": "无权查看此记录"}), 403
    
    return jsonify(history.to_dict())

@bp.route("/api/interpret", methods=["POST"])
@limit('ai_chat', key='user')   # AI 调用按用户限流：token 计费，成本归属需清晰
@require_role('admin', 'doctor')
def interpret_detection():
    """
    调用AI服务生成医疗建议
    支持本地部署和第三方API
    """
    data = request.json
    detections = data.get("detections", [])
    custom_prompt = data.get("prompt", "")
    image_base64 = data.get("image_base64", None)

    if not detections:
        return jsonify({"error": "没有检测结果可供解读"}), 400

    if not custom_prompt:
        detection_summary = []
        for i, det in enumerate(detections, 1):
            cls = det.get("class", "未知")
            conf = det.get("confidence", 0)
            bbox = det.get("bbox", [])
            detection_summary.append(f"检测{i}: 类别={cls}, 置信度={conf:.2f}, 位置={bbox}")

        detection_text = "\n".join(detection_summary)

        prompt = f"""你是一位专业的骨科医生助手。我将提供骨折检测的X光片图像和检测结果，请结合图像和检测信息进行专业分析。

检测结果：
{detection_text}

请结合X光片图像和检测结果，提供以下信息：
1. 图像分析：观察X光片中的骨折位置、类型和严重程度
2. 风险评估：根据检测到的骨折类型和图像表现，评估病情的严重程度
3. 进一步检查建议：建议进行哪些进一步检查（如CT、MRI等）
4. 处置建议：初步的处置建议（如固定、手术、转诊等）
5. 注意事项：患者应该注意的事项
6. 免责声明：提示此为AI辅助诊断，最终诊断需由专业医生确定

请用中文回复，结构化输出。"""
    else:
        prompt = custom_prompt

    # RAG：以检出的骨折类别为线索检索处置规范与分型标准，
    # 让解读有据可依，而不是全凭模型自由发挥。
    # 检索失败返回 ('', [])，解读照常进行。
    user = get_current_user()
    classes = [str(d.get('class', '')).strip() for d in detections if d.get('class')]
    requested_patient = data.get('patient_id')
    include_personal = bool(requested_patient) and can_access_patient(user, requested_patient)
    if requested_patient and not include_personal:
        return jsonify({"error": "无权访问该患者的病历"}), 403

    rag_query = (f"{'、'.join(classes)} 骨折 处置 建议 分型" if classes
                 else '骨折 处置 建议')
    rag_context, references = build_rag_context(
        rag_query,
        patient_id=int(requested_patient) if include_personal else None,
        include_personal=include_personal,
    )
    if rag_context:
        from services.rag.prompts import RAG_PROMPT
        prompt = f'{prompt}\n\n{RAG_PROMPT.format(context=rag_context, question=rag_query)}'

    try:
        # 获取AI配置并构造统一客户端
        ai_config = get_ai_settings()
        provider = ai_config['provider']

        # 原实现仅 local 与 modelscope 会携带图片，其余 provider 忽略该参数，
        # 此处保持原行为以免多模态模型不支持时调用失败
        image = image_base64 if provider in ('local', 'modelscope') else None

        client = get_llm_client()
        reply = client.chat_text(prompt, image_base64=image)

        # 记录操作日志
        log_operation(f"AI解读检测结果:检测数={len(detections)},提供商={provider},引用={len(references)}")

        return jsonify({
            "success": True,
            "interpretation": reply,
            "references": references,
            "detections_count": len(detections),
            "ai_provider": provider
        })

    # 同时捕获新客户端的 LLMConnectionError 与底层 requests 异常：
    # 统一客户端已重试 MAX_RETRIES 次仍失败才会抛到此处
    except (LLMConnectionError, requests.exceptions.ConnectionError):
        ai_config = get_ai_settings()
        provider = ai_config.get('provider', 'local')
        if provider == 'local':
            return jsonify({
                "error": "无法连接到本地AI服务",
                "hint": "请确保本地AI服务已启动 (http://127.0.0.1:8000)，或切换到其他AI提供商 (OpenAI/ModelScope等)"
            }), 503
        else:
            return jsonify({
                "error": "无法连接到 AI 服务",
                "hint": "请检查AI服务配置和网络连接"
            }), 503
    except (LLMTimeoutError, requests.exceptions.Timeout):
        return jsonify({"error": "AI 服务响应超时"}), 504
    except LLMConfigError as e:
        return jsonify({"error": f"AI 服务配置有误: {e}"}), 400
    except Exception as e:
        logger.error(f"AI解读接口错误: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# video_tasks 已抽至 core.state

@bp.route("/api/video/detect", methods=["POST"])
@require_role('admin', 'doctor')
def video_detect():
    """视频流检测 - 开始任务"""
    if 'video' not in request.files:
        return jsonify({"error": "没有上传视频文件"}), 400
    
    file = request.files['video']
    model_name = request.form.get('model', 'yolov8s')
    username = get_current_user().username   # 检测记录归属：不能由请求头自称
    
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    
    # 检查并加载模型
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                logger.info(f"Video detect: Dynamically loaded system model {model_name}")
            except Exception as e:
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    logger.info(f"Video detect: Dynamically loaded custom model {model_name}")
                except Exception as e:
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                return jsonify({"error": f"模型 {model_name} 未加载或不存在"}), 400
    
    # 保存视频文件
    timestamp = int(time.time())
    filename = f"{timestamp}_{file.filename}"
    video_path = os.path.join(UPLOADS, filename)
    file.save(video_path)
    
    # 创建任务ID
    task_id = f"video_{timestamp}"
    
    # 初始化任务状态
    video_tasks[task_id] = {
        'status': 'processing',
        'progress': 0,
        'current_frame': 0,
        'total_frames': 0,
        'detections': [],
        'clients': set()
    }
    
    # 启动异步处理线程
    thread = threading.Thread(
        target=process_video_stream,
        args=(task_id, video_path, model_name, username)
    )
    thread.daemon = True
    thread.start()
    
    log_operation(f"开始视频流检测:{filename},模型:{model_name}")
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "视频检测任务已启动"
    })

# ==================== 摄像头实时检测接口 ====================

@bp.route("/api/camera/detect", methods=["POST"])
@require_role('admin', 'doctor')
def camera_detect():
    """摄像头实时检测单帧"""
    data = request.json
    image_data = data.get('image', '')
    model_name = data.get('model', 'yolov8s')
    
    if not image_data:
        return jsonify({"error": "没有图像数据"}), 400
    
    # 检查并加载模型
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                logger.info(f"Camera detect: Dynamically loaded system model {model_name}")
            except Exception as e:
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    logger.info(f"Camera detect: Dynamically loaded custom model {model_name}")
                except Exception as e:
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                return jsonify({"error": f"模型 {model_name} 未加载或不存在"}), 400
    
    try:
        # 解码 base64 图像
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "无法解码图像"}), 400
        
        # 进行检测
        model = models[model_name]
        results = model(frame)
        
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])
                
                detections.append({
                    'class': cls_name,
                    'confidence': conf,
                    'bbox': box.xyxy[0].tolist()
                })
                
                # 绘制检测框
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{cls_name} {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 编码结果图像
        _, buffer = cv2.imencode('.jpg', frame)
        result_image = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            "success": True,
            "detections": detections,
            "result_image": result_image,
            "count": len(detections)
        })
        
    except Exception as e:
        logger.error(f"摄像头检测错误: {e}")
        return jsonify({"error": str(e)}), 500

def process_video_stream(task_id, video_path, model_name, username):
    """处理视频流检测"""
    try:
        model = models[model_name]
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            video_tasks[task_id]['status'] = 'error'
            video_tasks[task_id]['message'] = '无法打开视频文件'
            return
        
        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_tasks[task_id]['total_frames'] = total_frames
        
        frame_count = 0
        detected_frames = 0
        total_detections = 0
        all_confidences = []
        
        # 处理间隔（每5帧处理一帧）
        process_interval = 5
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 只处理指定间隔的帧
            if frame_count % process_interval != 0:
                continue
            
            # 进行检测
            results = model(frame)
            detections = []
            
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    conf = float(box.conf[0])
                    
                    detections.append({
                        'class': cls_name,
                        'confidence': conf,
                        'bbox': box.xyxy[0].tolist()
                    })
                    
                    # 绘制检测框
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"{cls_name} {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # 计算统计
            if detections:
                detected_frames += 1
                total_detections += len(detections)
                avg_conf = sum(d['confidence'] for d in detections) / len(detections)
                all_confidences.append(avg_conf)
            
            # 编码图像为 base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 更新任务状态
            video_tasks[task_id]['current_frame'] = frame_count
            video_tasks[task_id]['progress'] = (frame_count / total_frames) * 100 if total_frames > 0 else 0
            
            # 广播给所有连接的客户端
            message = {
                'type': 'frame',
                'frame': frame_count,
                'timestamp': frame_count / fps if fps > 0 else 0,
                'image': img_base64,
                'detections': detections,
                'avg_confidence': sum(d['confidence'] for d in detections) / len(detections) if detections else 0
            }
            
            # 发送到所有 WebSocket 客户端
            for client in list(video_tasks[task_id].get('clients', [])):
                try:
                    client.send(json.dumps(message))
                except:
                    pass
            
            # 发送统计信息（每30帧）
            if frame_count % (process_interval * 6) == 0:
                stats_message = {
                    'type': 'stats',
                    'stats': {
                        'total_frames': frame_count,
                        'detected_frames': detected_frames,
                        'total_detections': total_detections,
                        'avg_confidence': round(sum(all_confidences) / len(all_confidences) * 100, 1) if all_confidences else 0
                    }
                }
                for client in list(video_tasks[task_id].get('clients', [])):
                    try:
                        client.send(json.dumps(stats_message))
                    except:
                        pass
        
        cap.release()
        
        # 发送完成消息
        video_tasks[task_id]['status'] = 'completed'
        complete_message = {
            'type': 'complete',
            'stats': {
                'total_frames': frame_count,
                'detected_frames': detected_frames,
                'total_detections': total_detections,
                'avg_confidence': round(sum(all_confidences) / len(all_confidences) * 100, 1) if all_confidences else 0
            }
        }
        for client in list(video_tasks[task_id].get('clients', [])):
            try:
                client.send(json.dumps(complete_message))
            except:
                pass
        
        log_operation(f"视频流检测完成:{task_id},共{frame_count}帧")
        
    except Exception as e:
        logger.error(f"视频处理错误: {e}")
        video_tasks[task_id]['status'] = 'error'
        error_message = {'type': 'error', 'message': str(e)}
        for client in list(video_tasks[task_id].get('clients', [])):
            try:
                client.send(json.dumps(error_message))
            except:
                pass
