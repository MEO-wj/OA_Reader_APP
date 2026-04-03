#!/usr/bin/env python3
"""导入技能数据到数据库。

将 skills/ 目录下的技能定义和参考资料导入到数据库中。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import Config
from src.core.db import get_pool
from src.core.skill_parser import SkillParser


DEFAULT_SKILLS_DIR = Path("skills")


async def import_skill(skill_dir: Path, parser: SkillParser) -> dict:
    """
    导入单个技能。

    Args:
        skill_dir: 技能目录路径
        parser: SkillParser 实例

    Returns:
        导入结果字典
    """
    try:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return {"status": "error", "message": f"未找到 SKILL.md: {skill_dir}"}

        # 解析 SKILL.md
        skill_info = parser.parse_file(skill_md)
        skill_name = skill_info.name

        print(f"  [解析] {skill_name}")
        print(f"    描述: {skill_info.description[:60]}...")

        # 读取 TOOLS.md（如果存在）
        tools_content = None
        tools_md = skill_dir / "TOOLS.md"
        if tools_md.exists():
            tools_content = tools_md.read_text(encoding="utf-8")
            print(f"    [TOOLS.md] 已加载 ({len(tools_content)} 字符)")

        # 构建元数据 JSON
        metadata = dict(skill_info.metadata or {})
        metadata.setdefault("name", skill_name)
        metadata.setdefault("description", skill_info.description)
        metadata.setdefault("verification_token", skill_info.verification_token)

        # 插入或更新技能记录
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO skills (name, metadata, content, tools, is_static)
                VALUES ($1, $2::jsonb, $3, $4, true)
                ON CONFLICT (name) DO UPDATE SET
                    metadata = EXCLUDED.metadata,
                    content = EXCLUDED.content,
                    tools = EXCLUDED.tools,
                    updated_at = NOW()
                RETURNING id
                """,
                skill_name,
                json.dumps(metadata),
                skill_info.content,
                tools_content,
            )
            skill_id = row["id"]

        print(f"    [数据库] 技能 ID: {skill_id}")

        # 处理 references 目录
        references_dir = skill_dir / "references"
        ref_count = 0

        if references_dir.exists() and references_dir.is_dir():
            async with pool.acquire() as conn:
                # 先删除旧的参考资料
                await conn.execute("DELETE FROM skill_references WHERE skill_id = $1", skill_id)

                # 递归扫描 references 目录
                for ref_file in references_dir.rglob("*"):
                    if ref_file.is_file():
                        # 计算相对路径作为文件名
                        rel_path = ref_file.relative_to(references_dir)
                        file_path = str(rel_path)

                        # 读取文件内容
                        try:
                            content = ref_file.read_text(encoding="utf-8")
                        except UnicodeDecodeError:
                            # 跳过二进制文件
                            continue

                        # 插入参考资料记录
                        await conn.execute(
                            """
                            INSERT INTO skill_references (skill_id, file_path, content)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (skill_id, file_path) DO UPDATE SET
                                content = EXCLUDED.content
                            """,
                            skill_id,
                            file_path,
                            content,
                        )
                        ref_count += 1

        print(f"    [参考资料] 导入 {ref_count} 个文件")

        return {
            "status": "success",
            "skill_name": skill_name,
            "skill_id": skill_id,
            "ref_count": ref_count,
        }
    except Exception as exc:
        import traceback

        return {
            "status": "error",
            "message": f"{str(exc)}\n{traceback.format_exc()}",
            "skill_dir": str(skill_dir),
        }


async def main(skills_dir: Path | None = None):
    """
    主函数：扫描 skills 目录并导入所有技能。

    Args:
        skills_dir: 技能目录路径，默认为 DEFAULT_SKILLS_DIR
    """
    skills_dir = skills_dir or DEFAULT_SKILLS_DIR

    if not skills_dir.exists():
        print(f"错误：技能目录不存在: {skills_dir}")
        return

    # 检查数据库配置
    config = Config.load()
    if not config.db_host or not config.db_name:
        print("错误：数据库配置不完整，请设置 DB_HOST, DB_NAME 等环境变量")
        return

    print(f"扫描技能目录: {skills_dir}")

    # 查找所有包含 SKILL.md 的子目录
    skill_dirs = []
    for item in skills_dir.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            skill_dirs.append(item)

    skill_dirs.sort(key=lambda p: p.name)

    if not skill_dirs:
        print("未找到任何技能（包含 SKILL.md 的目录）")
        return

    print(f"找到 {len(skill_dirs)} 个技能\n")

    parser = SkillParser()
    results = []

    for i, skill_dir in enumerate(skill_dirs, 1):
        skill_name = skill_dir.name
        print(f"[{i}/{len(skill_dirs)}] 导入: {skill_name}")

        result = await import_skill(skill_dir, parser)
        results.append(result)

        if result["status"] == "success":
            print(
                f"  成功: {result['skill_name']} (ID: {result.get('skill_id')}, "
                f"参考资料: {result.get('ref_count', 0)})"
            )
        else:
            print(f"  失败: {skill_name}\n  {result['message']}")

        print()  # 空行分隔

    # 统计结果
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = len(results) - success_count

    print("=" * 60)
    print(f"导入完成！成功: {success_count}, 失败: {error_count}")

    # 显示详细信息
    if error_count > 0:
        print("\n失败的技能:")
        for r in results:
            if r["status"] == "error":
                print(f"  - {r.get('skill_dir', 'unknown')}: {r.get('message', 'unknown error')}")


if __name__ == "__main__":
    asyncio.run(main())
