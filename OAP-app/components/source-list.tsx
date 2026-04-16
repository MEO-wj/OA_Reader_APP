import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { CaretDown, CaretUp, Files } from 'phosphor-react-native';

import { SourceCard } from '@/components/source-card';
import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import type { RelatedArticle } from '@/types/article';

type SourceListProps = {
  related: RelatedArticle[];
  highlights: string[];
  expanded: boolean;
  onToggle: () => void;
  onOpenArticle: (article: RelatedArticle) => void;
  embedded?: boolean;
};

export function SourceList({
  related,
  highlights,
  expanded,
  onToggle,
  onOpenArticle,
  embedded = false,
}: SourceListProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme, embedded), [colorScheme, embedded, palette]);

  return (
    <View style={styles.sourceWrap}>
      <Pressable onPress={onToggle} style={styles.sourceHeaderRow}>
        <View style={styles.sourceHeaderMain}>
          <View style={styles.sourceBadge}>
            <Files size={14} color={palette.gold500} weight="fill" />
            <Text style={styles.sourceBadgeCount}>{related.length}</Text>
          </View>
          <View style={styles.sourceHeaderText}>
            <Text style={styles.sourceTitle}>参考来源</Text>
            <Text style={styles.sourceHint}>
              {expanded ? '点击卡片查看原文详情' : '展开查看回答依据与相关文章'}
            </Text>
          </View>
        </View>

        <View style={styles.sourceToggleChip}>
          <Text style={styles.sourceToggleText}>{expanded ? '收起' : '展开'}</Text>
          {expanded ? (
            <CaretUp size={12} color={palette.gold500} weight="bold" />
          ) : (
            <CaretDown size={12} color={palette.gold500} weight="bold" />
          )}
        </View>
      </Pressable>

      {expanded ? (
        <View style={styles.sourceCardsWrap}>
          {related.map((article) => (
            <SourceCard
              key={article.id}
              article={article}
              highlights={highlights}
              onPress={onOpenArticle}
              embedded={embedded}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark', embedded: boolean) {
  const wrapBackground = embedded
    ? colorScheme === 'dark'
      ? 'rgba(42,36,19,0.22)'
      : colors.surfaceWarm
    : 'transparent';
  const wrapBorder = embedded
    ? colorScheme === 'dark'
      ? 'rgba(255,255,255,0.06)'
      : colors.gold100
    : 'transparent';
  const toggleBackground = colorScheme === 'dark' ? 'rgba(42,36,19,0.22)' : colors.white;

  return StyleSheet.create({
    sourceWrap: {
      width: '100%',
      gap: 14,
      minHeight: embedded ? 72 : undefined,
      justifyContent: 'center',
      paddingHorizontal: embedded ? 14 : 0,
      paddingVertical: embedded ? 10 : 0,
      borderRadius: embedded ? 22 : 0,
      backgroundColor: wrapBackground,
      borderWidth: embedded ? 1 : 0,
      borderColor: wrapBorder,
    },
    sourceHeaderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
      minHeight: 48,
    },
    sourceHeaderMain: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      flex: 1,
      minHeight: 48,
    },
    sourceBadge: {
      minWidth: 42,
      height: 34,
      paddingHorizontal: 10,
      borderRadius: 16,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      backgroundColor: colorScheme === 'dark' ? colors.gold50 : colors.white,
      borderWidth: 1,
      borderColor: embedded ? colors.gold100 : colors.stone100,
    },
    sourceBadgeCount: {
      fontSize: 11,
      fontWeight: '800',
      color: colors.gold500,
    },
    sourceHeaderText: {
      flex: 1,
      gap: 1,
      justifyContent: 'center',
      minHeight: 36,
    },
    sourceTitle: {
      fontSize: 13,
      lineHeight: 18,
      fontWeight: '800',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
    },
    sourceHint: {
      fontSize: 11,
      lineHeight: 15,
      color: colors.stone500,
    },
    sourceToggleChip: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 5,
      paddingHorizontal: 10,
      minHeight: 36,
      paddingVertical: 7,
      borderRadius: 999,
      backgroundColor: toggleBackground,
      borderWidth: 1,
      borderColor: embedded ? colors.gold100 : colors.stone100,
      alignSelf: 'center',
    },
    sourceToggleText: {
      fontSize: 11,
      fontWeight: '700',
      color: colors.gold500,
    },
    sourceCardsWrap: {
      gap: 10,
    },
  });
}
