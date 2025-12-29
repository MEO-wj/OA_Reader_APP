import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { ArrowUpRight, Paperclip } from 'phosphor-react-native';

import { shadows } from '@/constants/shadows';
import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import type { Article } from '@/types/article';
import { formatTimeLabel } from '@/utils/date';

type ArticleCardProps = {
  article: Article;
  index: number;
  isRead: boolean;
  attachmentsCount: number;
  priority: 'high' | 'normal';
  onPress: (article: Article) => void;
};

export function ArticleCard({
  article,
  index,
  isRead,
  attachmentsCount,
  priority,
  onPress,
}: ArticleCardProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  return (
    <Pressable
      onPress={() => onPress(article)}
      style={({ pressed }) => [
        styles.cardPressable,
        pressed && styles.cardPressed,
        index === 0 && { marginTop: 8 },
      ]}
    >
      <LinearGradient
        colors={[palette.white, palette.cardTint]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.card}
      >
        <View style={styles.cardGlow} />
        <View style={styles.cardHeader}>
          <View style={styles.cardMetaLeft}>
            <View
              style={[styles.tag, priority === 'high' ? styles.tagHigh : styles.tagNormal]}
            >
              <Text
                style={[
                  styles.tagText,
                  priority === 'high' ? styles.tagTextHigh : styles.tagTextNormal,
                ]}
              >
                {article.unit || '公告'}
              </Text>
            </View>
            <Text style={styles.cardTime}>{formatTimeLabel(article.created_at)}</Text>
          </View>
          {!isRead && (
            <View style={styles.unreadDot}>
              <View style={styles.unreadPulse} />
              <View style={styles.unreadCore} />
            </View>
          )}
        </View>

        <View style={styles.cardBody}>
          <Text style={styles.cardTitle} numberOfLines={2}>
            {article.title}
          </Text>
          <Text style={styles.cardSummary}>{article.summary || '暂无摘要'}</Text>
        </View>

        <View style={styles.cardFooter}>
          <View style={styles.cardStats}>
            {attachmentsCount > 0 && (
              <View style={styles.cardStatItem}>
                <Paperclip size={14} color={palette.stone400} weight="bold" />
                <Text style={styles.cardStatText}>{attachmentsCount}</Text>
              </View>
            )}
          </View>
          <View style={styles.cardArrow}>
            <ArrowUpRight size={16} color={palette.stone400} weight="bold" />
          </View>
        </View>
      </LinearGradient>
    </Pressable>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const isDark = colorScheme === 'dark';
  return StyleSheet.create({
    cardPressable: {
      marginBottom: 20,
    },
    cardPressed: {
      transform: [{ scale: 0.99 }],
    },
    card: {
      borderRadius: 28,
      padding: 22,
      borderWidth: 1,
      borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.7)',
      ...shadows.card,
      overflow: 'hidden',
    },
    cardGlow: {
      position: 'absolute',
      top: -20,
      right: -30,
      width: 120,
      height: 120,
      borderRadius: 60,
      backgroundColor: isDark ? 'rgba(212, 175, 55, 0.16)' : 'rgba(243, 224, 175, 0.7)',
    },
    cardHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 14,
    },
    cardMetaLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    tag: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 8,
      borderWidth: 1,
    },
    tagHigh: {
      backgroundColor: colors.imperial50,
      borderColor: colors.imperial100,
    },
    tagNormal: {
      backgroundColor: colors.stone100,
      borderColor: colors.stone200,
    },
    tagText: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 1,
    },
    tagTextHigh: {
      color: colors.imperial600,
    },
    tagTextNormal: {
      color: colors.stone600,
    },
    cardTime: {
      fontSize: 11,
      color: colors.stone400,
      fontWeight: '600',
    },
    unreadDot: {
      width: 12,
      height: 12,
      alignItems: 'center',
      justifyContent: 'center',
    },
    unreadPulse: {
      position: 'absolute',
      width: 12,
      height: 12,
      borderRadius: 6,
      backgroundColor: colors.imperial400,
      opacity: 0.4,
    },
    unreadCore: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: colors.imperial600,
    },
    cardBody: {
      marginBottom: 18,
    },
    cardTitle: {
      fontSize: 16,
      fontWeight: '700',
      color: colors.stone900,
      marginBottom: 8,
    },
    cardSummary: {
      fontSize: 13,
      lineHeight: 18,
      color: colors.stone500,
    },
    cardFooter: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingTop: 14,
      borderTopWidth: 1,
      borderTopColor: colors.stone100,
    },
    cardStats: {
      flexDirection: 'row',
      gap: 14,
    },
    cardStatItem: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    cardStatText: {
      fontSize: 12,
      color: colors.stone400,
      fontWeight: '600',
    },
    cardArrow: {
      width: 34,
      height: 34,
      borderRadius: 17,
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colors.stone100,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
}
