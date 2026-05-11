"""
data_loader.py

负责加载、清洗和预处理所有输入数据。
"""
import io
import re
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import pandas as pd
from pathlib import Path

# 定义数据文件路径
DATA_DIR = Path(__file__).parent.parent / 'data'
_PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_BASE_DIR = _PROJECT_ROOT / '1.DataBase' / 'CSV'
RAW_BASE_DIR = _PROJECT_ROOT / '1.DataBase'
PARAMETER_PATH = DATA_DIR / 'Parameter.csv'
DATA_DIRECTORIES = [path for path in [CSV_BASE_DIR, RAW_BASE_DIR] if path.exists()]
SUPPORTED_SUFFIXES = ['.csv', '.xls', '.xlsx']
DATE_INPUT_FORMATS = [
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m.%d.%Y",
]

DATE_PATTERN = re.compile(r'_(\d{8})')

ZCPRS_HEADER_KEYWORDS = ["Work Center", "Order Number", "Material"]
ZC228_HEADER_KEYWORDS = ["Matl-Comp", "MRP", "Parent"]


def _detect_text_encoding(file_path: Path) -> str:
    with file_path.open('rb') as handle:
        prefix = handle.read(4)
    if prefix.startswith(b'\xff\xfe') or prefix.startswith(b'\xfe\xff'):
        return 'utf-16'
    return 'utf-8-sig'


def _read_text_lines(file_path: Path) -> List[str]:
    encoding = _detect_text_encoding(file_path)
    with file_path.open('r', encoding=encoding, errors='ignore') as handle:
        return handle.readlines()


def _extract_table_from_lines(lines: List[str], header_keywords: Sequence[str]) -> pd.DataFrame:
    header_index = None
    for idx, raw_line in enumerate(lines):
        normalized = raw_line.strip()
        if not normalized:
            continue
        if all(keyword.lower() in normalized.lower() for keyword in header_keywords):
            header_index = idx
            break

    if header_index is None:
        raise ValueError("未能在文本内容中找到期望的表头。")

    table_lines: List[str] = []
    for raw_line in lines[header_index:]:
        if not raw_line.strip():
            continue
        table_lines.append(raw_line.lstrip('\t,'))

    if not table_lines:
        raise ValueError("文本内容不包含可读取的数据行。")

    delimiter = _infer_delimiter(table_lines[0])
    buffer = io.StringIO('\n'.join(table_lines))
    df = pd.read_csv(buffer, sep=delimiter, engine='python')
    df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed', case=False)]
    return df


def _load_text_table(file_path: Path, header_keywords: Sequence[str]) -> pd.DataFrame:
    lines = _read_text_lines(file_path)
    return _extract_table_from_lines(lines, header_keywords)


def _normalize_column_name(col: str) -> str:
    return re.sub(r"\s+", " ", col.strip().lower())


def _standardize_columns(df: pd.DataFrame, alias_map: Dict[str, str]) -> pd.DataFrame:
    renamed = df.copy()
    column_mapping: Dict[str, str] = {}
    for column in renamed.columns:
        normalized = _normalize_column_name(str(column))
        if normalized in alias_map:
            column_mapping[column] = alias_map[normalized]
        else:
            column_mapping[column] = column.strip()
    renamed.rename(columns=column_mapping, inplace=True)
    return renamed


def _drop_empty_identifier_rows(df: pd.DataFrame, identifier_cols: Sequence[str]) -> pd.DataFrame:
    filtered = df.copy()
    for col in identifier_cols:
        if col in filtered.columns:
            filtered[col] = (
                filtered[col]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )
    mask = filtered[identifier_cols[0]].astype(str).str.len() > 0
    filtered = filtered[mask]
    filtered.reset_index(drop=True, inplace=True)
    return filtered


def _infer_delimiter(line: str) -> str:
    tab_count = line.count('\t')
    comma_count = line.count(',')
    return '\t' if tab_count > comma_count else ','


