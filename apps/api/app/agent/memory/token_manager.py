"""TokenManager — 管理对话历史的 token 计数和截断"""

import logging
from typing import List

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

# 模型 → tiktoken encoding name 映射
MODEL_ENCODING_MAP = {
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "deepseek-v3": "cl100k_base",
    "deepseek-chat": "cl100k_base",
    "default": "cl100k_base",
}

_tiktoken_initialized = False
_tiktoken = None


def _get_tiktoken():
    global _tiktoken, _tiktoken_initialized
    if not _tiktoken_initialized:
        try:
            import tiktoken
            _tiktoken = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"tiktoken 初始化失败: {e}，使用朴素截断")
            _tiktoken = None
        _tiktoken_initialized = True
    return _tiktoken


def _count_tokens_text(text: str, encoding) -> int:
    """对单段文本计数 token（tiktoken 方式）"""
    return len(encoding.encode(text))


class TokenManager:
    """
    管理对话历史的 token 数量，自动截断超长历史。
    支持任意 model_id，自动选择对应 tiktoken encoding。
    """

    def __init__(self, model_id: str = "default", max_tokens: int = 16000):
        encoding_name = MODEL_ENCODING_MAP.get(model_id, MODEL_ENCODING_MAP["default"])
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"tiktoken encoding '{encoding_name}' 初始化失败: {e}，使用朴素截断")
            self._encoding = None
        self._max_tokens = max_tokens

    def count_tokens(self, messages: List[BaseMessage]) -> int:
        if self._encoding is None:
            # 朴素截断：按字符数估算（1 token ≈ 4 字符）
            return sum(len((m.content or "")) // 4 for m in messages)
        return sum(
            len(self._encoding.encode(m.content or ""))
            for m in messages
        )

    def truncate_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """从最旧的消息开始截断，确保 total <= max_tokens"""
        if self._encoding is None:
            return self._truncate_naive(messages)

        result: List[BaseMessage] = []
        total = 0
        # 从最新到最旧遍历
        for msg in reversed(list(messages)):
            content = msg.content or ""
            tokens = len(self._encoding.encode(content))
            if total + tokens <= self._max_tokens:
                result.insert(0, msg)
                total += tokens
            else:
                break
        return result

    def _truncate_naive(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """朴素截断（无 tiktoken 时）：按字符数估算"""
        result: List[BaseMessage] = []
        total = 0
        char_limit = self._max_tokens * 4
        for msg in reversed(list(messages)):
            content = msg.content or ""
            if total + len(content) <= char_limit:
                result.insert(0, msg)
                total += len(content)
            else:
                break
        return result
