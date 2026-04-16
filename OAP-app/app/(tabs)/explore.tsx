
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Keyboard,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import Markdown from 'react-native-markdown-display';
import { WebView } from 'react-native-webview';
import { Crown } from 'phosphor-react-native';

import { AmbientBackground } from '@/components/ambient-background';
import { ArticleDetailSheet } from '@/components/article-detail-sheet';
import { BottomDock } from '@/components/bottom-dock';
import { ChatInput } from '@/components/chat-input';
import { ChatMessageItem } from '@/components/chat-message';
import { MarkdownTableCards } from '@/components/markdown-table-cards';
import { SourceList } from '@/components/source-list';
import { TopBar } from '@/components/top-bar';
import { getChatInputDockOffset, getTabContentBottomPadding } from '@/constants/layout-metrics';
import { shadows } from '@/constants/shadows';
import { useAiChat } from '@/hooks/use-ai-chat';
import { useAuthToken } from '@/hooks/use-auth-token';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useDisplayName } from '@/hooks/use-display-name';
import { useMermaidScript } from '@/hooks/use-mermaid';
import { usePalette } from '@/hooks/use-palette';
import type { Palette } from '@/constants/palette';
import { buildArticleFromRelated, fetchArticleDetail } from '@/services/articles';
import { formatDateLabel, getDayPeriod } from '@/utils/date';
import { segmentMarkdownForMobile } from '@/utils/mobile-ai-markdown';
import type { Article, ArticleDetail, RelatedArticle } from '@/types/article';
const mermaidHtml = (diagram: string, script: string, theme: 'neutral' | 'dark') => `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body { margin: 0; padding: 0; background: transparent; }
      #container { padding: 8px; }
    </style>
    <script>${script}</script>
  </head>
  <body>
    <div id="container" class="mermaid">${diagram}</div>
    <script>
      mermaid.initialize({ startOnLoad: true, theme: '${theme}' });
    </script>
  </body>
</html>`;

