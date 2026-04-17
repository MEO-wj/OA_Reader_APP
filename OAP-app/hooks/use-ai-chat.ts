import { useCallback, useEffect, useRef, useState } from 'react';

import type { RelatedArticle } from '@/types/article';
import { resolveStreamFailure } from '@/hooks/use-ai-chat-logic';
import { askAi, clearAiMemory, streamAiChat } from '@/services/ai';
import { isAiRequestAbortedError } from '@/services/ai-errors';
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
  const streamAbortControllerRef = useRef<AbortController | null>(null);

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
      streamAbortControllerRef.current?.abort();
      streamAbortControllerRef.current = null;
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

  const setStreaming = useCallback((id: string, isStreaming: boolean) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, isStreaming } : item)));
  }, []);

  const sendChat = useCallback(
    async (question: string) => {
      if (!question.trim() || isThinking) {
        return;
      }

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

      streamAbortControllerRef.current?.abort();
      const abortController = new AbortController();
      streamAbortControllerRef.current = abortController;

      try {
        if (!token) {
          throw new Error('missing token');
        }

        let receivedDelta = false;
        let partialText = '';
        let activeConversationId = conversationId;

        try {
          await streamAiChat({
            question,
            token,
            displayName,
            conversationId: activeConversationId,
            signal: abortController.signal,
            onStart: ({ conversationId: nextConversationId }) => {
              if (nextConversationId) {
                activeConversationId = nextConversationId;
                setConversationId(nextConversationId);
              }
            },
            onDelta: (delta) => {
              receivedDelta = true;
              partialText += delta;
              appendMessageText(aiMessageId, delta);
            },
            onRelated: (related) => {
              updateRelated(aiMessageId, related);
            },
          });
        } catch (streamError) {
          const resolution = resolveStreamFailure({
            receivedDelta,
            partialText,
            error: streamError,
            defaultMessage: DEFAULT_ERROR_MESSAGE,
          });

          if (resolution.kind === 'ignore') {
            return;
          }

          if (resolution.kind === 'show_message') {
            setMessageText(aiMessageId, resolution.message);
            return;
          }

          const fallback = await askAi(
            question,
            token,
            displayName,
            activeConversationId,
            abortController.signal
          );
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
        if (isAiRequestAbortedError(err)) {
          return;
        }
        if (err instanceof Error && err.message === 'missing token') {
          setMessageText(aiMessageId, MISSING_TOKEN_MESSAGE);
          return;
        }
        const errorMsg = err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE;
        setMessageText(aiMessageId, errorMsg);
      } finally {
        if (streamAbortControllerRef.current === abortController) {
          streamAbortControllerRef.current = null;
        }
        setStreaming(aiMessageId, false);
        setIsThinking(false);
      }
    },
    [appendMessageText, conversationId, displayName, isThinking, setMessageText, setStreaming, token, updateRelated]
/*
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
*/
  );

  const clearChat = useCallback(async () => {
    streamAbortControllerRef.current?.abort();
    streamAbortControllerRef.current = null;
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
