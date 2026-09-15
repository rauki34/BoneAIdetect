"""AI 内容安全

从 app.py 抽出：敏感词过滤、提示词注入检测、输入净化。

注意：当前为黑名单式防护，可被同义改写 / 编码绕过。
"""
import re

# 敏感词列表
SENSITIVE_WORDS = [
    '密码', 'password', '身份证', 'id card', 'credit card', '信用卡',
    '银行卡', 'bank account', '社保', 'social security',
    'api_key', 'secret', 'token', 'private key'
]

# 提示词注入检测模式
PROMPT_INJECTION_PATTERNS = [
    r'ignore\s+(previous|above|all)\s+instructions?',
    r'forget\s+(everything|all|previous)',
    r'you\s+are\s+now',
    r'new\s+instructions?',
    r'system\s*:\s*',
    r'<\s*script\s*>',
    r'javascript\s*:',
    r'eval\s*\(',
    r'exec\s*\(',
]


def filter_sensitive_content(text):
    """过滤AI回复中的敏感信息
    
    Args:
        text: AI回复文本
    
    Returns:
        str: 过滤后的文本
    
    需求: 7.4
    """
    if not text:
        return text
    
    filtered_text = text
    
    # 过滤敏感词
    for word in SENSITIVE_WORDS:
        if word.lower() in filtered_text.lower():
            # 用星号替换敏感词
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            filtered_text = pattern.sub('***', filtered_text)
    
    return filtered_text

def detect_prompt_injection(text):
    """检测提示词注入攻击
    
    Args:
        text: 用户输入文本
    
    Returns:
        bool: 是否检测到注入攻击
    
    需求: 7.4
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # 检查注入模式
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    return False

def sanitize_ai_input(text):
    """清理AI输入内容
    
    Args:
        text: 用户输入文本
    
    Returns:
        str: 清理后的文本
    
    需求: 7.4
    """
    if not text:
        return text
    
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    
    # 移除JavaScript代码
    text = re.sub(r'javascript\s*:', '', text, flags=re.IGNORECASE)
    
    # 限制长度
    max_length = 2000
    if len(text) > max_length:
        text = text[:max_length]
    
    return text.strip()
