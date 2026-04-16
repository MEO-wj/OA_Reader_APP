import React from 'react';
import { StyleSheet, View } from 'react-native';

type LoginShellCardProps = {
  left: React.ReactNode;
  right: React.ReactNode;
};

export function LoginShellCard({ left, right }: LoginShellCardProps) {
  return (
    <View style={styles.wrap}>
      <View style={styles.left}>{left}</View>
      <View style={styles.right}>{right}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: '100%',
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 40,
    paddingHorizontal: 48,
    paddingVertical: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 36,
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 10 },
    elevation: 10,
  },
  left: {
    flex: 1,
    minWidth: 260,
    justifyContent: 'center',
  },
  right: {
    flex: 1,
    minWidth: 320,
    maxWidth: 520,
  },
});

