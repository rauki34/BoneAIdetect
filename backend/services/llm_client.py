"""统一 LLM 接入层

替代原先散落在 app.py 中的 8 个重复请求函数：
    call_local_ai / call_openai_api / call_custom_api / call_modelscope_api
    call_local_ai_assistant / call_openai_assistant / call_custom_assistant / call_modelscope_assistant

设计目标：
1. 屏蔽 provider 差异，调用方只关心 chat(messages)
2. 统一超时、错误处理、重试与指数退避
3. 支持流式输出
4. 新增 provider 只需实现一个类并注册到 PROVIDER_MAP

调用方保持原有行为的关键参数（各调用点差异很大，必须显式传递）：
    timeout      : 30 / 60 / 120 / 180（原各函数不同）
    max_tokens   : 500 / 1000 / 2000（原各函数不同）
    temperature  : 统一 0.7
"""
import json
import logging
import time
from abc import ABC, abstractmethod

import requests

logger = logging.getLogger('llm')


# ==================== 异常体系 ====================

class LLMError(Exception):
    """LLM 调用相关错误基类"""


class LLMConfigError(LLMError):
    """配置缺失（如未填 API Key）"""


class LLMTimeoutError(LLMError):
    """请求超时（可重试）"""


class LLMConnectionError(LLMError):
    """连接失败（可重试）"""


class LLMResponseError(LLMError):
    """响应存在但格式异常 / 服务端报错（不重试）"""


# ==================== Provider 基类 ====================

class BaseProvider(ABC):
    """所有 Provider 的基类

    子类至少需要实现 _build_request() 与 _extract_text()。
    """

    name = 'base'
    default_timeout = 60
    default_max_tokens = None
    default_temperature = 0.7
    # 未配置 api_url 时的回退地址（子类覆盖）
    default_api_url = ''

    # 可在构造时覆盖的字段
    _CONFIG_KEYS = ('api_key', 'api_url', 'model', 'timeout',
                    'max_tokens', 'temperature')

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.api_key = config.get('api_key') or ''
        # 数据库中的 ai_api_url 常为空，必须回退，否则会拼出 "/chat" 这类无效地址
        self.api_url = config.get('api_url') or self.default_api_url
        self.model = config.get('model') or ''
        self.timeout = config.get('timeout') or self.default_timeout
        self.max_tokens = config.get('max_tokens', self.default_max_tokens)
        self.temperature = config.get('temperature', self.default_temperature)

    # ---------- 子类实现 ----------

    @abstractmethod
    def _build_request(self, messages, max_tokens, temperature, stream):
        """构造请求，返回 (url, headers, payload)"""
        raise NotImplementedError

    @abstractmethod
    def _extract_text(self, result: dict) -> str:
        """从响应 JSON 中提取文本"""
        raise NotImplementedError

    # ---------- 对外主入口 ----------

    def chat(self, messages, *, max_tokens=None, temperature=None,
             timeout=None, image_base64=None, prompt_style='raw'):
        """非流式对话，返回文本

        Args:
            messages: OpenAI 格式消息列表
            max_tokens / temperature / timeout: 覆盖实例默认值
            image_base64: 多模态图片（base64，不含 data URI 前缀）
            prompt_style: 仅 LocalProvider 使用，决定 messages -> prompt 的拼装方式
        """
        text = self._send(messages, max_tokens, temperature, timeout,
                          image_base64, prompt_style, stream=False)
        return text

    def stream(self, messages, *, max_tokens=None, temperature=None,
               timeout=None, image_base64=None, prompt_style='raw'):
        """流式对话，逐块产出文本"""
        response = self._post(messages, max_tokens, temperature, timeout,
                              image_base64, prompt_style, stream=True)
        yield from self._iter_stream(response)

    # ---------- 内部 ----------

    def _send(self, messages, max_tokens, temperature, timeout,
              image_base64, prompt_style, stream):
        response = self._post(messages, max_tokens, temperature, timeout,
                              image_base64, prompt_style, stream)
        if stream:
            return response
        try:
            result = response.json()
        except ValueError as e:
            raise LLMResponseError(
                f'{self.name} 响应非 JSON: {response.text[:200]}'
            ) from e
        return self._extract_text(result)

    def _post(self, messages, max_tokens, temperature, timeout,
              image_base64, prompt_style, stream):
        url, headers, payload = self._build_request(
            messages,
            max_tokens if max_tokens is not None else self.max_tokens,
            temperature if temperature is not None else self.temperature,
            stream,
        )
        if image_base64:
            payload = self._attach_image(payload, image_base64, prompt_style)

        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            response = requests.post(url, headers=headers, json=payload,
                                     timeout=effective_timeout, stream=stream)
        except requests.exceptions.Timeout as e:
            raise LLMTimeoutError(f'{self.name} 请求超时（{effective_timeout}s）') from e
        except requests.exceptions.ConnectionError as e:
            raise LLMConnectionError(f'{self.name} 连接失败: {e}') from e

        if response.status_code != 200:
            raise LLMResponseError(
                f'{self.name} 调用失败: HTTP {response.status_code} - {response.text[:300]}'
            )
        return response

    def _attach_image(self, payload, image_base64, prompt_style):
        """默认实现：按 OpenAI 多模态格式追加图片

        LocalProvider 会覆盖此方法（它使用自定义协议）。
        """
        for msg in payload.get('messages', []):
            if msg.get('role') != 'user':
                continue
            content = msg.get('content')
            parts = content if isinstance(content, list) else [
                {'type': 'text', 'text': content or ''}
            ]
            parts.append({
                'type': 'image_url',
                'image_url': {'url': f'data:image/jpeg;base64,{image_base64}'},
            })
            msg['content'] = parts
            break
        return payload

    def _iter_stream(self, response):
        """流式解析（SSE 格式，OpenAI 兼容接口通用）"""
        for raw in response.iter_lines():
            if not raw:
                continue
            line = raw.decode('utf-8', errors='ignore').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                obj = json.loads(data)
                choices = obj.get('choices') or []
                if not choices:
                    continue
                delta = choices[0].get('delta') or {}
                chunk = delta.get('content')
                if chunk:
                    yield chunk
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue


