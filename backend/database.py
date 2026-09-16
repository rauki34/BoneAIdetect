"""
SQLite 数据库配置和模型定义
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json

from utils.logger import logger
db = SQLAlchemy()

# 时区偏移（中国时区 UTC+8）
TIMEZONE_OFFSET = 8 * 60 * 60  # 8小时转秒


def to_local_time(dt):
    """将UTC时间转换为本地时间（中国时区 UTC+8）
    
    Args:
        dt: datetime对象或None
        
    Returns:
        ISO格式的时间字符串或None
    """
    if not dt:
        return None
    local_time = dt + timedelta(hours=8)
    return local_time.isoformat()


def safe_json_loads(value, default=None):
    """安全解析JSON字符串
    
    Args:
        value: 要解析的JSON字符串
        default: 解析失败时的默认值
        
    Returns:
        解析后的Python对象或默认值
    """
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


# ==================== pgvector 向量列 ====================

# 向量维度：BAAI/bge-m3 = 1024。
# 这是**数据库 schema 的一部分**（决定 DDL 里的 vector(1024)），
# 因此不做成可配置项——配置改了而列宽没改只会更难排查。
# 换模型时由 services/rag/embedder.py 里的维度断言负责报错。
EMBEDDING_DIM = 1024

try:
    from pgvector.sqlalchemy import Vector as _PGVector
except ImportError:      # 未安装 pgvector：非 PG 环境仍可启动，向量能力关闭
    _PGVector = None


class VectorType(db.TypeDecorator):
    """pgvector 向量列

    仅在 PostgreSQL 方言下渲染为 vector(1024)；其他方言退化为 TEXT 并以
    JSON 存储。原因：config.py 在未设置 DATABASE_URL 时默认回退 SQLite，
    装了向量列不能连累那条降级启动路径。
    """
    impl = db.Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and _PGVector is not None:
            return dialect.type_descriptor(_PGVector(EMBEDDING_DIM))
        return dialect.type_descriptor(db.Text())

    @property
    def comparator_factory(self):
        """把 pgvector 的 `<=>` 比较器暴露到表达式层

        只重写 load_dialect_impl 是不够的：那只影响**建表时的 DDL**，
        ORM 表达式走的是 TypeDecorator 自己的 comparator（默认取自 impl，
        也就是 TEXT）。不接上这一层，`KnowledgeChunk.embedding.cosine_distance(...)`
        会直接 AttributeError。
        """
        if _PGVector is None:
            return super().comparator_factory
        return _PGVector.Comparator

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql' and _PGVector is not None:
            return value                      # pgvector 自行序列化 list[float]
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql' and _PGVector is not None:
            return value
        return safe_json_loads(value, [])


def get_display_name(user, fallback_attr='username'):
    """获取用户显示名称

    Args:
        user: 用户对象
        fallback_attr: 备用属性名
        
    Returns:
        用户全名或用户名，如果用户不存在则返回None
    """
    if not user:
        return None
    # 优先使用 full_name，如果不存在则使用 fallback_attr
    full_name = getattr(user, 'full_name', None)
    if full_name:
        return full_name
    return getattr(user, fallback_attr, None)


def format_file_size(size):
    """格式化文件大小
    
    Args:
        size: 文件大小（字节）
        
    Returns:
        格式化后的文件大小字符串
    """
    if size is None:
        return '-'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024 or unit == 'TB':
            return f"{size:.2f} {unit}"
        size /= 1024

# ==================== 数据模型 ====================

class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='patient', index=True)  # 添加索引以优化角色筛选查询
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'created_at': to_local_time(self.created_at)
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class DetectionHistory(db.Model):
    """检测历史模型"""
    __tablename__ = 'detection_history'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), db.ForeignKey('users.username'), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # 患者ID，添加索引以优化患者报告查询
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    filename = db.Column(db.String(255), nullable=False)
    model = db.Column(db.String(50), default='yolov8')
    result_image = db.Column(db.String(500))
    detections = db.Column(db.Text)  # JSON 格式存储
    count = db.Column(db.Integer, default=0)
    confidence = db.Column(db.Float, default=0.0)   # 单张图平均置信度
    medical_advice = db.Column(db.Text)  # 医疗建议（JSON格式存储）
    original_image = db.Column(db.String(500))  # 原始图片路径
    diagnosis = db.Column(db.Text)  # 诊断结论
    follow_up_notes = db.Column(db.Text)  # 随访备注
    
    # 关系定义
    doctor = db.relationship('User', foreign_keys=[username], backref='created_reports')
    patient = db.relationship('User', foreign_keys=[patient_id], backref='medical_reports')
    
    def to_dict(self):
        detections = safe_json_loads(self.detections, [])
        medical_advice = safe_json_loads(self.medical_advice, None)
        
        # 提取骨折类型信息
        fracture_types = []
        for det in detections:
            if det.get('class') and det['class'] not in fracture_types:
                fracture_types.append(det['class'])
        
        # 获取医生和患者信息
        doctor_name = get_display_name(self.doctor)
        patient_name = get_display_name(self.patient)
        
        return {
            'id': self.id,
            'username': self.username,
            'patient_id': self.patient_id,
            'doctor_name': doctor_name,
            'patient_name': patient_name,
            'timestamp': to_local_time(self.timestamp),
            'filename': self.filename,
            'model': self.model,
            'result_image': self.result_image,
            'original_image': self.original_image,
            'detections': detections,
            'count': self.count,
            'confidence': self.confidence,
            'fracture_types': fracture_types,
            'has_medical_advice': medical_advice is not None,
            'medical_advice': medical_advice,
            'diagnosis': self.diagnosis,
            'follow_up_notes': self.follow_up_notes
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


class UserAIModel(db.Model):
    """用户AI模型配置 - 存储用户用过的模型ID和API密钥"""
    __tablename__ = 'user_ai_models'
    
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)  # modelscope/openai/custom
    model_id = db.Column(db.String(200), nullable=False)  # 模型ID
    api_key = db.Column(db.Text)  # API密钥
    api_url = db.Column(db.String(500))  # 自定义API地址
    created_by = db.Column(db.String(80), db.ForeignKey('users.username'))  # 用户名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 联合唯一约束：同一用户的同一提供商下，模型ID不能重复
    __table_args__ = (
        db.UniqueConstraint('provider', 'model_id', 'created_by', name='uix_user_model'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'model_id': self.model_id,
            'api_key': self.api_key,
            'api_url': self.api_url,
            'created_by': self.created_by
        }
    
    def __repr__(self):
        return f'<UserAIModel {self.provider}:{self.model_id}>'


class AIConversation(db.Model):
    """AI对话记录模型"""
    __tablename__ = 'ai_conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_id = db.Column(db.String(50), nullable=False, index=True)  # 会话ID
    message_type = db.Column(db.String(20), nullable=False)  # user/assistant
    message_content = db.Column(db.Text, nullable=False)
    # RAG 引用溯源结果（JSON 数组字符串）。不存这一列的话，
    # 页面一刷新引用卡片就没了——回答正文还留着自己的 [1][2] 角标。
    references = db.Column(db.Text)
    context_report_id = db.Column(db.Integer, db.ForeignKey('detection_history.id'))  # 关联的报告
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # 关系定义
    patient = db.relationship('User', backref='ai_conversations')
    context_report = db.relationship('DetectionHistory', backref='ai_conversations')
    
    def to_dict(self):
        # 获取患者信息
        patient_name = None
        if self.patient:
            patient_name = self.patient.full_name or self.patient.username
        
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': patient_name,
            'session_id': self.session_id,
            'message_type': self.message_type,
            'message_content': self.message_content,
            'references': safe_json_loads(self.references, []),
            'context_report_id': self.context_report_id,
            'created_at': to_local_time(self.created_at)
        }
    
    def __repr__(self):
        return f'<AIConversation {self.id}>'


class OperationLog(db.Model):
    """操作日志模型 - 借鉴pear-admin-flask"""
    __tablename__ = 'operation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    method = db.Column(db.String(10))  # GET/POST/PUT/DELETE
    url = db.Column(db.String(255))
    ip = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    # 用 Text 而非 String(255)：操作描述可能包含异常堆栈、SQL 语句等长文本
    # （实测最长 1421 字符）。SQLite 不强制 VARCHAR 长度，所以此前未暴露；
    # 迁移到 PostgreSQL 时会报 StringDataRightTruncation。
    description = db.Column(db.Text)  # 操作描述
    success = db.Column(db.Boolean, default=True)  # 是否成功
    error_msg = db.Column(db.Text)  # 错误信息
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
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
            'timestamp': to_local_time(self.timestamp)
        }
    
    def __repr__(self):
        return f'<OperationLog {self.id}>'


class Dataset(db.Model):
    """数据集模型"""
    __tablename__ = 'datasets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 数据集名称
    description = db.Column(db.String(500))  # 数据集描述
    dataset_path = db.Column(db.String(500), nullable=False)  # 数据集路径
    file_size = db.Column(db.Integer)  # 文件大小（字节）
    num_images = db.Column(db.Integer, default=0)  # 图片数量
    num_classes = db.Column(db.Integer, default=0)  # 类别数量
    class_names = db.Column(db.Text)  # 类别名称（JSON格式）
    status = db.Column(db.String(20), default='active')  # active/disabled
    uploader = db.Column(db.String(80))  # 上传者
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        # 格式化文件大小
        size_str = format_file_size(self.file_size)

        # 解析类别名称
        class_list = safe_json_loads(self.class_names, [])

        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'dataset_path': self.dataset_path,
            'file_size': self.file_size,
            'size_str': size_str,
            'num_images': self.num_images,
            'image_count': self.num_images,
            'num_classes': self.num_classes,
            'class_names': class_list,
            'classes': class_list,
            'status': self.status,
            'uploader': self.uploader,
            'created_at': to_local_time(self.created_at),
            'updated_at': to_local_time(self.updated_at)
        }

    def __repr__(self):
        return f'<Dataset {self.name}>'


# 保留FileRecord模型用于向后兼容（可选）
class FileRecord(db.Model):
    """文件记录模型（保留用于兼容）"""
    __tablename__ = 'file_records'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    extension = db.Column(db.String(20))
    uploader = db.Column(db.String(80))
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        size_str = format_file_size(self.file_size)
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
            'created_at': to_local_time(self.created_at)
        }


class CustomModel(db.Model):
    """自定义训练模型"""
    __tablename__ = 'custom_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 模型名称
    model_key = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 模型标识
    description = db.Column(db.String(255))  # 模型描述
    base_model = db.Column(db.String(50), nullable=False)  # 基础模型 (yolov8/yolo11/yolo26)
    model_path = db.Column(db.String(500), nullable=False)  # 模型文件路径
    dataset_path = db.Column(db.String(500))  # 训练数据集路径
    status = db.Column(db.String(20), default='training')  # training/trained/published/disabled
    accuracy = db.Column(db.Float)  # 综合评分 (mAP50 + mAP50-95 + F1) / 3
    map50 = db.Column(db.Float)  # mAP@0.5
    map50_95 = db.Column(db.Float)  # mAP@0.5:0.95
    precision = db.Column(db.Float)  # 精确率
    recall = db.Column(db.Float)  # 召回率
    f1_score = db.Column(db.Float)  # F1-Score (Precision和Recall的调和平均)
    epochs = db.Column(db.Integer, default=100)  # 训练轮数
    batch_size = db.Column(db.Integer, default=16)  # 批次大小
    img_size = db.Column(db.Integer, default=640)  # 图像尺寸

    created_by = db.Column(db.String(80))  # 创建者
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)  # 发布时间
    
    def to_dict(self):
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
            'precision': self.precision,
            'recall': self.recall,
            'f1_score': self.f1_score,
            'epochs': self.epochs,
            'batch_size': self.batch_size,
            'img_size': self.img_size,
            'created_by': self.created_by,
            'created_at': to_local_time(self.created_at),
            'updated_at': to_local_time(self.updated_at),
            'published_at': to_local_time(self.published_at)
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
        return {
            'id': self.id,
            'task_name': self.task_name,
            'name': self.task_name,
            'model_id': self.model_id,
            'model_name': self.model.name if self.model else None,
            'base_model': self.model.base_model if self.model else None,
            'status': self.status,
            'progress': self.progress,
            'current_epoch': self.current_epoch,
            'total_epochs': self.total_epochs,
            'loss': self.loss,
            'val_loss': self.val_loss,
            'log_file': self.log_file,
            'error_message': self.error_message,
            'started_at': to_local_time(self.started_at),
            'completed_at': to_local_time(self.completed_at),
            'created_by': self.created_by,
            'created_at': to_local_time(self.created_at)
        }
    
    def __repr__(self):
        return f'<TrainingTask {self.id}>'


class Patient(db.Model):
    """患者模型"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 患者姓名
    age = db.Column(db.Integer)  # 年龄
    gender = db.Column(db.String(10))  # 性别
    medical_history = db.Column(db.Text)  # 病史
    contact_info = db.Column(db.String(255))  # 联系方式
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'age': self.age,
            'gender': self.gender,
            'medical_history': self.medical_history,
            'contact_info': self.contact_info,
            'created_at': to_local_time(self.created_at),
            'updated_at': to_local_time(self.updated_at)
        }
    
    def __repr__(self):
        return f'<Patient {self.name}>'


