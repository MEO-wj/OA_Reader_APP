import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { useAuthTokenState } from '@/hooks/use-auth-token';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { registerNotificationTaskIfEnabled } from '@/notifications/notification-task';
import { refreshSessionOnForeground } from '@/services/auth';

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const router = useRouter();
  const segments = useSegments();
  const { token, isLoading } = useAuthTokenState();

  useEffect(() => {
    registerNotificationTaskIfEnabled();
  }, []);

  useEffect(() => {
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
      <StatusBar style="auto" />
    </ThemeProvider>
  );
}
