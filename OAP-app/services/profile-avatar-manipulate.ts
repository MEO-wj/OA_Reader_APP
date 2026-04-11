import { manipulateAsync, SaveFormat, type ImageManipulatorAction } from 'expo-image-manipulator';
import { Platform } from 'react-native';
import { AVATAR_TARGET_SIZE, AVATAR_WEBP_QUALITY, buildResizeActions } from './profile-avatar-upload';

export type ManipulatedAvatar = {
  uri: string;
  width: number;
  height: number;
};

export async function manipulateAvatarToWebP(pickerUri: string): Promise<ManipulatedAvatar> {
  if (Platform.OS === 'web') {
    return { uri: pickerUri, width: AVATAR_TARGET_SIZE, height: AVATAR_TARGET_SIZE };
  }

  const actions = buildResizeActions() as ImageManipulatorAction[];
  const result = await manipulateAsync(pickerUri, actions, {
    compress: 0,
  });
  return {
    uri: result.uri,
    width: result.width,
    height: result.height,
  };
}
