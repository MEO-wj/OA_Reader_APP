import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '@/types/chat';
import { ThinkingIndicator } from '@/components/thinking-indicator';
import type { Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type ChatMessageProps = {
  message: ChatMessage;
  renderMarkdown: (content: string) => React.ReactNode;
  isThinking?: boolean;
};

export function ChatMessageItem({ message, renderMarkdown, isThinking }: ChatMessageProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  return (
    <View
      style={[
        styles.messageWrap,
        message.isUser ? styles.messageRight : styles.messageLeft,
      ]}
    >
      <Text style={styles.messageLabel}>{message.isUser ? 'ME' : 'AI ASSISTANT'}</Text>
      <View
        style={[
          styles.messageBubble,
          message.isUser ? styles.messageUser : styles.messageAi,
        ]}
      >
        {!message.isUser && <View style={styles.aiLine} />}
        {message.isUser && <View style={styles.userLine} />}
        {message.isUser ? (
          <Text style={styles.messageText}>{message.text}</Text>
        ) : isThinking ? (
          <ThinkingIndicator />
        ) : (
          renderMarkdown(message.text || ' ')
        )}
      </View>
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const aiBackground = colorScheme === 'dark' ? colors.white : 'rgba(255,255,255,0.9)';
  const aiBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.6)';
  const userBackground = colorScheme === 'dark' ? colors.stone200 : colors.stone800;
  const userText = colorScheme === 'dark' ? colors.stone900 : colors.gold50;

  return StyleSheet.create({
  messageWrap: {
    gap: 8,
  },
  messageRight: {
    alignItems: 'flex-end',
  },
  messageLeft: {
    alignItems: 'flex-start',
  },
  messageLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 2,
    color: colors.stone400,
  },
  messageBubble: {
    maxWidth: '85%',
    padding: 14,
    borderRadius: 20,
    overflow: 'hidden',
  },
  messageUser: {
    backgroundColor: userBackground,
    borderBottomRightRadius: 6,
  },
  messageAi: {
    backgroundColor: aiBackground,
    borderColor: aiBorder,
    borderWidth: 1,
    borderBottomLeftRadius: 6,
  },
  messageText: {
    color: userText,
    fontSize: 14,
    lineHeight: 20,
  },
  aiLine: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 4,
    height: '100%',
    backgroundColor: colors.gold400,
  },
  userLine: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: 4,
    height: '100%',
    backgroundColor: colors.imperial600,
  },
  });
}
