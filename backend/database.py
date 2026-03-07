"""
SQLite 数据库配置和模型定义
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

# 时区偏移（中国时区 UTC+8）
TIMEZONE_OFFSET = 8 * 60 * 60  # 8小时转秒

# ==================== 数据模型 ====================

class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        # 将UTC时间转换为本地时间（中国时区 UTC+8）
        local_created_at = None
        if self.created_at:
            from datetime import timedelta
            local_time = self.created_at + timedelta(hours=8)
            local_created_at = local_time.isoformat()
        
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': local_created_at
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class DetectionHistory(db.Model):
    """检测历史模型"""
    __tablename__ = 'detection_history'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), db.ForeignKey('users.username'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    filename = db.Column(db.String(255), nullable=False)
    model = db.Column(db.String(50), default='yolov8')
    result_image = db.Column(db.String(500))
    detections = db.Column(db.Text)  # JSON 格式存储
    count = db.Column(db.Integer, default=0)
    confidence = db.Column(db.Float, default=0.0)   # 单张图平均置信度
    medical_advice = db.Column(db.Text)  # 医疗建议（JSON格式存储）
    original_image = db.Column(db.String(500))  # 原始图片路径
    
    def to_dict(self):
        try:
            detections = json.loads(self.detections) if self.detections else []
        except:
            detections = []
        
        try:
            medical_advice = json.loads(self.medical_advice) if self.medical_advice else None
        except:
            medical_advice = self.medical_advice
        
        # 将UTC时间转换为本地时间（中国时区 UTC+8）
        local_timestamp = None
        if self.timestamp:
            from datetime import timedelta
            local_time = self.timestamp + timedelta(hours=8)
            local_timestamp = local_time.isoformat()
        
        # 提取骨折类型信息
        fracture_types = []
        for det in detections:
            if det.get('class') and det['class'] not in fracture_types:
                fracture_types.append(det['class'])
        
        return {
            'id': self.id,
            'username': self.username,
            'timestamp': local_timestamp,
            'filename': self.filename,
            'model': self.model,
            'result_image': self.result_image,
            'original_image': self.original_image,
            'detections': detections,
            'count': self.count,
            'confidence': self.confidence,
            'fracture_types': fracture_types,
            'has_medical_advice': medical_advice is not None,
            'medical_advice': medical_advice
        }
    
    def __repr__(self):
        return f'<DetectionHistory {self.id}>'


class SystemSettings(db.Model):
    """系统设置模型"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'description': self.description
        }
    
    def __repr__(self):
        return f'<SystemSettings {self.key}>'


class OperationLog(db.Model):
    """操作日志模型 - 借鉴pear-admin-flask"""
    __tablename__ = 'operation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    method = db.Column(db.String(10))  # GET/POST/PUT/DELETE
    url = db.Column(db.String(255))
    ip = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    description = db.Column(db.String(255))  # 操作描述
    success = db.Column(db.Boolean, default=True)  # 是否成功
    error_msg = db.Column(db.Text)  # 错误信息
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        # 将UTC时间转换为本地时间（中国时区 UTC+8）
        local_timestamp = None
        if self.timestamp:
            from datetime import timedelta
            local_time = self.timestamp + timedelta(hours=8)
            local_timestamp = local_time.isoformat()
        
        return {
            'id': self.id,
            'username': self.username,
            'method': self.method,
            'url': self.url,
            'ip': self.ip,
            'user_agent': self.user_agent,
            'description': self.description,
            'success': self.success,
            'error_msg': self.error_msg,
            'timestamp': local_timestamp
        }
    
    def __repr__(self):
        return f'<OperationLog {self.id}>'


