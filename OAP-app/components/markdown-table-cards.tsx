import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';

import type { MobileCardField, MobileTableCardRow } from '@/utils/mobile-ai-markdown';
import type { Palette } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type MarkdownTableCardsProps = {
  rows: MobileTableCardRow[];
};

function isMetaField(field: MobileCardField) {
  return /日期|时间|单位|来源|发布|栏目/i.test(field.label) && field.value.length <= 40;
}

function isSummaryField(field: MobileCardField) {
  return /摘要|要点|说明|内容|重点|关注|条件/i.test(field.label);
}

function getMetaIconName(label: string): React.ComponentProps<typeof MaterialIcons>['name'] {
  if (/日期|时间/i.test(label)) {
    return 'calendar-today';
  }
  if (/单位|来源|发布|栏目/i.test(label)) {
    return 'business';
  }
  return 'info-outline';
}

export function MarkdownTableCards({ rows }: MarkdownTableCardsProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  return (
    <View style={styles.list}>
      {rows.map((row, index) => {
        const metaFields = row.fields.filter(isMetaField);
        const detailFields = row.fields.filter((field) => !isMetaField(field));
        const orderedDetailFields = [
          ...detailFields.filter(isSummaryField),
          ...detailFields.filter((field) => !isSummaryField(field)),
        ];

        return (
          <View key={`${row.title}-${index}`} style={styles.card}>
            <Text style={styles.title}>{row.title}</Text>

            {metaFields.length > 0 ? (
              <View style={styles.metaWrap}>
                {metaFields.map((field) => (
                  <View key={`${row.title}-${field.label}`} style={styles.metaChip}>
                    <View style={styles.metaIconWrap}>
                      <MaterialIcons
                        name={getMetaIconName(field.label)}
                        size={14}
                        color={palette.gold500}
                      />
                    </View>
                    <View style={styles.metaTextWrap}>
                      <Text style={styles.metaLabel}>{field.label}</Text>
                      <Text style={styles.metaValue}>{field.value}</Text>
                    </View>
                  </View>
                ))}
              </View>
            ) : null}

            <View style={styles.detailWrap}>
              {orderedDetailFields.map((field) => (
                <View
                  key={`${row.title}-${field.label}-detail`}
                  style={[
                    styles.detailBlock,
                    isSummaryField(field) ? styles.summaryBlock : styles.noteBlock,
                  ]}
                >
                  <Text style={styles.detailLabel}>{field.label}</Text>
                  <Text style={styles.detailValue}>{field.value}</Text>
                </View>
              ))}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const cardBackground = colorScheme === 'dark' ? 'rgba(20,19,18,0.82)' : colors.white;
  const cardBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;
  const subtleBackground = colorScheme === 'dark' ? 'rgba(42,36,19,0.22)' : colors.surfaceWarm;

  return StyleSheet.create({
    list: {
      gap: 12,
      marginTop: 6,
      marginBottom: 14,
    },
    card: {
      paddingHorizontal: 16,
      paddingTop: 18,
      paddingBottom: 16,
      borderRadius: 22,
      backgroundColor: cardBackground,
      borderWidth: 1,
      borderColor: cardBorder,
      gap: 14,
      ...shadows.softSubtle,
    },
    title: {
      fontSize: 18,
      lineHeight: 27,
      fontWeight: '800',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    metaWrap: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
    },
    metaChip: {
      minHeight: 50,
      paddingHorizontal: 12,
      paddingVertical: 10,
      borderRadius: 16,
      backgroundColor: subtleBackground,
      borderWidth: 1,
      borderColor: cardBorder,
      gap: 10,
      flexDirection: 'row',
      alignItems: 'center',
      flexGrow: 1,
      flexBasis: 0,
      minWidth: 132,
    },
    metaIconWrap: {
      width: 28,
      height: 28,
      borderRadius: 14,
      backgroundColor: colors.gold50,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
      borderColor: colors.gold100,
    },
    metaTextWrap: {
      flex: 1,
      justifyContent: 'center',
      gap: 2,
    },
    metaLabel: {
      fontSize: 10,
      fontWeight: '700',
      color: colors.stone400,
    },
    metaValue: {
      fontSize: 13,
      fontWeight: '700',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
    },
    detailWrap: {
      gap: 12,
    },
    detailBlock: {
      gap: 6,
      borderRadius: 16,
      paddingHorizontal: 14,
      paddingVertical: 12,
      borderWidth: 1,
      borderColor: cardBorder,
    },
    summaryBlock: {
      backgroundColor: subtleBackground,
    },
    noteBlock: {
      backgroundColor: colorScheme === 'dark' ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.75)',
    },
    detailLabel: {
      fontSize: 11,
      fontWeight: '700',
      letterSpacing: 1,
      color: colors.imperial600,
    },
    detailValue: {
      fontSize: 14,
      lineHeight: 23,
      color: colorScheme === 'dark' ? colors.stone850 : colors.stone700,
    },
  });
}
