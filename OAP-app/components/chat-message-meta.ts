export type AiMessageStatusTone = 'streaming' | 'ready' | 'warning';

export type AiMessageMeta = {
  label: string;
  subtitle: string;
  tone: AiMessageStatusTone;
};

export function getAiMessageMeta(isThinking: boolean, text: string): AiMessageMeta {
  const hasText = text.trim().length > 0;
  const isInterrupted = text.includes('流式输出已中断');

  if (isInterrupted) {
    return {
      label: '输出已中断',
      subtitle: '可继续追问补全回答',
      tone: 'warning',
    };
  }

  if (isThinking && hasText) {
    return {
      label: '流式输出中',
      subtitle: '内容正在逐段生成',
      tone: 'streaming',
    };
  }

  if (isThinking) {
    return {
      label: '正在组织回答',
      subtitle: '准备结构与重点',
      tone: 'streaming',
    };
  }

  return {
    label: '已整理完成',
    subtitle: '可继续追问或查看来源',
    tone: 'ready',
  };
}
