import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useNavigation, useRouter } from 'expo-router';
import { usePreventRemove } from '@react-navigation/native';
import { CaretLeft, PencilSimple, Plus } from 'phosphor-react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { AmbientBackground } from '@/components/ambient-background';
import { TopBar } from '@/components/top-bar';
import type { Palette } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { usePalette } from '@/hooks/use-palette';
import { useUserProfile } from '@/hooks/use-user-profile';
import {
  updateProfile,
  uploadProfileAvatar,
} from '@/services/profile';
import {
  getDisplayName,
  getProfileAvatarUri,
  getProfileInitial,
  normalizeProfileTags,
  PRESET_PROFILE_TAGS,
  PROFILE_LIMITS,
  sanitizeDisplayName,
  sanitizeProfileBio,
} from '@/utils/profile';
import { formatDateLabel } from '@/utils/date';

function buildDraftSnapshot(params: {
  displayName: string;
  avatarLocalUri: string;
  avatarUrl: string;
  tags: string[];
  bio: string;
  pendingTag: string;
}) {
  return JSON.stringify({
    displayName: sanitizeDisplayName(params.displayName),
    avatarLocalUri: params.avatarLocalUri.trim(),
    avatarUrl: params.avatarUrl.trim(),
    tags: normalizeProfileTags(params.tags),
    bio: sanitizeProfileBio(params.bio),
    pendingTag: params.pendingTag.trim(),
  });
}

function showDiscardChangesPrompt(onConfirm: () => void) {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    if (window.confirm('你有未保存的资料修改，确定离开吗？')) {
      onConfirm();
    }
    return;
  }

  Alert.alert('离开编辑', '你有未保存的资料修改，确定离开吗？', [
    { text: '继续编辑', style: 'cancel' },
    { text: '离开', style: 'destructive', onPress: onConfirm },
  ]);
}

