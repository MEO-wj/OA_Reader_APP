import type { RelatedArticle } from '@/types/article';
import { getApiBaseUrl } from '@/services/api';

/** 用户友好的错误消息映射 */
const USER_FRIENDLY_ERRORS: Record<string, string> = {
  // 后端控制的错误消息（白名单）
  '服务繁忙，请稍后再试': '服务繁忙，请稍后再试',
  'AI服务配置不完整': 'AI服务暂时不可用',
  '请求参数错误，缺少question字段': '请求参数错误',
  // 通用错误映射
};

/** 将后端错误转换为用户友好消息 */
function toUserFriendlyError(errorData: { error?: string; message?: string }, status: number): string {
  const rawError = errorData.error || errorData.message || '';

  // 检查白名单中是否有匹配的消息
  for (const [key, friendlyMsg] of Object.entries(USER_FRIENDLY_ERRORS)) {
    if (rawError.includes(key)) {
      return friendlyMsg;
    }
  }

  // 根据状态码返回通用消息
  if (status === 503) {
    return '服务繁忙，请稍后再试';
  }
  if (status === 500) {
    return '服务器内部错误，请稍后再试';
  }
  if (status === 401) {
    return '登录已过期，请重新登录';
  }

  // 默认消息
  return '抱歉，当前服务不可用，请稍后再试。';
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
    // 尝试解析错误响应
    let errorData: { error?: string; message?: string } = {};
    try {
      errorData = (await resp.json()) as { error?: string; message?: string };
    } catch {
      // JSON解析失败，使用通用消息
    }

    // 转换为用户友好的错误消息
    throw new Error(toUserFriendlyError(errorData, resp.status));
  }
  return (await resp.json()) as {
    answer?: string;
    related_articles?: RelatedArticle[];
  };
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
    throw new Error('ai clear memory failed');
  }
  return (await resp.json()) as {
    cleared?: boolean;
  };
}
