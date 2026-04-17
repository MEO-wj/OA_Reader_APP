import type { RelatedArticle } from '@/types/article';

export type ChatMessage = {
  id: string;
  isUser: boolean;
  text: string;
  highlights?: string[];
  related?: RelatedArticle[];
  isStreaming?: boolean;
};
