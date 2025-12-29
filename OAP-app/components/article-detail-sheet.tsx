import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Dimensions,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Buildings, Sparkle, X } from 'phosphor-react-native';

import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import type { Article, ArticleDetail } from '@/types/article';

type ArticleDetailSheetProps = {
  visible: boolean;
  article: Article | null;
  detail: ArticleDetail | null;
  onClose: () => void;
};

const screenHeight = Dimensions.get('window').height;

function normalizeParagraphs(text: string) {
  if (!text) {
    return '';
  }
  const normalized = text
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/([^\n])\n([^\n])/g, '$1 $2')
    .trim();
  return normalized;
}

export function ArticleDetailSheet({
  visible,
  article,
  detail,
  onClose,
}: ArticleDetailSheetProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  const sheetAnim = useRef(new Animated.Value(screenHeight)).current;
  const [mounted, setMounted] = useState(visible);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(sheetAnim, {
        toValue: 0,
        duration: 450,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(sheetAnim, {
        toValue: screenHeight,
        duration: 320,
        useNativeDriver: true,
      }).start(() => {
        setMounted(false);
      });
    }
  }, [sheetAnim, visible]);

  const displaySummary = detail?.summary || article?.summary || '暂无摘要';
  const displayContent = useMemo(() => {
    const normalized = normalizeParagraphs(detail?.content || '');
    return normalized || '暂无正文内容，稍后再试。';
  }, [detail?.content]);

  if (!mounted) {
    return null;
  }

  const aiCardColors =
    colorScheme === 'dark'
      ? [palette.stone200, palette.stone300]
      : [palette.stone900, palette.stone800];

  const aiTextColor = colorScheme === 'dark' ? palette.stone850 : '#E7E2D8';

  return (
    <Modal transparent visible={mounted} animationType="none">
      <View style={styles.sheetOverlay}>
        <Pressable style={styles.sheetBackdrop} onPress={onClose} />
        <Animated.View
          style={[
            styles.sheetContainer,
            { transform: [{ translateY: sheetAnim }] },
          ]}
        >
          <View style={styles.sheetHandle} />
          <Pressable style={styles.sheetClose} onPress={onClose}>
            <X size={16} color={palette.stone500} weight="bold" />
          </Pressable>
          <ScrollView
            contentContainerStyle={styles.sheetContent}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.detailHeader}>
              <View style={styles.detailIcon}>
                <Buildings size={20} color={palette.imperial600} weight="fill" />
              </View>
              <View>
                <Text style={styles.detailUnit}>{article?.unit || '公告'}</Text>
                <Text style={styles.detailDate}>{article?.published_on || '--'}</Text>
              </View>
            </View>

            <Text style={styles.detailTitle}>{article?.title || ''}</Text>

            <LinearGradient
              colors={aiCardColors}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.aiCard}
            >
              <View style={styles.aiLine} />
              <View style={styles.aiBadgeRow}>
                <Sparkle size={14} color={palette.gold300} weight="fill" />
                <Text style={styles.aiBadge}>AI SUMMARY</Text>
              </View>
              <Text style={[styles.aiText, { color: aiTextColor }]}>{displaySummary}</Text>
            </LinearGradient>

            <View style={styles.detailContentWrap}>
              <Text style={styles.detailLead}>各部门、各单位：</Text>
              <Text style={styles.detailContent}>{displayContent}</Text>
            </View>
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const isDark = colorScheme === 'dark';
  return StyleSheet.create({
    sheetOverlay: {
      flex: 1,
      justifyContent: 'flex-end',
    },
    sheetBackdrop: {
      ...StyleSheet.absoluteFillObject,
      backgroundColor: isDark ? 'rgba(0, 0, 0, 0.65)' : 'rgba(28, 25, 23, 0.4)',
    },
    sheetContainer: {
      height: screenHeight * 0.9,
      backgroundColor: colors.surface,
      borderTopLeftRadius: 40,
      borderTopRightRadius: 40,
      overflow: 'hidden',
    },
    sheetHandle: {
      position: 'absolute',
      top: 12,
      alignSelf: 'center',
      width: 44,
      height: 5,
      borderRadius: 99,
      backgroundColor: isDark ? colors.stone300 : colors.stone200,
      zIndex: 2,
    },
    sheetClose: {
      position: 'absolute',
      top: 18,
      right: 18,
      zIndex: 2,
      width: 30,
      height: 30,
      borderRadius: 15,
      backgroundColor: colors.stone100,
      alignItems: 'center',
      justifyContent: 'center',
    },
    sheetContent: {
      paddingTop: 48,
      paddingHorizontal: 26,
      paddingBottom: 40,
    },
    detailHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: 16,
    },
    detailIcon: {
      width: 38,
      height: 38,
      borderRadius: 19,
      backgroundColor: colors.imperial50,
      borderWidth: 1,
      borderColor: colors.imperial100,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: 12,
    },
    detailUnit: {
      fontSize: 12,
      fontWeight: '700',
      color: colors.stone400,
      textTransform: 'uppercase',
      letterSpacing: 1.2,
    },
    detailDate: {
      marginTop: 2,
      fontSize: 10,
      color: colors.stone300,
    },
    detailTitle: {
      fontSize: 22,
      fontWeight: '800',
      color: colors.stone900,
      lineHeight: 30,
      marginBottom: 18,
    },
    aiCard: {
      borderRadius: 24,
      padding: 20,
      marginBottom: 18,
    },
    aiLine: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      height: 4,
      backgroundColor: colors.gold400,
    },
    aiBadgeRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: 10,
    },
    aiBadge: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 2,
      color: colors.gold300,
    },
    aiText: {
      fontSize: 13,
      lineHeight: 20,
    },
    detailContentWrap: {
      marginTop: 4,
    },
    detailLead: {
      fontSize: 13,
      fontWeight: '600',
      color: colors.stone900,
      marginBottom: 8,
    },
    detailContent: {
      fontSize: 13,
      lineHeight: 22,
      color: colors.stone600,
    },
  });
}
