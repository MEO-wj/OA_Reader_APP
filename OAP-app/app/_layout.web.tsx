// 网页端根布局文件
// 主要功能：配置网页端的全局布局、主题、路由守卫
// 特别处理网页端的 localStorage 异步加载和路由守卫逻辑

import { ActivityIndicator, View } from 'react-native';
import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { useEffect, useState } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';
import { Asset } from 'expo-asset';

import { useAuthTokenState } from '@/hooks/use-auth-token';
import { useColorScheme } from '@/hooks/use-color-scheme';

export default function RootLayout() {
  // 设置SEO元数据（组件级别）
  useEffect(() => {
    // 设置title
    document.title = 'OA Reader - 校内OA通知助手';

    // 设置meta标签
    const setMeta = (name: string, content: string) => {
      let meta = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null;
      if (!meta) {
        meta = document.createElement('meta');
        meta.name = name;
        document.head.appendChild(meta);
      }
      meta.content = content;
    };

    setMeta('description', '实时获取校内OA系统通知，AI智能摘要，便捷查阅。支持文章搜索、AI问答、个性化推送。');
    setMeta('keywords', 'OA,校园通知,OA助手,智能摘要,AI问答');

    // iOS Web Clip（添加到主屏幕后全屏打开）
    setMeta('apple-mobile-web-app-capable', 'yes');
    setMeta('apple-mobile-web-app-status-bar-style', 'default');
    setMeta('apple-mobile-web-app-title', 'OA Reader');

    // Android/Chrome 等
    setMeta('mobile-web-app-capable', 'yes');
    setMeta('theme-color', '#ffffff');
    setMeta('format-detection', 'telephone=no');

    // 设置link标签（Web Clip 图标）
    const setLink = (id: string, rel: string, href: string) => {
      let link = document.querySelector(`link#${id}`) as HTMLLinkElement | null;
      if (!link) {
        link = document.createElement('link');
        link.id = id;
        link.rel = rel;
        document.head.appendChild(link);
      }
      link.href = href;
    };

    let manifestObjectUrl: string | null = null;

    try {
      const iconHref = Asset.fromModule(require('../assets/images/icon.png')).uri;
      setLink('oareader-apple-touch-icon', 'apple-touch-icon', iconHref);
      setLink('oareader-icon', 'icon', iconHref);

      const manifest = {
        name: 'OA Reader',
        short_name: 'OA Reader',
        start_url: '/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#ffffff',
        icons: [
          { src: iconHref, sizes: '1024x1024', type: 'image/png', purpose: 'any' },
          { src: iconHref, sizes: '1024x1024', type: 'image/png', purpose: 'maskable' },
        ],
      };

      manifestObjectUrl = URL.createObjectURL(
        new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' })
      );
      setLink('oareader-manifest', 'manifest', manifestObjectUrl);
    } catch {
      // ignore
    }

    // 设置viewport
    let viewport = document.querySelector('meta[name="viewport"]') as HTMLMetaElement | null;
    if (!viewport) {
      viewport = document.createElement('meta');
      viewport.name = 'viewport';
      document.head.appendChild(viewport);
    }
    viewport.content =
      'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover';

    return () => {
      if (manifestObjectUrl) {
        URL.revokeObjectURL(manifestObjectUrl);
      }
    };
  }, []);

  const colorScheme = useColorScheme();
  const router = useRouter();
  const segments = useSegments();
  const { token, isLoading } = useAuthTokenState();

  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) {
      return;
    }

    const setMeta = (name: string, content: string) => {
      let meta = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null;
      if (!meta) {
        meta = document.createElement('meta');
        meta.name = name;
        document.head.appendChild(meta);
      }
      meta.content = content;
    };

    setMeta('theme-color', colorScheme === 'dark' ? '#151718' : '#ffffff');
    setMeta('apple-mobile-web-app-status-bar-style', colorScheme === 'dark' ? 'black' : 'default');
  }, [colorScheme, isMounted]);

  useEffect(() => {
    if (!isMounted || isLoading) return;

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
  }, [isMounted, isLoading, router, segments, token]);

  if (!isMounted) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fff' }}>
        <ActivityIndicator size="large" color="#000" />
      </View>
    );
  }

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
