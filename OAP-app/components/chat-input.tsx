import React, { useMemo } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { ArrowUp } from 'phosphor-react-native';

import { shadows } from '@/constants/shadows';
import type { Palette } from '@/constants/palette';
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
    paddingHorizontal: 18,
    paddingBottom: 12,
  },
  inputShell: {
    borderRadius: 26,
    padding: 6,
    backgroundColor: shellBackground,
    borderWidth: 1,
    borderColor: shellBorder,
  },
  input: {
    paddingLeft: 16,
    paddingRight: 56,
    paddingVertical: 12,
    fontSize: 14,
    color: colorScheme === 'dark' ? colors.stone900 : colors.stone800,
  },
  sendButton: {
    position: 'absolute',
    right: 10,
    top: 8,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.imperial600,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadows.glowImperialStrong,
  },
  });
}