class Examination(db.Model):
    """检查记录模型"""
    __tablename__ = 'examinations'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    exam_date = db.Column(db.DateTime, default=datetime.utcnow)  # 检查日期
    image_path = db.Column(db.String(500))  # 检查图像路径
    detection_result = db.Column(db.Text)  # 检测结果（JSON格式）
    report = db.Column(db.Text)  # 诊断报告
    follow_up_date = db.Column(db.DateTime)  # 随访日期
    created_by = db.Column(db.String(80))  # 检查医生
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联模型
    patient = db.relationship('Patient', backref='examinations')
    
    def to_dict(self):
        detection_result = safe_json_loads(self.detection_result, {})
        
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': get_display_name(self.patient, 'name'),
            'exam_date': to_local_time(self.exam_date),
            'image_path': self.image_path,
            'detection_result': detection_result,
            'report': self.report,
            'follow_up_date': to_local_time(self.follow_up_date),
            'created_by': self.created_by,
            'created_at': to_local_time(self.created_at)
        }
    
    def __repr__(self):
        return f'<Examination {self.id}>'


# ==================== 智慧骨科系统新增模型 ====================

class DoctorProfile(db.Model):
    """医生详细信息"""
    __tablename__ = 'doctor_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    department = db.Column(db.String(100))  # 科室
    title = db.Column(db.String(50))  # 职称（主任医师、副主任医师等）
    license_number = db.Column(db.String(100))  # 执业证号
    specialty = db.Column(db.Text)  # 专长
    hospital = db.Column(db.String(200))  # 所属医院
    status = db.Column(db.String(20), default='pending')  # pending/active/rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # 审核人
    approved_at = db.Column(db.DateTime)  # 审核时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('doctor_profile', uselist=False))
    approver = db.relationship('User', foreign_keys=[approved_by])
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'full_name': self.user.full_name if self.user else None,
            'department': self.department,
            'title': self.title,
            'license_number': self.license_number,
            'specialty': self.specialty,
            'hospital': self.hospital,
            'status': self.status,
            'approved_at': to_local_time(self.approved_at),
            'created_at': to_local_time(self.created_at)
        }


