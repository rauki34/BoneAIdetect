"""统计分析接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, require_admin, require_auth, require_role
from database import db, DetectionHistory, Examination, User

bp = Blueprint('analysis', __name__)

# ==================== 统计分析接口 ====================

@bp.route("/api/analysis", methods=["GET"])
@require_role('admin')
def get_analysis():
    history_list = DetectionHistory.query.all()
    total_images = len(history_list)
    models_used = {}
    classes_detected = {}

    total_boxes = 0
    total_confidence = 0.0

    for item in history_list:
        model = item.model or "unknown"
        models_used[model] = models_used.get(model, 0) + 1

        try:
            detections = json.loads(item.detections) if item.detections else []
        except:
            detections = []

        for detection in detections:
            cls = detection.get("class", "unknown")
            classes_detected[cls] = classes_detected.get(cls, 0) + 1
            conf = float(detection.get("confidence", 0))
            total_confidence += conf
            total_boxes += 1

    avg_confidence = (total_confidence / total_boxes) if total_boxes > 0 else 0

    return jsonify({
        "total_detections": total_images,
        "models_used": models_used,
        "classes_detected": classes_detected,
        "avg_confidence": avg_confidence
    })

# ==================== 置信度趋势折线接口 ====================

@bp.route("/api/analysis/confidence_series", methods=["GET"])
@require_role('admin')          # 只有管理员可看趋势
def confidence_series():
    """
    返回最近 200 条检测的置信度序列，按时间升序
    """
    from datetime import timedelta
    
    rows = (DetectionHistory.query
            .order_by(DetectionHistory.timestamp.desc())
            .limit(200)
            .all())[::-1]          # 升序，图表从左到右

    data = [
        {
            # 将UTC时间转换为本地时间（中国时区 UTC+8）
            "timestamp": (r.timestamp + timedelta(hours=8)).strftime("%m-%d %H:%M:%S"),
            "confidence": round(float(r.confidence or 0), 3)
        }
        for r in rows
    ]
    return jsonify(data)

@bp.route("/api/analysis/user_confidence_series", methods=["GET"])
@require_auth
def user_confidence_series():
    """
    返回当前用户最近 100 条检测的置信度序列，按时间升序
    """
    from datetime import timedelta
    user = get_current_user()
    
    rows = (DetectionHistory.query
            .filter_by(username=user.username)
            .order_by(DetectionHistory.timestamp.desc())
            .limit(100)
            .all())[::-1]          # 升序，图表从左到右

    data = [
        {
            # 将UTC时间转换为本地时间（中国时区 UTC+8）
            "timestamp": (r.timestamp + timedelta(hours=8)).strftime("%m-%d %H:%M:%S"),
            "confidence": round(float(r.confidence or 0), 3)
        }
        for r in rows
    ]
    return jsonify(data)

@bp.route("/api/analysis/user_stats", methods=["GET"])
@require_auth
def user_stats():
    """
    返回当前用户的检测统计数据
    """
    user = get_current_user()
    
    # 总检测次数
    total_detections = DetectionHistory.query.filter_by(username=user.username).count()
    
    # 模型使用统计
    models_used = {}
    histories = DetectionHistory.query.filter_by(username=user.username).all()
    for history in histories:
        model = history.model
        models_used[model] = models_used.get(model, 0) + 1
    
    # 检测类别统计
    # 修复: fracture_types 不是 DetectionHistory 的列，而是 to_dict() 中
    # 从 detections(JSON) 解析出的派生字段。原实现直接访问
    # history.fracture_types 会抛 AttributeError，导致本接口恒返回 500。
    classes_detected = {}
    for history in histories:
        for fracture_type in history.to_dict()['fracture_types']:
            classes_detected[fracture_type] = classes_detected.get(fracture_type, 0) + 1
    
    # 平均置信度
    total_confidence = 0
    confidence_count = 0
    for history in histories:
        if history.confidence:
            total_confidence += float(history.confidence)
            confidence_count += 1
    avg_confidence = total_confidence / confidence_count if confidence_count > 0 else 0
    
    # 最近检测
    recent_detections = []
    recent_histories = DetectionHistory.query.filter_by(username=user.username).order_by(DetectionHistory.timestamp.desc()).limit(5).all()
    for history in recent_histories:
        item = history.to_dict()
        recent_detections.append({
            "id": item["id"],
            "timestamp": item["timestamp"],
            "model": item["model"],
            "count": item["count"],
            "confidence": item["confidence"],
            "fracture_types": item["fracture_types"],
        })
    
    return jsonify({
        "total_detections": total_detections,
        "models_used": models_used,
        "classes_detected": classes_detected,
        "avg_confidence": avg_confidence,
        "recent_detections": recent_detections
    })