class FileRecord(db.Model):
    """文件记录模型 - 借鉴pear-admin-flask"""
    __tablename__ = 'file_records'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))  # 原始文件名
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)  # 文件大小（字节）
    mime_type = db.Column(db.String(100))  # MIME类型
    extension = db.Column(db.String(20))  # 文件扩展名
    uploader = db.Column(db.String(80))  # 上传者
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        # 将UTC时间转换为本地时间（中国时区 UTC+8）
        local_created_at = None
        if self.created_at:
            from datetime import timedelta
            local_time = self.created_at + timedelta(hours=8)
            local_created_at = local_time.isoformat()
        
        # 格式化文件大小
        size_str = self.format_file_size(self.file_size) if self.file_size else '-'
        
        return {
            'id': self.id,
            'filename': self.filename,
            'original_name': self.original_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'size_str': size_str,
            'mime_type': self.mime_type,
            'extension': self.extension,
            'uploader': self.uploader,
            'description': self.description,
            'created_at': local_created_at
        }
    
    @staticmethod
    def format_file_size(size):
        """格式化文件大小"""
        if size is None:
            return '-'
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"
    
    def __repr__(self):
        return f'<FileRecord {self.filename}>'


class CustomModel(db.Model):
    """自定义训练模型"""
    __tablename__ = 'custom_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 模型名称
    model_key = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 模型标识
    description = db.Column(db.String(255))  # 模型描述
    base_model = db.Column(db.String(50), nullable=False)  # 基础模型 (yolov8/yolo11/yolo12)
    model_path = db.Column(db.String(500), nullable=False)  # 模型文件路径
    dataset_path = db.Column(db.String(500))  # 训练数据集路径
    status = db.Column(db.String(20), default='training')  # training/trained/published/disabled
    accuracy = db.Column(db.Float)  # 准确率
    map50 = db.Column(db.Float)  # mAP@0.5
    map50_95 = db.Column(db.Float)  # mAP@0.5:0.95
    epochs = db.Column(db.Integer, default=100)  # 训练轮数
    batch_size = db.Column(db.Integer, default=16)  # 批次大小
    img_size = db.Column(db.Integer, default=640)  # 图像尺寸
    created_by = db.Column(db.String(80))  # 创建者
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)  # 发布时间
    
    def to_dict(self):
        from datetime import timedelta
        
        local_created_at = None
        if self.created_at:
            local_time = self.created_at + timedelta(hours=8)
            local_created_at = local_time.isoformat()
        
        local_updated_at = None
        if self.updated_at:
            local_time = self.updated_at + timedelta(hours=8)
            local_updated_at = local_time.isoformat()
        
        local_published_at = None
        if self.published_at:
            local_time = self.published_at + timedelta(hours=8)
            local_published_at = local_time.isoformat()
        
        return {
            'id': self.id,
            'name': self.name,
            'model_key': self.model_key,
            'description': self.description,
            'base_model': self.base_model,
            'model_path': self.model_path,
            'dataset_path': self.dataset_path,
            'status': self.status,
            'accuracy': self.accuracy,
            'map50': self.map50,
            'map50_95': self.map50_95,
            'epochs': self.epochs,
            'batch_size': self.batch_size,
            'img_size': self.img_size,
            'created_by': self.created_by,
            'created_at': local_created_at,
            'updated_at': local_updated_at,
            'published_at': local_published_at
        }
    
    def __repr__(self):
        return f'<CustomModel {self.model_key}>'


class TrainingTask(db.Model):
    """模型训练任务"""
    __tablename__ = 'training_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    model_id = db.Column(db.Integer, db.ForeignKey('custom_models.id'))
    status = db.Column(db.String(20), default='pending')  # pending/running/completed/failed
    progress = db.Column(db.Float, default=0.0)  # 训练进度 0-100
    current_epoch = db.Column(db.Integer, default=0)
    total_epochs = db.Column(db.Integer, default=100)
    loss = db.Column(db.Float)  # 当前损失
    val_loss = db.Column(db.Float)  # 验证损失
    log_file = db.Column(db.String(500))  # 训练日志路径
    error_message = db.Column(db.Text)  # 错误信息
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联模型
    model = db.relationship('CustomModel', backref='training_tasks')
    
    def to_dict(self):
        from datetime import timedelta
        
        local_created_at = None
        if self.created_at:
            local_time = self.created_at + timedelta(hours=8)
            local_created_at = local_time.isoformat()
        
        local_started_at = None
        if self.started_at:
            local_time = self.started_at + timedelta(hours=8)
            local_started_at = local_time.isoformat()
        
        local_completed_at = None
        if self.completed_at:
            local_time = self.completed_at + timedelta(hours=8)
            local_completed_at = local_time.isoformat()
        
        return {
            'id': self.id,
            'task_name': self.task_name,
            'model_id': self.model_id,
            'model_name': self.model.name if self.model else None,
            'status': self.status,
            'progress': self.progress,
            'current_epoch': self.current_epoch,
            'total_epochs': self.total_epochs,
            'loss': self.loss,
            'val_loss': self.val_loss,
            'log_file': self.log_file,
            'error_message': self.error_message,
            'started_at': local_started_at,
            'completed_at': local_completed_at,
            'created_by': self.created_by,
            'created_at': local_created_at
        }
    
    def __repr__(self):
        return f'<TrainingTask {self.id}>'


