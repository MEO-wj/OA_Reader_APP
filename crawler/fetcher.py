"""OA 系统文章获取模块。

该模块负责从 OA 系统获取文章列表和详细内容，是爬虫的核心数据采集组件。
主要功能包括：
- 获取指定日期的文章列表
- 解析文章元数据（标题、发布单位、链接、发布日期）
- 获取单篇文章的详细内容
- 解析文章附件信息
- 清理和格式化 HTML 内容

使用 requests 库发送 HTTP 请求，BeautifulSoup 解析 HTML 页面。
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from crawler.models import ArticleMeta, DetailResult

# OA 系统基础 URL
BASE_URL = "http://oa.stu.edu.cn"
# 文章列表页面 URL（增量抓取）
LIST_URL = f"{BASE_URL}/login/Login.jsp?logintype=1"
# 回填分页列表接口
PAGED_LIST_URL = f"{BASE_URL}/csweb/list.jsp"
# 请求文章详情时的默认参数
DETAIL_PAYLOAD = {"pageindex": "1", "pagesize": "50", "fwdw": "-1"}


def _post(url: str, data: dict | None = None) -> str | None:
    """发送 POST 请求并返回响应内容。
    
    参数：
        url: 请求的 URL
        data: POST 请求的表单数据
        
    返回：
        str | None: 响应内容，请求失败时返回 None
    """
    try:
        resp = requests.post(url, data=data, timeout=30)
        if resp.status_code == 200:
            return resp.text
        print(f"请求失败: {url} status={resp.status_code}")
    except requests.RequestException as exc:
        print(f"请求 {url} 失败: {exc}")
    return None


def fetch_list(target_date: str) -> list[ArticleMeta]:
    """获取指定日期的文章列表。
    
    从 OA 系统获取指定日期发布的所有文章列表，并解析出文章的元数据。
    
    参数：
        target_date: 目标日期，格式为 YYYY-MM-DD
        
    返回：
        list[ArticleMeta]: 文章元数据列表
    """
    # 发送请求获取文章列表页面
    page = _post(LIST_URL, DETAIL_PAYLOAD)
    if not page:
        return []

    # 解析 HTML 页面
    soup = BeautifulSoup(page, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return []

    results: list[ArticleMeta] = []
    # 遍历所有文章行
    for row in tbody.find_all("tr", class_="datalight"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # 解析文章链接
        link_tag = cells[0].find("a")
        if not link_tag:
            continue

        # 过滤指定日期的文章
        date_str = cells[2].get_text(strip=True)
        if date_str != target_date:
            continue

        # 获取文章链接
        href = link_tag.get("href", "").strip()
        if not href:
            continue

        # 创建文章元数据对象
        results.append(
            ArticleMeta(
                title=link_tag.get("title", "").strip() or link_tag.get_text(strip=True),
                unit=cells[1].get_text(strip=True),  # 发布单位
                link=urljoin(BASE_URL, href),  # 完整文章链接
                published_on=date_str,  # 发布日期
            )
        )
    return results


def fetch_list_paged(target_date: str, page_size: int = 10) -> list[ArticleMeta]:
    """回填场景使用的分页列表抓取。

    通过分页接口遍历列表，直到命中目标日期或越过日期范围。

    参数：
        target_date: 目标日期，格式为 YYYY-MM-DD
        page_size: 每页条数

    返回：
        list[ArticleMeta]: 文章元数据列表
    """
    results: list[ArticleMeta] = []
    page_index = 1

    while True:
        payload = {
            "pageindex": str(page_index),
            "pagesize": str(page_size),
            "totalcount": "",
            "totalindex": "",
            "keyword": "",
            "fwdw": "-1",
        }
        page = _post(PAGED_LIST_URL, payload)
        if not page:
            break

        soup = BeautifulSoup(page, "html.parser")
        tbody = soup.find("tbody")
        if not tbody:
            break

        rows = tbody.find_all("tr", class_="datalight")
        if not rows:
            break

        page_dates: list[str] = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            date_str = cells[2].get_text(strip=True)
            if date_str:
                page_dates.append(date_str)
            if date_str != target_date:
                continue

            link_tag = cells[0].find("a")
            if not link_tag:
                continue
            href = link_tag.get("href", "").strip()
            if not href:
                continue

            results.append(
                ArticleMeta(
                    title=link_tag.get("title", "").strip() or link_tag.get_text(strip=True),
                    unit=cells[1].get_text(strip=True),
                    link=urljoin(BASE_URL, href),
                    published_on=date_str,
                )
            )

        # 页面日期都早于目标日期，说明已越过目标区间
        if page_dates and min(page_dates) < target_date:
            break

        page_index += 1

    return results


def _clean_text(soup: BeautifulSoup) -> str:
    """清理 HTML 内容，提取纯文本（保留自然段落）。"""
    for tag in soup(["script", "style"]):
        tag.decompose()

    container = soup.select_one("#spanContent") or soup
    body = container.find("body") if container else None
    if body:
        container = body

    for table in container.select("table.viewform"):
        table.decompose()
    for row in container.select("tr[id^=accessory_dsp_tr_]"):
        row.decompose()

    paragraphs = []
    for p in container.find_all("p"):
        if p.find("p") is not None:
            continue
        text = p.get_text(separator="\n", strip=True)
        text = text.replace("\xa0", " ").strip()
        if not text:
            continue
        if "相关附件" in text or text.startswith("附件"):
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            paragraphs.append(" ".join(lines))

    if not paragraphs:
        text = container.get_text(separator="\n")
        text = text.replace("\xa0", " ")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        paragraphs = lines

    return "\n\n".join(paragraphs)


def _parse_attachments(soup: BeautifulSoup) -> list[dict[str, str]]:
    """解析文章附件信息。
    
    参数：
        soup: BeautifulSoup 对象
        
    返回：
        list[dict[str, str]]: 附件列表，每个附件包含名称和链接
    """
    attachments: list[dict[str, str]] = []
    # 查找所有附件行
    for row in soup.select("tr[id^=accessory_dsp_tr_]"):
        tds = row.find_all("td")
        name = ""
        if len(tds) >= 2:
            name = tds[1].get_text(strip=True)

        # 查找下载按钮
        button = row.find("button", onclick=True)
        if not button:
            continue
        onclick = button.get("onclick", "")
        # 解析下载链接
        match = re.search(r"['\"](\/weaver\/weaver\.file\.FileDownload[^'\"]+)['\"]", onclick)
        if not match:
            continue
        url = urljoin(BASE_URL, match.group(1))
        attachments.append({"名称": name, "链接": url})
    return attachments


def fetch_detail(link: str) -> DetailResult:
    """获取文章详情内容和附件信息。
    
    参数：
        link: 文章详情页面的 URL
        
    返回：
        DetailResult: 文章详情结果，包含内容和附件列表
    """
    html = _post(link, DETAIL_PAYLOAD)
    if not html:
        return DetailResult("", [])

    soup = BeautifulSoup(html, "html.parser")
    # 解析附件
    attachments = _parse_attachments(soup)
    content = _clean_text(soup)

    if attachments:
        attach_lines = [f"附件: {item.get('名称','')} ({item.get('链接','')})" for item in attachments]
        content = f"{content}\n\n" + "\n".join(attach_lines)

    return DetailResult(content=content, attachments=attachments)