def _load_dynamic_table(file_path: Path, header_keywords: Sequence[str]) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == '.csv':
        return _load_text_table(file_path, header_keywords)

    if suffix in {'.xls', '.xlsx'}:
        engine = 'xlrd' if suffix == '.xls' else 'openpyxl'
        try:
            raw_df = pd.read_excel(file_path, header=None, engine=engine)
        except Exception as exc:
            message = str(exc).lower()
            if 'unsupported format' in message or 'file format cannot be determined' in message:
                return _load_text_table(file_path, header_keywords)
            raise
        header_index = None
        for idx in range(len(raw_df)):
            row_values = [str(value).strip() for value in raw_df.iloc[idx].tolist() if not pd.isna(value)]
            normalized = ' '.join(row_values)
            if normalized and all(keyword.lower() in normalized.lower() for keyword in header_keywords):
                header_index = idx
                break

        if header_index is None:
            raise ValueError(f"未能在文件 {file_path.name} 中找到期望的表头。")

        data = raw_df.iloc[header_index:].copy()
        data.columns = data.iloc[0].fillna('').astype(str).str.strip()
        data = data[1:]
        data = data.dropna(how='all').reset_index(drop=True)
        data = data.loc[:, ~data.columns.astype(str).str.contains('^Unnamed', case=False)]
        return data

    raise ValueError(f"不支持的文件格式: {file_path.suffix}")


def _normalize_target_date(target_date: Optional[object]) -> Optional[datetime]:
    if target_date is None:
        return None
    if isinstance(target_date, datetime):
        return target_date
    text = str(target_date).strip()
    if not text:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {target_date}")


