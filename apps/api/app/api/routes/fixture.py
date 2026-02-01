"""Fixture 测试接口"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import get_llm_client
from app.engine.excel_parser import ExcelParser
from app.engine.models import FileCollection, column_index_to_letter
from app.processor import ExcelProcessor, ProcessConfig, EventType
from app.services.fixture import get_fixture_service
from app.services.oss import upload_file, OSSError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fixture", tags=["fixture"])


# ============ SSE 事件辅助函数 ============


def _sse(data: Any, event: Optional[str] = None) -> ServerSentEvent:
    """创建 SSE 事件"""
    return ServerSentEvent(data=json.dumps(data, ensure_ascii=False), event=event)


def sse_meta(scenario_id: str, case_id: str, case_name: str, prompt: str) -> ServerSentEvent:
    """创建 meta 事件（测试用例元信息）"""
    return _sse(
        {
            "scenario_id": scenario_id,
            "case_id": case_id,
            "case_name": case_name,
            "prompt": prompt,
        },
        event="meta",
    )


def sse_step_running(step: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤开始事件"""
    data = {"step": step, "status": "running"}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_streaming(step: str, delta: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤流式输出事件"""
    data = {"step": step, "status": "streaming", "delta": delta}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_done(step: str, output: Any, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤完成事件"""
    data = {"step": step, "status": "done", "output": output}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_error(step: str, error: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤错误事件"""
    data = {"step": step, "status": "error", "error": error}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_complete(
    success: bool,
    errors: Optional[List[str]] = None,
    output_files: Optional[List[Dict[str, str]]] = None,
) -> ServerSentEvent:
    """
    创建完成事件

    Args:
        success: 是否成功
        errors: 错误列表
        output_files: 输出文件列表，每个元素为 {"file_id": str, "filename": str, "url": str}
    """
    data = {"success": success, "errors": errors}
    if output_files:
        data["output_files"] = output_files
    return _sse(data, event="complete")


def sse_error(message: str) -> ServerSentEvent:
    """创建错误事件"""
    return _sse({"message": message}, event="error")


# ============ 数据构建辅助函数 ============


def _dtype_to_friendly(dtype: str) -> str:
    """
    将 pandas dtype 转换为友好的类型名称

    Args:
        dtype: pandas dtype 字符串

    Returns:
        友好的类型名称：number, text, date, boolean
    """
    dtype_lower = dtype.lower()

    # 数值类型
    if any(t in dtype_lower for t in ["int", "float", "decimal"]):
        return "number"

    # 日期时间类型
    if any(t in dtype_lower for t in ["datetime", "date", "time", "timedelta"]):
        return "date"

    # 布尔类型
    if "bool" in dtype_lower:
        return "boolean"

    # 其他都视为文本
    return "text"


def _build_file_collection_info(tables: FileCollection) -> List[Dict[str, Any]]:
    """
    构建 FileCollection 的详细信息

    Args:
        tables: FileCollection 对象

    Returns:
        文件信息数组，结构如下：
        [
            {
                "file_id": "xxx",
                "filename": "orders.xlsx",
                "sheets": [
                    {
                        "name": "Sheet1",
                        "row_count": 100,
                        "columns": [
                            {"name": "订单号", "letter": "A", "type": "text"},
                            {"name": "金额", "letter": "B", "type": "number"},
                            ...
                        ]
                    }
                ]
            }
        ]
    """
    files_info = []

    for excel_file in tables:
        file_info = {
            "file_id": excel_file.file_id,
            "filename": excel_file.filename,
            "sheets": []
        }

        for sheet_name in excel_file.get_sheet_names():
            table = excel_file.get_sheet(sheet_name)
            df = table.get_data()

            columns_info = []
            for idx, col_name in enumerate(table.get_columns()):
                col_letter = column_index_to_letter(idx)
                dtype = str(df[col_name].dtype)
                friendly_type = _dtype_to_friendly(dtype)

                columns_info.append({
                    "name": col_name,
                    "letter": col_letter,
                    "type": friendly_type
                })

            sheet_info = {
                "name": sheet_name,
                "row_count": table.row_count(),
                "columns": columns_info
            }
            file_info["sheets"].append(sheet_info)

        files_info.append(file_info)

    return files_info


# ============ Helper Functions ============


async def _export_fixture_results(
    tables,
    modified_file_ids: List[str],
    scenario_id: str,
    case_id: str,
) -> List[Dict[str, str]]:
    """
    导出修改过的文件到 OSS

    Args:
        tables: FileCollection
        modified_file_ids: 被修改的文件 ID 列表
        scenario_id: 场景 ID
        case_id: 用例 ID

    Returns:
        导出文件列表，每个元素为 {"file_id": str, "filename": str, "url": str}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_files = []

    for file_id in modified_file_ids:
        try:
            # 获取文件信息
            file_info = tables.get_file_info(file_id)
            filename = file_info["filename"]

            # 导出单个文件到字节流
            excel_bytes = await asyncio.to_thread(
                tables.export_file_to_bytes, file_id
            )

            # 生成对象名称：fixture_outputs/{scenario_id}/{case_id}/{timestamp}/{filename}
            object_name = f"fixture_outputs/{scenario_id}/{case_id}/{timestamp}/{filename}"

            # 上传到 OSS
            public_url = upload_file(
                data=excel_bytes,
                object_name=object_name,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            output_files.append({
                "file_id": file_id,
                "filename": filename,
                "url": public_url,
            })

        except Exception as e:
            logger.warning(f"Export file {file_id} failed: {e}")
            # 继续处理其他文件，不中断

    return output_files


# ============ Response Models ============


class GroupResponse(BaseModel):
    """分组响应"""

    id: str
    name: str
    description: str
    scenario_count: int


class ScenarioSummary(BaseModel):
    """场景摘要"""

    id: str
    name: str
    group: str
    tags: List[str]
    case_count: int = 0


class CaseSummary(BaseModel):
    """用例摘要"""

    id: str
    name: str
    prompt: str
    tags: List[str]


class DatasetInfo(BaseModel):
    """数据集信息"""

    file: str
    description: str


class ScenarioDetail(BaseModel):
    """场景详情"""

    id: str
    name: str
    description: str
    group: str
    tags: List[str]
    datasets: List[DatasetInfo]
    cases: List[CaseSummary]


class FixtureListResponse(BaseModel):
    """Fixture 列表响应"""

    groups: List[GroupResponse]
    scenarios: List[ScenarioSummary]


# ============ API Endpoints ============


@router.get("/list", response_model=FixtureListResponse)
async def get_fixture_list():
    """
    获取所有测试用例列表

    返回分组和场景信息，用于构建测试界面。
    """
    service = get_fixture_service()

    try:
        index = service.load_index()

        # 构建分组响应
        groups = []
        for g in index.groups:
            groups.append(
                GroupResponse(
                    id=g.id,
                    name=g.name,
                    description=g.description,
                    scenario_count=len(g.scenario_ids),
                )
            )

        # 构建场景摘要
        scenarios = []
        for s in index.scenarios:
            # 加载场景以获取用例数量
            try:
                scenario = service.load_scenario(s["id"])
                case_count = len(scenario.cases)
            except Exception:
                case_count = 0

            scenarios.append(
                ScenarioSummary(
                    id=s["id"],
                    name=s["name"],
                    group=s.get("group", ""),
                    tags=s.get("tags", []),
                    case_count=case_count,
                )
            )

        return FixtureListResponse(groups=groups, scenarios=scenarios)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"获取 Fixture 列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取列表失败: {e}")


@router.get("/scenario/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario_detail(scenario_id: str):
    """
    获取场景详情

    包含数据集和用例列表。
    """
    service = get_fixture_service()

    try:
        scenario = service.load_scenario(scenario_id)

        return ScenarioDetail(
            id=scenario.id,
            name=scenario.name,
            description=scenario.description,
            group=scenario.group,
            tags=scenario.tags,
            datasets=[
                DatasetInfo(file=ds.file, description=ds.description)
                for ds in scenario.datasets
            ],
            cases=[
                CaseSummary(id=c.id, name=c.name, prompt=c.prompt, tags=c.tags) for c in scenario.cases
            ],
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"获取场景详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取详情失败: {e}")


@router.post("/run/{scenario_id}/{case_id}")
async def run_fixture_case(
    scenario_id: str,
    case_id: str,
    stream_llm: bool = Query(True, description="是否使用流式 LLM 调用"),
):
    """
    运行单个测试用例（SSE 流式响应）

    Args:
        scenario_id: 场景 ID（如 "01-titanic"）
        case_id: 用例 ID（如 "missing-value"）
        stream_llm: 是否使用流式 LLM（默认 True）

    SSE 事件协议:
    - event: meta     - 测试用例元信息
    - event: error    - 系统级错误
    - event: complete - 测试完成
    - (default)       - 步骤事件 { step, status, delta/output/error }

    步骤事件:
    - analyze: 需求分析 → { content }
    - generate: 生成操作 → { operations }
    - execute: 执行操作 → { formulas, variables, new_columns }
    """
    service = get_fixture_service()

    # 预加载场景和用例（在流之前验证）
    try:
        scenario, case = service.get_case(scenario_id, case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def stream():
        # 发送元信息
        # yield sse_meta(scenario_id, case_id, case.name, case.prompt)

        try:
            # 1. 加载数据集
            file_paths = {ds.path.stem: ds.path for ds in scenario.datasets}
            load_file_stage_id = str(uuid.uuid4())
            yield sse_step_running("load:file", load_file_stage_id)
            # 使用 asyncio.to_thread 避免阻塞事件循环，让 SSE 事件能及时发送
            tables = await asyncio.to_thread(ExcelParser.parse_multiple_files, file_paths)
            yield sse_step_done("load:file", _build_file_collection_info(tables), load_file_stage_id)

            # 2. 创建处理器
            llm_client = get_llm_client()
            processor = ExcelProcessor(llm_client)
            config = ProcessConfig(stream_llm=stream_llm)

            # 3. 执行处理并转换事件
            gen = processor.process(tables, case.prompt, config)
            _GENERATOR_DONE = object()  # 哨兵值，标记生成器结束

            def get_next_event():
                """在线程中获取下一个事件，避免阻塞事件循环"""
                try:
                    return next(gen)
                except StopIteration as e:
                    # StopIteration 不能通过 asyncio.to_thread 正常传播
                    # 返回哨兵值和结果
                    return _GENERATOR_DONE, e.value

            result = None
            while True:
                # 使用 asyncio.to_thread 避免阻塞事件循环
                event_or_done = await asyncio.to_thread(get_next_event)

                # 检查是否结束
                if isinstance(event_or_done, tuple) and event_or_done[0] is _GENERATOR_DONE:
                    result = event_or_done[1]
                    break

                event = event_or_done
                step_name = event.stage.value
                stage_id = event.stage_id

                if event.event_type == EventType.STAGE_START:
                    yield sse_step_running(step_name, stage_id)

                elif event.event_type == EventType.STAGE_STREAM:
                    yield sse_step_streaming(step_name, event.delta, stage_id)

                elif event.event_type == EventType.STAGE_DONE:
                    yield sse_step_done(step_name, event.output, stage_id)

                elif event.event_type == EventType.STAGE_ERROR:
                    yield sse_step_error(step_name, event.error, stage_id)
                    yield sse_complete(False, [event.error])
                    return

            # 4. 导出修改过的文件到 OSS
            output_files = None
            modified_file_ids = result.get_modified_file_ids()

            if modified_file_ids and result.modified_tables and not result.has_errors():
                try:
                    export_stage_id = str(uuid.uuid4())
                    yield sse_step_running("export:result", export_stage_id)
                    output_files = await _export_fixture_results(
                        result.modified_tables,
                        modified_file_ids,
                        scenario_id,
                        case_id,
                    )
                    yield sse_step_done(
                        "export:result",
                        {"file_count": len(output_files)},
                        export_stage_id,
                    )
                except OSSError as e:
                    logger.warning(f"Export fixture results to OSS failed: {e}")
                    yield sse_step_error("export:result", str(e), export_stage_id)
                except Exception as e:
                    logger.warning(f"Export fixture results failed: {e}")
                    yield sse_step_error("export:result", str(e), export_stage_id)

            # 5. 发送完成事件
            yield sse_complete(
                success=not result.has_errors(),
                errors=result.errors if result.errors else None,
                output_files=output_files if output_files else None,
            )

        except Exception as e:
            logger.exception(f"运行测试用例失败: {e}")
            yield sse_error(f"运行失败: {e}")

    return EventSourceResponse(stream())


@router.get("/cases", response_model=List[Dict[str, Any]])
async def list_all_cases(
    group: Optional[str] = Query(None, description="按分组筛选（basic/advanced/multi-table）"),
):
    """
    列出所有测试用例

    Args:
        group: 可选的分组 ID 筛选

    Returns:
        用例列表
    """
    service = get_fixture_service()

    try:
        if group:
            return service.list_cases_by_group(group)
        else:
            return service.list_all_cases()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"列出用例失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取列表失败: {e}")
