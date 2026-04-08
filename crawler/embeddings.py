"""文本向量化模块。

该模块提供了文本向量化功能，使用 OpenAI 兼容的 embedding API 将文本转换为向量表示。
主要用于文章内容的向量化，以便后续进行相似性查询和语义搜索。

使用 requests 库发送 HTTP 请求到配置的 embedding API 服务。
"""

from __future__ import annotations

from typing import List, Optional

from crawler.config import Config
from crawler.utils import http_post


class Embedder:
    """向量化器类（OpenAI embeddings 兼容）。
    
    该类封装了文本向量化的功能，支持批量文本处理，使用配置的 embedding API 服务。
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        """初始化向量化器。
        
        参数：
            config: 配置对象，若为 None 则使用默认配置
        """
        self.config = config or Config()

    def embed_batch(self, texts: List[str]) -> List[List[float]] | None:
        """批量文本向量化。
        
        将输入的文本列表转换为向量列表，每个文本对应一个向量。
        
        参数：
            texts: 待向量化的文本列表
            
        返回：
            List[List[float]] | None: 向量列表，每个向量是一个浮点数列表；
                                     若配置缺失或 API 调用失败则返回 None
        """
        cfg = self.config
        # 检查配置是否完整
        if not (cfg.embed_base_url and cfg.embed_model and cfg.embed_api_key):
            print("Embedding 配置缺失，跳过向量化")
            return None

        # 准备 API 请求头和参数
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.embed_api_key}",
        }
        payload = {"model": cfg.embed_model, "input": texts}
        
        resp = http_post(cfg.embed_base_url, payload=payload, headers=headers, timeout=60)
        if resp is None:
            return None

        # 检查响应状态码
        if resp.status_code != 200:
            print(f"Embedding API 状态码异常: {resp.status_code}")
            return None

        # 解析响应数据
        data = resp.json()
        items = data.get("data") or []
        embeddings: List[List[float]] = []

        # 提取向量数据
        for entry in items:
            emb = entry.get("embedding")
            if isinstance(emb, list):
                embeddings.append(emb)

        # 验证向量数量是否与输入文本数量一致
        if len(embeddings) != len(texts):
            print("Embedding 数量与输入不一致")
            return None

        return embeddings
