
import { useCallback, useEffect, useState } from 'react';

import type { RelatedArticle } from '@/types/article';
import { askAi, clearAiMemory } from '@/services/ai';
import { clearChatHistory, getChatHistory, setChatHistory } from '@/storage/chat-storage';
import type { ChatMessage } from '@/types/chat';
import { extractKeywords } from '@/utils/text';

export function useAiChat(token?: string | null, displayName?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    let mounted = true;
    getChatHistory().then((history) => {
      if (!mounted) {
        return;
      }
      if (history && history.length > 0) {
        setMessages(history);
      }
      setIsHydrated(true);
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }
    void setChatHistory(messages);
  }, [isHydrated, messages]);

  const setMessageText = useCallback((id: string, text: string) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, text } : item)));
  }, []);

  const updateRelated = useCallback((id: string, related: RelatedArticle[]) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, related } : item)));
  }, []);

  const sendChat = useCallback(
    async (question: string) => {
      if (!question.trim() || isThinking) {
        return;
      }
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
        highlights,
      };
      setMessages((prev) => [...prev, userMessage, aiMessage]);
      setIsThinking(true);

      try {
        if (!token) {
          throw new Error('missing token');
        }
        const result = await askAi(question, token, displayName);
        const answer = result.answer || '抱歉，当前服务不可用，请稍后再试。';
        setMessageText(aiMessageId, answer);
        if (result.related_articles?.length) {
          updateRelated(aiMessageId, result.related_articles);
        }
      } catch (err) {
        if (err instanceof Error && err.message === 'missing token') {
          setMessageText(aiMessageId, '登录已过期，请重新登录。');
          return;
        }
        const errorMsg = err instanceof Error ? err.message : '抱歉，当前服务不可用，请稍后再试。';
        setMessageText(aiMessageId, errorMsg);
      } finally {
        setIsThinking(false);
      }
    },
    [displayName, isThinking, setMessageText, token, updateRelated]
  );

  const clearChat = useCallback(async () => {
    setMessages([]);
    setIsThinking(false);
    if (token) {
      try {
        await clearAiMemory(token);
      } catch {
        // 忽略服务端清理失败，确保本地状态重置
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
