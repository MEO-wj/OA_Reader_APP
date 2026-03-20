"""OA系统历史数据渐进式回填模块。

该模块实现了历史数据的渐进式回填功能，主要特点：
1. 断点续传：通过状态文件记录进度，支持中断后继续
2. 随机延迟：模拟真人访问，避免触发反爬机制
3. 批量处理：每次只处理少量日期，分散访问压力

使用方法：
    python -m crawler.backfill        # 执行回填
    python -m crawler.backfill --reset  # 重置状态（谨慎使用）

配置：
    在 crawler/.env 中配置回填参数：
    - BACKFILL_START_DATE: 起始日期
    - BACKFILL_END_DATE: 结束日期
    - BACKFILL_BATCH_SIZE: 每次爬几天
    - BACKFILL_DELAY_MIN/MAX: 详情页延迟
    - BACKFILL_DAY_DELAY_MIN/MAX: 天间延迟
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 保证以脚本运行时也能找到 crawler 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawler.config import Config
from crawler.pipeline import Crawler
from crawler.utils import format_date, parse_date, random_delay, safe_json_parse


# 状态文件名称
STATE_FILENAME = "backfill_state.json"


def date_range(start_date: str, end_date: str, reverse: bool = True) -> list[str]:
    """生成日期范围列表。

    参数：
        start_date: 起始日期，格式 YYYY-MM-DD
        end_date: 结束日期，格式 YYYY-MM-DD
        reverse: 是否倒序排列（默认True，从新到旧）

    返回：
        list[str]: 日期字符串列表，格式 YYYY-MM-DD
    """
    start = parse_date(start_date)
    end = parse_date(end_date)

    if start > end:
        raise ValueError(f"起始日期 {start_date} 不能晚于结束日期 {end_date}")

    delta = (end - start).days + 1
    dates = [format_date(start + timedelta(days=i)) for i in range(delta)]

    return dates[::-1] if reverse else dates


class BackfillState:
    """回填状态管理类。

    负责持久化和管理回填任务的进度状态。
    """

    def __init__(self, state_file: Path) -> None:
        """初始化状态管理器。

        参数：
            state_file: 状态文件路径
        """
        self.state_file = state_file
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """从文件加载状态数据。"""
        if self.state_file.exists():
            try:
                data = safe_json_parse(self.state_file.read_text(encoding="utf-8"), default={})
                self._data = data if isinstance(data, dict) else {}
            except OSError:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """保存状态数据到文件。"""
        try:
            self.state_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    @property
    def completed_dates(self) -> list[str]:
        """获取已完成日期列表。"""
        return self._data.get("completed_dates", [])

    @property
    def failed_dates(self) -> list[str]:
        """获取失败日期列表。"""
        return self._data.get("failed_dates", [])

    @property
    def total_articles(self) -> int:
        """获取已爬取文章总数。"""
        return self._data.get("total_articles", 0)

    def mark_completed(self, date: str, article_count: int = 0) -> None:
        """标记日期为已完成。

        参数：
            date: 完成的日期
            article_count: 该日期爬取的文章数
        """
        if date not in self._data.get("completed_dates", []):
            self._data.setdefault("completed_dates", []).append(date)
        self._data["total_articles"] = self._data.get("total_articles", 0) + article_count
        self._data["last_run"] = datetime.now().isoformat()
        self._save()

    def mark_failed(self, date: str) -> None:
        """标记日期为失败。

        参数：
            date: 失败的日期
        """
        if date not in self._data.get("failed_dates", []):
            self._data.setdefault("failed_dates", []).append(date)
        self._data["last_run"] = datetime.now().isoformat()
        self._save()

    def remove_from_failed(self, date: str) -> None:
        """从失败列表中移除日期（重试成功时调用）。

        参数：
            date: 要移除的日期
        """
        if date in self._data.get("failed_dates", []):
            self._data["failed_dates"].remove(date)
            self._save()

    def get_progress(self, start_date: str, end_date: str) -> dict:
        """获取回填进度信息。

        参数：
            start_date: 起始日期
            end_date: 结束日期

        返回：
            dict: 包含进度信息的字典
        """
        all_dates = date_range(start_date, end_date)
        total = len(all_dates)
        completed = len(self.completed_dates)
        failed = len(self.failed_dates)

        return {
            "status": "已完成" if completed >= total else "进行中",
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total,
            "completed_days": completed,
            "failed_days": failed,
            "progress_percent": round(completed / total * 100, 2) if total > 0 else 0,
            "total_articles": self.total_articles,
            "last_run": self._data.get("last_run"),
        }

    def reset(self) -> None:
        """重置回填状态。"""
        self._data = {}
        self._save()


class BackfillRunner:
    """回填执行器类。

    负责执行实际的回填任务，包括延迟控制和进度管理。
    """

    def __init__(self, config: Config) -> None:
        """初始化回填执行器。

        参数：
            config: 配置对象
        """
        self.config = config
        state_file = Path(__file__).resolve().parent / STATE_FILENAME
        self.state = BackfillState(state_file)

    def _random_delay(self, min_seconds: float, max_seconds: float) -> None:
        """随机延迟。

        参数：
            min_seconds: 最小延迟秒数
            max_seconds: 最大延迟秒数
        """
        if not self.config.backfill_enable_random_delay:
            return

        random_delay(
            min_seconds,
            max_seconds,
            enabled=self.config.backfill_enable_random_delay,
            msg="天间延迟",
        )

    def run(self) -> None:
        """执行回填任务。"""
        # 检查配置
        if not self.config.backfill_start_date or not self.config.backfill_end_date:
            print("❌ 回填配置未设置，请在 .env 中配置 BACKFILL_START_DATE 和 BACKFILL_END_DATE")
            return

        start_date = self.config.backfill_start_date
        end_date = self.config.backfill_end_date

        batch_size = self.config.backfill_batch_size

        # 生成所有日期列表
        all_dates = date_range(start_date, end_date, reverse=True)
        completed = set(self.state.completed_dates)

        # 获取待处理日期
        pending = [d for d in all_dates if d not in completed]
        if not pending:
            progress = self.state.get_progress(start_date, end_date)
            if progress["status"] == "已完成":
                print("✅ 回填任务已全部完成！")
                print(f"   总计爬取 {progress['total_articles']} 篇文章")
            else:
                print("ℹ️ 没有待处理的日期")
            return

        # 取一批
        batch_dates = pending[:batch_size]

        print(f"📋 本批待处理日期: {', '.join(batch_dates)}")

        progress = self.state.get_progress(start_date, end_date)
        print(f"   当前进度: {progress['progress_percent']}%")

        # 处理每个日期
        for i, date_str in enumerate(batch_dates, 1):
            print(f"\n[{i}/{len(batch_dates)}] 处理日期: {date_str}")

            try:
                # 创建爬虫实例并运行（启用延迟）
                crawler = Crawler(target_date=date_str, enable_delay=True)
                crawler.run()

                # 获取实际入库的文章数并标记完成
                article_count = crawler.get_article_count()
                self.state.mark_completed(date_str, article_count)
                self.state.remove_from_failed(date_str)

                # 天间延迟（不是最后一天）
                if i < len(batch_dates):
                    day_delay_min = self.config.backfill_day_delay_min
                    day_delay_max = self.config.backfill_day_delay_max
                    self._random_delay(day_delay_min, day_delay_max)

            except Exception as e:
                print(f"❌ 日期 {date_str} 处理失败: {e}")
                self.state.mark_failed(date_str)

        # 输出完成信息
        progress = self.state.get_progress(start_date, end_date)
        print(f"\n✅ 本批处理完成")
        print(f"   当前进度: {progress['progress_percent']}%")
        print(f"   已完成: {progress['completed_days']}/{progress['total_days']} 天")
        if progress['failed_days'] > 0:
            print(f"   失败: {progress['failed_days']} 天")

    def status(self) -> None:
        """显示回填状态。"""
        if not self.config.backfill_start_date or not self.config.backfill_end_date:
            print("回填配置未设置，请在 .env 中配置 BACKFILL_START_DATE 和 BACKFILL_END_DATE")
            return

        progress = self.state.get_progress(
            self.config.backfill_start_date,
            self.config.backfill_end_date
        )

        print("📊 回填进度状态:")
        print(f"   状态: {progress['status']}")
        print(f"   日期范围: {progress['start_date']} 至 {progress['end_date']}")
        print(f"   完成进度: {progress['completed_days']}/{progress['total_days']} 天 ({progress['progress_percent']}%)")
        print(f"   已爬取文章: {progress['total_articles']} 篇")

        if progress['failed_days'] > 0:
            print(f"   失败日期: {', '.join(self.state.failed_dates)}")

        if progress['last_run']:
            print(f"   上次运行: {progress['last_run']}")

    def reset(self) -> None:
        """重置回填状态。"""
        self.state.reset()
        print("✅ 回填状态已重置")


def main() -> None:
    """主函数入口。"""
    parser = argparse.ArgumentParser(description="OA系统历史数据渐进式回填工具")
    parser.add_argument("--reset", action="store_true", help="重置回填状态（谨慎使用）")
    parser.add_argument("--status", action="store_true", help="查看回填状态")

    args = parser.parse_args()

    config = Config()
    runner = BackfillRunner(config)

    if args.reset:
        runner.reset()
    elif args.status:
        runner.status()
    else:
        runner.run()


if __name__ == "__main__":
    main()
