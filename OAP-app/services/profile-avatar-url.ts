export function toStoredAvatarUrl(avatarUrl?: string | null) {
  const normalized = avatarUrl?.trim() ?? '';
  if (!normalized) {
    return '';
  }

  if (normalized.startsWith('/uploads/')) {
    return normalized;
  }

  try {
    const parsed = new URL(normalized);
    const relativeUploadsPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    if (relativeUploadsPath.startsWith('/uploads/')) {
      return relativeUploadsPath;
    }
  } catch {
    // Keep the original value when it is not a valid absolute URL.
  }

  return normalized;
}
