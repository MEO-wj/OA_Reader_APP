export const AVATAR_TARGET_SIZE = 256;
export const AVATAR_WEBP_QUALITY = 80;

export type ResizeAction = {
  resize: { width: number; height: number };
};

export type SaveAction = {
  save: { format: string; quality: number };
};

export function buildResizeActions(): (ResizeAction | SaveAction)[] {
  return [
    { resize: { width: AVATAR_TARGET_SIZE, height: AVATAR_TARGET_SIZE } },
    { save: { format: 'webp', quality: AVATAR_WEBP_QUALITY } },
  ];
}

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
    name: payload.fileName || 'avatar.webp',
    type: payload.mimeType || 'image/webp',
  };
}
