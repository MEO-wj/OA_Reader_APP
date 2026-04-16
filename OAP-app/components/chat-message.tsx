import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Sparkle } from 'phosphor-react-native';

import { getAiMessageMeta } from '@/components/chat-message-meta';
import { ThinkingIndicator } from '@/components/thinking-indicator';
import type { Palette } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import type { ChatMessage } from '@/types/chat';

type ChatMessageProps = {
  message: ChatMessage;
  renderMarkdown: (content: string) => React.ReactNode;
  isThinking?: boolean;
  footer?: React.ReactNode;
};

export function ChatMessageItem({
  message,
  renderMarkdown,
  isThinking,
  footer,
}: ChatMessageProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);
  const aiMeta = message.isUser ? null : getAiMessageMeta(!!isThinking, message.text);

  return (
    <View
      style={[
        styles.messageWrap,
        message.isUser ? styles.messageRight : styles.messageLeft,
      ]}
    >
      {message.isUser ? (
        <>
          <Text style={styles.messageLabel}>ME</Text>
          <View style={styles.userBubble}>
            <View style={styles.userLine} />
            <Text style={styles.messageText}>{message.text}</Text>
          </View>
        </>
      ) : (
        <View style={styles.aiCard}>
          <View style={styles.aiGlowLarge} />
          <View style={styles.aiGlowSmall} />

          <View style={styles.aiHeader}>
            <View style={styles.aiIdentity}>
              <View style={styles.aiBadge}>
                <Sparkle size={16} color={palette.gold500} weight="fill" />
              </View>
              <View style={styles.aiIdentityText}>
                <Text style={styles.aiEyebrow}>AI ASSISTANT</Text>
                <Text style={styles.aiTitle}>校园智能助理</Text>
                <Text style={styles.aiSubtitle}>{aiMeta?.subtitle}</Text>
              </View>
            </View>

            <View
              style={[
                styles.aiStatusChip,
                aiMeta?.tone === 'streaming' && styles.aiStatusChipStreaming,
                aiMeta?.tone === 'ready' && styles.aiStatusChipReady,
                aiMeta?.tone === 'warning' && styles.aiStatusChipWarning,
              ]}
            >
              {aiMeta?.tone === 'ready' ? (
                <MaterialIcons name="check-circle" size={13} color={palette.imperial600} />
              ) : aiMeta?.tone === 'warning' ? (
                <MaterialIcons name="warning-amber" size={13} color={palette.imperial600} />
              ) : (
                <Sparkle size={12} color={palette.gold500} weight="fill" />
              )}
              <Text
                style={[
                  styles.aiStatusText,
                  aiMeta?.tone === 'streaming' && styles.aiStatusTextStreaming,
                  aiMeta?.tone === 'ready' && styles.aiStatusTextReady,
                  aiMeta?.tone === 'warning' && styles.aiStatusTextWarning,
                ]}
              >
                {aiMeta?.label}
              </Text>
            </View>
          </View>

          <View style={styles.aiBody}>
            {isThinking && !message.text.trim() ? (
              <ThinkingIndicator />
            ) : (
              renderMarkdown(message.text || ' ')
            )}
          </View>

          {footer ? <View style={styles.aiFooter}>{footer}</View> : null}
        </View>
      )}
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const aiBackground = colorScheme === 'dark' ? colors.white : 'rgba(255,255,255,0.96)';
  const aiBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;
  const aiMuted = colorScheme === 'dark' ? colors.stone600 : colors.stone500;
  const userBackground = colorScheme === 'dark' ? colors.stone200 : colors.stone800;
  const userText = colorScheme === 'dark' ? colors.stone900 : colors.gold50;
  const statusReadyBg = colorScheme === 'dark' ? 'rgba(255,133,133,0.16)' : colors.imperial50;
  const statusReadyBorder = colorScheme === 'dark' ? 'rgba(255,133,133,0.2)' : colors.imperial100;
  const statusWarningBg = colorScheme === 'dark' ? 'rgba(225,108,108,0.16)' : '#FFF1F1';
  const statusWarningBorder = colorScheme === 'dark' ? 'rgba(225,108,108,0.22)' : '#F5CACA';

  return StyleSheet.create({
    messageWrap: {
      gap: 8,
      width: '100%',
    },
    messageRight: {
      alignItems: 'flex-end',
    },
    messageLeft: {
      alignItems: 'stretch',
    },
    messageLabel: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 2,
      color: colors.stone400,
      marginRight: 4,
    },
    userBubble: {
      maxWidth: '82%',
      paddingHorizontal: 16,
      paddingVertical: 14,
      borderRadius: 22,
      borderBottomRightRadius: 8,
      backgroundColor: userBackground,
      overflow: 'hidden',
      ...shadows.softSubtle,
    },
    messageText: {
      color: userText,
      fontSize: 14,
      lineHeight: 22,
    },
    userLine: {
      position: 'absolute',
      top: 0,
      right: 0,
      width: 4,
      height: '100%',
      backgroundColor: colors.imperial600,
    },
    aiCard: {
      width: '100%',
      paddingHorizontal: 18,
      paddingTop: 18,
      paddingBottom: 16,
      borderRadius: 28,
      backgroundColor: aiBackground,
      borderWidth: 1,
      borderColor: aiBorder,
      overflow: 'hidden',
      ...shadows.cardSoft,
    },
    aiGlowLarge: {
      position: 'absolute',
      top: -56,
      left: -36,
      width: 180,
      height: 180,
      borderRadius: 90,
      backgroundColor: colors.gold50,
      opacity: colorScheme === 'dark' ? 0.18 : 0.9,
    },
    aiGlowSmall: {
      position: 'absolute',
      right: -48,
      bottom: -72,
      width: 168,
      height: 168,
      borderRadius: 84,
      backgroundColor: colors.rose100,
      opacity: colorScheme === 'dark' ? 0.08 : 0.34,
    },
    aiHeader: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 12,
    },
    aiIdentity: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      flex: 1,
    },
    aiBadge: {
      width: 42,
      height: 42,
      borderRadius: 16,
      backgroundColor: colorScheme === 'dark' ? colors.gold50 : colors.white,
      borderWidth: 1,
      borderColor: aiBorder,
      alignItems: 'center',
      justifyContent: 'center',
      ...shadows.glowGoldSoft,
    },
    aiIdentityText: {
      flex: 1,
      gap: 2,
    },
    aiEyebrow: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 1.8,
      color: colors.gold500,
    },
    aiTitle: {
      fontSize: 18,
      fontWeight: '800',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    aiSubtitle: {
      fontSize: 12,
      lineHeight: 18,
      color: aiMuted,
    },
    aiStatusChip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 10,
      paddingVertical: 7,
      borderRadius: 999,
      borderWidth: 1,
      alignSelf: 'flex-start',
    },
    aiStatusChipStreaming: {
      backgroundColor: colors.gold50,
      borderColor: colors.gold100,
    },
    aiStatusChipReady: {
      backgroundColor: statusReadyBg,
      borderColor: statusReadyBorder,
    },
    aiStatusChipWarning: {
      backgroundColor: statusWarningBg,
      borderColor: statusWarningBorder,
    },
    aiStatusText: {
      fontSize: 11,
      fontWeight: '700',
      letterSpacing: 0.3,
    },
    aiStatusTextStreaming: {
      color: colors.gold500,
    },
    aiStatusTextReady: {
      color: colors.imperial600,
    },
    aiStatusTextWarning: {
      color: colors.imperial600,
    },
    aiBody: {
      marginTop: 18,
    },
    aiFooter: {
      marginTop: 18,
      paddingTop: 16,
      borderTopWidth: 1,
      borderTopColor: colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100,
    },
  });
}
