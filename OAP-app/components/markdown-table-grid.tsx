import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';

import type { Palette } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type MarkdownTableGridProps = {
  headers: string[];
  rows: string[][];
};

export function MarkdownTableGrid({ headers, rows }: MarkdownTableGridProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const { width } = useWindowDimensions();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  const normalizedRows = useMemo(
    () => rows.map((row) => headers.map((_, index) => row[index]?.trim() ?? '')),
    [headers, rows]
  );

  const columnWidth = headers.length <= 3 ? 164 : 148;
  const tableMinWidth = Math.max(headers.length * columnWidth, width - 84, 320);

  if (headers.length === 0 || normalizedRows.length === 0) {
    return null;
  }

  return (
    <View style={styles.shell}>
      <View style={styles.headerBar}>
        <View style={styles.headerTitleWrap}>
          <View style={styles.headerIconWrap}>
            <MaterialIcons name="table-chart" size={16} color={palette.gold500} />
          </View>
          <View style={styles.headerTextWrap}>
            <Text style={styles.headerTitle}>表格</Text>
            <Text style={styles.headerHint}>左右滑动查看完整内容</Text>
          </View>
        </View>
      </View>

      <View style={styles.tableFrame}>
        <ScrollView
          horizontal
          nestedScrollEnabled
          persistentScrollbar
          showsHorizontalScrollIndicator
          contentContainerStyle={styles.tableScrollContent}
        >
          <View style={[styles.table, { minWidth: tableMinWidth }]}>
            <View style={styles.headerRow}>
              {headers.map((header, index) => (
                <View
                  key={`${header}-${index}`}
                  style={[
                    styles.headerCell,
                    index !== headers.length - 1 && styles.cellDivider,
                    { width: columnWidth },
                  ]}
                >
                  <Text style={styles.headerCellText}>{header}</Text>
                </View>
              ))}
            </View>

            {normalizedRows.map((row, rowIndex) => (
              <View
                key={`row-${rowIndex}`}
                style={[
                  styles.bodyRow,
                  rowIndex % 2 === 1 && styles.altRow,
                ]}
              >
                {row.map((cell, cellIndex) => (
                  <View
                    key={`row-${rowIndex}-cell-${cellIndex}`}
                    style={[
                      styles.bodyCell,
                      cellIndex !== headers.length - 1 && styles.cellDivider,
                      rowIndex !== normalizedRows.length - 1 && styles.rowDivider,
                      { width: columnWidth },
                    ]}
                  >
                    <Text style={styles.bodyCellText}>{cell || '—'}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const shellBackground = colorScheme === 'dark' ? 'rgba(20,19,18,0.82)' : colors.white;
  const shellBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;
  const frameBackground = colorScheme === 'dark' ? 'rgba(255,255,255,0.03)' : colors.surfaceWarm;
  const cellBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;
  const headerBackground = colorScheme === 'dark' ? 'rgba(42,36,19,0.42)' : 'rgba(248, 238, 216, 0.95)';
  const altBackground = colorScheme === 'dark' ? 'rgba(255,255,255,0.025)' : 'rgba(255,255,255,0.78)';

  return StyleSheet.create({
    shell: {
      marginTop: 6,
      marginBottom: 14,
      borderRadius: 22,
      backgroundColor: shellBackground,
      borderWidth: 1,
      borderColor: shellBorder,
      overflow: 'hidden',
      ...shadows.softSubtle,
    },
    headerBar: {
      paddingHorizontal: 14,
      paddingTop: 14,
      paddingBottom: 12,
      borderBottomWidth: 1,
      borderBottomColor: shellBorder,
    },
    headerTitleWrap: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    headerIconWrap: {
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.gold50,
      borderWidth: 1,
      borderColor: colors.gold100,
    },
    headerTextWrap: {
      flex: 1,
      gap: 2,
      justifyContent: 'center',
    },
    headerTitle: {
      fontSize: 15,
      lineHeight: 20,
      fontWeight: '800',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    headerHint: {
      fontSize: 11,
      lineHeight: 15,
      color: colors.stone400,
    },
    tableFrame: {
      paddingHorizontal: 10,
      paddingTop: 10,
      paddingBottom: 12,
      backgroundColor: frameBackground,
    },
    tableScrollContent: {
      paddingBottom: 2,
    },
    table: {
      borderRadius: 18,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: cellBorder,
      backgroundColor: colors.white,
    },
    headerRow: {
      flexDirection: 'row',
      backgroundColor: headerBackground,
    },
    bodyRow: {
      flexDirection: 'row',
      backgroundColor: colors.white,
    },
    altRow: {
      backgroundColor: altBackground,
    },
    headerCell: {
      minHeight: 56,
      paddingHorizontal: 12,
      paddingVertical: 12,
      alignItems: 'center',
      justifyContent: 'center',
    },
    bodyCell: {
      minHeight: 72,
      paddingHorizontal: 12,
      paddingVertical: 14,
      alignItems: 'center',
      justifyContent: 'center',
    },
    cellDivider: {
      borderRightWidth: 1,
      borderRightColor: cellBorder,
    },
    rowDivider: {
      borderBottomWidth: 1,
      borderBottomColor: cellBorder,
    },
    headerCellText: {
      fontSize: 14,
      lineHeight: 20,
      fontWeight: '800',
      textAlign: 'center',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    bodyCellText: {
      fontSize: 13,
      lineHeight: 21,
      fontWeight: '600',
      textAlign: 'center',
      color: colorScheme === 'dark' ? colors.stone850 : colors.stone700,
    },
  });
}
