"""输入校验工具

从 app.py 抽出，供各蓝图与注册/登录流程共用。
"""
import re
from datetime import datetime

# ==================== 输入验证工具函数 ====================

def validate_role(role):
    """验证角色值的有效性
    
    Args:
        role: 角色字符串
    
    Returns:
        bool: 是否有效
    
    需求: 1.4
    """
    return role in ['admin', 'doctor', 'patient']

def validate_username(username):
    """验证用户名格式
    
    Args:
        username: 用户名字符串
    
    Returns:
        tuple: (是否有效, 错误消息)
    
    需求: 15.1
    """
    if not username:
        return False, "用户名不能为空"
    
    if len(username) < 3:
        return False, "用户名长度至少3个字符"
    
    if len(username) > 80:
        return False, "用户名长度不能超过80个字符"
    
    # 只允许字母、数字、下划线
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"
    
    return True, None

def validate_password(password):
    """验证密码格式
    
    Args:
        password: 密码字符串
    
    Returns:
        tuple: (是否有效, 错误消息)
    
    需求: 15.1
    """
    if not password:
        return False, "密码不能为空"
    
    if len(password) < 6:
        return False, "密码长度至少6个字符"
    
    if len(password) > 128:
        return False, "密码长度不能超过128个字符"
    
    return True, None

def validate_email(email):
    """验证邮箱格式
    
    Args:
        email: 邮箱字符串
    
    Returns:
        tuple: (是否有效, 错误消息)
    
    需求: 15.1
    """
    if not email:
        return True, None  # 邮箱是可选的
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "邮箱格式不正确"
    
    if len(email) > 120:
        return False, "邮箱长度不能超过120个字符"
    
    return True, None

def validate_phone(phone):
    """验证电话格式
    
    Args:
        phone: 电话字符串
    
    Returns:
        tuple: (是否有效, 错误消息)
    
    需求: 15.1
    """
    if not phone:
        return True, None  # 电话是可选的
    
    # 中国手机号格式: 1开头,第二位是3-9,共11位
    phone_pattern = r'^1[3-9]\d{9}$'
    if not re.match(phone_pattern, phone):
        return False, "电话格式不正确(请输入11位中国手机号)"
    
    return True, None

def calculate_age(birth_date):
    """计算年龄"""
    if not birth_date:
        return 0
    today = datetime.today()
    age = today.year - birth_date.year
    if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
        age -= 1
    return age
