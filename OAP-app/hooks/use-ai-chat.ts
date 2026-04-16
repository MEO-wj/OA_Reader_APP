import { useCallback, useEffect, useRef, useState } from 'react';

import type { RelatedArticle } from '@/types/article';
import { chatSSE, clearAiMemory } from '@/services/ai';
import { clearChatHistory, getChatHistory, setChatHistory } from '@/storage/chat-storage';
import type { ChatMessage } from '@/types/chat';
import { extractKeywords } from '@/utils/text';

export function useAiChat(token?: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [conversationId, setConversationId] = useState<string>();
  const abortRef = useRef(false);

  useEffect(() => {
    let mounted = true;
    getChatHistory().then((history) => {
      if (!mounted) return;
      if (history && history.length > 0) setMessages(history);
      setIsHydrated(true);
    });
    return () => {
      mounted = false;
      abortRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    void setChatHistory(messages);
  }, [isHydrated, messages]);

  const setMessageText = useCallback((id: string, text: string) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, text } : item)));
  }, []);

  const updateRelated = useCallback((id: string, related: RelatedArticle[]) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, related } : item)));
  }, []);

  const setStreaming = useCallback((id: string, isStreaming: boolean) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, isStreaming } : item)));
  }, []);

  const sendChat = useCallback(
    async (question: string) => {
      if (!question.trim() || isThinking) return;
      const highlights = extractKeywords(question);

      const userMessage: ChatMessage = {
        id: `u-${Date.now()}`,
        isUser: true,
        text: question,
      };
      const aiMessageId = `a-${Date.now()}`;
      const aiMessage: ChatMessage = {
        id: aiMessageId,
        isUser: false,
        text: '',
        isStreaming: true,
        highlights,
      };
      setMessages((prev) => [...prev, userMessage, aiMessage]);
      setIsThinking(true);
      abortRef.current = false;

      let fullText = '';
      let relatedArticles: RelatedArticle[] = [];

      await chatSSE(
        question,
        token || '',
        (event) => {
          if (abortRef.current) return;

          if (event.type === 'start') {
            const convId = (event as { conversation_id?: string }).conversation_id;
            if (convId) setConversationId(convId);
          } else if (event.type === 'delta') {
            const content = (event as { content?: string }).content || '';
            fullText += content;
            setMessageText(aiMessageId, fullText);
          } else if (event.type === 'tool_result') {
            const tool = (event as { tool?: string }).tool;
            if (tool === 'search_articles') {
              try {
                const result = JSON.parse((event as { result?: string }).result || '[]');
                if (Array.isArray(result)) {
                  relatedArticles = result
                    .slice(0, 5)
                    .map((doc: Record<string, unknown>) => ({
                      id: doc.id as number,
                      title: (doc.title as string) || '',
                      unit: doc.unit as string | undefined,
                      published_on: doc.published_on as string | undefined,
                      summary_snippet: doc.summary_snippet as string | undefined,
                    }));
                }
              } catch {
                // ignore parse errors
              }
            }
          } else if (event.type === 'done') {
            setStreaming(aiMessageId, false);
            if (relatedArticles.length > 0) {
              updateRelated(aiMessageId, relatedArticles);
            }
            setIsThinking(false);
          } else if (event.type === 'error') {
            const msg = (event as { message?: string }).message;
            if (!fullText) {
              setMessageText(aiMessageId, msg || '抱歉，当前服务不可用，请稍后再试。');
            }
            setStreaming(aiMessageId, false);
            setIsThinking(false);
          }
        },
        conversationId,
        (error) => {
          if (abortRef.current) return;
          const errorMsg =
            error.message === 'missing token'
              ? '登录已过期，请重新登录。'
              : error.message;
          setMessageText(aiMessageId, errorMsg);
          setStreaming(aiMessageId, false);
          setIsThinking(false);
        },
      );
    },
    [conversationId, isThinking, setMessageText, setStreaming, token, updateRelated],
  );

  const clearChat = useCallback(async () => {
    setMessages([]);
    setIsThinking(false);
    setConversationId(undefined);
    if (token) {
      try {
        await clearAiMemory(token);
      } catch {
        // ignore server-side cleanup failure
      }
    }
    await clearChatHistory();
  }, [token]);

  return {
    messages,
    isThinking,
    sendChat,
    setMessages,
    clearChat,
  };
}
