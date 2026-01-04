export function getApiBaseUrl() {
  return process.env.EXPO_PUBLIC_API_BASE_URL || 'https://oap-backend.handywote.top/api';
}

export function buildAuthHeaders(token?: string | null) {
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
