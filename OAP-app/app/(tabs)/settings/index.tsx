import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Switch,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import {
  BellRinging,
  CaretRight,
  Code,
  HouseSimple,
  MoonStars,
  Package,
  PencilSimple,
  SunDim,
} from 'phosphor-react-native';
import Constants from 'expo-constants';

import { AmbientBackground } from '@/components/ambient-background';
import { BottomDock } from '@/components/bottom-dock';
import { TopBar } from '@/components/top-bar';
import { getTabContentBottomPadding } from '@/constants/layout-metrics';
import type { Palette } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import { useUserProfile } from '@/hooks/use-user-profile';
import { setAuthToken } from '@/hooks/use-auth-token';
import { clearAllArticleCache } from '@/storage/article-storage';
import { clearAuthStorage } from '@/storage/auth-storage';
import { clearChatHistory } from '@/storage/chat-storage';
import { getThemePreference, setThemePreference, type ThemePreference } from '@/storage/theme-storage';
import { disableNotifications } from '@/notifications/notification-task';
import { setNotificationsEnabled } from '@/notifications/notification-storage';
import { formatDateLabel } from '@/utils/date';
import { getDisplayName, getProfileAvatarUri, getProfileInitial } from '@/utils/profile';

export default function SettingsScreen() {
  const router = useRouter();
  const { profile, syncError, syncProfileFromRemote } = useUserProfile();
  const { width: windowWidth } = useWindowDimensions();
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);

  const appJsonVersion = useMemo(() => {
    try {
      return (require('../../../app.json') as any)?.expo?.version as string | undefined;
    } catch {
      return undefined;
    }
  }, []);

  const appVersion =
    ((Constants as any).nativeAppVersion as string | undefined) ??
    appJsonVersion ??
    Constants.expoConfig?.version ??
    '1.3.0';

  const [a2hsVisible, setA2hsVisible] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>('system');

  const isWeb = Platform.OS === 'web';
  const isIosWeb =
    isWeb &&
    typeof navigator !== 'undefined' &&
    /iphone|ipad|ipod/i.test(navigator.userAgent);

  const guideCardWidth = Math.min(420, windowWidth - 48);
  const guideImageHeight = 320;
  const a2hsGuideImages = useMemo(
    () => [
      require('../../../assets/images/pic1.webp'),
      require('../../../assets/images/pic2.webp'),
      require('../../../assets/images/pic3.webp'),
    ],
    []
  );

  useEffect(() => {
    let mounted = true;
    void getThemePreference().then((pref) => {
      if (mounted) {
        setThemePreferenceState(pref);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    void syncProfileFromRemote().catch(() => {});
  }, [syncProfileFromRemote]);

  useEffect(() => {
    if (!syncError) {
      return;
    }
    Alert.alert('资料同步失败', syncError);
  }, [syncError]);

  useEffect(() => {
    if (!isWeb) {
      return;
    }

    const calcStandalone = () => {
      const nav = navigator as Navigator & { standalone?: boolean };
      const byMedia = window.matchMedia?.('(display-mode: standalone)')?.matches ?? false;
      const byIos = nav.standalone === true;
      setIsStandalone(byMedia || byIos);
    };

    calcStandalone();
    window.addEventListener('resize', calcStandalone);

    return () => {
      window.removeEventListener('resize', calcStandalone);
    };
  }, [isWeb]);

  const displayName = getDisplayName(profile, '用户');
  const initials = getProfileInitial(profile, '用户');
  const avatarUri = getProfileAvatarUri(profile);
  const profileTags = profile?.profile_tags ?? [];
  const profileBio = profile?.bio?.trim() || '这个人很低调，还没有留下简介';
  const isAdmin = displayName.trim().toLowerCase() === 'admin';
  const vipExpiredAt = profile?.vip_expired_at ? new Date(profile.vip_expired_at) : null;
  const vipExpiredAtValid = vipExpiredAt ? !Number.isNaN(vipExpiredAt.getTime()) : false;
  const now = new Date();
  const isVipActive =
    !!profile?.is_vip && (!vipExpiredAtValid || (vipExpiredAt ? vipExpiredAt > now : true));
  const isVipExpired =
    !!profile?.is_vip && vipExpiredAtValid && vipExpiredAt ? vipExpiredAt <= now : false;

  const vipTag = useMemo(() => {
    if (isVipActive) {
      return { text: 'VIP Access', style: styles.vipActiveTag, textStyle: styles.vipActiveText };
    }
    if (isVipExpired) {
      return { text: '已过期', style: styles.vipExpiredTag, textStyle: styles.vipExpiredText };
    }
    return null;
  }, [isVipActive, isVipExpired, styles]);

  const handleLogout = useCallback(async () => {
    await clearAuthStorage();
    await clearChatHistory();
    await clearAllArticleCache();
    await setAuthToken(null);
    await setNotificationsEnabled(false);
    await disableNotifications();
    router.replace('/login');
  }, [router]);

  const followSystem = themePreference === 'system';
  const isDarkSelected = themePreference === 'dark';

  const handleToggleFollowSystem = useCallback(async () => {
    if (!followSystem) {
      setThemePreferenceState('system');
      await setThemePreference('system');
      return;
    }

    const next: ThemePreference = colorScheme === 'dark' ? 'dark' : 'light';
    setThemePreferenceState(next);
    await setThemePreference(next);
  }, [colorScheme, followSystem]);

  const handleToggleDarkMode = useCallback(async (nextValue: boolean) => {
    const next: ThemePreference = nextValue ? 'dark' : 'light';
    setThemePreferenceState(next);
    await setThemePreference(next);
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <AmbientBackground variant="explore" />
      <TopBar variant="explore" title="个人中心" dateText={formatDateLabel()} />

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.profileCard}>
          <View style={styles.profileBlock}>
            <LinearGradient
              colors={[palette.gold300, palette.imperial100]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.avatarRing}
            >
              <View style={styles.avatarInner}>
                {avatarUri ? (
                  <Image source={{ uri: avatarUri }} style={styles.avatarImage} />
                ) : (
                  <Text style={styles.avatarText}>{initials}</Text>
                )}
              </View>
            </LinearGradient>
            <Text style={styles.profileName}>{displayName}</Text>
            {vipTag ? (
              <View style={[styles.vipTagBase, vipTag.style]}>
                <Text style={[styles.vipTagTextBase, vipTag.textStyle]}>{vipTag.text}</Text>
              </View>
            ) : null}
            <View style={styles.tagWrap}>
              {profileTags.length > 0 ? (
                profileTags.map((tag) => (
                  <View key={tag} style={styles.profileTagChip}>
                    <Text style={styles.profileTagText}>{tag}</Text>
                  </View>
                ))
              ) : (
                <View style={[styles.profileTagChip, styles.profileTagChipPlaceholder]}>
                  <Text style={[styles.profileTagText, styles.profileTagTextPlaceholder]}>
                    添加你的第一个标签
                  </Text>
                </View>
              )}
            </View>
            <Text style={styles.profileBio} numberOfLines={2}>
              {profileBio}
            </Text>
            <Pressable
              onPress={() => router.push('/(tabs)/settings/profile-edit')}
              style={({ pressed }) => [styles.editProfileButton, pressed && styles.editProfileButtonPressed]}
            >
              <PencilSimple size={16} color={palette.stone900} weight="fill" />
              <Text style={styles.editProfileButtonText}>编辑资料</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.card}>
          <Pressable
            onPress={() => router.push('/(tabs)/settings/notifications')}
            style={({ pressed }) => [styles.cardRow, pressed && styles.cardRowPressed]}
          >
            <View style={styles.cardRowLeft}>
              <View style={styles.cardIcon}>
                <BellRinging size={16} color={palette.stone600} weight="fill" />
              </View>
              <Text style={styles.cardRowText}>通知管理</Text>
            </View>
            <CaretRight size={16} color={palette.stone300} weight="bold" />
          </Pressable>
        </View>

        <View style={styles.card}>
          <View style={styles.cardRow}>
            <View style={styles.cardRowLeft}>
              <View style={styles.cardIcon}>
                <SunDim size={16} color={palette.stone600} weight="fill" />
              </View>
              <Text style={styles.cardRowTextToggle}>跟随系统</Text>
            </View>
            <Switch
              value={followSystem}
              onValueChange={() => void handleToggleFollowSystem()}
              trackColor={{ false: palette.stone200, true: palette.stone800 }}
              thumbColor={palette.white}
            />
          </View>
        </View>

        <View style={styles.card}>
          <View style={[styles.cardRow, followSystem && styles.cardRowDisabled]}>
            <View style={styles.cardRowLeft}>
              <View style={styles.cardIcon}>
                <MoonStars size={16} color={palette.stone600} weight="fill" />
              </View>
              <Text style={styles.cardRowTextToggle}>夜间模式</Text>
            </View>
            <Switch
              disabled={followSystem}
              value={isDarkSelected}
              onValueChange={(value) => void handleToggleDarkMode(value)}
              trackColor={{ false: palette.stone200, true: palette.stone800 }}
              thumbColor={palette.white}
            />
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.cardRow}>
            <View style={styles.cardRowLeft}>
              <View style={styles.cardIcon}>
                <Package size={16} color={palette.stone600} weight="fill" />
              </View>
              <Text style={styles.cardRowText}>当前版本</Text>
            </View>
            <Text style={styles.versionText}>v{appVersion}</Text>
          </View>
        </View>

        {isWeb ? (
          <View style={styles.card}>
            <Pressable
              onPress={() => setA2hsVisible(true)}
              style={({ pressed }) => [styles.cardRow, pressed && styles.cardRowPressed]}
            >
              <View style={styles.cardRowLeft}>
                <View style={styles.cardIcon}>
                  <HouseSimple size={16} color={palette.stone600} weight="fill" />
                </View>
                <Text style={styles.cardRowText}>添加到主屏幕</Text>
              </View>
              <CaretRight size={16} color={palette.stone300} weight="bold" />
            </Pressable>
          </View>
        ) : null}

        {isAdmin ? (
          <View style={styles.card}>
            <Pressable
              onPress={() => router.push('/(tabs)/settings/developer')}
              style={({ pressed }) => [styles.cardRow, pressed && styles.cardRowPressed]}
            >
              <View style={styles.cardRowLeft}>
                <View style={styles.cardIcon}>
                  <Code size={16} color={palette.stone600} weight="fill" />
                </View>
                <Text style={styles.cardRowText}>开发者模式</Text>
              </View>
              <CaretRight size={16} color={palette.stone300} weight="bold" />
            </Pressable>
          </View>
        ) : null}

        <Pressable
          style={({ pressed }) => [styles.logoutButton, pressed && styles.logoutPressed]}
          onPress={handleLogout}
        >
          <Text style={styles.logoutText}>退出登录</Text>
        </Pressable>
      </ScrollView>

      {isWeb ? (
        <Modal
          transparent
          visible={a2hsVisible}
          animationType="fade"
          onRequestClose={() => setA2hsVisible(false)}
        >
          <View style={styles.a2hsOverlay}>
            <Pressable style={styles.a2hsBackdrop} onPress={() => setA2hsVisible(false)} />
            <View style={[styles.a2hsCard, { width: guideCardWidth }]}>
              <Text style={styles.a2hsTitle}>添加到主屏幕</Text>
              {isStandalone ? (
                <Text style={styles.a2hsText}>
                  你当前已经在「主屏幕模式」打开，界面会保持全屏（无浏览器栏）。
                </Text>
              ) : isIosWeb ? (
                <>
                  <Text style={styles.a2hsText}>
                    按步骤操作（左右滑动查看）：{'\n'}
                    1. 点击 Safari 下方的「分享」按钮{'\n'}
                    2. 选择「添加到主屏幕」{'\n'}
                    3. 回到桌面，从「OA Reader」图标进入即可全屏使用（无浏览器栏）。
                  </Text>
                  <ScrollView
                    horizontal
                    pagingEnabled
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.a2hsGuideScrollContent}
                    style={{ height: guideImageHeight }}
                  >
                    {a2hsGuideImages.map((source, index) => (
                      <View key={String(index)} style={[styles.a2hsGuidePage, { width: guideCardWidth - 44 }]}>
                        <Image
                          source={source}
                          resizeMode="contain"
                          style={[styles.a2hsGuideImage, { height: guideImageHeight }]}
                        />
                      </View>
                    ))}
                  </ScrollView>
                </>
              ) : (
                <Text style={styles.a2hsText}>
                  请在手机浏览器菜单中选择「安装应用」或「添加到主屏幕」，之后从桌面图标进入即可全屏使用。
                </Text>
              )}
              <Pressable
                style={({ pressed }) => [styles.a2hsPrimaryButton, pressed && styles.a2hsPrimaryPressed]}
                onPress={() => setA2hsVisible(false)}
              >
                <Text style={styles.a2hsPrimaryText}>我知道了</Text>
              </Pressable>
            </View>
          </View>
        </Modal>
      ) : null}

      <BottomDock
        activeTab="settings"
        onHome={() => router.push('/(tabs)')}
        onAi={() => router.push('/(tabs)/explore')}
        onSettings={() => undefined}
      />
    </SafeAreaView>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
    safeArea: {
      flex: 1,
      backgroundColor: colors.surface,
    },
    content: {
      paddingTop: 4,
      paddingHorizontal: 20,
      paddingBottom: getTabContentBottomPadding(8),
      gap: 20,
    },
    profileCard: {
      padding: 22,
      borderRadius: 32,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    profileBlock: {
      alignItems: 'center',
      gap: 10,
    },
    avatarRing: {
      width: 104,
      height: 104,
      borderRadius: 52,
      padding: 4,
      ...shadows.avatarRing,
    },
    avatarInner: {
      flex: 1,
      borderRadius: 48,
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
      fontSize: 24,
      fontWeight: '800',
      color: colors.stone900,
    },
    profileName: {
      fontSize: 20,
      fontWeight: '700',
      color: colors.stone900,
    },
    vipTagBase: {
      paddingHorizontal: 12,
      paddingVertical: 4,
      borderRadius: 999,
      borderWidth: 1,
    },
    vipTagTextBase: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 2,
    },
    vipActiveTag: {
      backgroundColor: colors.gold50,
      borderColor: colors.gold200,
    },
    vipActiveText: {
      color: colors.gold600,
    },
    vipExpiredTag: {
      backgroundColor: colors.imperial50,
      borderColor: colors.imperial100,
    },
    vipExpiredText: {
      color: colors.imperial600,
    },
    tagWrap: {
      width: '100%',
      flexDirection: 'row',
      flexWrap: 'wrap',
      justifyContent: 'center',
      gap: 8,
      marginTop: 2,
    },
    profileTagChip: {
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 999,
      backgroundColor: colors.stone100,
      borderWidth: 1,
      borderColor: colors.stone200,
    },
    profileTagChipPlaceholder: {
      backgroundColor: colors.gold50,
      borderColor: colors.gold100,
    },
    profileTagText: {
      fontSize: 12,
      fontWeight: '600',
      color: colors.stone700,
    },
    profileTagTextPlaceholder: {
      color: colors.gold600,
    },
    profileBio: {
      width: '100%',
      marginTop: 2,
      fontSize: 13,
      lineHeight: 21,
      textAlign: 'center',
      color: colors.stone600,
    },
    editProfileButton: {
      marginTop: 6,
      minHeight: 48,
      paddingHorizontal: 20,
      borderRadius: 18,
      backgroundColor: colors.gold300,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      ...shadows.glowGoldSoft,
    },
    editProfileButtonPressed: {
      transform: [{ scale: 0.98 }],
    },
    editProfileButtonText: {
      fontSize: 13,
      fontWeight: '700',
      color: colors.stone900,
    },
    card: {
      backgroundColor: colors.white,
      borderRadius: 32,
      borderWidth: 1,
      borderColor: colors.stone100,
      padding: 8,
      ...shadows.cardSoft,
    },
    cardRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      borderRadius: 24,
    },
    cardRowPressed: {
      borderRadius: 24,
      backgroundColor: colors.white,
    },
    cardRowDisabled: {
      opacity: 0.6,
    },
    cardRowLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
    },
    cardIcon: {
      width: 32,
      height: 32,
      borderRadius: 16,
      backgroundColor: colors.stone100,
      alignItems: 'center',
      justifyContent: 'center',
    },
    cardRowText: {
      fontSize: 14,
      fontWeight: '600',
      color: colors.stone700,
    },
    cardRowTextToggle: {
      fontSize: 14,
      fontWeight: Platform.OS === 'android' ? '500' : '600',
      color: colors.stone700,
    },
    versionText: {
      fontSize: 12,
      fontWeight: '700',
      color: colors.stone400,
      letterSpacing: 1.2,
    },
    logoutButton: {
      paddingVertical: 14,
      borderRadius: 18,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.imperial100,
      alignItems: 'center',
      ...shadows.cardSoft,
    },
    logoutPressed: {
      transform: [{ scale: 0.98 }],
    },
    logoutText: {
      color: colors.imperial600,
      fontSize: 12,
      fontWeight: '700',
    },
    a2hsOverlay: {
      flex: 1,
      justifyContent: 'center',
      paddingHorizontal: 24,
    },
    a2hsBackdrop: {
      ...StyleSheet.absoluteFillObject,
      backgroundColor: 'rgba(28, 25, 23, 0.45)',
    },
    a2hsCard: {
      borderRadius: 28,
      padding: 22,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    a2hsTitle: {
      fontSize: 16,
      fontWeight: '800',
      color: colors.stone900,
      marginBottom: 10,
    },
    a2hsText: {
      fontSize: 13,
      lineHeight: 20,
      color: colors.stone700,
      marginBottom: 18,
    },
    a2hsGuideScrollContent: {
      paddingBottom: 16,
    },
    a2hsGuidePage: {
      borderRadius: 18,
      overflow: 'hidden',
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      ...shadows.cardSoft,
    },
    a2hsGuideImage: {
      width: '100%',
    },
    a2hsPrimaryButton: {
      paddingVertical: 12,
      borderRadius: 16,
      backgroundColor: colors.stone900,
      alignItems: 'center',
    },
    a2hsPrimaryPressed: {
      transform: [{ scale: 0.98 }],
    },
    a2hsPrimaryText: {
      color: colors.white,
      fontSize: 12,
      fontWeight: '800',
      letterSpacing: 2,
    },
  });
}
