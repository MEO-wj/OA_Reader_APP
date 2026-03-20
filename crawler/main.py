"""OA系统通知爬取与邮件发送入口程序

该文件是OA系统通知处理的主入口点，负责：
1. 解析命令行参数，支持指定目标日期
2. 标准化目标日期格式
3. 创建并运行爬虫实例，抓取指定日期的OA通知
4. 处理可能的日期格式错误

使用方法：
- 直接运行：默认使用当前日期的前一天
- 指定日期：python main.py --date YYYY-MM-DD

依赖：
- crawler模块的Crawler类，用于执行实际的爬取操作
"""

from __future__ import annotations

import argparse
from datetime import datetime

from pathlib import Path
import sys

# 保证以脚本运行时也能找到 crawler 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawler import Crawler
from crawler.utils import format_date, parse_date


def _normalize_target_date(raw: str | None) -> str:
    """标准化目标日期格式
    
    该函数负责将输入的原始日期字符串标准化为YYYY-MM-DD格式，或者在未提供日期时返回当前日期。
    
    参数：
        raw: 原始日期字符串，格式为YYYY-MM-DD，或None
    
    返回：
        str: 标准化后的日期字符串，格式为YYYY-MM-DD
    
    异常：
        ValueError: 当输入的日期格式无效时抛出
    """
    if raw is None:
        return format_date(datetime.now())  # 未提供日期时返回当前日期
    try:
        parsed = parse_date(raw)  # 解析输入的日期字符串
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("日期格式必须为 YYYY-MM-DD") from exc  # 日期格式无效时抛出异常
    return format_date(parsed)  # 返回标准化后的日期字符串


def main(target_date: str | None = None) -> None:
    """主函数，执行OA通知的爬取和处理流程
    
    该函数是程序的核心执行函数，负责：
    1. 调用_normalize_target_date标准化目标日期
    2. 打印计划处理的日期信息
    3. 创建Crawler实例，传入标准化后的日期
    4. 运行爬虫实例，执行实际的爬取操作
    
    参数：
        target_date: 指定要爬取的目标日期，格式为YYYY-MM-DD，或None
    """
    date_str = _normalize_target_date(target_date)  # 标准化目标日期格式
    print(f"计划处理 {date_str} 的OA通知")  # 打印处理信息
    crawler = Crawler(target_date=date_str)  # 创建爬虫实例
    crawler.run()  # 运行爬虫，执行爬取操作


if __name__ == "__main__":
    """脚本直接运行时的入口点
    
    当直接运行该脚本时，执行以下操作：
    1. 创建命令行参数解析器
    2. 添加日期参数选项
    3. 解析命令行参数
    4. 调用main函数执行主流程
    5. 捕获并处理可能的日期格式错误
    """
    parser = argparse.ArgumentParser(description="抓取OA通知并发送邮件")  # 创建命令行参数解析器
    parser.add_argument("--date", help="指定目标日期，默认使用当前日期 (YYYY-MM-DD)")  # 添加日期参数选项
    args = parser.parse_args()  # 解析命令行参数

    try:
        main(target_date=args.date)  # 调用main函数执行主流程
    except ValueError as exc:
        print(exc)  # 捕获并处理日期格式错误
