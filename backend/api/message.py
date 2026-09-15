"""医患消息与系统公告接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from core.auth import get_current_user, require_auth, require_role
from core.helpers import log_operation
from database import (
    Announcement, AnnouncementRead, DoctorPatientRelation,
    DoctorProfile, Message, PatientProfile, User, db,
)
from utils.logger import logger

bp = Blueprint('message', __name__)

# -------------------- 消息系统 API --------------------

@bp.route("/api/messages/send", methods=["POST"])
@require_auth
def send_message():
    """发送消息（患者和医生都可以使用）"""
    user = get_current_user()
    data = request.json
    
    receiver_id = data.get('receiver_id')
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    
    if not receiver_id:
        return jsonify({"error": "请选择接收人"}), 400
    if not content:
        return jsonify({"error": "消息内容不能为空"}), 400
    
    # 验证接收人是否存在
    receiver = db.session.get(User, receiver_id)
    if not receiver:
        return jsonify({"error": "接收人不存在"}), 404
    
    # 验证医患关系（必须是主治医生和患者关系）
    if user.role == 'patient':
        # 患者只能给主治医生发消息
        relation = DoctorPatientRelation.query.filter_by(
            patient_id=user.id,
            doctor_id=receiver_id,
            status='active'
        ).first()
        if not relation:
            return jsonify({"error": "只能给主治医生发送消息"}), 403
    elif user.role == 'doctor':
        # 医生只能给自己的患者发消息
        relation = DoctorPatientRelation.query.filter_by(
            doctor_id=user.id,
            patient_id=receiver_id,
            status='active'
        ).first()
        if not relation:
            return jsonify({"error": "只能给自己的患者发送消息"}), 403
    
    try:
        message = Message(
            sender_id=user.id,
            receiver_id=receiver_id,
            title=title or f"来自{user.full_name or user.username}的消息",
            content=content,
            message_type='chat',
            is_read=False
        )
        db.session.add(message)
        db.session.commit()
        
        log_operation(f"发送消息: {user.username} -> {receiver.username}")
        
        return jsonify({
            "success": True,
            "message": "发送成功",
            "data": message.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"发送消息失败: {e}")
        return jsonify({"error": "发送失败"}), 500

@bp.route("/api/messages/conversation/<int:other_user_id>", methods=["GET"])
@require_auth
def get_conversation(other_user_id):
    """获取与特定用户的聊天记录"""
    user = get_current_user()
    
    # 验证对方用户是否存在
    other_user = db.session.get(User, other_user_id)
    if not other_user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 获取双向消息
    messages = Message.query.filter(
        ((Message.sender_id == user.id) & (Message.receiver_id == other_user_id)) |
        ((Message.sender_id == other_user_id) & (Message.receiver_id == user.id))
    ).order_by(Message.created_at.asc()).all()
    
    messages_data = []
    for msg in messages:
        sender = db.session.get(User, msg.sender_id) if msg.sender_id else None
        messages_data.append({
            "id": msg.id,
            "content": msg.content,
            "sender_id": msg.sender_id,
            "sender_name": sender.full_name if sender else "系统",
            "sender_role": sender.role if sender else "system",
            "receiver_id": msg.receiver_id,
            "is_read": msg.is_read,
            "created_at": msg.created_at.isoformat() if msg.created_at else None
        })
    
    return jsonify({
        "success": True,
        "messages": messages_data,
        "other_user": {
            "id": other_user.id,
            "full_name": other_user.full_name,
            "role": other_user.role
        }
    })

@bp.route("/api/messages/contacts", methods=["GET"])
@require_auth
def get_message_contacts():
    """获取可发送消息的联系人和最近聊天列表"""
    user = get_current_user()
    
    contacts = []
    
    if user.role == 'patient':
        # 患者获取主治医生列表
        relations = DoctorPatientRelation.query.filter_by(
            patient_id=user.id,
            status='active'
        ).all()
        
        for relation in relations:
            doctor = db.session.get(User, relation.doctor_id)
            if doctor:
                profile = DoctorProfile.query.filter_by(user_id=doctor.id).first()
                # 获取未读消息数
                unread_count = Message.query.filter_by(
                    sender_id=doctor.id,
                    receiver_id=user.id,
                    is_read=False
                ).count()
                
                # 获取最后一条消息
                last_message = Message.query.filter(
                    ((Message.sender_id == user.id) & (Message.receiver_id == doctor.id)) |
                    ((Message.sender_id == doctor.id) & (Message.receiver_id == user.id))
                ).order_by(Message.created_at.desc()).first()
                
                contacts.append({
                    "id": doctor.id,
                    "full_name": doctor.full_name,
                    "role": doctor.role,
                    "department": profile.department if profile else '',
                    "title": profile.title if profile else '',
                    "is_primary": relation.is_primary,
                    "unread_count": unread_count,
                    "last_message": last_message.content if last_message else None,
                    "last_message_time": last_message.created_at.isoformat() if last_message else None
                })
    
    elif user.role == 'doctor':
        # 医生获取患者列表
        relations = DoctorPatientRelation.query.filter_by(
            doctor_id=user.id,
            status='active'
        ).all()
        
        for relation in relations:
            patient = db.session.get(User, relation.patient_id)
            if patient:
                profile = PatientProfile.query.filter_by(user_id=patient.id).first()
                # 获取未读消息数
                unread_count = Message.query.filter_by(
                    sender_id=patient.id,
                    receiver_id=user.id,
                    is_read=False
                ).count()
                
                # 获取最后一条消息
                last_message = Message.query.filter(
                    ((Message.sender_id == user.id) & (Message.receiver_id == patient.id)) |
                    ((Message.sender_id == patient.id) & (Message.receiver_id == user.id))
                ).order_by(Message.created_at.desc()).first()
                
                contacts.append({
                    "id": patient.id,
                    "full_name": patient.full_name,
                    "role": patient.role,
                    "patient_number": profile.patient_number if profile else '',
                    "gender": profile.gender if profile else '',
                    "is_primary": relation.is_primary,
                    "unread_count": unread_count,
                    "last_message": last_message.content if last_message else None,
                    "last_message_time": last_message.created_at.isoformat() if last_message else None
                })
    
    return jsonify({
        "success": True,
        "contacts": contacts
    })

@bp.route("/api/messages/mark-read", methods=["POST"])
@require_auth
def mark_messages_read():
    """批量标记消息为已读"""
    user = get_current_user()
    data = request.json
    sender_id = data.get('sender_id')

    if not sender_id:
        return jsonify({"error": "请指定发送人"}), 400

    try:
        # 标记该发送人发送给当前用户的所有未读消息为已读
        Message.query.filter_by(
            sender_id=sender_id,
            receiver_id=user.id,
            is_read=False
        ).update({"is_read": True})

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "已标记为已读"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"标记已读失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@bp.route("/api/announcements", methods=["GET"])
@require_auth
def get_announcements():
    """获取当前用户的公告列表"""
    user = get_current_user()

    try:
        # 根据用户角色筛选公告
        query = Announcement.query.filter_by(is_active=True)

        if user.role == 'patient':
            query = query.filter(Announcement.target_role.in_(['all', 'patient']))
        elif user.role == 'doctor':
            query = query.filter(Announcement.target_role.in_(['all', 'doctor']))

        announcements = query.order_by(Announcement.created_at.desc()).all()

        # 获取用户已读记录
        read_ids = set(
            r.announcement_id for r in
            AnnouncementRead.query.filter_by(user_id=user.id).all()
        )

        result = []
        for a in announcements:
            item = a.to_dict()
            item['is_read'] = a.id in read_ids
            result.append(item)

        return jsonify({
            "success": True,
            "announcements": result
        })
    except Exception as e:
        logger.error(f"获取公告失败: {e}")
        return jsonify({"error": "获取失败"}), 500

@bp.route("/api/announcements/<int:announcement_id>/read", methods=["POST"])
@require_auth
def mark_announcement_read(announcement_id):
    """标记公告为已读"""
    user = get_current_user()

    try:
        # 检查是否已存在记录
        existing = AnnouncementRead.query.filter_by(
            announcement_id=announcement_id,
            user_id=user.id
        ).first()

        if not existing:
            read_record = AnnouncementRead(
                announcement_id=announcement_id,
                user_id=user.id
            )
            db.session.add(read_record)
            db.session.commit()

        return jsonify({
            "success": True,
            "message": "已标记为已读"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"标记已读失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@bp.route("/api/announcements/unread-count", methods=["GET"])
@require_auth
def get_unread_announcement_count():
    """获取未读公告数量"""
    user = get_current_user()

    try:
        # 根据用户角色筛选公告
        query = Announcement.query.filter_by(is_active=True)

        if user.role == 'patient':
            query = query.filter(Announcement.target_role.in_(['all', 'patient']))
        elif user.role == 'doctor':
            query = query.filter(Announcement.target_role.in_(['all', 'doctor']))

        all_announcements = query.all()

        # 获取用户已读记录
        read_ids = set(
            r.announcement_id for r in
            AnnouncementRead.query.filter_by(user_id=user.id).all()
        )

        unread_count = sum(1 for a in all_announcements if a.id not in read_ids)

        return jsonify({
            "success": True,
            "unread_count": unread_count
        })
    except Exception as e:
        logger.error(f"获取未读公告数失败: {e}")
        return jsonify({"error": "获取失败"}), 500
