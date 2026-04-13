"""LLM 适配层通用类型定义"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class LLMProviderConfig:
    id: Optional[UUID]
    name: str
    type: str
    base_url: Optional[str]
    api_key: Optional[str]
    capabilities: Dict[str, Any]


@dataclass
class LLMModelConfig:
    id: Optional[UUID]
    name: str
    model_id: str
    defaults: Dict[str, Any]
    limits: Dict[str, Any]


@dataclass
class LLMStageConfig:
    stage: str
    provider: LLMProviderConfig
    model: LLMModelConfig


@dataclass
class LLMRequest:
    model_id: str
    messages: List[Dict[str, str]]
    temperature: float = 0
    max_tokens: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None
    extra_params: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None


@dataclass
class LLMResponse:
    content: str
    raw: Optional[Any] = None
    usage: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class LLMStreamChunk:
    delta: str
    full_content: str
    raw: Optional[Any] = None
