import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import { getApiBaseUrl } from '@/services/api';
import { clearAuthStorage, getAccessToken } from '@/storage/auth-storage';
import { setAuthToken } from '@/hooks/use-auth-token';
import {
  getLastSince,
  getNextAllowedAt,
  getNotificationsEnabled,
  resetNotificationState,
  setLastSince,
  setNextAllowedAt,
} from '@/notifications/notification-storage';
import { isExpoGo } from '@/notifications/notification-env';
import { appendNotificationLog } from '@/notifications/notification-log';

const TASK_NAME = 'oap-articles-background-fetch';
const CHANNEL_ID = 'oa-updates';
const BASE_INTERVAL_MS = 30 * 60 * 1000; // 30分钟基础间隔
const JITTER_RANGE_MS = 15 * 60 * 1000; // ±15分钟随机抖动

let notificationHandlerReady = false;

function ensureNotificationHandler(Notifications: typeof import('expo-notifications')) {
  if (notificationHandlerReady) {
    return;
  }
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
  notificationHandlerReady = true;
}

async function getNotificationsModule() {
  if (Platform.OS !== 'android' || isExpoGo()) {
    return null;
  }
  return await import('expo-notifications');
}

function isWithinWindow(date: Date) {
  const hour = date.getHours();
  return hour >= 8 && hour < 24;
}

function buildNextAllowedAt(now: number) {
  // 30分钟基础 + 随机±15分钟（总间隔在15-45分钟之间）
  const jitter = Math.floor((Math.random() - 0.5) * 2 * JITTER_RANGE_MS);
  return now + BASE_INTERVAL_MS + jitter;
}

async function ensureAndroidChannel() {
  const Notifications = await getNotificationsModule();
  if (!Notifications) {
    return;
  }
  await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
    name: 'OA通知',
    importance: Notifications.AndroidImportance.DEFAULT,
  });
}

async function notifySingle(summary: string) {
  const Notifications = await getNotificationsModule();
  if (!Notifications) {
    return;
  }
  ensureNotificationHandler(Notifications);
  await Notifications.scheduleNotificationAsync({
    content: {
      title: '最新OA',
      body: summary,
    },
    trigger: null,
  });
}

async function notifyCombined(summaries: string[], total: number) {
  const Notifications = await getNotificationsModule();
  if (!Notifications) {
    return;
  }
  ensureNotificationHandler(Notifications);
  const body = summaries.join('\n');
  await Notifications.scheduleNotificationAsync({
    content: {
      title: `最新OA（${total}条）`,
      body,
    },
    trigger: null,
  });
}

async function notifyAuthExpired() {
  const Notifications = await getNotificationsModule();
  if (!Notifications) {
    return;
  }
  ensureNotificationHandler(Notifications);
  await Notifications.scheduleNotificationAsync({
    content: {
      title: '登录已过期',
      body: '长时间未使用已自动退出，请打开应用重新登录或刷新。',
    },
    trigger: null,
  });
}

