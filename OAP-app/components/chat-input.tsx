import React, { useMemo } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { ArrowUp } from 'phosphor-react-native';

import { shadows } from '@/constants/shadows';
import type { Palette } from '@/constants/palette';
import { CHAT_INPUT_LAYOUT } from '@/constants/layout-metrics';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';

type ChatInputProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSend: () => void;
};

export function ChatInput({ value, onChangeText, onSend }: ChatInputProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const styles = useMemo(() => createStyles(palette, colorScheme), [colorScheme, palette]);

  return (
    <View style={styles.inputWrap}>
      <View style={styles.inputShell}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder="输入指令..."
          placeholderTextColor={palette.stone400}
          style={styles.input}
          onSubmitEditing={onSend}
          returnKeyType="send"
        />
        <Pressable style={styles.sendButton} onPress={onSend}>
          <ArrowUp size={16} color={palette.white} weight="bold" />
        </Pressable>
      </View>
    </View>
  );
}

function createStyles(colors: Palette, colorScheme: 'light' | 'dark') {
  const shellBackground =
    colorScheme === 'dark' ? 'rgba(20, 19, 18, 0.92)' : 'rgba(255,255,255,0.7)';
  const shellBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.8)';

  return StyleSheet.create({
  inputWrap: {
    paddingHorizontal: CHAT_INPUT_LAYOUT.outerHorizontal,
    paddingBottom: CHAT_INPUT_LAYOUT.outerBottom,
  },
  inputShell: {
    borderRadius: CHAT_INPUT_LAYOUT.shellRadius,
    padding: CHAT_INPUT_LAYOUT.shellPadding,
    backgroundColor: shellBackground,
    borderWidth: 1,
    borderColor: shellBorder,
  },
  input: {
    paddingLeft: CHAT_INPUT_LAYOUT.inputHorizontalLeft,
    paddingRight: CHAT_INPUT_LAYOUT.inputHorizontalRight,
    paddingVertical: CHAT_INPUT_LAYOUT.inputVertical,
    fontSize: 14,
    color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
  },
  sendButton: {
    position: 'absolute',
    right: CHAT_INPUT_LAYOUT.sendButtonRight,
    top: CHAT_INPUT_LAYOUT.sendButtonTop,
    width: CHAT_INPUT_LAYOUT.sendButtonSize,
    height: CHAT_INPUT_LAYOUT.sendButtonSize,
    borderRadius: CHAT_INPUT_LAYOUT.sendButtonSize / 2,
    backgroundColor: colors.imperial600,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadows.glowImperialStrong,
  },
  });
}
