"""LLM Excel 数据处理系统 - 主入口"""

import sys
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv

from app.engine.models import FileCollection
from app.engine.excel_parser import ExcelParser
from app.engine.llm_client import LLMClient
from app.engine.executor import execute_operations
from app.engine.excel_generator import generate_formulas, format_formula_output


def load_excel_files(file_paths: List[str]) -> FileCollection:
    """
    加载 Excel 文件

    Args:
        file_paths: Excel 文件路径列表

    Returns:
        FileCollection 对象
    """
    collection = FileCollection()

    for file_path in file_paths:
        file_path = Path(file_path)

        if not file_path.exists():
            print(f"⚠️  文件不存在: {file_path}")
            continue

        try:
            print(f"\n📄 文件: {file_path.name}")
            file_info = ExcelParser.get_file_info(file_path)

            # 使用文件名作为 file_id（简化 CLI）
            file_id = file_path.stem

            if len(file_info['sheets']) > 1:
                print(f"   包含 {len(file_info['sheets'])} 个 sheet:")
                for sheet_name, info in file_info['sheets'].items():
                    print(f"   - {sheet_name}: {info['rows']} 行 x {info['columns']} 列")
            else:
                sheet_name = list(file_info['sheets'].keys())[0]
                info = file_info['sheets'][sheet_name]
                print(f"   {info['rows']} 行 x {info['columns']} 列")

            # 解析整个文件（包含所有 sheets）
            file_collection = ExcelParser.parse_file_all_sheets(file_path, file_id=file_id)

            # 添加到总集合
            for excel_file in file_collection:
                collection.add_file(excel_file)

            print(f"   ✅ 解析成功")

        except Exception as e:
            print(f"   ❌ 解析失败: {e}")

    return collection


def display_schemas(tables: FileCollection):
    """显示表结构（两层）"""
    print("\n" + "=" * 60)
    print("📊 已加载的文件和 Sheet:")
    print("=" * 60)

    schemas = tables.get_schemas()
    for file_id, file_sheets in schemas.items():
        excel_file = tables.get_file(file_id)
        print(f"\n文件: {excel_file.filename} (ID: {file_id})")
        for sheet_name, columns in file_sheets.items():
            print(f"  Sheet: {sheet_name}")
            column_display = ", ".join([
                f"{col_letter}({col_name})"
                for col_letter, col_name in columns.items()
            ])
            print(f"    字段: {column_display}")


