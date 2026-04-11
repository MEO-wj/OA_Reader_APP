
import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { AmbientBackground } from '@/components/ambient-background';
import { colors } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { getApiBaseUrl } from '@/services/api';
import { setAuthToken } from '@/hooks/use-auth-token';
import { setRefreshToken, setUserProfileRaw } from '@/storage/auth-storage';

export default function LoginScreen() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const apiBaseUrl = getApiBaseUrl();

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setError('请输入账号和密码');
      return;
    }

    setError('');
    setIsSubmitting(true);

    try {
      const resp = await fetch(`${apiBaseUrl}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        setError(data?.error || '登录失败，请检查账号或密码');
        return;
      }

      await setRefreshToken(data.refresh_token || null);
      await setUserProfileRaw(JSON.stringify(data.user || {}));
      await setAuthToken(data.access_token || null);

      router.replace('/(tabs)');
    } catch (err) {
      console.error('[Login] 登录异常:', err);
      setError('网络异常，请稍后重试');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <AmbientBackground variant="login" />

      <KeyboardAvoidingView
        behavior={Platform.select({ ios: 'padding', android: undefined })}
        style={styles.flex}>
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled">
          <View style={styles.brandBlock}>
            <View style={styles.logoBox}>
              <MaterialCommunityIcons name="shield-check" size={28} color={colors.gold50} />
            </View>
            <Text style={styles.title}>
              OA{'\n'}
              <Text style={styles.titleAccent}>Reader.</Text>
            </Text>
            <Text style={styles.subtitle}>每日摘要 · 尊享智能</Text>
          </View>

          <View style={styles.formBlock}>
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>账号</Text>
              <View style={styles.inputShell}>
                <TextInput
                  value={username}
                  onChangeText={setUsername}
                  placeholder="请输入账号"
                  placeholderTextColor={colors.stone300}
                  autoCapitalize="none"
                  style={styles.input}
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>密码</Text>
              <View style={styles.inputShell}>
                <TextInput
                  value={password}
                  onChangeText={setPassword}
                  placeholder="请输入密码"
                  placeholderTextColor={colors.stone300}
                  secureTextEntry
                  style={styles.input}
                />
              </View>
            </View>

            <Pressable onPress={handleLogin} style={({ pressed }) => [
              styles.loginButton,
              isSubmitting && styles.loginButtonDisabled,
              pressed && styles.loginButtonPressed,
            ]} disabled={isSubmitting}>
              {isSubmitting ? (
                <View style={styles.loadingRow}>
                  <ActivityIndicator size="small" color={colors.gold400} />
                  <Text style={styles.loginButtonText}>登录中...</Text>
                </View>
              ) : (
                <>
                  <Text style={styles.loginButtonText}>登录</Text>
                  <View style={styles.loginButtonIcon}>
                    <MaterialCommunityIcons name="chevron-right" size={22} color={colors.gold400} />
                  </View>
                </>
              )}
            </Pressable>
            {!!error && <Text style={styles.errorText}>{error}</Text>}

            <View style={styles.secureRow}>
              <MaterialCommunityIcons name="shield-check" size={14} color={colors.gold500} />
              <Text style={styles.secureText}>ENTERPRISE SECURE</Text>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  flex: {
    flex: 1,
  },
  container: {
    flexGrow: 1,
    paddingHorizontal: 28,
    paddingTop: 44,
    paddingBottom: 72,
    justifyContent: 'flex-start',
  },
  brandBlock: {
    gap: 12,
    marginBottom: 36,
  },
  logoBox: {
    width: 64,
    height: 64,
    borderRadius: 18,
    backgroundColor: colors.imperial600,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.3)',
    ...shadows.logo,
  },
  title: {
    fontSize: 42,
    fontWeight: '800',
    color: colors.stone900,
    lineHeight: 46,
    letterSpacing: -1,
  },
  titleAccent: {
    color: colors.gold500,
    fontWeight: '800',
  },
  subtitle: {
    color: colors.stone500,
    fontSize: 16,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  formBlock: {
    gap: 18,
    paddingBottom: 16,
  },
  inputGroup: {
    gap: 8,
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.imperial600,
    letterSpacing: 1,
  },
  inputShell: {
    backgroundColor: 'rgba(255,255,255,0.7)',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.85)',
    paddingHorizontal: 20,
    paddingVertical: 4,
    ...shadows.softSubtle,
  },
  input: {
    height: 48,
    fontSize: 15,
    color: colors.stone900,
    fontWeight: '500',
  },
  loginButton: {
    height: 64,
    backgroundColor: colors.stone900,
    borderRadius: 32,
    paddingLeft: 28,
    paddingRight: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: colors.stone800,
    ...shadows.primary,
  },
  loginButtonPressed: {
    transform: [{ scale: 0.98 }],
  },
  loginButtonDisabled: {
    opacity: 0.8,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  loginButtonText: {
    color: colors.gold50,
    fontSize: 18,
    fontWeight: '700',
  },
  loginButtonIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secureRow: {
    marginTop: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    opacity: 0.7,
  },
  secureText: {
    fontSize: 10,
    letterSpacing: 2.5,
    fontWeight: '700',
    color: colors.stone500,
  },
  errorText: {
    color: colors.imperial600,
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
});
