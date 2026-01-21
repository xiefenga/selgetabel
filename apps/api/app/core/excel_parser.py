"""Excel 解析器 - 负责读取 Excel 文件并转换为系统内部数据结构"""

from pathlib import Path
from typing import Union, List, Dict
import pandas as pd
from app.core.models import Table, TableCollection


class ExcelParser:
    """Excel 文件解析器"""

    @staticmethod
    def parse_file(file_path: Union[str, Path], table_name: str = None) -> Table:
        """
        解析单个 Excel 文件

        Args:
            file_path: Excel 文件路径
            table_name: 表名（如果为 None，则使用文件名）

        Returns:
            Table 对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式不支持
        """
        file_path = Path(file_path)

        # 检查文件是否存在
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 检查文件扩展名
        if file_path.suffix.lower() not in ['.xlsx', '.xls', '.xlsm']:
            raise ValueError(f"不支持的文件格式: {file_path.suffix}")

        # 确定表名
        if table_name is None:
            table_name = file_path.stem  # 使用文件名（不含扩展名）

        # 读取 Excel 文件（读取第一个 sheet）
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
        except Exception as e:
            raise ValueError(f"读取 Excel 文件失败: {str(e)}") from e

        # 数据清洗
        df = ExcelParser._clean_dataframe(df)

        # 创建 Table 对象
        return Table(name=table_name, data=df)

    @staticmethod
    def parse_file_all_sheets(
        file_path: Union[str, Path],
        sheet_names: List[str] = None
    ) -> TableCollection:
        """
        解析 Excel 文件的所有（或指定）sheet

        Args:
            file_path: Excel 文件路径
            sheet_names: 要解析的 sheet 名称列表（None 表示全部）

        Returns:
            TableCollection 对象
        """
        file_path = Path(file_path)

        # 检查文件是否存在
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 读取所有 sheets
        try:
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
            all_sheet_names = excel_file.sheet_names
        except Exception as e:
            raise ValueError(f"读取 Excel 文件失败: {str(e)}") from e

        # 确定要解析的 sheets
        if sheet_names is None:
            sheets_to_parse = all_sheet_names
        else:
            # 验证 sheet 名称是否存在
            invalid_sheets = set(sheet_names) - set(all_sheet_names)
            if invalid_sheets:
                raise ValueError(f"Sheet 不存在: {', '.join(invalid_sheets)}")
            sheets_to_parse = sheet_names

        # 创建表集合
        collection = TableCollection()

        # 解析每个 sheet
        for sheet_name in sheets_to_parse:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
            df = ExcelParser._clean_dataframe(df)

            # 使用 sheet 名称作为表名
            table = Table(name=sheet_name, data=df)
            collection.add_table(table)

        return collection

    @staticmethod
    def parse_multiple_files(
        file_paths: Dict[str, Union[str, Path]]
    ) -> TableCollection:
        """
        解析多个 Excel 文件

        Args:
            file_paths: 字典，格式：{"表名": "文件路径"}

        Returns:
            TableCollection 对象
        """
        collection = TableCollection()

        for table_name, file_path in file_paths.items():
            table = ExcelParser.parse_file(file_path, table_name)
            collection.add_table(table)

        return collection

    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗 DataFrame 数据

        - 处理空值
        - 标准化列名
        - 处理数据类型
        """
        # 标准化列名（去除空格，转为小写）
        df.columns = [str(col).strip() for col in df.columns]

        # 删除完全空的行
        df = df.dropna(how='all')

        # 重置索引
        df = df.reset_index(drop=True)

        # 处理 NaN 值（保留为 None）
        df = df.where(pd.notna(df), None)

        return df

    @staticmethod
    def get_file_info(file_path: Union[str, Path]) -> Dict:
        """
        获取 Excel 文件信息

        Args:
            file_path: Excel 文件路径

        Returns:
            文件信息字典
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')

            sheets_info = {}
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
                sheets_info[sheet_name] = {
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": list(df.columns)
                }

            return {
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size,
                "sheets": sheets_info
            }
        except Exception as e:
            raise ValueError(f"读取文件信息失败: {str(e)}") from e

