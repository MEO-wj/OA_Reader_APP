import React, { type PropsWithChildren } from 'react';
import { ScrollViewStyleReset } from 'expo-router/html';

export default function Html({ children }: PropsWithChildren) {
  return (
    <html lang="zh-CN">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <title>OA Reader - 校内OA通知助手</title>
        <meta
          name="description"
          content="实时获取校内OA系统通知，AI智能摘要，便捷查阅。支持文章搜索、AI问答、个性化推送。"
        />
        <meta name="keywords" content="OA,校园通知,OA助手,智能摘要,AI问答" />

        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover"
        />

        {/* iOS Web Clip（添加到主屏幕后全屏打开） */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="OA Reader" />

        {/* Android/Chrome 等 */}
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="theme-color" content="#ffffff" />
        <meta name="format-detection" content="telephone=no" />

        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  );
}

