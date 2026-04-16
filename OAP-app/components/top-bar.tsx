import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { Bell } from 'phosphor-react-native';
import { shadows } from '@/constants/shadows';
import type { Palette } from '@/constants/palette';
import { TOP_BAR_LAYOUT } from '@/constants/layout-metrics';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type TopBarVariant = 'home' | 'explore';

type TopBarProps = {
  variant: TopBarVariant;
  title: string;
  dateText: string;
  isScrolled?: boolean;
  hasUnread?: boolean;
  onPressAction?: () => void;
  actions?: React.ReactNode;
};

export function TopBar({
  variant,
  title,
  dateText,
  isScrolled = false,
  hasUnread = false,
  onPressAction,
  actions,
}: TopBarProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);

  if (variant === 'home') {
    return (
      <View style={styles.homeWrap}>
        <BlurView intensity={60} tint={colorScheme === 'dark' ? 'dark' : 'light'} style={styles.homeBlur}>
          <View style={[styles.homeBar, isScrolled && styles.homeBarScrolled]}>
            <View>
              <View style={styles.dateRowHome}>
                <View style={styles.dateDot} />
                <Text style={styles.dateTextHome}>{dateText}</Text>
              </View>
              <Text style={styles.homeTitle}>{title}</Text>
            </View>
            {actions ? (
              <View style={styles.actionRow}>{actions}</View>
            ) : (
              <Pressable style={styles.bellButton} onPress={onPressAction}>
                <Bell size={18} color={palette.stone400} weight="fill" />
                {hasUnread && <View style={styles.bellDot} />}
              </Pressable>
            )}
          </View>
        </BlurView>
      </View>
    );
  }

  return (
    <View style={styles.exploreWrap}>
      <BlurView intensity={60} tint={colorScheme === 'dark' ? 'dark' : 'light'} style={styles.exploreBlur}>
        <View style={styles.exploreBar}>
          <View>
            <View style={styles.dateRowExplore}>
              <View style={styles.dateDot} />
              <Text style={styles.dateTextExplore}>{dateText}</Text>
            </View>
            <Text style={styles.exploreTitle}>{title}</Text>
          </View>
          {actions ? (
            <View style={styles.actionRow}>{actions}</View>
          ) : (
            onPressAction && (
              <Pressable style={styles.bellButton} onPress={onPressAction}>
                <Bell size={18} color={palette.stone400} weight="fill" />
                {hasUnread && <View style={styles.bellDot} />}
              </Pressable>
            )
          )}
        </View>
      </BlurView>
    </View>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
  homeWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
  },
  homeBlur: {
    paddingHorizontal: 20,
    paddingTop: TOP_BAR_LAYOUT.homeTopPadding,
    paddingBottom: TOP_BAR_LAYOUT.homeBlurBottom,
  },
  homeBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingVertical: TOP_BAR_LAYOUT.homeBarVertical,
    borderRadius: 28,
  },
  homeBarScrolled: {
    backgroundColor: colors.white,
    paddingVertical: 8,
    paddingHorizontal: 8,
  },
  exploreWrap: {
    paddingTop: TOP_BAR_LAYOUT.exploreTopPadding,
    paddingHorizontal: 16,
    zIndex: 10,
  },
  exploreBlur: {
    borderRadius: 24,
    overflow: 'hidden',
  },
  exploreBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: TOP_BAR_LAYOUT.exploreBarHorizontal,
    paddingVertical: TOP_BAR_LAYOUT.exploreBarVertical,
  },
  dateRowHome: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  dateRowExplore: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dateDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.gold400,
  },
  dateTextHome: {
    fontSize: 10,
    letterSpacing: 2.2,
    fontWeight: '700',
    textTransform: 'uppercase',
    color: colors.imperial600,
  },
  dateTextExplore: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 2,
    color: colors.imperial600,
    textTransform: 'uppercase',
  },
  homeTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.stone900,
  },
  exploreTitle: {
    marginTop: TOP_BAR_LAYOUT.exploreTitleMarginTop,
    fontSize: 22,
    fontWeight: '800',
    color: colors.stone900,
  },
  bellButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.gold100,
    ...shadows.soft,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  bellDot: {
    position: 'absolute',
    top: 9,
    right: 9,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.imperial500,
    borderWidth: 1,
    borderColor: colors.white,
  },
  });
}
