export function getStaticBaseUrl(apiBaseUrl: string): string {
  const apiSuffix = '/api';
  if (apiBaseUrl.endsWith(apiSuffix)) {
    return apiBaseUrl.slice(0, -apiSuffix.length);
  }
  return apiBaseUrl;
}

export function resolveStaticUrl(relativePath: string | null | undefined, apiBaseUrl: string): string | null {
  const trimmed = relativePath?.trim();
  if (!trimmed) {
    return null;
  }
  if (!trimmed.startsWith('/')) {
    return trimmed;
  }
  return getStaticBaseUrl(apiBaseUrl) + trimmed;
}
