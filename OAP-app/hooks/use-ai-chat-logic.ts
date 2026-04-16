export const STREAM_INTERRUPTED_NOTICE = '（流式输出已中断，可重试继续提问）';

export type StreamFailureResolution =
  | { kind: 'ignore' }
  | { kind: 'fallback' }
  | { kind: 'show_message'; message: string };

type ResolveStreamFailureOptions = {
  receivedDelta: boolean;
  partialText: string;
  error: unknown;
  defaultMessage: string;
};

function isAbortedStreamLikeError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  const abortLikeError = error as Error & { code?: string };
  return abortLikeError.code === 'stream_aborted' || abortLikeError.name === 'AbortError';
}

export function resolveStreamFailure({
  receivedDelta,
  partialText,
  error,
  defaultMessage,
}: ResolveStreamFailureOptions): StreamFailureResolution {
  if (isAbortedStreamLikeError(error)) {
    return { kind: 'ignore' };
  }

  if (!receivedDelta) {
    return { kind: 'fallback' };
  }

  const normalizedText = partialText.trimEnd();
  if (!normalizedText.trim()) {
    return {
      kind: 'show_message',
      message: defaultMessage,
    };
  }

  return {
    kind: 'show_message',
    message: `${normalizedText}\n\n${STREAM_INTERRUPTED_NOTICE}`,
  };
}