export default function ProfileEditScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);
  const { profile, isProfileLoaded } = useUserProfile();

  const [displayNameInput, setDisplayNameInput] = useState('');
  const [avatarLocalUri, setAvatarLocalUri] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [avatarUploadMeta, setAvatarUploadMeta] = useState<{
    fileName?: string | null;
    mimeType?: string | null;
    webFile?: File | null;
  } | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [customTagInput, setCustomTagInput] = useState('');
  const [bioInput, setBioInput] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [tagError, setTagError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const initializedRef = useRef(false);
  const initialSnapshotRef = useRef('');
  const initialAvatarLocalUriRef = useRef('');

  useEffect(() => {
    if (!isProfileLoaded || initializedRef.current) {
      return;
    }

    const nextDisplayName = getDisplayName(profile, '').trim();
    const nextAvatarLocalUri = profile?.avatar_local_uri?.trim() || '';
    const nextAvatarUrl = profile?.avatar_url?.trim() || '';
    const nextTags = normalizeProfileTags(profile?.profile_tags ?? []);
    const nextBio = profile?.bio?.trim() || '';

    setDisplayNameInput(nextDisplayName);
    setAvatarLocalUri(nextAvatarLocalUri);
    setAvatarUrl(nextAvatarUrl);
    setAvatarUploadMeta(null);
    setSelectedTags(nextTags);
    setBioInput(nextBio);

    initialAvatarLocalUriRef.current = nextAvatarLocalUri;
    initialSnapshotRef.current = buildDraftSnapshot({
      displayName: nextDisplayName,
      avatarLocalUri: nextAvatarLocalUri,
      avatarUrl: nextAvatarUrl,
      tags: nextTags,
      bio: nextBio,
      pendingTag: '',
    });
    initializedRef.current = true;
  }, [isProfileLoaded, profile]);

  const displayName = sanitizeDisplayName(displayNameInput);
  const avatarPreviewUri = avatarLocalUri.trim() || avatarUrl.trim() || getProfileAvatarUri(profile) || '';
  const avatarInitial = getProfileInitial(
    {
      ...profile,
      display_name: displayName || profile?.display_name,
    },
    '用户'
  );

  const draftSnapshot = useMemo(
    () =>
      buildDraftSnapshot({
        displayName: displayNameInput,
        avatarLocalUri,
        avatarUrl,
        tags: selectedTags,
        bio: bioInput,
        pendingTag: customTagInput,
      }),
    [avatarLocalUri, avatarUrl, bioInput, customTagInput, displayNameInput, selectedTags]
  );

  const hasUnsavedChanges = initializedRef.current && draftSnapshot !== initialSnapshotRef.current;

  const handleConfirmedBack = useCallback(() => {
    router.back();
  }, [router]);

  const handleBack = useCallback(() => {
    if (!hasUnsavedChanges || isSaving) {
      handleConfirmedBack();
      return;
    }

    showDiscardChangesPrompt(handleConfirmedBack);
  }, [handleConfirmedBack, hasUnsavedChanges, isSaving]);

  usePreventRemove(hasUnsavedChanges && !isSaving, ({ data }) => {
    showDiscardChangesPrompt(() => {
      navigation.dispatch(data.action);
    });
  });

  const toggleTag = useCallback((tag: string) => {
    setTagError(null);
    setSelectedTags((current) => {
      if (current.includes(tag)) {
        return current.filter((item) => item !== tag);
      }

      if (current.length >= PROFILE_LIMITS.maxTags) {
        setTagError(`最多设置 ${PROFILE_LIMITS.maxTags} 个标签`);
        return current;
      }

      return normalizeProfileTags([...current, tag]);
    });
  }, []);

  const addCustomTag = useCallback(
    (rawTag: string) => {
      const tag = rawTag.trim();
      if (!tag) {
        return true;
      }

      if (tag.length < PROFILE_LIMITS.tagMinLength || tag.length > PROFILE_LIMITS.tagMaxLength) {
        setTagError(
          `单个标签长度需在 ${PROFILE_LIMITS.tagMinLength}-${PROFILE_LIMITS.tagMaxLength} 个字之间`
        );
        return false;
      }

      const normalizedExisting = normalizeProfileTags(selectedTags).map((item) =>
        item.toLocaleLowerCase()
      );
      if (normalizedExisting.includes(tag.toLocaleLowerCase())) {
        setTagError('标签不能重复');
        return false;
      }

      if (selectedTags.length >= PROFILE_LIMITS.maxTags) {
        setTagError(`最多设置 ${PROFILE_LIMITS.maxTags} 个标签`);
        return false;
      }

      setTagError(null);
      setSelectedTags((current) => normalizeProfileTags([...current, tag]));
      setCustomTagInput('');
      return true;
    },
    [selectedTags]
  );

  const handlePickAvatar = useCallback(async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('无法访问相册', '请在系统设置中允许访问相册后再试。');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.8,
      });

      if (result.canceled || !result.assets?.length) {
        return;
      }

      const asset = result.assets[0];
      if (!asset?.uri) {
        Alert.alert('头像读取失败', '选中的图片无法读取，请重新选择。');
        return;
      }

      setAvatarLocalUri(asset.uri);
      setAvatarUploadMeta({
        fileName: asset.fileName,
        mimeType: asset.mimeType,
        webFile: asset.file ?? null,
      });
    } catch (error) {
      console.error('[Profile] Failed to pick avatar:', error);
      Alert.alert('头像选择失败', '本次未能完成头像选择，请稍后重试。');
    }
  }, []);

  const handleSave = useCallback(async () => {
    const nextDisplayName = sanitizeDisplayName(displayNameInput);
    if (
      nextDisplayName.length < PROFILE_LIMITS.nameMinLength ||
      nextDisplayName.length > PROFILE_LIMITS.nameMaxLength
    ) {
      setNameError(
        `昵称长度需在 ${PROFILE_LIMITS.nameMinLength}-${PROFILE_LIMITS.nameMaxLength} 个字之间`
      );
      return;
    }

    const customTagOk = addCustomTag(customTagInput);
    if (!customTagOk) {
      return;
    }

    const finalTags = normalizeProfileTags(
      customTagInput.trim() ? [...selectedTags, customTagInput.trim()] : selectedTags
    );
    const nextBio = sanitizeProfileBio(bioInput);
    const nextUpdatedAt = new Date().toISOString();

    setIsSaving(true);
    setNameError(null);

    try {
      let nextAvatarUrl = avatarUrl.trim() || undefined;

      if (
        avatarLocalUri.trim() &&
        avatarLocalUri.trim() !== initialAvatarLocalUriRef.current
      ) {
        const uploadResult = await uploadProfileAvatar({
          uri: avatarLocalUri.trim(),
          fileName: avatarUploadMeta?.fileName,
          mimeType: avatarUploadMeta?.mimeType,
          webFile: avatarUploadMeta?.webFile,
        });
        nextAvatarUrl = uploadResult.avatar_url;
      }

      await updateProfile({
        display_name: nextDisplayName,
        profile_tags: finalTags,
        bio: nextBio,
        avatar_url: nextAvatarUrl,
        profile_updated_at: nextUpdatedAt,
      });

      initialAvatarLocalUriRef.current = avatarLocalUri.trim();
      initialSnapshotRef.current = buildDraftSnapshot({
        displayName: nextDisplayName,
        avatarLocalUri: avatarLocalUri.trim(),
        avatarUrl: nextAvatarUrl || '',
        tags: finalTags,
        bio: nextBio,
        pendingTag: '',
      });

      router.back();
    } catch (error) {
      const message = error instanceof Error ? error.message : '资料保存失败，请稍后重试。';
      Alert.alert('保存失败', message);
    } finally {
      setIsSaving(false);
    }
  }, [addCustomTag, avatarLocalUri, avatarUploadMeta, avatarUrl, bioInput, customTagInput, displayNameInput, router, selectedTags]);

  if (!isProfileLoaded || !initializedRef.current) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <AmbientBackground variant="explore" />
        <TopBar variant="explore" title="编辑资料" dateText={formatDateLabel()} />
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={palette.gold400} />
          <Text style={styles.loadingText}>正在加载资料...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <AmbientBackground variant="explore" />
      <KeyboardAvoidingView
        style={styles.safeArea}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <TopBar variant="explore" title="编辑资料" dateText={formatDateLabel()} />

        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <View style={styles.headerActions}>
            <Pressable onPress={handleBack} style={styles.backButton}>
              <CaretLeft size={16} color={palette.stone500} weight="bold" />
              <Text style={styles.backButtonText}>返回</Text>
            </Pressable>
            <Text style={styles.headerHint}>保存后将直接更新服务器资料</Text>
          </View>

          <View style={styles.heroCard}>
            <LinearGradient
              colors={[palette.gold300, palette.imperial100]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.avatarRing}
            >
              <Pressable onPress={handlePickAvatar} style={styles.avatarInner}>
                {avatarPreviewUri ? (
                  <Image source={{ uri: avatarPreviewUri }} style={styles.avatarImage} />
                ) : (
                  <Text style={styles.avatarText}>{avatarInitial}</Text>
                )}
              </Pressable>
            </LinearGradient>
            <Pressable onPress={handlePickAvatar} style={styles.avatarEditChip}>
              <PencilSimple size={14} color={palette.stone900} weight="fill" />
              <Text style={styles.avatarEditChipText}>点击更换头像</Text>
            </Pressable>
          </View>

          <View style={styles.formCard}>
            <Text style={styles.fieldLabel}>昵称</Text>
            <TextInput
              value={displayNameInput}
              onChangeText={(value) => {
                setDisplayNameInput(value);
                setNameError(null);
              }}
              placeholder="请输入你的名字"
              placeholderTextColor={palette.stone400}
              maxLength={PROFILE_LIMITS.nameMaxLength}
              style={styles.input}
            />
            <Text style={styles.fieldHint}>
              {displayName.length || 0} / {PROFILE_LIMITS.nameMaxLength}
            </Text>
            {nameError ? <Text style={styles.errorText}>{nameError}</Text> : null}
          </View>

          <View style={styles.formCard}>
            <Text style={styles.fieldLabel}>个性化标签</Text>
            <View style={styles.selectedTagWrap}>
              {selectedTags.length > 0 ? (
                selectedTags.map((tag) => (
                  <Pressable
                    key={tag}
                    onPress={() => toggleTag(tag)}
                    style={[styles.tagChip, styles.tagChipSelected]}
                  >
                    <Text style={[styles.tagChipText, styles.tagChipTextSelected]}>{tag} ×</Text>
                  </Pressable>
                ))
              ) : (
                <View style={[styles.tagChip, styles.tagChipPlaceholder]}>
                  <Text style={[styles.tagChipText, styles.tagChipTextPlaceholder]}>
                    添加你的第一个标签
                  </Text>
                </View>
              )}
            </View>
            <Text style={styles.fieldSubLabel}>预设标签</Text>
            <View style={styles.presetTagWrap}>
              {PRESET_PROFILE_TAGS.map((tag) => {
                const selected = selectedTags.includes(tag);
                return (
                  <Pressable
                    key={tag}
                    onPress={() => toggleTag(tag)}
                    style={[styles.tagChip, selected && styles.tagChipSelected]}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextSelected]}>
                      {tag}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.fieldSubLabel}>自定义标签</Text>
            <View style={styles.inlineRow}>
              <TextInput
                value={customTagInput}
                onChangeText={(value) => {
                  setCustomTagInput(value);
                  setTagError(null);
                }}
                placeholder="输入自定义标签后添加"
                placeholderTextColor={palette.stone400}
                maxLength={PROFILE_LIMITS.tagMaxLength}
                style={[styles.input, styles.inlineInput]}
              />
              <Pressable onPress={() => addCustomTag(customTagInput)} style={styles.inlineButton}>
                <Plus size={14} color={palette.stone900} weight="bold" />
                <Text style={styles.inlineButtonText}>添加</Text>
              </Pressable>
            </View>
            <Text style={styles.fieldHint}>
              已选 {selectedTags.length} / {PROFILE_LIMITS.maxTags}
            </Text>
            {tagError ? <Text style={styles.errorText}>{tagError}</Text> : null}
          </View>

          <View style={styles.formCard}>
            <Text style={styles.fieldLabel}>个人简介</Text>
            <TextInput
              value={bioInput}
              onChangeText={setBioInput}
              placeholder="用一句话介绍你自己"
              placeholderTextColor={palette.stone400}
              multiline
              maxLength={PROFILE_LIMITS.bioMaxLength}
              textAlignVertical="top"
              style={styles.textarea}
            />
            <Text style={styles.fieldHint}>
              {bioInput.length} / {PROFILE_LIMITS.bioMaxLength}
            </Text>
          </View>

          <Pressable
            onPress={() => void handleSave()}
            disabled={isSaving}
            style={({ pressed }) => [
              styles.saveButton,
              (pressed || isSaving) && styles.saveButtonPressed,
            ]}
          >
            {isSaving ? (
              <ActivityIndicator color={palette.stone900} />
            ) : (
              <Text style={styles.saveButtonText}>保存资料</Text>
            )}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
    safeArea: {
      flex: 1,
      backgroundColor: colors.surface,
    },
    loadingWrap: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 12,
    },
    loadingText: {
      fontSize: 13,
      color: colors.stone600,
    },
    content: {
      paddingTop: 16,
      paddingHorizontal: 20,
      paddingBottom: 48,
      gap: 16,
    },
    headerActions: {
      gap: 10,
    },
    backButton: {
      alignSelf: 'flex-start',
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingVertical: 10,
      paddingHorizontal: 12,
      borderRadius: 999,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    backButtonText: {
      fontSize: 12,
      fontWeight: '600',
      color: colors.stone500,
    },
    headerHint: {
      fontSize: 12,
      color: colors.stone500,
    },
    heroCard: {
      alignItems: 'center',
      gap: 12,
      paddingVertical: 24,
      borderRadius: 32,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    avatarRing: {
      width: 112,
      height: 112,
      borderRadius: 56,
      padding: 4,
      ...shadows.avatarRing,
    },
    avatarInner: {
      flex: 1,
      borderRadius: 52,
      backgroundColor: colors.white,
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
    },
    avatarImage: {
      width: '100%',
      height: '100%',
    },
    avatarText: {
      fontSize: 26,
      fontWeight: '800',
      color: colors.stone900,
    },
    avatarEditChip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingVertical: 10,
      paddingHorizontal: 14,
      borderRadius: 999,
      backgroundColor: colors.gold50,
      borderWidth: 1,
      borderColor: colors.gold100,
    },
    avatarEditChipText: {
      fontSize: 12,
      fontWeight: '700',
      color: colors.stone900,
    },
    formCard: {
      gap: 12,
      padding: 18,
      borderRadius: 28,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    fieldLabel: {
      fontSize: 15,
      fontWeight: '700',
      color: colors.stone900,
    },
    fieldSubLabel: {
      fontSize: 12,
      fontWeight: '700',
      color: colors.stone600,
    },
    input: {
      minHeight: 48,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.stone200,
      backgroundColor: colors.stone100,
      paddingHorizontal: 16,
      fontSize: 14,
      color: colors.stone900,
    },
    inlineRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    inlineInput: {
      flex: 1,
    },
    inlineButton: {
      minHeight: 48,
      paddingHorizontal: 16,
      borderRadius: 18,
      backgroundColor: colors.gold300,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
    },
    inlineButtonText: {
      fontSize: 12,
      fontWeight: '700',
      color: colors.stone900,
    },
    textarea: {
      minHeight: 112,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.stone200,
      backgroundColor: colors.stone100,
      paddingHorizontal: 16,
      paddingVertical: 14,
      fontSize: 14,
      lineHeight: 20,
      color: colors.stone900,
    },
    fieldHint: {
      fontSize: 11,
      color: colors.stone500,
    },
    errorText: {
      fontSize: 12,
      color: colors.imperial600,
    },
    selectedTagWrap: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    presetTagWrap: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    tagChip: {
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.stone200,
      backgroundColor: colors.stone100,
    },
    tagChipSelected: {
      backgroundColor: colors.gold50,
      borderColor: colors.gold200,
    },
    tagChipPlaceholder: {
      backgroundColor: colors.stone100,
    },
    tagChipText: {
      fontSize: 12,
      fontWeight: '600',
      color: colors.stone700,
    },
    tagChipTextSelected: {
      color: colors.gold600,
    },
    tagChipTextPlaceholder: {
      color: colors.stone500,
    },
    saveButton: {
      minHeight: 48,
      borderRadius: 18,
      backgroundColor: colors.gold300,
      alignItems: 'center',
      justifyContent: 'center',
      ...shadows.glowGoldSoft,
    },
    saveButtonPressed: {
      opacity: 0.85,
      transform: [{ scale: 0.99 }],
    },
    saveButtonText: {
      fontSize: 14,
      fontWeight: '800',
      color: colors.stone900,
    },
  });
}