def process_requirement_two_step(
    requirement: str,
    tables: FileCollection,
    llm_client: LLMClient
):
    """
    两步流程处理用户需求

    第一步：需求分析
    第二步：生成操作描述
    """
    schemas = tables.get_schemas()

    # 构建 file_sheets 映射
    file_sheets = {}
    for file_id in tables.get_file_ids():
        excel_file = tables.get_file(file_id)
        file_sheets[file_id] = excel_file.get_sheet_names()

    # ==================== 第一步：需求分析 ====================
    print("\n" + "=" * 60)
    print("🔍 第一步：需求分析")
    print("=" * 60)

    try:
        analysis = llm_client.analyze_requirement(requirement, schemas)
        print("\n" + analysis)
    except Exception as e:
        print(f"\n❌ 需求分析失败: {e}")
        return

    # 用户确认
    print("\n" + "-" * 60)
    confirm = input("📋 以上分析是否正确？(y/n/修改建议): ").strip()

    if confirm.lower() == 'n':
        print("❌ 已取消")
        return
    elif confirm.lower() != 'y' and confirm:
        # 用户提供了修改建议，追加到分析结果
        analysis = analysis + f"\n\n用户补充：{confirm}"
        print(f"✅ 已添加补充说明")

    # ==================== 第二步：生成操作描述 ====================
    print("\n" + "=" * 60)
    print("⚙️  第二步：生成操作描述")
    print("=" * 60)

    try:
        json_str = llm_client.generate_operations(requirement, analysis, schemas)

        print("\n📝 生成的 JSON:")
        print("-" * 40)
        try:
            formatted_json = json.dumps(
                json.loads(json_str), indent=2, ensure_ascii=False
            )
            print(formatted_json)
        except json.JSONDecodeError:
            print(json_str)
        print("-" * 40)

    except Exception as e:
        print(f"\n❌ 生成操作描述失败: {e}")
        return

    # 解析和验证
    from app.engine.parser import parse_and_validate
    operations, parse_errors = parse_and_validate(json_str, file_sheets)

    if parse_errors:
        print("\n⚠️  解析错误:")
        for error in parse_errors:
            print(f"   - {error}")
        return

    # ==================== 第三步：执行操作 ====================
    print("\n" + "=" * 60)
    print("🚀 第三步：执行操作")
    print("=" * 60)

    try:
        result = execute_operations(operations, tables)

        if result.variables:
            print("\n📊 计算结果:")
            for var_name, value in result.variables.items():
                print(f"   {var_name} = {value}")

        if result.new_columns:
            print("\n📋 新增列（三层结构）:")
            for file_id, sheets in result.new_columns.items():
                excel_file = tables.get_file(file_id)
                print(f"   文件: {excel_file.filename}")
                for sheet_name, columns in sheets.items():
                    print(f"     Sheet: {sheet_name}")
                    for col_name, values in columns.items():
                        preview = values[:5] if len(values) > 5 else values
                        print(f"       {col_name}: {preview}...")

        if result.errors:
            print("\n⚠️  执行错误:")
            for error in result.errors:
                print(f"   - {error}")

    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        return

    # ==================== 第四步：生成 Excel 公式 ====================
    print("\n" + "=" * 60)
    print("📝 第四步：Excel 复现公式")
    print("=" * 60)

    try:
        formula_results = generate_formulas(operations, tables)
        output = format_formula_output(formula_results)
        print(output)
    except Exception as e:
        print(f"\n❌ 公式生成失败: {e}")

    # ==================== 第五步：导出结果 ====================
    if result.new_columns and not result.has_errors():
        print("\n" + "=" * 60)
        print("💾 第五步：导出结果")
        print("=" * 60)

        # 将新增列应用到表中（三层结构）
        tables.apply_new_columns(result.new_columns)

        # 生成输出文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"output_{timestamp}.xlsx"

        try:
            tables.export_to_excel(output_file)
            print(f"\n✅ 已导出到: {output_file}")

            # 显示导出的文件和 sheet
            for file_id, sheets in result.new_columns.items():
                excel_file = tables.get_file(file_id)
                print(f"   文件: {excel_file.filename}")
                for sheet_name in sheets.keys():
                    table = tables.get_table(file_id, sheet_name)
                    print(f"     - {sheet_name}: {table.row_count()} 行 x {len(table.get_columns())} 列")
        except Exception as e:
            print(f"\n❌ 导出失败: {e}")


def main():
    """主函数"""
    load_dotenv()

    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print("LLM Excel 数据处理系统 V2\n")
        print("用法:")
        print("  python main.py <excel_file1> [excel_file2] ...")
        print("  python main.py --help")
        print("\n示例:")
        print("  python main.py data/orders.xlsx")
        print("  python main.py data/orders.xlsx data/customers.xlsx")
        print("\n环境变量:")
        print("  OPENAI_API_KEY    - OpenAI API Key（必需）")
        print("  OPENAI_BASE_URL   - API Base URL（可选）")
        print("  OPENAI_MODEL      - 模型名称（默认: gpt-4）")
        return

    # 加载 Excel 文件
    excel_files = sys.argv[1:]
    print("=" * 60)
    print("📂 正在加载 Excel 文件...")
    print("=" * 60)

    tables = load_excel_files(excel_files)

    if not tables.get_file_ids():
        print("\n⚠️  没有成功加载任何文件")
        return

    display_schemas(tables)

    # 初始化 LLM 客户端
    llm_client = None
    try:
        llm_client = LLMClient()
        print(f"\n✅ LLM 客户端已初始化")
        print(f"   模型: {llm_client.model}")
    except ValueError as e:
        print(f"\n⚠️  LLM 客户端初始化失败: {e}")
        print("   将无法使用 LLM 生成操作描述")
        return

    # 示例需求
    requirement = """
    贴现发生额明细（简称 S1）、卖断发生额明细（简称 S2）
根据“票据（包）号”和“子票区间”两个字段进行匹配（两张表中同时相同的），在 S1 和 S2 中获得票据唯一匹配值 P1、P2；
将 S1 中的 P1 与 S2 中的 P2 进行匹配，确认是否有相同项，如有，则该匹配值 P1 对应的票据已完成了卖断。
输出新表，S1 + 新字段（卖断： 已卖断/未卖断）
    """.strip()

    print("\n" + "=" * 60)
    print("📋 用户需求:")
    print("=" * 60)
    print(requirement)

    # 使用两步流程处理
    process_requirement_two_step(requirement, tables, llm_client)


if __name__ == "__main__":
    main()
