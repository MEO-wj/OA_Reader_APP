import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
<<<<<<< Updated upstream
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
=======
import { useEffect, useState } from 'react';
import { ActivityIndicator, View, StyleSheet } from 'react-native';
import { Stack, useRouter } from 'expo-router';
>>>>>>> Stashed changes
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { useAuthTokenState } from '@/hooks/use-auth-token';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useAuthToken } from '@/hooks/use-auth-token';
import { colors } from '@/constants/palette';
import { registerNotificationTaskIfEnabled } from '@/notifications/notification-task';
import { refreshSessionOnForeground } from '@/services/auth';

export default function RootLayout() {
  const colorScheme = useColorScheme();
<<<<<<< Updated upstream
  const router = useRouter();
  const segments = useSegments();
  const { token, isLoading } = useAuthTokenState();
=======
  const token = useAuthToken();
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);
>>>>>>> Stashed changes

  useEffect(() => {
    registerNotificationTaskIfEnabled();
  }, []);

  useEffect(() => {
<<<<<<< Updated upstream
    const refreshIfActive = () => {
      void refreshSessionOnForeground();
    };

    refreshIfActive();

    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        refreshIfActive();
      }
    });

    return () => {
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (isLoading) return;

    const first = segments[0];
    const inLogin = first === 'login';
    const inTabs = first === '(tabs)';

    if (!token && !inLogin) {
      router.replace('/login');
      return;
    }

    if (token && inLogin) {
      router.replace('/(tabs)');
    }
  }, [isLoading, router, segments, token]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack initialRouteName="login">
        <Stack.Screen name="login" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen 
          name="modal" 
          options={{ 
            presentation: 'modal',
            title: 'Modal',
            headerShown: true
          }} 
        />
      </Stack>
=======
    if (token === null) {
      // 没有token，跳转到登录页面
      router.replace('/login');
    } else {
      // 有token，跳转到主页面
      router.replace('/(tabs)');
    }
    setIsLoading(false);
  }, [token, router]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.gold500} />
        </View>
      ) : (
        <Stack>
          <Stack.Screen name="login" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="modal" options={{ presentation: 'modal', title: 'Modal' }} />
        </Stack>
      )}
>>>>>>> Stashed changes
      <StatusBar style="auto" />
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.surface,
  },
});