# ==================== 具体 Provider ====================

class OpenAICompatProvider(BaseProvider):
    """OpenAI 兼容协议（OpenAI / ModelScope / 兼容 OpenAI 的自定义服务）"""

    def _build_request(self, messages, max_tokens, temperature, stream):
        url = self._endpoint()
        headers = {
            'Content-Type': 'application/json',
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'stream': stream,
        }
        if max_tokens:
            payload['max_tokens'] = max_tokens
        return url, headers, payload

    def _endpoint(self):
        """子类返回完整请求地址"""
        raise NotImplementedError

    def _extract_text(self, result: dict) -> str:
        choices = result.get('choices') or []
        if not choices:
            raise LLMResponseError(f'{self.name} 返回格式异常: {str(result)[:200]}')
        return choices[0]['message']['content']


class OpenAIProvider(OpenAICompatProvider):
    name = 'openai'
    default_timeout = 60
    default_max_tokens = 1000
    default_api_url = 'https://api.openai.com/v1'

    def _endpoint(self):
        if not self.api_key:
            raise LLMConfigError('OpenAI 未配置 API Key')
        return f'{self.api_url.rstrip("/")}/chat/completions'


class ModelScopeProvider(OpenAICompatProvider):
    name = 'modelscope'
    default_timeout = 120
    default_max_tokens = 2000
    default_api_url = 'https://api-inference.modelscope.cn/v1'

    def _endpoint(self):
        if not self.api_key:
            raise LLMConfigError('ModelScope 未配置 API Key')
        return f'{self.api_url.rstrip("/")}/chat/completions'


class CustomProvider(OpenAICompatProvider):
    """自定义 API

    api_url 为**完整**请求地址（原 call_custom_api 直接 POST 该地址）。
    响应格式兼容度更高：依次尝试 choices / result / reply，最后回退字符串化。
    """

    name = 'custom'
    default_timeout = 60
    default_max_tokens = None

    def _endpoint(self):
        if not self.api_url:
            raise LLMConfigError('自定义 API 未配置请求地址')
        return self.api_url

    def _extract_text(self, result: dict) -> str:
        if 'choices' in result:
            choices = result['choices'] or []
            if choices:
                return choices[0]['message']['content']
        for key in ('result', 'reply'):
            if key in result:
                return result[key]
        return str(result)


