tools:
  - name: search_documents
    description: |
      向量搜索相关文档，返回匹配文档的标题和摘要。

      使用场景：
      - 用户询问某个主题时，先用此工具找到相关文档
      - 获取文档 ID 和摘要，判断是否需要获取详情

      参数说明：
      - query: 搜索查询文本，描述要查找的文档主题
      - keywords: (可选) 关键词，逗号分隔，用于精确匹配
      - top_k: 返回结果数量，默认 10
      - threshold: 相似度阈值 0-1，默认 0.5
    parameters:
      type: object
      properties:
        query:
          type: string
          description: 搜索查询文本
        keywords:
          type: string
          description: 关键词，逗号分隔，如 "合同,违约,赔偿"
        top_k:
          type: integer
          description: 返回结果数量，默认 10
        threshold:
          type: number
          description: 相似度阈值，默认 0.5
      required:
        - query
    handler: document_retrieval.search_documents

  - name: grep_document
    description: |
      获取指定文档的具体内容。支持多种搜索模式。

      搜索模式：
      - auto: 自动检测（根据参数选择）
      - summary: 返回文档前500字摘要
      - keyword: 关键词精确匹配（返回包含关键词的段落）
      - regex: 正则表达式匹配（适用于多种表述）
      - section: 按章节标题提取
      - line_range: 精确行范围

      返回格式：
      - status: success / not_found / error
      - data.title: 文档标题
      - data.matches: 匹配结果列表，每个包含 content, line_number, context_before, context_after, highlight_ranges
      - metadata: total_matches, search_mode

      使用建议：
      - 获取详情：mode="summary"
      - 查找具体条款：mode="keyword" + context_lines=2
      - 查找多种表述：mode="regex"
    parameters:
      type: object
      properties:
        document_id:
          type: integer
          description: 文档 ID（从 search_documents 返回结果中获取）
        keyword:
          type: string
          description: 关键词（mode="keyword" 时使用）
        section:
          type: string
          description: 章节标题（mode="section" 时使用）
        mode:
          type: string
          description: 搜索模式
          enum: ["auto", "summary", "keyword", "regex", "section", "line_range"]
          default: "auto"
        context_lines:
          type: integer
          description: 上下文行数，默认 0
        max_results:
          type: integer
          description: 最大结果数，默认 3
        pattern:
          type: string
          description: 正则表达式（mode="regex" 时使用）
        start_line:
          type: integer
          description: 起始行号（mode="line_range" 时使用）
        end_line:
          type: integer
          description: 结束行号（mode="line_range" 时使用）
      required:
        - document_id
    handler: document_retrieval.grep_document

  - name: grep_documents
    description: |
      跨多个文档搜索内容。用于对比多个文档的同一主题。

      使用场景：
      - 对比多个方案在交付条款上的差异
      - 查找多个文档中关于责任边界的描述
    parameters:
      type: object
      properties:
        document_ids:
          type: array
          items:
            type: integer
          description: 文档 ID 列表
        keyword:
          type: string
          description: 关键词
        section:
          type: string
          description: 章节标题
        mode:
          type: string
          description: 搜索模式，默认 "auto"
          enum: ["auto", "keyword", "section", "regex"]
        context_lines:
          type: integer
          description: 上下文行数
        max_results:
          type: integer
          description: 每个文档的最大结果数
        pattern:
          type: string
          description: 正则表达式（mode="regex" 时使用）
      required:
        - document_ids
    handler: document_retrieval.grep_documents
