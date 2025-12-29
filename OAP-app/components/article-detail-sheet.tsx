import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Dimensions,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import {
  ArrowDown,
  Buildings,
  File,
  FileCode,
  FileDoc,
  FileImage,
  FilePdf,
  FilePpt,
  FileText,
  FileXls,
  FileZip,
  Sparkle,
  X,
} from 'phosphor-react-native';

import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import type { Article, ArticleAttachment, ArticleDetail } from '@/types/article';

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

function stripAttachmentLines(text: string) {
  if (!text) {
    return '';
  }
  const cleaned = text.replace(/^[\s\t]*附件[:：].*$/gm, '').replace(/\n{3,}/g, '\n\n').trim();
  return cleaned;
}

type AttachmentItem = {
  name: string;
  url: string;
  ext: string;
  label: string;
};

type AttachmentTone = {
  icon: React.ComponentType<any>;
  badge: string;
  badgeText: string;
  iconColor: string;
  border: string;
  pill: string;
  arrowBg: string;
  arrowColor: string;
};

function parseAttachments(
  input: ArticleAttachment[] | string | null | undefined
): AttachmentItem[] {
  if (!input) {
    return [];
  }
  let source: ArticleAttachment[] | null = null;
  if (Array.isArray(input)) {
    source = input;
  } else if (typeof input === 'string') {
    try {
      const parsed = JSON.parse(input);
      source = Array.isArray(parsed) ? parsed : null;
    } catch {
      source = null;
    }
  }
  if (!source) {
    return [];
  }
  return source
    .map((item, index) => {
      if (!item || typeof item !== 'object') {
        return null;
      }
      const name =
        item['名称'] ||
        item['name'] ||
        item['filename'] ||
        item['title'] ||
        item['文件名'] ||
        '';
      const url = item['链接'] || item['link'] || item['url'] || '';
      const extMatch = (name || url).match(/\.([A-Za-z0-9]+)(?:[?#]|$)/);
      const ext = extMatch ? extMatch[1].toLowerCase() : '';
      const label = ext ? ext.toUpperCase() : 'FILE';
      return {
        name: name || url || `附件${index + 1}`,
        url,
        ext,
        label,
      };
    })
    .filter((item): item is AttachmentItem => !!item);
}

function resolveAttachmentTone(
  ext: string,
  palette: Palette,
  colorScheme: 'light' | 'dark'
): AttachmentTone {
  const isDark = colorScheme === 'dark';
  const common = {
    border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(28, 25, 23, 0.08)',
  };

  switch (ext) {
    case 'pdf':
      return {
        icon: FilePdf,
        badge: isDark ? '#3B1518' : '#FDE8E8',
        badgeText: isDark ? '#FCA5A5' : '#B91C1C',
        iconColor: isDark ? '#FCA5A5' : '#C02425',
        border: isDark ? '#5B1F23' : '#F7CFCF',
        pill: isDark ? '#221012' : '#FFF4F3',
        arrowBg: isDark ? '#2E1417' : '#FCECEC',
        arrowColor: isDark ? '#FCA5A5' : '#C02425',
      };
    case 'xls':
    case 'xlsx':
    case 'csv':
      return {
        icon: FileXls,
        badge: isDark ? '#0F2A20' : '#DCFCE7',
        badgeText: isDark ? '#86EFAC' : '#15803D',
        iconColor: isDark ? '#86EFAC' : '#1D9A4E',
        border: isDark ? '#1E3A2E' : '#BBF7D0',
        pill: isDark ? '#10241B' : '#F0FDF4',
        arrowBg: isDark ? '#143124' : '#ECFDF3',
        arrowColor: isDark ? '#86EFAC' : '#16A34A',
      };
    case 'doc':
    case 'docx':
      return {
        icon: FileDoc,
        badge: isDark ? '#12233D' : '#DBEAFE',
        badgeText: isDark ? '#93C5FD' : '#1D4ED8',
        iconColor: isDark ? '#93C5FD' : '#2563EB',
        border: isDark ? '#1C2F4E' : '#BFDBFE',
        pill: isDark ? '#111C30' : '#EFF6FF',
        arrowBg: isDark ? '#17243B' : '#E8F1FE',
        arrowColor: isDark ? '#93C5FD' : '#2563EB',
      };
    case 'ppt':
    case 'pptx':
      return {
        icon: FilePpt,
        badge: isDark ? '#2E1B12' : '#FFEDD5',
        badgeText: isDark ? '#FDBA74' : '#C2410C',
        iconColor: isDark ? '#FDBA74' : '#EA580C',
        border: isDark ? '#3D2418' : '#FED7AA',
        pill: isDark ? '#24160F' : '#FFF7ED',
        arrowBg: isDark ? '#2E1B12' : '#FFF1E6',
        arrowColor: isDark ? '#FDBA74' : '#C2410C',
      };
    case 'zip':
    case 'rar':
    case '7z':
      return {
        icon: FileZip,
        badge: isDark ? '#2B1E3F' : '#EDE9FE',
        badgeText: isDark ? '#C4B5FD' : '#6D28D9',
        iconColor: isDark ? '#C4B5FD' : '#7C3AED',
        border: isDark ? '#3A2A52' : '#DDD6FE',
        pill: isDark ? '#20172F' : '#F5F3FF',
        arrowBg: isDark ? '#2B1E3F' : '#F0ECFF',
        arrowColor: isDark ? '#C4B5FD' : '#7C3AED',
      };
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'bmp':
    case 'webp':
      return {
        icon: FileImage,
        badge: isDark ? '#0D2B2B' : '#CCFBF1',
        badgeText: isDark ? '#5EEAD4' : '#0F766E',
        iconColor: isDark ? '#5EEAD4' : '#0F766E',
        border: isDark ? '#1C3D3D' : '#99F6E4',
        pill: isDark ? '#112524' : '#F0FDFA',
        arrowBg: isDark ? '#123330' : '#E8FFFA',
        arrowColor: isDark ? '#5EEAD4' : '#0F766E',
      };
    case 'txt':
    case 'md':
      return {
        icon: FileText,
        badge: isDark ? '#2A2521' : '#F1F5F9',
        badgeText: isDark ? '#E2E8F0' : '#475569',
        iconColor: isDark ? '#E2E8F0' : '#475569',
        border: isDark ? '#3B3531' : '#E2E8F0',
        pill: isDark ? '#1F1B18' : '#F8FAFC',
        arrowBg: isDark ? '#2A2521' : '#EEF2F6',
        arrowColor: isDark ? '#E2E8F0' : '#475569',
      };
    case 'json':
    case 'xml':
    case 'html':
    case 'htm':
    case 'js':
    case 'ts':
      return {
        icon: FileCode,
        badge: isDark ? '#2A1E11' : '#FEF3C7',
        badgeText: isDark ? '#FCD34D' : '#B45309',
        iconColor: isDark ? '#FCD34D' : '#B45309',
        border: isDark ? '#3D2C17' : '#FDE68A',
        pill: isDark ? '#21170E' : '#FFFBEB',
        arrowBg: isDark ? '#2A1E11' : '#FFF6D8',
        arrowColor: isDark ? '#FCD34D' : '#B45309',
      };
    default:
      return {
        icon: File,
        badge: isDark ? '#1F1A17' : palette.stone100,
        badgeText: isDark ? palette.stone800 : palette.stone600,
        iconColor: isDark ? palette.stone800 : palette.stone600,
        border: common.border,
        pill: isDark ? '#171411' : palette.white,
        arrowBg: isDark ? '#1F1A17' : palette.stone100,
        arrowColor: isDark ? palette.stone800 : palette.stone600,
      };
  }
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
  const attachments = useMemo(
    () => parseAttachments(detail?.attachments ?? article?.attachments ?? null),
    [article?.attachments, detail?.attachments]
  );
  const hasAttachments = attachments.length > 0;

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
    const cleaned = stripAttachmentLines(normalized);
    return cleaned || '暂无正文内容，稍后再试。';
  }, [detail?.content]);
  const handleOpenAttachment = useCallback(async (url: string) => {
    if (!url) {
      return;
    }
    try {
      await Linking.openURL(url);
    } catch {
      // 忽略错误，避免打断阅读
    }
  }, []);

  if (!mounted) {
    return null;
  }

  const aiCardColors: readonly [string, string] =
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

            {hasAttachments && (
              <View style={styles.attachmentsSection}>
                <View style={styles.attachmentsHeader}>
                  <Text style={styles.attachmentsTitle}>附件下载</Text>
                  <View style={styles.attachmentsCountBadge}>
                    <Text style={styles.attachmentsCountText}>{attachments.length} 个</Text>
                  </View>
                </View>
                <View style={styles.attachmentsList}>
                  {attachments.map((item, index) => {
                    const tone = resolveAttachmentTone(item.ext, palette, colorScheme);
                    const Icon = tone.icon;
                    return (
                      <Pressable
                        key={`${item.url || item.name}-${index}`}
                        onPress={() => handleOpenAttachment(item.url)}
                        disabled={!item.url}
                        style={({ pressed }) => [
                          styles.attachmentCard,
                          { backgroundColor: tone.pill, borderColor: tone.border },
                          pressed && styles.attachmentCardPressed,
                          !item.url && styles.attachmentCardDisabled,
                        ]}
                      >
                        <View
                          style={[
                            styles.attachmentIconWrap,
                            { backgroundColor: tone.badge, borderColor: tone.border },
                          ]}
                        >
                          <Icon size={18} color={tone.iconColor} weight="fill" />
                        </View>
                        <View style={styles.attachmentInfo}>
                          <Text style={styles.attachmentName} numberOfLines={2}>
                            {item.name}
                          </Text>
                          <View style={styles.attachmentMetaRow}>
                            <View
                              style={[
                                styles.attachmentTypeBadge,
                                { backgroundColor: tone.badge },
                              ]}
                            >
                              <Text style={[styles.attachmentTypeText, { color: tone.badgeText }]}>
                                {item.label}
                              </Text>
                            </View>
                            <Text style={styles.attachmentAction}>点击下载</Text>
                          </View>
                        </View>
                        <View
                          style={[styles.attachmentArrow, { backgroundColor: tone.arrowBg }]}
                        >
                          <ArrowDown size={14} color={tone.arrowColor} weight="bold" />
                        </View>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            )}
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
    attachmentsSection: {
      marginTop: 22,
    },
    attachmentsHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 12,
    },
    attachmentsTitle: {
      fontSize: 13,
      fontWeight: '700',
      color: colors.stone700,
    },
    attachmentsCountBadge: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 999,
      backgroundColor: colors.stone100,
    },
    attachmentsCountText: {
      fontSize: 10,
      fontWeight: '700',
      color: colors.stone500,
    },
    attachmentsList: {
      gap: 12,
    },
    attachmentCard: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: 14,
      paddingHorizontal: 14,
      borderRadius: 18,
      borderWidth: 1,
    },
    attachmentCardPressed: {
      transform: [{ scale: 0.98 }],
      opacity: 0.9,
    },
    attachmentCardDisabled: {
      opacity: 0.6,
    },
    attachmentIconWrap: {
      width: 38,
      height: 38,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
      marginRight: 12,
    },
    attachmentInfo: {
      flex: 1,
    },
    attachmentName: {
      fontSize: 13,
      fontWeight: '600',
      color: colors.stone900,
      marginBottom: 6,
    },
    attachmentMetaRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    attachmentTypeBadge: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 8,
    },
    attachmentTypeText: {
      fontSize: 9,
      fontWeight: '700',
      letterSpacing: 0.6,
    },
    attachmentAction: {
      fontSize: 11,
      color: colors.stone400,
      fontWeight: '600',
    },
    attachmentArrow: {
      width: 30,
      height: 30,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      marginLeft: 10,
    },
  });
}