def _sort_candidate(path: Path) -> datetime:
    match = DATE_PATTERN.search(path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%m%d%Y")
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def _select_data_file(prefix: str, target_date: Optional[datetime]) -> Path:
    if not DATA_DIRECTORIES:
        raise FileNotFoundError("未找到原始数据目录，请检查 1.DataBase 路径。")

    if target_date:
        token = target_date.strftime("%m%d%Y")
        for directory in DATA_DIRECTORIES:
            for suffix in SUPPORTED_SUFFIXES:
                candidate = directory / f"{prefix}_{token}{suffix}"
                if candidate.exists():
                    _mirror_to_csv(candidate)
                    return candidate
        raise FileNotFoundError(f"未找到 {prefix}_{token}.* 数据文件，请确认文件已放置在 1.DataBase 或其 CSV 子目录中。")

    candidates: List[Path] = []
    for directory in DATA_DIRECTORIES:
        for suffix in SUPPORTED_SUFFIXES:
            candidates.extend(directory.glob(f"{prefix}_*{suffix}"))

    if not candidates:
        raise FileNotFoundError(f"在 {', '.join(str(d) for d in DATA_DIRECTORIES)} 中未找到 {prefix}_*.{{csv,xls,xlsx}} 文件。")

    candidates.sort(key=_sort_candidate)
    selected = candidates[-1]
    _mirror_to_csv(selected)
    return selected


def _mirror_to_csv(source_path: Path) -> None:
    try:
        CSV_BASE_DIR.mkdir(parents=True, exist_ok=True)
        target_path = CSV_BASE_DIR / f"{source_path.stem}.csv"
        source_mtime = source_path.stat().st_mtime
        if target_path.exists() and target_path.stat().st_mtime >= source_mtime:
            return
        suffix = source_path.suffix.lower()
        if suffix == '.csv':
            shutil.copy2(source_path, target_path)
        elif suffix in {'.xls', '.xlsx'}:
            try:
                engine = 'xlrd' if suffix == '.xls' else 'openpyxl'
                df = pd.read_excel(source_path, engine=engine)
            except Exception:
                # SAP often exports .xls as UTF-16 text; fall back to text read
                encoding = _detect_text_encoding(source_path)
                lines = source_path.read_text(encoding=encoding, errors='ignore').splitlines()
                delimiter = _infer_delimiter(lines[0]) if lines else '\t'
                # Find first non-empty line as header
                header_idx = 0
                for i, ln in enumerate(lines):
                    if ln.strip():
                        header_idx = i
                        break
                buf = io.StringIO('\n'.join(lines[header_idx:]))
                df = pd.read_csv(buf, sep=delimiter, engine='python')
            df.to_csv(target_path, index=False)
        else:
            return
        print(f"已同步 CSV 备份: {target_path.name}")
    except Exception as exc:
        print(f"警告: 无法为 {source_path.name} 生成 CSV 备份 ({exc})")
        import traceback; traceback.print_exc()


def _export_dataframe_snapshot(df: pd.DataFrame, source_path: Path) -> None:
    try:
        if df is None or df.empty:
            return
        CSV_BASE_DIR.mkdir(parents=True, exist_ok=True)
        target_path = CSV_BASE_DIR / f"{source_path.stem}.csv"
        df.to_csv(target_path, index=False)
        print(f"已生成 CSV 快照: {target_path.name}")
    except Exception as exc:
        print(f"警告: 无法写入 {source_path.stem}.csv ({exc})")


def _clean_zcprs(df: pd.DataFrame) -> pd.DataFrame:
    alias_map = {
        'plant': 'Plant',
        'work center': 'Work Center',
        'order number': 'Order Number',
        'material': 'Material',
        'description': 'Description',
        'startdate': 'StartDate',
        'start date': 'StartDate',
        'starttime': 'StartTime',
        'start time': 'StartTime',
        'enddate': 'EndDate',
        'end date': 'EndDate',
        'endtime': 'EndTime',
        'end time': 'EndTime',
        'batch #': 'Batch #',
        'batch#': 'Batch #',
        'planned quantity': 'Planned Quantity',
        'planned qty': 'Planned Quantity',
        'deliv. quantity': 'Deliv. Quantity',
        'delivery quantity': 'Deliv. Quantity',
        'actual production %': 'Actual Production %',
        'actual production%': 'Actual Production %',
        'uom': 'UoM',
        'minlotsize': 'MinLotSize',
        'min lot size': 'MinLotSize',
        'comments': 'Comments',
        'mrp element': 'Mrp Element',
        'mrp element.': 'Mrp Element'
    }

    cleaned = _standardize_columns(df, alias_map)
    required_columns = [
        'StartDate', 'StartTime', 'EndDate', 'EndTime', 'Plant', 'Work Center',
        'Material', 'Description', 'Order Number', 'Batch #', 'Mrp Element',
        'Planned Quantity', 'UoM'
    ]

    for col in required_columns:
        if col not in cleaned.columns:
            cleaned[col] = pd.NA

    cleaned = _drop_empty_identifier_rows(cleaned, ['Order Number'])

    for text_col in ['Order Number', 'Material', 'Batch #']:
        if text_col in cleaned.columns:
            cleaned[text_col] = (
                cleaned[text_col]
                .fillna('')
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )

    if 'Mrp Element' in cleaned.columns:
        cleaned['Mrp Element'] = cleaned['Mrp Element'].fillna('').astype(str).str.strip()

    def _valid_date(series: pd.Series) -> pd.Series:
        """Accept any string that looks like a date (multiple formats)."""
        s = series.fillna('').astype(str).str.strip()
        return s.str.contains(
            r'\d{1,4}[/\-.年]\d{1,2}[/\-.月]\d{1,4}',
            na=False,
        )

    cleaned = cleaned[_valid_date(cleaned['StartDate']) & _valid_date(cleaned['EndDate'])]
    cleaned.reset_index(drop=True, inplace=True)
    return cleaned


def _clean_zc228(df: pd.DataFrame) -> pd.DataFrame:
    alias_map = {
        'matl-comp': 'Matl-Comp',
        'cmrpc': 'CMRPC',
        'matl desc -comp': 'Matl Desc -Comp',
        'mrp element': 'MRP element',
        'amt reqd': 'Amt Reqd',
        'uom': 'UOM',
        'off st date': 'Off St Date',
        'off st time': 'Off St Time',
        'st time': 'St Time',
        'st date': 'St Date',
        'resource': 'Resource',
        'parent ord': 'Parent Ord'
    }

    cleaned = _standardize_columns(df, alias_map)
    required_columns = [
        'Matl-Comp', 'CMRPC', 'Matl Desc -Comp', 'MRP element', 'Amt Reqd',
        'UOM', 'Off St Date', 'Off St Time', 'St Time', 'St Date', 'Resource',
        'Parent Ord'
    ]

    for col in required_columns:
        if col not in cleaned.columns:
            cleaned[col] = pd.NA

    cleaned = _drop_empty_identifier_rows(cleaned, ['Parent Ord'])

    for text_col in ['Parent Ord', 'Matl-Comp']:
        if text_col in cleaned.columns:
            cleaned[text_col] = (
                cleaned[text_col]
                .fillna('')
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )
    return cleaned


def _clean_parameter(df: pd.DataFrame) -> pd.DataFrame:
    if 'Material' not in df.columns:
        return df
    cleaned = df.copy()
    cleaned['Material'] = (
        cleaned['Material']
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    before = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset=['Material']).reset_index(drop=True)
    if len(cleaned) != before:
        print(f"Parameter 去重: 从 {before} 行精简到 {len(cleaned)} 行。")
    return cleaned


def _resolve_parameter_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PARAMETER_PATH.exists():
        return PARAMETER_PATH

    legacy_candidates: List[Path] = [
        CSV_BASE_DIR / 'Parameter.csv',
        CSV_BASE_DIR / 'Parameter.xlsx',
    ]
    if RAW_BASE_DIR.exists():
        legacy_candidates.extend([
            RAW_BASE_DIR / 'Parameter.csv',
            RAW_BASE_DIR / 'Parameter.xlsx',
        ])

    for candidate in legacy_candidates:
        if candidate.exists():
            shutil.copy2(candidate, PARAMETER_PATH)
            print(f"Parameter 表已迁移到 {PARAMETER_PATH}")
            return PARAMETER_PATH

    raise FileNotFoundError("未找到 Parameter.csv 或 Parameter.xlsx，请将文件放入 data 目录或 1.DataBase 中。")

def load_data(file_path: Path) -> pd.DataFrame:
    """通用数据加载函数，支持csv和excel。"""
    print(f"正在加载文件: {file_path.name}...")
    if not file_path.exists():
        raise FileNotFoundError(f"错误：数据文件不存在 -> {file_path}")
    
    if file_path.suffix == '.csv':
        return pd.read_csv(file_path)
    elif file_path.suffix in ['.xlsx', '.xls']:
        # 假设数据在第一个sheet
        return pd.read_excel(file_path, engine='openpyxl' if file_path.suffix == '.xlsx' else 'xlrd')
    else:
        raise ValueError(f"不支持的文件格式: {file_path.suffix}")

def get_all_data(target_date: Optional[object] = None):
    """加载所有需要的数据文件。"""

    try:
        normalized_date = _normalize_target_date(target_date)
        if normalized_date:
            print(f"指定日期: {normalized_date.strftime('%Y-%m-%d')}，尝试加载对应数据文件。")
        else:
            print("未指定日期，加载最新可用数据文件。")

        zcprs_path = _select_data_file('ZCPRS', normalized_date)
        zcprs_raw = _load_dynamic_table(zcprs_path, ZCPRS_HEADER_KEYWORDS)
        zcprs_df = _clean_zcprs(zcprs_raw)
        _export_dataframe_snapshot(zcprs_df, zcprs_path)

        zc228_path = _select_data_file('ZC228', normalized_date)
        zc228_raw = _load_dynamic_table(zc228_path, ZC228_HEADER_KEYWORDS)
        zc228_df = _clean_zc228(zc228_raw)
        _export_dataframe_snapshot(zc228_df, zc228_path)

        parameter_path = _resolve_parameter_path()
        parameter_df = load_data(parameter_path)
        parameter_df = _clean_parameter(parameter_df)
        
        # Making Capacity 和 12t_to_6t 可能是Excel或CSV，这里假设它们在data目录下
        making_capacity_path = DATA_DIR / 'Making Capacity.xlsx'
        conversion_list_path = DATA_DIR / '12t_to_6t_conversion_list.xlsx'

        making_capacity_df = load_data(making_capacity_path)
        conversion_df = load_data(conversion_list_path)
        
        print("\n数据加载初步完成。")
        print(f"ZCPRS 文件: {zcprs_path.name}, 列名:", zcprs_df.columns.tolist())
        print(f"ZC228 文件: {zc228_path.name}, 列名:", zc228_df.columns.tolist())
        print("Parameter 列名:", parameter_df.columns.tolist())
        print("Making Capacity 列名:", making_capacity_df.columns.tolist())
        print("Conversion List 列名:", conversion_df.columns.tolist())

        # 返回已加载的数据帧
        return {
            "zcprs": zcprs_df,
            "zc228": zc228_df,
            "parameter": parameter_df,
            "making_capacity": making_capacity_df,
            "conversion": conversion_df
        }

    except FileNotFoundError as e:
        print(f"\n文件加载失败: {e}")
        print("请确保以下文件存在于 'c:/0.Local/12.HP Making Batch management tool/1.DataBase/' 目录或其 CSV 子目录中:")
        print("- ZCPRS_*.csv/.xls/.xlsx")
        print("- ZC228_*.csv/.xls/.xlsx")
        print("- Parameter.csv")
        print("\n并且 'Making Capacity.xlsx' 和 '12t_to_6t_conversion_list.xlsx' 文件需要被放入 'BatchManagementTool/data' 目录。")
        return None
    except Exception as e:
        print(f"加载数据时发生未知错误: {e}")
        return None

if __name__ == '__main__':
    print("--- 测试数据加载模块 ---")
    all_data = get_all_data()
    if all_data:
        print("\n成功加载了以下数据表:")
        for name, df in all_data.items():
            print(f"- {name}: {df.shape[0]} 行, {df.shape[1]} 列")
    else:
        print("\n数据加载测试失败。")
