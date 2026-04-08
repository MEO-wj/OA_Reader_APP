#!/usr/bin/env python3
"""验收测试独立运行脚本"""
import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.acceptance.test_acceptance import AcceptanceTestRunner


async def main():
    parser = argparse.ArgumentParser(description="验收测试运行器")
    parser.add_argument(
        "--level",
        choices=["p0", "p1", "p2", "all"],
        default="p0",
        help="测试级别（默认: p0）"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="服务地址（默认: http://localhost:8000）"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="最大并发数（默认: 4）"
    )

    args = parser.parse_args()

    print(f"🚀 启动验收测试")
    print(f"   级别: {args.level.upper()}")
    print(f"   服务: {args.url}")
    print(f"   并发: {args.concurrency}")
    print()

    runner = AcceptanceTestRunner(base_url=args.url, level=args.level)

    print(f"📋 加载测试用例: {len(runner.test_cases)} 个")
    print()

    results = await runner.run_all(max_concurrency=args.concurrency)

    # 输出摘要
    summary = results["summary"]
    print(f"✅ 测试完成")
    print(f"   总数: {summary['total']}")
    print(f"   通过: {summary['passed']}")
    print(f"   失败: {summary['failed']}")
    print(f"   耗时: {summary['duration_seconds']}s")
    print()

    # 保存结果
    filepath = runner.save_results(results)
    print(f"💾 结果已保存: {filepath}")
    print()

    # 列出失败的测试
    if summary["failed"] > 0:
        print("❌ 失败的测试:")
        for r in results["test_results"]:
            if r["status"] in ["failed", "error"]:
                print(f"   - {r['id']}: {r.get('notes', [])}")
        print()

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
