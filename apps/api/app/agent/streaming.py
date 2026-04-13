"""SSE 事件数据结构"""

from dataclasses import dataclass


@dataclass
class StreamEvent:
    """
    SSE 事件数据结构。

    事件类型：
      session     { thread_id: str, is_new: bool }
      tool_start  { tool: str, args: dict }
      tool_stream { tool: str, delta: str, partial: str }
      tool_end    { tool: str, observation: str, data: dict }
      agent_end   { response: str }
      error       { message: str }
      complete    { status: str }
    """

    event: str
    data: dict
