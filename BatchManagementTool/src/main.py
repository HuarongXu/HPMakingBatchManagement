"""
main.py

项目主入口文件。
负责编排整个数据处理、逻辑计算和报告生成的流程。
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

# 将src目录添加到Python路径，以便导入其他模块
sys.path.append(str(Path(__file__).parent.absolute()))

from data_loader import get_all_data
from logic import process_logic
from report import generate_report


def run_analysis(target_date: Optional[str] = None):
    """
    执行完整分析流程
    """
    print("======================================")
    print("=  生产计划管理工具 v0.1 (开发中)  =")
    print("======================================")
    
    # --- 第一阶段：加载数据 ---
    if target_date:
        print(f"\n--- 阶段1: 加载数据 (指定日期: {target_date}) ---")
    else:
        print("\n--- 阶段1: 加载数据 ---")
    all_data = get_all_data(target_date=target_date)
    
    if not all_data:
        print("\n数据加载失败，程序终止。请检查文件路径和格式。")
        return

    print("\n所有必需的数据文件已成功加载。")
    
    # --- 第二阶段：核心逻辑 ---
    print("\n--- 阶段2: 核心逻辑 ---")
    # 调用 logic.py 中的函数来处理数据
    processed_orders, batches, alerts = process_logic(all_data)
    
    # --- 第三阶段：生成报告 (待开发) ---
    print("\n--- 阶段3: 生成报告 ---")
    report_path = generate_report(processed_orders, batches, alerts)
    print(f"报告已生成: {report_path}")
    
    print("\n======================================")
    print("=           分析流程结束           =")
    print("======================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生产计划管理工具")
    parser.add_argument(
        "--date",
        "-d",
        help="指定要加载的数据日期，例如 2026/01/19 或 20260119。"
    )
    args = parser.parse_args()
    run_analysis(target_date=args.date)
