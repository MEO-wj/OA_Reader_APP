tools:
  - name: search_articles
    description: |
      向量搜索相关文章，返回匹配文章的标题、发布单位和摘要。

      使用场景：
      - 用户询问某个主题时，先用此工具找到相关文章
      - 获取文章 ID 和摘要，判断是否需要获取详情
      - 用户查询某个时间段的通知时，使用日期范围筛选

      当 query 为空时，仅按日期范围筛选文章（需提供 start_date 或 end_date）。
    parameters:
      type: object
      properties:
        query:
          type: string
          description: 搜索查询文本，可选。为空时仅按日期范围筛选文章。
        keywords:
          type: string
          description: 关键词，逗号分隔，如 "考试,安排,期末"
        start_date:
          type: string
          description: 起始日期，格式 YYYY-MM-DD，如 "2025-03-01"
        end_date:
          type: string
          description: 结束日期，格式 YYYY-MM-DD，如 "2025-03-31"
        top_k:
          type: integer
          description: 返回结果数量，默认 10
        threshold:
          type: number
          description: 相似度阈值，默认 0.5
      required: []
    handler: article_retrieval.search_articles

  - name: grep_article
    description: |
      获取指定文章的具体内容。支持多种搜索模式。

      搜索模式：
      - auto: 自动检测（根据参数选择）
      - summary: 返回文章前500字摘要
      - keyword: 关键词精确匹配
      - regex: 正则表达式匹配
      - section: 按章节标题提取
      - line_range: 精确行范围
    parameters:
      type: object
      properties:
        article_id:
          type: integer
          description: 文章 ID（从 search_articles 返回结果中获取）
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
        - article_id
    handler: article_retrieval.grep_article

  - name: grep_articles
    description: |
      跨多个文章搜索内容。用于对比多篇文章的同一主题。
    parameters:
      type: object
      properties:
        article_ids:
          type: array
          items:
            type: integer
          description: 文章 ID 列表
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
          description: 每篇文章的最大结果数
        pattern:
          type: string
          description: 正则表达式（mode="regex" 时使用）
      required:
        - article_ids
    handler: article_retrieval.grep_articles