class LocalProvider(BaseProvider):
    """本地部署的 AI 服务（AI/app.py 提供的 POST /chat）

    与 OpenAI 协议不同，只接受 {"prompt": "...", "image": "<base64>"}。
    """

    name = 'local'
    default_timeout = 180
    default_max_tokens = None
    default_temperature = None
    default_api_url = 'http://127.0.0.1:8000'

    def _build_request(self, messages, max_tokens, temperature, stream):
        endpoint = '/chat/stream' if stream else '/chat'
        url = f'{self.api_url.rstrip("/")}{endpoint}'
        payload = {'prompt': self._to_prompt(messages)}
        return url, {'Content-Type': 'application/json'}, payload

    def _iter_stream(self, response):
        """本地服务的 SSE 事件格式为 {"delta": "..."}

        与 OpenAI 兼容格式（choices[0].delta.content）不同，需单独解析。
        """
        for raw in response.iter_lines():
            if not raw:
                continue
            line = raw.decode('utf-8', errors='ignore').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if obj.get('error'):
                raise LLMResponseError(f'本地服务流式错误: {obj["error"]}')
            chunk = obj.get('delta')
            if chunk:
                yield chunk

    @staticmethod
    def _to_prompt(messages):
        """messages -> 纯文本 prompt

        多模态时图片单独由 _attach_image 处理，此处只取文本部分。
        """
        parts = []
        for msg in messages:
            content = msg.get('content')
            if isinstance(content, list):
                text = ''.join(
                    p.get('text', '') for p in content if isinstance(p, dict)
                    and p.get('type') == 'text'
                )
            else:
                text = content or ''
            parts.append(text)
        return '\n'.join(p for p in parts if p)

    def _attach_image(self, payload, image_base64, prompt_style):
        payload['image'] = image_base64
        return payload

    def _extract_text(self, result: dict) -> str:
        value = result.get('reply') or result.get('result')
        if value is None:
            raise LLMResponseError(f'本地服务返回格式异常: {str(result)[:200]}')
        return value


PROVIDER_MAP = {
    'openai': OpenAIProvider,
    'modelscope': ModelScopeProvider,
    'custom': CustomProvider,
    'local': LocalProvider,
}


# ==================== 统一客户端 ====================

class LLMClient:
    """统一 LLM 客户端

    包装 Provider，提供重试与指数退避：
    - 超时 / 连接失败 -> 重试（最多 MAX_RETRIES 次）
    - 配置错误 / 响应格式错误 -> 立即抛出，不重试
    """

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0     # 秒，实际等待 BACKOFF_BASE * 2^attempt

    def __init__(self, provider_name: str, config: dict | None = None):
        provider_cls = PROVIDER_MAP.get(provider_name)
        if provider_cls is None:
            raise LLMConfigError(
                f'未知的 AI 服务提供商: {provider_name}（可选: {list(PROVIDER_MAP)}）'
            )
        self.provider_name = provider_name
        self.config = config or {}
        self.provider = provider_cls(config)

    # ---------- 对外 ----------

    def chat(self, messages, *, stream=False, **kwargs):
        """对话。stream=True 时返回生成器，否则返回完整文本"""
        if stream:
            return self._stream_with_retry(messages, **kwargs)
        return self._call_with_retry('chat', messages, **kwargs)

    def chat_text(self, prompt, **kwargs):
        """单轮文本对话的便捷入口"""
        return self.chat([{'role': 'user', 'content': prompt}], **kwargs)

    # ---------- 重试逻辑 ----------

    def _call_with_retry(self, method, *args, **kwargs):
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return getattr(self.provider, method)(*args, **kwargs)
            except (LLMTimeoutError, LLMConnectionError) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    logger.warning('%s 第 %d 次调用失败，%.1fs 后重试: %s',
                                   self.provider_name, attempt + 1, wait, e)
                    time.sleep(wait)
            except LLMError:
                raise       # 配置/响应错误不重试
        raise last_error

    def _stream_with_retry(self, messages, **kwargs):
        """流式：仅在建立连接阶段重试（一旦开始产出数据就不再重试）"""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                yield from self.provider.stream(messages, **kwargs)
                return
            except (LLMTimeoutError, LLMConnectionError) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    logger.warning('%s 流式第 %d 次失败，%.1fs 后重试: %s',
                                   self.provider_name, attempt + 1, wait, e)
                    time.sleep(wait)
            except LLMError:
                raise
        raise last_error

    # ---------- 构造 ----------

    @classmethod
    def from_settings(cls, ai_config: dict) -> 'LLMClient':
        """由 get_ai_settings() 的返回值构造

        ai_config 形如:
            {'provider': 'modelscope', 'api_key': 'ms-xxx',
             'api_url': '', 'model': 'moonshotai/Kimi-K2.5'}
        """
        provider = ai_config.get('provider') or 'local'
        return cls(provider, {
            'api_key': ai_config.get('api_key') or '',
            'api_url': ai_config.get('api_url') or '',
            'model': ai_config.get('model') or '',
        })