TaskManager.defineTask(TASK_NAME, async () => {
  const startedAt = new Date().toISOString();
  const record = async (status: string, detail?: string, count?: number) => {
    try {
      await appendNotificationLog({ at: startedAt, status, detail, count });
    } catch {
      return;
    }
  };

  if (Platform.OS !== 'android' || isExpoGo()) {
    await record('unsupported', '非 Android 或 Expo Go');
    return BackgroundFetch.BackgroundFetchResult.NoData;
  }
  const enabled = await getNotificationsEnabled();
  if (!enabled) {
    await record('disabled', '通知未开启');
    return BackgroundFetch.BackgroundFetchResult.NoData;
  }

  const now = new Date();
  if (!isWithinWindow(now)) {
    await record('out_of_window', '不在通知时间窗');
    return BackgroundFetch.BackgroundFetchResult.NoData;
  }

  const nowMs = now.getTime();
  const nextAllowedAt = await getNextAllowedAt();
  if (nextAllowedAt && nowMs < nextAllowedAt) {
    await record('rate_limited', '未到下次允许轮询时间');
    return BackgroundFetch.BackgroundFetchResult.NoData;
  }

  try {
    const since = await getLastSince();
    const params = since ? `?since=${since}` : '';
    const headers: Record<string, string> = {};
    if (since) {
      headers['If-Modified-Since'] = new Date(since).toUTCString();
    }
    const token = await getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const resp = await fetch(`${getApiBaseUrl()}/articles/today${params}`, { headers });

    if (resp.status === 401) {
      await notifyAuthExpired();
      await clearAuthStorage();
      await setAuthToken(null);
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await record('auth_expired', '401 未授权');
      return BackgroundFetch.BackgroundFetchResult.Failed;
    }

    if (resp.status === 304) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await record('not_modified', '304 无变化');
      return BackgroundFetch.BackgroundFetchResult.NoData;
    }

    if (!resp.ok) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await record('http_error', `HTTP ${resp.status}`);
      return BackgroundFetch.BackgroundFetchResult.Failed;
    }

    const data = await resp.json();
    const articles = Array.isArray(data?.articles) ? data.articles : [];
    if (articles.length === 0) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await record('no_articles', '返回空列表');
      return BackgroundFetch.BackgroundFetchResult.NoData;
    }

    const parsed = articles
      .map((article: { created_at?: string; summary?: string }) => {
        const createdAt = article.created_at ? new Date(article.created_at).getTime() : 0;
        return {
          createdAt,
          summary: article.summary || '暂无摘要',
        };
      })
      .filter((item: { createdAt: number }) => item.createdAt > 0)
      .sort((a: { createdAt: number }, b: { createdAt: number }) => b.createdAt - a.createdAt);

    const newItems = since ? parsed.filter((item) => item.createdAt > since) : parsed;
    if (newItems.length === 0) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await record('no_new_items', '无新增文章');
      return BackgroundFetch.BackgroundFetchResult.NoData;
    }

    await ensureAndroidChannel();

    if (newItems.length <= 2) {
      for (const item of newItems) {
        await notifySingle(item.summary);
      }
    } else {
      const summaries = newItems.slice(0, 3).map((item) => item.summary);
      await notifyCombined(summaries, newItems.length);
    }

    const maxCreatedAt = Math.max(...newItems.map((item) => item.createdAt));
    await setLastSince(maxCreatedAt);
    await setNextAllowedAt(buildNextAllowedAt(nowMs));
    await record('new_articles', `新增 ${newItems.length} 条`, newItems.length);
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch (error) {
    await setNextAllowedAt(buildNextAllowedAt(nowMs));
    await record('exception', error instanceof Error ? error.message : '未知异常');
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerNotificationTask() {
  if (Platform.OS !== 'android' || isExpoGo()) {
    return;
  }
  const tasks = await BackgroundFetch.getRegisteredTasksAsync();
  const alreadyRegistered = tasks.some((task) => task.taskName === TASK_NAME);
  if (alreadyRegistered) {
    return;
  }
  await BackgroundFetch.registerTaskAsync(TASK_NAME, {
    minimumInterval: BASE_INTERVAL_MS / 1000,
    stopOnTerminate: false,
    startOnBoot: true,
  });
}

export async function unregisterNotificationTask() {
  if (Platform.OS !== 'android' || isExpoGo()) {
    return;
  }
  await BackgroundFetch.unregisterTaskAsync(TASK_NAME);
}

export async function disableNotifications() {
  const Notifications = await getNotificationsModule();
  if (Notifications) {
    await Notifications.cancelAllScheduledNotificationsAsync();
  }
  await unregisterNotificationTask();
  await resetNotificationState();
}

export async function registerNotificationTaskIfEnabled() {
  if (Platform.OS !== 'android' || isExpoGo()) {
    return;
  }
  const enabled = await getNotificationsEnabled();
  if (enabled) {
    await registerNotificationTask();
  }
}

export async function triggerTestNotification() {
  const now = new Date().toISOString();
  if (Platform.OS !== 'android' || isExpoGo()) {
    try {
      await appendNotificationLog({ at: now, status: 'manual_test_blocked', detail: '非 Android 或 Expo Go' });
    } catch {
      return { ok: false, reason: 'unsupported' };
    }
    return { ok: false, reason: 'unsupported' };
  }
  await ensureAndroidChannel();
  await notifySingle('这是一条模拟的通知，用于测试系统弹窗。');
  try {
    await appendNotificationLog({ at: now, status: 'manual_test', detail: '已触发模拟通知' });
  } catch {
    return { ok: true };
  }
  return { ok: true };
}

async function notifyTestResult(body: string) {
  const Notifications = await getNotificationsModule();
  if (!Notifications) {
    return;
  }
  ensureNotificationHandler(Notifications);
  await Notifications.scheduleNotificationAsync({
    content: {
      title: '延迟轮询测试结果',
      body,
    },
    trigger: null,
  });
}

/**
 * 延迟轮询测试：点击后等待指定时间，然后执行一次真实的文章检查请求
 * 无论是否有更新都会弹出通知，用于测试后台轮询和通知功能
 *
 * @param delayMs 延迟时间（毫秒），默认 1 分钟
 * @param onProgress 进度回调，返回剩余秒数
 * @returns 测试结果
 */
export async function delayedPollTest(
  delayMs: number = 60 * 1000,
  onProgress?: (remainingSeconds: number) => void
): Promise<{ ok: boolean; status: string; detail: string; count?: number }> {
  const startTime = new Date().toISOString();
  const totalSeconds = Math.floor(delayMs / 1000);

  // 记录测试开始
  try {
    await appendNotificationLog({
      at: startTime,
      status: 'delayed_test_scheduled',
      detail: `延迟测试已启动，${totalSeconds}秒后执行`,
    });
  } catch {
    // 忽略日志记录失败
  }

  // 倒计时
  let remainingSeconds = totalSeconds;
  const intervalMs = 1000;
  const intervalId = setInterval(() => {
    remainingSeconds--;
    if (onProgress) {
      onProgress(remainingSeconds);
    }
  }, intervalMs);

  await new Promise((resolve) => setTimeout(resolve, delayMs));
  clearInterval(intervalId);

  // 执行时间到
  const executionTime = new Date().toISOString();
  const nowMs = Date.now();

  // 平台检查
  if (Platform.OS !== 'android' || isExpoGo()) {
    try {
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_failed',
        detail: '非 Android 或 Expo Go',
      });
    } catch {
    }
    return { ok: false, status: 'delayed_test_failed', detail: '非 Android 或 Expo Go' };
  }

  await ensureAndroidChannel();

  // 获取 token
  const token = await getAccessToken();

  // 获取上次轮询时间
  const since = await getLastSince();
  const params = since ? `?since=${since}` : '';
  const headers: Record<string, string> = {};
  if (since) {
    headers['If-Modified-Since'] = new Date(since).toUTCString();
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const resp = await fetch(`${getApiBaseUrl()}/articles/today${params}`, { headers });

    // 处理 401
    if (resp.status === 401) {
      await notifyAuthExpired();
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_result',
        detail: '登录已过期 (401)',
      });
      return { ok: true, status: 'delayed_test_result', detail: '登录已过期 (401)' };
    }

    // 处理 304
    if (resp.status === 304) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await notifyTestResult('检查完成：无新文章 (304 未修改)');
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_result',
        detail: '无新文章 (304)',
      });
      return { ok: true, status: 'delayed_test_result', detail: '无新文章 (304)' };
    }

    // 处理其他错误状态码
    if (!resp.ok) {
      const errorMsg = `请求失败 (HTTP ${resp.status})`;
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await notifyTestResult(errorMsg);
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_result',
        detail: errorMsg,
      });
      return { ok: true, status: 'delayed_test_result', detail: errorMsg };
    }

    // 解析响应
    const data = await resp.json();
    const articles = Array.isArray(data?.articles) ? data.articles : [];

    // 空列表
    if (articles.length === 0) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await notifyTestResult('检查完成：返回空列表');
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_result',
        detail: '返回空列表',
        count: 0,
      });
      return { ok: true, status: 'delayed_test_result', detail: '返回空列表', count: 0 };
    }

    // 解析文章
    const NotificationsModule = await getNotificationsModule();
    if (NotificationsModule) {
      ensureNotificationHandler(NotificationsModule);
    }

    const parsed = articles
      .map((article: { created_at?: string; summary?: string; title?: string }) => {
        const createdAt = article.created_at ? new Date(article.created_at).getTime() : 0;
        return {
          createdAt,
          summary: article.summary || article.title || '暂无标题',
        };
      })
      .filter((item: { createdAt: number }) => item.createdAt > 0)
      .sort((a: { createdAt: number }, b: { createdAt: number }) => b.createdAt - a.createdAt);

    // 计算新增文章
    const newItems = since ? parsed.filter((item) => item.createdAt > since) : parsed;

    // 发送通知
    if (newItems.length === 0) {
      await setNextAllowedAt(buildNextAllowedAt(nowMs));
      await notifyTestResult(`检查完成：共 ${articles.length} 篇文章，无新增`);
      await appendNotificationLog({
        at: executionTime,
        status: 'delayed_test_result',
        detail: `共 ${articles.length} 篇，无新增`,
        count: 0,
      });
      return { ok: true, status: 'delayed_test_result', detail: `共 ${articles.length} 篇，无新增`, count: 0 };
    }

    // 有新增文章
    if (newItems.length <= 2) {
      for (const item of newItems) {
        await notifySingle(item.summary);
      }
    } else {
      const summaries = newItems.slice(0, 3).map((item) => item.summary);
      await notifyCombined(summaries, newItems.length);
    }

    // 发送测试完成通知
    const maxCreatedAt = Math.max(...newItems.map((item) => item.createdAt));
    await setLastSince(maxCreatedAt);
    await setNextAllowedAt(buildNextAllowedAt(nowMs));
    await notifyTestResult(`检查完成：发现 ${newItems.length} 篇新文章`);

    await appendNotificationLog({
      at: executionTime,
      status: 'delayed_test_result',
      detail: `发现 ${newItems.length} 篇新文章`,
      count: newItems.length,
    });
    return {
      ok: true,
      status: 'delayed_test_result',
      detail: `发现 ${newItems.length} 篇新文章`,
      count: newItems.length,
    };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : '未知异常';
    await setNextAllowedAt(buildNextAllowedAt(nowMs));
    await notifyTestResult(`检查失败：${errorMsg}`);
    await appendNotificationLog({
      at: executionTime,
      status: 'delayed_test_result',
      detail: `异常: ${errorMsg}`,
    });
    return { ok: false, status: 'delayed_test_result', detail: `异常: ${errorMsg}` };
  }
}
