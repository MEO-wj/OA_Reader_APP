import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import type { Palette } from '@/constants/palette';
import { usePalette } from '@/hooks/use-palette';

type AmbientVariant = 'home' | 'explore' | 'login';

type AmbientBackgroundProps = {
  variant: AmbientVariant;
};

export function AmbientBackground({ variant }: AmbientBackgroundProps) {
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);

  if (variant === 'home') {
    return (
      <View style={styles.ambientBg}>
        <LinearGradient
          colors={[palette.surface, palette.surfaceWarm]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFillObject}
        />
        <View style={[styles.orb, styles.orbGold]} />
        <View style={[styles.orb, styles.orbRed]} />
        <View style={[styles.orb, styles.orbWarmHome]} />
      </View>
    );
  }

  if (variant === 'explore') {
    return (
      <View style={styles.ambientBg}>
        <View style={[styles.orb, styles.orbGold]} />
        <View style={[styles.orb, styles.orbRed]} />
        <View style={[styles.orb, styles.orbWarmExplore]} />
      </View>
    );
  }

  return (
    <View pointerEvents="none" style={styles.ambientBgLogin}>
      <View style={[styles.orb, styles.orbGoldLogin]} />
      <View style={[styles.orb, styles.orbRedLogin]} />
      <View style={[styles.orb, styles.orbWarmLogin]} />
    </View>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
  ambientBg: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.surface,
  },
  ambientBgLogin: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surface,
  },
  orb: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.5,
  },
  orbGold: {
    width: 320,
    height: 320,
    backgroundColor: colors.gold100,
    top: -60,
    left: -60,
  },
  orbRed: {
    width: 300,
    height: 300,
    backgroundColor: colors.rose100,
    bottom: -60,
    right: -30,
  },
  orbWarmHome: {
    width: 220,
    height: 220,
    backgroundColor: colors.warm100,
    top: '48%',
    left: '50%',
    marginLeft: -110,
    marginTop: -110,
  },
  orbWarmExplore: {
    width: 220,
    height: 220,
    backgroundColor: colors.warm100,
    top: '45%',
    left: '50%',
    marginLeft: -110,
    marginTop: -110,
  },
  orbGoldLogin: {
    width: 320,
    height: 320,
    backgroundColor: colors.gold100,
    top: -60,
    left: -60,
  },
  orbRedLogin: {
    width: 320,
    height: 320,
    backgroundColor: colors.rose100,
    bottom: -40,
    right: -40,
  },
  orbWarmLogin: {
    width: 220,
    height: 220,
    backgroundColor: colors.warm100,
    top: '48%',
    left: '50%',
    marginLeft: -110,
    marginTop: -110,
  },
  });
}
