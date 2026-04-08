export type AvatarFormValue = File | {
  uri: string;
  name: string;
  type: string;
};

export type BuildAvatarFormValuePayload = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  webFile?: File | null;
};

export function buildAvatarFormValue(
  payload: BuildAvatarFormValuePayload,
  isWeb: boolean
): AvatarFormValue {
  if (isWeb && payload.webFile) {
    return payload.webFile;
  }

  return {
    uri: payload.uri,
    name: payload.fileName || 'avatar.jpg',
    type: payload.mimeType || 'image/jpeg',
  };
}