class PatientProfile(db.Model):
    """患者详细信息"""
    __tablename__ = 'patient_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    patient_number = db.Column(db.String(50), unique=True)  # 病历号
    id_card = db.Column(db.String(18))  # 身份证号
    gender = db.Column(db.String(10))  # 性别
    birth_date = db.Column(db.Date)  # 出生日期
    address = db.Column(db.Text)  # 地址
    emergency_contact = db.Column(db.String(100))  # 紧急联系人
    emergency_phone = db.Column(db.String(20))  # 紧急联系人电话
    allergies = db.Column(db.Text)  # 过敏史
    medical_history = db.Column(db.Text)  # 既往病史
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # 创建人（医生或自行注册）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('patient_profile', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by])
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'full_name': self.user.full_name if self.user else None,
            'patient_number': self.patient_number,
            'id_card': self.id_card,
            'gender': self.gender,
            'birth_date': self.birth_date.isoformat() if self.birth_date else None,
            'address': self.address,
            'emergency_contact': self.emergency_contact,
            'emergency_phone': self.emergency_phone,
            'allergies': self.allergies,
            'medical_history': self.medical_history,
            'created_at': to_local_time(self.created_at)
        }


class DoctorPatientRelation(db.Model):
    """医生-患者关联关系"""
    __tablename__ = 'doctor_patient_relations'
    
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_primary = db.Column(db.Boolean, default=True)  # 是否为主治医师
    status = db.Column(db.String(20), default='active')  # active/archived
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='patients')
    patient = db.relationship('User', foreign_keys=[patient_id], backref='doctors')
    
    # 联合唯一约束
    __table_args__ = (
        db.UniqueConstraint('doctor_id', 'patient_id', name='uix_doctor_patient'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'doctor_id': self.doctor_id,
            'doctor_name': self.doctor.full_name if self.doctor else None,
            'patient_id': self.patient_id,
            'patient_name': self.patient.full_name if self.patient else None,
            'is_primary': self.is_primary,
            'status': self.status,
            'notes': self.notes,
            'created_at': to_local_time(self.created_at)
        }


class Message(db.Model):
    """消息通知"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 发送者ID，None表示系统消息
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 接收者ID，None表示广播消息
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), default='system')  # system/doctor/appointment/reminder
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    
    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'title': self.title,
            'content': self.content,
            'message_type': self.message_type,
            'is_read': self.is_read,
            'created_at': to_local_time(self.created_at)
        }


class Announcement(db.Model):
    """系统公告"""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # 发布者ID（管理员）
    target_role = db.Column(db.String(20), default='all')  # all/patient/doctor 目标用户角色
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    priority = db.Column(db.String(20), default='normal')  # low/normal/high/urgent 优先级
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    author = db.relationship('User', foreign_keys=[author_id], backref='published_announcements')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'author_id': self.author_id,
            'author_name': self.author.full_name if self.author else None,
            'target_role': self.target_role,
            'is_active': self.is_active,
            'priority': self.priority,
            'created_at': to_local_time(self.created_at),
            'updated_at': to_local_time(self.updated_at)
        }


class AnnouncementRead(db.Model):
    """公告已读记录"""
    __tablename__ = 'announcement_reads'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    announcement = db.relationship('Announcement', backref='read_records')
    user = db.relationship('User', backref='announcement_reads')

    def to_dict(self):
        return {
            'id': self.id,
            'announcement_id': self.announcement_id,
            'user_id': self.user_id,
            'read_at': to_local_time(self.read_at)
        }


class MedicalRecord(db.Model):
    """病历记录"""
    __tablename__ = 'medical_records'
    
    id = db.Column(db.Integer, primary_key=True)
    record_number = db.Column(db.String(50), unique=True)  # 病历编号
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    diagnosis = db.Column(db.Text)  # 诊断结果
    symptoms = db.Column(db.Text)  # 症状描述
    treatment = db.Column(db.Text)  # 治疗方案
    prescription = db.Column(db.Text)  # 处方（JSON格式）
    advice = db.Column(db.Text)  # 医嘱
    status = db.Column(db.String(20), default='active')  # active/archived/deleted
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)  # 就诊日期
    follow_up_date = db.Column(db.DateTime)  # 复诊日期
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    patient = db.relationship('User', foreign_keys=[patient_id], backref='medical_records')
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='created_records')
    
    def to_dict(self):
        prescription = safe_json_loads(self.prescription, {})
        
        return {
            'id': self.id,
            'record_number': self.record_number,
            'patient_id': self.patient_id,
            'patient_name': get_display_name(self.patient),
            'doctor_id': self.doctor_id,
            'doctor_name': get_display_name(self.doctor),
            'diagnosis': self.diagnosis,
            'symptoms': self.symptoms,
            'treatment': self.treatment,
            'prescription': prescription,
            'advice': self.advice,
            'status': self.status,
            'visit_date': to_local_time(self.visit_date),
            'follow_up_date': to_local_time(self.follow_up_date),
            'created_at': to_local_time(self.created_at)
        }


class DoctorRegistration(db.Model):
    """医生注册申请表"""
    __tablename__ = 'doctor_registrations'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100))
    title = db.Column(db.String(50))
    license_number = db.Column(db.String(100))
    hospital = db.Column(db.String(200))
    specialty = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    review_note = db.Column(db.Text)  # 审核备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    
    # 关系
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'department': self.department,
            'title': self.title,
            'license_number': self.license_number,
            'hospital': self.hospital,
            'specialty': self.specialty,
            'status': self.status,
            'review_note': self.review_note,
            'created_at': to_local_time(self.created_at),
            'reviewed_at': to_local_time(self.reviewed_at)
        }


# ==================== 知识库（RAG，阶段 7） ====================

class KnowledgeDoc(db.Model):
    """知识库文档

    共享知识库与患者个人病历共用一张表：
    - 共享文档：patient_id 为 NULL
    - 个人文档：patient_id = 病历所属患者

    合并的理由：混合检索的 RRF 融合需要一份可比的候选列表，拆两张表意味着
    2×（向量+BM25）四次查询、两套去重、以及跨语料不可比的分数。
    隔离靠严格的口径维持——共享行 patient_id IS NULL，个人行 patient_id = 属主，
    所有读路径都套 RetrievalScope 过滤（见 services/rag/retriever.py）。
    """
    __tablename__ = 'knowledge_docs'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    # guideline / classification / drug / rehab / anatomy / textbook / record / other
    doc_type = db.Column(db.String(50), default='other', index=True)
    department = db.Column(db.String(100))
    source = db.Column(db.String(500))       # 出处：URL 或文献引用
    # public=公开资料原文 | curated=本项目整理摘要 | patient_record=患者个人病历
    origin = db.Column(db.String(20), default='curated', index=True)
    language = db.Column(db.String(10), default='zh')
    file_path = db.Column(db.String(500))    # 相对 KNOWLEDGE_DIR；DB 派生的病历为 NULL
    file_hash = db.Column(db.String(64), index=True)   # sha256，幂等重入库依据
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending/processing/ready/failed
    error_msg = db.Column(db.Text)
    chunk_count = db.Column(db.Integer, default=0)
    char_count = db.Column(db.Integer, default=0)
    doc_meta = db.Column(db.Text)            # JSON：frontmatter 其余字段 + 原始文件名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chunks = db.relationship(
        'KnowledgeChunk', backref='doc', lazy='dynamic',
        cascade='all, delete-orphan', foreign_keys='KnowledgeChunk.doc_id',
    )
    patient = db.relationship('User', foreign_keys=[patient_id])
    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def to_dict(self, with_content=False):
        return {
            'id': self.id,
            'title': self.title,
            'doc_type': self.doc_type,
            'department': self.department,
            'source': self.source,
            'origin': self.origin,
            'language': self.language,
            'patient_id': self.patient_id,
            'patient_name': get_display_name(self.patient),
            'uploaded_by': self.uploaded_by,
            'status': self.status,
            'error_msg': self.error_msg,
            'chunk_count': self.chunk_count,
            'char_count': self.char_count,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'doc_meta': safe_json_loads(self.doc_meta, {}),
            'is_shared': self.patient_id is None,
            'created_at': to_local_time(self.created_at),
            'updated_at': to_local_time(self.updated_at),
        }

    def __repr__(self):
        return f'<KnowledgeDoc {self.id} {self.title[:20]}>'


class KnowledgeChunk(db.Model):
    """知识库切片

    patient_id 从所属文档反规范化下来，使隔离过滤是单表条件、无需 JOIN，
    因而能作为 ANN 查询的前置过滤（否则只能先取后筛，召回会被稀释）。
    """
    __tablename__ = 'knowledge_chunks'

    id = db.Column(db.Integer, primary_key=True)
    doc_id = db.Column(
        db.Integer,
        db.ForeignKey('knowledge_docs.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    chunk_index = db.Column(db.Integer, nullable=False, default=0)
    content = db.Column(db.Text, nullable=False)
    token_count = db.Column(db.Integer, default=0)
    section = db.Column(db.String(255))      # 标题路径，如 "3 分型标准 > 3.2 股骨远端"
    page = db.Column(db.Integer)             # 1-based；MD/TXT 无页概念时为 NULL
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    embedding = db.Column(VectorType)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_kb_chunks_doc_chunk', 'doc_id', 'chunk_index'),
        db.Index('ix_kb_chunks_patient_doc', 'patient_id', 'doc_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'doc_id': self.doc_id,
            'chunk_index': self.chunk_index,
            'content': self.content,
            'token_count': self.token_count,
            'section': self.section,
            'page': self.page,
            'is_personal': self.patient_id is not None,
        }

    def __repr__(self):
        return f'<KnowledgeChunk {self.id} doc={self.doc_id}>'


# ==================== 数据库初始化函数 ====================

def init_db(app):
    """初始化数据库"""
    from werkzeug.security import generate_password_hash
    
    db.init_app(app)
    
    with app.app_context():
        # pgvector 引导：CREATE EXTENSION 必须在 create_all 之前，否则首次在
        # 新机器上建 knowledge_chunks 会报 type "vector" does not exist
        # （此前是手工执行的，仓库里没有任何记录）。
        # 而 HNSW / GIN 索引和新增列是 create_all 做不到的，必须在其后补。
        try:
            from services.rag.store import (
                ensure_columns, ensure_extensions, ensure_indexes,
            )
            _ext = ensure_extensions()
            db.create_all()
            _idx = ensure_indexes()
            _col = ensure_columns()
            logger.info(
                "✅ 数据库表已创建（pgvector 扩展=%s，索引=%s，新增列=%s）",
                _ext.get('vector'), _idx, _col,
            )
        except Exception as e:
            logger.warning("pgvector 引导失败，知识库检索将降级: %s", e, exc_info=True)
            db.create_all()

        # 回收中断的入库任务，避免 processing 状态的行永远留在管理界面上
        try:
            from services.rag.store import recover_stale_docs
            _stale = recover_stale_docs()
            if _stale:
                logger.info("✅ 已回收 %d 个中断的入库任务", _stale)
        except Exception as e:
            logger.warning("回收中断入库任务失败: %s", e)


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
            logger.info("✅ 默认admin用户已创建（用户名: admin, 密码: 123456）")
        else:
            # 如果admin用户存在但密码未加密，更新密码
            if not (admin_user.password.startswith('$2b$') or 
                    admin_user.password.startswith('$2a$') or 
                    admin_user.password.startswith('pbkdf2:') or
                    admin_user.password.startswith('scrypt:') or
                    admin_user.password.startswith('argon2:')):
                logger.info("⚠️  检测到admin用户密码未加密，正在更新...")
                admin_user.password = generate_password_hash('123456')
                db.session.commit()
                logger.info("✅ admin用户密码已更新（密码: 123456）")
        
        # 初始化默认系统设置
        if not SystemSettings.query.filter_by(key='default_model').first():
            default_settings = [
                SystemSettings(key='default_model', value='yolov8', description='默认模型'),
                SystemSettings(key='confidence_threshold', value='0.25', description='置信度阈值'),
            ]
            for setting in default_settings:
                db.session.add(setting)
            db.session.commit()
            logger.info("✅ 系统设置已初始化")


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
                logger.info(f"✅ 已迁移 {len(users_data)} 个用户到数据库")
            except Exception as e:
                logger.error(f"❌ 迁移用户数据失败: {e}")
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
            logger.info("✅ 默认admin用户已创建（用户名: admin, 密码: 123456）")
        
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
                logger.info(f"✅ 已迁移 {len(history_data)} 条检测历史到数据库")
            except Exception as e:
                logger.error(f"❌ 迁移历史记录失败: {e}")
                db.session.rollback()
