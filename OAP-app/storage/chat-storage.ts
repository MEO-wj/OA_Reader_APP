import type { ChatMessage } from '@/types/chat';
import { getItem, removeItem, setItem } from '@/storage/universal-storage';

const CHAT_HISTORY_KEY = 'ai_chat_history.v1';
type CachedChat = {
  cached_at: number;
  messages: ChatMessage[];
  conversation_id?: string | null;
};

export async function getChatHistory() {
  const raw = await getItem(CHAT_HISTORY_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as CachedChat;
    if (!Array.isArray(parsed.messages)) {
      return null;
    }
    return {
      messages: parsed.messages,
      conversationId: parsed.conversation_id ?? null,
    };
  } catch {
    await removeItem(CHAT_HISTORY_KEY);
    return null;
  }
}

export async function setChatHistory(messages: ChatMessage[], conversationId?: string | null) {
  const payload: CachedChat = {
    cached_at: Date.now(),
    messages,
    conversation_id: conversationId ?? null,
  };
  await setItem(CHAT_HISTORY_KEY, JSON.stringify(payload));
}

export async function clearChatHistory() {
  await removeItem(CHAT_HISTORY_KEY);
}
