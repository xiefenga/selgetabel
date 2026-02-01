"""线程相关服务"""

from typing import Optional
from app.engine.llm_client import LLMClient


def generate_thread_title(query: str, llm_client: LLMClient) -> Optional[str]:
    """
    根据用户查询内容生成线程标题

    Args:
        query: 用户查询内容
        llm_client: LLM 客户端实例

    Returns:
        生成的标题，如果生成失败则返回 None
    """
    if not query or not query.strip():
        return None

    # 系统提示词：要求生成简洁的标题
    system_prompt = """你是一个专业的标题生成助手。根据用户的查询内容，生成一个简洁、准确的标题。

要求：
1. 标题应该简洁明了，不超过20个字符
2. 标题应该准确反映用户查询的核心内容
3. 只返回标题文本，不要包含任何其他说明或标记
4. 如果查询内容过于简短或无法理解，可以返回查询内容的前20个字符

示例：
- 查询："计算所有订单的总金额" -> 标题："计算订单总金额"
- 查询："统计每个产品的销售数量" -> 标题："统计产品销售数量"
- 查询："筛选出价格大于100的商品" -> 标题："筛选高价商品"
"""

    try:
        # 调用 LLM 生成标题
        title = llm_client._call_llm(system_prompt, query)

        # 清理标题：去除可能的引号、换行等
        title = title.strip().strip('"').strip("'").strip()

        # 限制长度
        if len(title) > 30:
            title = title[:30]

        return title if title else query
    except Exception as e:
        # 如果 LLM 调用失败，返回 None，不影响主流程
        print(e)
        return query
