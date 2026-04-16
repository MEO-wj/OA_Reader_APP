import EventSource from 'react-native-sse';

import type { RelatedArticle } from '@/types/article';
import { getApiBaseUrl } from '@/services/api';
import {
  dedupeRelatedArticles,
  extractRelatedArticlesFromToolResult,
} from '@/services/ai-stream';

const USER_FRIENDLY_ERRORS: Record<string, string> = {
  '服务繁忙，请稍后再试': '服务繁忙，请稍后再试',
  'AI服务配置不完整': 'AI 服务暂时不可用',
  '请求参数错误，缺少question字段': '请求参数错误',
};

function toUserFriendlyError(
  errorData: { error?: string; message?: string },
  status: number
): string {
  const rawError = errorData.error || errorData.message || '';

  for (const [key, friendlyMsg] of Object.entries(USER_FRIENDLY_ERRORS)) {
    if (rawError.includes(key)) {
      return friendlyMsg;
    }
  }

  if (status === 503) {
    return '服务繁忙，请稍后再试';
  }
  if (status === 500) {
    return '服务异常，请稍后再试';
  }
  if (status === 401) {
    return '登录已过期，请重新登录';
  }

  return '抱歉，当前服务不可用，请稍后再试。';
}

async function parseErrorResponse(resp: Response) {
  let errorData: { error?: string; message?: string } = {};
  try {
    errorData = (await resp.json()) as { error?: string; message?: string };
  } catch {
    // ignore invalid error body
  }
  return new Error(toUserFriendlyError(errorData, resp.status));
}

export async function askAi(question: string, token: string, displayName?: string) {
  const resp = await fetch(`${getApiBaseUrl()}/ai/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question, top_k: 3, display_name: displayName || undefined }),
  });
  if (!resp.ok) {
    throw await parseErrorResponse(resp);
  }
  return (await resp.json()) as {
    answer?: string;
    related_articles?: RelatedArticle[];
    conversation_id?: string;
  };
}

type StreamAiChatOptions = {
  question: string;
  token: string;
  displayName?: string;
  topK?: number;
  conversationId?: string | null;
  onStart?: (payload: { conversationId?: string }) => void;
  onDelta?: (delta: string) => void;
  onRelated?: (related: RelatedArticle[]) => void;
};

type AiStreamEventName = 'start' | 'delta' | 'tool_result' | 'done';

function parseEventData(raw: string | null) {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function readCustomEventData(event: { data: string | null }) {
  return parseEventData(event.data);
}

export async function streamAiChat({
  question,
  token,
  displayName,
  topK = 3,
  conversationId,
  onStart,
  onDelta,
  onRelated,
}: StreamAiChatOptions) {
  const url = `${getApiBaseUrl()}/ai/chat`;

  return new Promise<void>((resolve, reject) => {
    const collectedRelated: RelatedArticle[] = [];
    let settled = false;

    const es = new EventSource<AiStreamEventName>(url, {
      method: 'POST',
      timeout: 120000,
      timeoutBeforeConnection: 0,
      pollingInterval: 0,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message: question,
        top_k: topK,
        display_name: displayName || undefined,
        conversation_id: conversationId || undefined,
      }),
    });

    const cleanup = () => {
      es.removeAllEventListeners();
      es.close();
    };

    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve();
    };

    const fail = (error: Error) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(error);
    };

    es.addEventListener('start', (event) => {
      const data = readCustomEventData(event);
      onStart?.({
        conversationId:
          typeof data?.conversation_id === 'string' ? data.conversation_id : undefined,
      });
    });

    es.addEventListener('delta', (event) => {
      const data = readCustomEventData(event);
      const delta = typeof data?.content === 'string' ? data.content : '';
      if (delta) {
        onDelta?.(delta);
      }
    });

    es.addEventListener('tool_result', (event) => {
      const data = readCustomEventData(event);
      if (data?.tool !== 'search_articles') {
        return;
      }
      const related = extractRelatedArticlesFromToolResult(data.result ?? null);
      if (!related.length) {
        return;
      }
      collectedRelated.push(...related);
      onRelated?.(dedupeRelatedArticles(collectedRelated));
    });

    es.addEventListener('done', () => {
      finish();
    });

    es.addEventListener('close', () => {
      if (!settled) {
        fail(new Error('AI 连接已关闭'));
      }
    });

    es.addEventListener('error', (event) => {
      const rawData =
        'data' in event && (typeof event.data === 'string' || event.data === null)
          ? event.data
          : null;
      const data = parseEventData(rawData);
      if (typeof data?.message === 'string' && data.message) {
        fail(new Error(data.message));
        return;
      }
      if ('message' in event && typeof event.message === 'string' && event.message) {
        fail(new Error(event.message));
        return;
      }
      fail(new Error('抱歉，当前服务不可用，请稍后再试。'));
    });
  });
}

export async function clearAiMemory(token: string) {
  const resp = await fetch(`${getApiBaseUrl()}/ai/clear_memory`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });
  if (!resp.ok) {
    throw await parseErrorResponse(resp);
  }
  return (await resp.json()) as {
    cleared?: boolean;
    conversation_id?: string;
  };
}