export default function AiAssistantScreen() {
  const router = useRouter();
  const scrollRef = useRef<ScrollView>(null);
  const [input, setInput] = useState('');
  const [activeArticle, setActiveArticle] = useState<Article | null>(null);
  const [activeDetail, setActiveDetail] = useState<ArticleDetail | null>(null);
  const [sheetVisible, setSheetVisible] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});

  const token = useAuthToken();
  const displayName = useDisplayName('用户');
  const mermaidScript = useMermaidScript();
  const { messages, isThinking, sendChat, clearChat } = useAiChat(token, displayName);
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);
  const markdownStyles = useMemo(() => createMarkdownStyles(palette, colorScheme), [colorScheme, palette]);

  // 键盘高度状态
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  // 监听键盘显示/隐藏事件
  useEffect(() => {
    const showSubscription = Keyboard.addListener('keyboardDidShow', (e) => {
      setKeyboardHeight(e.endCoordinates.height);
    });
    const hideSubscription = Keyboard.addListener('keyboardDidHide', () => {
      setKeyboardHeight(0);
    });

    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);

  const greeting = useMemo(() => `${getDayPeriod(new Date())}，${displayName}`, [displayName]);
  const lastAiMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (!messages[i].isUser) {
        return messages[i].id;
      }
    }
    return null;
  }, [messages]);
  const dockOffset = getChatInputDockOffset();

  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    });
  }, []);

  const openArticle = useCallback(
    async (article: RelatedArticle) => {
      setActiveArticle(buildArticleFromRelated(article));
      setSheetVisible(true);
      setActiveDetail(null);
      try {
        const detail = await fetchArticleDetail(article.id, token);
        setActiveArticle(detail);
        setActiveDetail(detail);
      } catch {
        setActiveDetail(null);
      }
    },
    [token]
  );

  const closeArticle = useCallback(() => {
    setSheetVisible(false);
    setActiveArticle(null);
    setActiveDetail(null);
  }, []);

  const toggleSources = useCallback((id: string) => {
    setExpandedSources((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);
  const sendChatMessage = useCallback(async () => {
    const question = input.trim();
    if (!question || isThinking) {
      return;
    }
    setInput('');
    scrollToEnd();
    void sendChat(question).finally(scrollToEnd);
  }, [input, isThinking, scrollToEnd, sendChat]);

  const handleNewChat = useCallback(async () => {
    setInput('');
    setExpandedSources({});
    closeArticle();
    await clearChat();
  }, [clearChat, closeArticle]);

  const renderMarkdownWithMermaid = useCallback((content: string) => {
    const segments: { type: 'markdown' | 'mermaid'; content: string }[] = [];
    const regex = /```mermaid\s*([\s\S]*?)```/g;
    let lastIndex = 0;
    let match = regex.exec(content);
    while (match) {
      if (match.index > lastIndex) {
        segments.push({ type: 'markdown', content: content.slice(lastIndex, match.index) });
      }
      segments.push({ type: 'mermaid', content: match[1].trim() });
      lastIndex = match.index + match[0].length;
      match = regex.exec(content);
    }
    if (lastIndex < content.length) {
      segments.push({ type: 'markdown', content: content.slice(lastIndex) });
    }
    return segments.map((segment, index) => {
      if (segment.type === 'mermaid') {
        if (!mermaidScript) {
          return (
            <Markdown key={`mermaid-fallback-${index}`} style={markdownStyles}>
              {` \n\`\`\`mermaid\n${segment.content}\n\`\`\`\n `}
            </Markdown>
          );
        }
        return (
          <View key={`mermaid-${index}`} style={styles.mermaidWrap}>
            <WebView
              originWhitelist={['*']}
              source={{ html: mermaidHtml(segment.content, mermaidScript, colorScheme === 'dark' ? 'dark' : 'neutral') }}
              style={styles.mermaidWebview}
              scrollEnabled={false}
            />
          </View>
        );
      }
      return segmentMarkdownForMobile(segment.content).map((markdownSegment, nestedIndex) => {
        if (markdownSegment.type === 'table_cards') {
          return (
            <MarkdownTableCards
              key={`table-${index}-${nestedIndex}`}
              rows={markdownSegment.rows}
            />
          );
        }

        return (
          <Markdown key={`md-${index}-${nestedIndex}`} style={markdownStyles}>
            {markdownSegment.content || ' '}
          </Markdown>
        );
      });
    });
  }, [colorScheme, markdownStyles, mermaidScript, styles.mermaidWebview, styles.mermaidWrap]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <AmbientBackground variant="explore" />
      <TopBar
        variant="explore"
        title="智能助理"
        dateText={formatDateLabel()}
        actions={(
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="清空当前对话"
            style={styles.actionButton}
            onPress={handleNewChat}
          >
            <MaterialIcons name="delete-sweep" size={18} color={palette.stone400} />
          </Pressable>
        )}
      />

      <View style={styles.flex}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.chatContainer}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={scrollToEnd}
        >
          
          {messages.length === 0 ? (
            <View style={styles.emptyState}>
              <View style={styles.emptyIconWrap}>
                <View style={styles.emptyGlow} />
              <View style={styles.emptyIcon}>
                  <Crown size={28} color={palette.gold500} weight="fill" />
                </View>
              </View>
              <Text style={styles.emptyTitle}>{greeting}</Text>
              <Text style={styles.emptySub}>
                AI 助理随时为您待命。
              </Text>
            </View>
          ) : (
            messages.map((msg) => (
              <View key={msg.id} style={styles.messageBlock}>
                <ChatMessageItem
                  message={msg}
                  renderMarkdown={renderMarkdownWithMermaid}
                  isThinking={!!lastAiMessageId && isThinking && msg.id === lastAiMessageId}
                  footer={
                    !msg.isUser && msg.related && msg.related.length > 0 ? (
                      <SourceList
                        related={msg.related}
                        highlights={msg.highlights || []}
                        expanded={!!expandedSources[msg.id]}
                        onToggle={() => toggleSources(msg.id)}
                        onOpenArticle={openArticle}
                        embedded
                      />
                    ) : undefined
                  }
                />
              </View>
            ))
          )}

          
        </ScrollView>

        <View style={[styles.inputContainer, { paddingBottom: keyboardHeight > 0 ? keyboardHeight : dockOffset }]}>
          <ChatInput value={input} onChangeText={setInput} onSend={sendChatMessage} />
        </View>
      </View>

      <BottomDock
        activeTab="ai"
        onHome={() => router.push('/(tabs)')}
        onAi={() => undefined}
        onSettings={() => router.push('/(tabs)/settings')}
      />

      <ArticleDetailSheet
        visible={sheetVisible}
        article={activeArticle}
        detail={activeDetail}
        onClose={closeArticle}
      />
    </SafeAreaView>
  );
}

function createMarkdownStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const inlineCodeBackground = colorScheme === 'dark' ? colors.stone100 : colors.gold50;
  const inlineCodeText = colorScheme === 'dark' ? colors.stone900 : colors.stone800;
  const blockBackground = colorScheme === 'dark' ? colors.stone100 : colors.stone900;
  const blockText = colorScheme === 'dark' ? colors.stone850 : colors.gold50;
  const quoteBackground = colorScheme === 'dark' ? 'rgba(42,36,19,0.18)' : colors.surfaceWarm;
  const quoteBorder = colorScheme === 'dark' ? colors.gold200 : colors.gold300;
  const tableBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;

  return {
    body: {
      color: colorScheme === 'dark' ? colors.stone850 : colors.stone700,
      fontSize: 15,
      lineHeight: 26,
    },
    paragraph: {
      marginTop: 0,
      marginBottom: 12,
    },
    heading1: {
      marginTop: 4,
      marginBottom: 14,
      fontSize: 23,
      lineHeight: 30,
      fontWeight: '800' as const,
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    heading2: {
      marginTop: 4,
      marginBottom: 12,
      fontSize: 19,
      lineHeight: 26,
      fontWeight: '800' as const,
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
    },
    heading3: {
      marginTop: 2,
      marginBottom: 10,
      fontSize: 16,
      lineHeight: 22,
      fontWeight: '700' as const,
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
    },
    strong: {
      color: colors.imperial600,
      fontWeight: '700' as const,
    },
    link: {
      color: colors.gold500,
    },
    code_inline: {
      backgroundColor: inlineCodeBackground,
      color: inlineCodeText,
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 6,
    },
    fence: {
      marginTop: 8,
      marginBottom: 14,
      paddingHorizontal: 14,
      paddingVertical: 12,
      borderRadius: 16,
      backgroundColor: blockBackground,
      color: blockText,
      fontSize: 13,
      lineHeight: 20,
    },
    code_block: {
      color: blockText,
      fontSize: 13,
      lineHeight: 20,
    },
    blockquote: {
      marginTop: 6,
      marginBottom: 14,
      paddingHorizontal: 14,
      paddingVertical: 12,
      borderRadius: 16,
      backgroundColor: quoteBackground,
      borderLeftWidth: 4,
      borderLeftColor: quoteBorder,
    },
    bullet_list: {
      marginTop: 2,
      marginBottom: 14,
    },
    ordered_list: {
      marginTop: 2,
      marginBottom: 14,
    },
    list_item: {
      marginBottom: 8,
      color: colorScheme === 'dark' ? colors.stone850 : colors.stone700,
    },
    hr: {
      marginTop: 10,
      marginBottom: 18,
      backgroundColor: tableBorder,
      height: 1,
    },
    table: {
      marginTop: 8,
      marginBottom: 14,
      borderWidth: 1,
      borderColor: tableBorder,
      borderRadius: 14,
      overflow: 'hidden' as const,
      opacity: 0.7,
    },
    th: {
      paddingHorizontal: 10,
      paddingVertical: 10,
      backgroundColor: colorScheme === 'dark' ? colors.gold50 : colors.surfaceWarm,
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
      fontWeight: '700' as const,
    },
    td: {
      paddingHorizontal: 10,
      paddingVertical: 10,
      color: colorScheme === 'dark' ? colors.stone850 : colors.stone700,
      borderTopWidth: 1,
      borderTopColor: tableBorder,
    },
  };
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const actionBg = colorScheme === 'dark' ? 'rgba(20, 19, 18, 0.9)' : colors.white;
  const actionBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.gold100;

  return StyleSheet.create({
    safeArea: {
      flex: 1,
      backgroundColor: colors.surface,
    },
    flex: {
      flex: 1,
    },
    chatContainer: {
      flexGrow: 1,
      paddingHorizontal: 16,
      paddingTop: 4,
      paddingBottom: 24,
      gap: 22,
    },
    emptyState: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingTop: 80,
      paddingBottom: 80,
    },
    emptyIconWrap: {
      width: 86,
      height: 86,
      alignItems: 'center',
      justifyContent: 'center',
    },
    emptyGlow: {
      position: 'absolute',
      width: 86,
      height: 86,
      borderRadius: 32,
      backgroundColor: colors.gold400,
      opacity: 0.15,
    },
    emptyIcon: {
      width: 72,
      height: 72,
      borderRadius: 26,
      backgroundColor: colors.white,
      alignItems: 'center',
      justifyContent: 'center',
      ...shadows.glowGoldSoft,
    },
    emptyTitle: {
      marginTop: 18,
      fontSize: 18,
      fontWeight: '700',
      color: colorScheme === 'dark' ? colors.stone900 : colors.stone900,
    },
    emptySub: {
      marginTop: 8,
      fontSize: 12,
      color: colors.stone400,
      textAlign: 'center',
      lineHeight: 18,
    },
    messageBlock: {
      marginTop: 0,
      width: '100%',
    },
    mermaidWrap: {
      marginVertical: 8,
      borderRadius: 16,
      overflow: 'hidden',
      backgroundColor: colors.white,
      borderWidth: 1,
      borderColor: colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : colors.stone100,
    },
    mermaidWebview: {
      width: '100%',
      height: 240,
      backgroundColor: 'transparent',
    },
    actionButton: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: actionBg,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
      borderColor: actionBorder,
      ...shadows.soft,
    },
    inputContainer: {
      paddingHorizontal: 0,
    },
  });
}
