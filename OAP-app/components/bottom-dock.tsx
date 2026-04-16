import React, { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { Gear, House, Sparkle } from 'phosphor-react-native';

import { shadows } from '@/constants/shadows';
import type { Palette } from '@/constants/palette';
import { BOTTOM_DOCK_LAYOUT } from '@/constants/layout-metrics';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type DockTab = 'home' | 'ai' | 'settings';

type BottomDockProps = {
  activeTab: DockTab;
  onHome: () => void;
  onAi: () => void;
  onSettings: () => void;
};

export function BottomDock({ activeTab, onHome, onAi, onSettings }: BottomDockProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);

  const activeStyle =
    activeTab === 'home'
      ? styles.dockButtonHome
      : activeTab === 'ai'
        ? styles.dockButtonAi
        : styles.dockButtonSettings;

  return (
    <View style={styles.dockWrap}>
      <BlurView intensity={60} tint={colorScheme === 'dark' ? 'dark' : 'light'} style={styles.dock}>
        <Pressable
          style={[styles.dockButton, activeTab === 'home' && activeStyle]}
          onPress={onHome}
        >
          <House
            size={22}
            color={activeTab === 'home' ? palette.imperial600 : palette.stone400}
            weight={activeTab === 'home' ? 'fill' : 'bold'}
          />
        </Pressable>
        <Pressable
          style={[styles.dockButton, activeTab === 'ai' && activeStyle]}
          onPress={onAi}
        >
          <Sparkle
            size={22}
            color={activeTab === 'ai' ? palette.gold500 : palette.stone400}
            weight={activeTab === 'ai' ? 'fill' : 'bold'}
          />
        </Pressable>
        <Pressable
          style={[styles.dockButton, activeTab === 'settings' && activeStyle]}
          onPress={onSettings}
        >
          <Gear
            size={22}
            color={activeTab === 'settings' ? palette.stone800 : palette.stone400}
            weight={activeTab === 'settings' ? 'fill' : 'bold'}
          />
        </Pressable>
      </BlurView>
    </View>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
  dockWrap: {
    position: 'absolute',
    bottom: BOTTOM_DOCK_LAYOUT.bottomOffset,
    left: 0,
    right: 0,
    alignItems: 'center',
    paddingHorizontal: BOTTOM_DOCK_LAYOUT.horizontalPadding,
  },
  dock: {
    paddingHorizontal: 20,
    paddingVertical: BOTTOM_DOCK_LAYOUT.verticalPadding,
    borderRadius: 999,
    flexDirection: 'row',
    gap: BOTTOM_DOCK_LAYOUT.innerGap,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.stone100,
    overflow: 'hidden',
    ...shadows.dock,
  },
  dockButton: {
    width: BOTTOM_DOCK_LAYOUT.buttonSize,
    height: BOTTOM_DOCK_LAYOUT.buttonSize,
    borderRadius: BOTTOM_DOCK_LAYOUT.buttonRadius,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dockButtonHome: {
    backgroundColor: colors.imperial50,
    ...shadows.glowImperial,
  },
  dockButtonAi: {
    backgroundColor: colors.gold50,
    ...shadows.glowGold,
  },
  dockButtonSettings: {
    backgroundColor: colors.stone100,
    ...shadows.glowStone,
  },
  });
}