# ==================== 数据库初始化函数 ====================

def init_db(app):
    """初始化数据库"""
    from werkzeug.security import generate_password_hash
    
    db.init_app(app)
    
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✅ 数据库表已创建")
        
        # 初始化默认admin用户（如果不存在）
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                password=generate_password_hash('123456'),
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ 默认admin用户已创建（用户名: admin, 密码: 123456）")
        else:
            # 如果admin用户存在但密码未加密，更新密码
            if not (admin_user.password.startswith('$2b$') or 
                    admin_user.password.startswith('$2a$') or 
                    admin_user.password.startswith('pbkdf2:') or
                    admin_user.password.startswith('scrypt:') or
                    admin_user.password.startswith('argon2:')):
                print("⚠️  检测到admin用户密码未加密，正在更新...")
                admin_user.password = generate_password_hash('123456')
                db.session.commit()
                print("✅ admin用户密码已更新（密码: 123456）")
        
        # 初始化默认系统设置
        if not SystemSettings.query.filter_by(key='default_model').first():
            default_settings = [
                SystemSettings(key='default_model', value='yolov8', description='默认模型'),
                SystemSettings(key='confidence_threshold', value='0.25', description='置信度阈值'),
            ]
            for setting in default_settings:
                db.session.add(setting)
            db.session.commit()
            print("✅ 系统设置已初始化")


def migrate_from_json(app):
    """
    从 JSON 文件迁移数据到数据库（仅第一次初始化时执行）
    """
    import os
    from werkzeug.security import generate_password_hash
    
    with app.app_context():
        # 迁移用户数据
        users_json = 'users.json'
        if os.path.exists(users_json) and User.query.count() == 0:
            try:
                with open(users_json, 'r', encoding='utf-8') as f:
                    users_data = json.load(f)
                    for user_data in users_data:
                        # 如果密码未加密，进行加密
                        password = user_data['password']
                        if not (password.startswith('$2b$') or 
                                password.startswith('$2a$') or 
                                password.startswith('pbkdf2:') or
                                password.startswith('scrypt:') or
                                password.startswith('argon2:')):
                            password = generate_password_hash(password)
                        
                        user = User(
                            username=user_data['username'],
                            password=password,
                            role=user_data.get('role', 'user')
                        )
                        db.session.add(user)
                db.session.commit()
                print(f"✅ 已迁移 {len(users_data)} 个用户到数据库")
            except Exception as e:
                print(f"❌ 迁移用户数据失败: {e}")
                db.session.rollback()
        
        # 确保admin用户存在（在迁移后再次检查）
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                password=generate_password_hash('123456'),
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ 默认admin用户已创建（用户名: admin, 密码: 123456）")
        
        # 迁移检测历史
        history_json = 'detection_history.json'
        if os.path.exists(history_json) and DetectionHistory.query.count() == 0:
            try:
                with open(history_json, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    for item in history_data:
                        history = DetectionHistory(
                            username=item.get('username', 'admin'),  # 使用 admin 作为默认值
                            timestamp=datetime.fromisoformat(item['timestamp']),
                            filename=item['filename'],
                            model=item.get('model', 'yolov8'),
                            result_image=item.get('result_image', ''),
                            detections=json.dumps(item.get('detections', [])),
                            count=item.get('count', 0)
                        )
                        db.session.add(history)
                db.session.commit()
                print(f"✅ 已迁移 {len(history_data)} 条检测历史到数据库")
            except Exception as e:
                print(f"❌ 迁移历史记录失败: {e}")
                db.session.rollback()
