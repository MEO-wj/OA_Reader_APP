import React, { useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Sparkle } from 'phosphor-react-native';

import type { Palette } from '@/constants/palette';
import { usePalette } from '@/hooks/use-palette';

export function ThinkingIndicator() {
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette), [palette]);

  return (
    <View style={styles.thinkingRow}>
      <View style={styles.thinkingBadge}>
        <Sparkle size={12} color={palette.gold500} weight="fill" />
      </View>
      <Text style={styles.thinkingText}>THINKING...</Text>
      <ActivityIndicator size="small" color={palette.gold500} />
    </View>
  );
}

function createStyles(colors: Palette) {
  return StyleSheet.create({
  thinkingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  thinkingBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.gold50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thinkingText: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.6,
    color: colors.gold500,
  },
  });
}
