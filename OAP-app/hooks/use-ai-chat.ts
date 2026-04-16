import { useCallback, useEffect, useState } from 'react';

import type { RelatedArticle } from '@/types/article';
import { askAi, clearAiMemory, streamAiChat } from '@/services/ai';
import { getChatHistory, setChatHistory } from '@/storage/chat-storage';
import type { ChatMessage } from '@/types/chat';
import { extractKeywords } from '@/utils/text';

const DEFAULT_ERROR_MESSAGE = '抱歉，当前服务不可用，请稍后再试。';
const MISSING_TOKEN_MESSAGE = '登录已过期，请重新登录。';

export function useAiChat(token?: string | null, displayName?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getChatHistory().then((history) => {
      if (!mounted) {
        return;
      }
      if (history?.messages?.length) {
        setMessages(history.messages);
      }
      setConversationId(history?.conversationId ?? null);
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
    void setChatHistory(messages, conversationId);
  }, [conversationId, isHydrated, messages]);

  const setMessageText = useCallback((id: string, text: string) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, text } : item)));
  }, []);

  const appendMessageText = useCallback((id: string, text: string) => {
    setMessages((prev) =>
      prev.map((item) => (item.id === id ? { ...item, text: `${item.text}${text}` } : item))
    );
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

        let receivedDelta = false;
        try {
          await streamAiChat({
            question,
            token,
            displayName,
            conversationId,
            onStart: ({ conversationId: nextConversationId }) => {
              if (nextConversationId) {
                setConversationId(nextConversationId);
              }
            },
            onDelta: (delta) => {
              receivedDelta = true;
              appendMessageText(aiMessageId, delta);
            },
            onRelated: (related) => {
              updateRelated(aiMessageId, related);
            },
          });
        } catch (streamError) {
          if (receivedDelta) {
            throw streamError;
          }

          const fallback = await askAi(question, token, displayName);
          const answer = fallback.answer || DEFAULT_ERROR_MESSAGE;
          setMessageText(aiMessageId, answer);
          if (fallback.related_articles?.length) {
            updateRelated(aiMessageId, fallback.related_articles);
          }
          if (fallback.conversation_id) {
            setConversationId(fallback.conversation_id);
          }
          return;
        }

        if (!receivedDelta) {
          setMessageText(aiMessageId, DEFAULT_ERROR_MESSAGE);
        }
      } catch (err) {
        if (err instanceof Error && err.message === 'missing token') {
          setMessageText(aiMessageId, MISSING_TOKEN_MESSAGE);
          return;
        }
        const errorMsg = err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE;
        setMessageText(aiMessageId, errorMsg);
      } finally {
        setIsThinking(false);
      }
    },
    [appendMessageText, conversationId, displayName, isThinking, setMessageText, token, updateRelated]
  );

  const clearChat = useCallback(async () => {
    setMessages([]);
    setIsThinking(false);

    let nextConversationId: string | null = null;
    if (token) {
      try {
        const result = await clearAiMemory(token);
        nextConversationId = result.conversation_id ?? null;
      } catch {
        // Keep local reset even if server-side cleanup fails.
      }
    }

    setConversationId(nextConversationId);
    await setChatHistory([], nextConversationId);
  }, [token]);

  return {
    messages,
    isThinking,
    sendChat,
    setMessages,
    clearChat,
  };
}
