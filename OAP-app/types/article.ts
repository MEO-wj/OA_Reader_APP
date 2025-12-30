export type ArticleAttachment = Record<string, string>;

export type Article = {
  id: number;
  title: string;
  unit?: string;
  link?: string;
  published_on?: string;
  created_at?: string;
  summary?: string;
  attachments?: ArticleAttachment[] | null;
};

export type ArticleDetail = Article & {
  content?: string;
};

export type RelatedArticle = {
  id: number;
  title: string;
  unit?: string;
  published_on?: string;
  similarity?: number;
  content_snippet?: string;
  summary_snippet?: string;
};

/** 新增分页响应类型 */
export type PaginatedArticlesResponse = {
  articles: Article[];
  next_before_date: string | null;
  next_before_id: number | null;
  has_more: boolean;
};
