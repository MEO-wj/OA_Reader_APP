import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { RelatedArticle } from '@/types/article';
import { splitHighlightedText } from '@/utils/text';
import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type SourceCardProps = {
  article: RelatedArticle;
  highlights: string[];
  onPress: (article: RelatedArticle) => void;
};

function buildSnippet(article: RelatedArticle) {
  return article.content_snippet || article.summary_snippet || '';
}

export function SourceCard({ article, highlights, onPress }: SourceCardProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  return (
    <Pressable style={styles.sourceCard} onPress={() => onPress(article)}>
      <View style={styles.sourceHeader}>
        <Text style={styles.sourceTag}>{article.unit || '公告'}</Text>
        <Text style={styles.sourceDate}>{article.published_on || '--'}</Text>
      </View>
      <Text style={styles.sourceTitleText}>{article.title}</Text>
      <Text style={styles.snippetText}>
        {splitHighlightedText(buildSnippet(article), highlights).map((part, index) => (
          <Text
            key={`${article.id}-snippet-${index}`}
            style={part.isMatch ? styles.snippetHighlight : undefined}
          >
            {part.value}
          </Text>
        ))}
      </Text>
    </Pressable>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  return StyleSheet.create({
  sourceCard: {
    padding: 12,
    borderRadius: 18,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.stone100,
    gap: 6,
  },
  sourceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sourceTag: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.imperial600,
  },
  sourceDate: {
    fontSize: 10,
    color: colors.stone300,
  },
  sourceTitleText: {
    fontSize: 13,
    fontWeight: '700',
    color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
  },
  snippetText: {
    fontSize: 12,
    color: colors.stone500,
    lineHeight: 18,
  },
  snippetHighlight: {
    color: colors.imperial600,
    fontWeight: '700',
  },
  });
}
