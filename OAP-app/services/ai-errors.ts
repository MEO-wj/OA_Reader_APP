export const STREAM_ABORTED_ERROR_CODE = 'stream_aborted';

type AbortLikeError = Error & {
  code?: string;
};

export class StreamAbortedError extends Error {
  code = STREAM_ABORTED_ERROR_CODE;

  constructor(message = '流式请求已取消') {
    super(message);
    this.name = 'StreamAbortedError';
  }
}

export function isAiRequestAbortedError(error: unknown): error is AbortLikeError {
  if (!(error instanceof Error)) {
    return false;
  }

  const abortLikeError = error as AbortLikeError;
  return (
    abortLikeError.code === STREAM_ABORTED_ERROR_CODE ||
    abortLikeError.name === 'AbortError'
  );
}
