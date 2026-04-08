import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { CaretLeft, Code, Info, Timer } from 'phosphor-react-native';
import * as TaskManager from 'expo-task-manager';
import { isExpoGo } from '@/notifications/notification-env';
import { AmbientBackground } from '@/components/ambient-background';
import { TopBar } from '@/components/top-bar';
import { colors } from '@/constants/palette';
import { shadows } from '@/constants/shadows';
import { useUserProfile } from '@/hooks/use-user-profile';
import { triggerTestNotification, delayedPollTest } from '@/notifications/notification-task';
import {
  clearNotificationLogs,
  getNotificationLogs,
  NotificationPollLog,
} from '@/notifications/notification-log';
import {
  getLastSince,
  getNextAllowedAt,
  getNotificationsEnabled,
} from '@/notifications/notification-storage';
import { formatDateLabel } from '@/utils/date';

const statusLabels: Record<string, string> = {
  unsupported: '不支持',
  disabled: '已关闭',
  out_of_window: '不在时间窗',
  rate_limited: '节流中',
  auth_expired: '登录过期',
  not_modified: '无变化',
  http_error: '请求失败',
  no_articles: '空列表',
  no_new_items: '无新增',
  new_articles: '有新增',
  exception: '异常',
  manual_test: '手动测试',
  manual_test_blocked: '测试受限',
  delayed_test_scheduled: '延迟测试已启动',
  delayed_test_result: '延迟测试结果',
  delayed_test_failed: '延迟测试失败',
};

function formatLogTime(value?: string) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatTimestamp(ms?: number | null) {
  if (!ms) {
    return '-';
  }
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) {
    return '-';
  }
  return date.toLocaleString();
}

function isWithinWindowNow() {
  const hour = new Date().getHours();
  return hour >= 8 && hour < 24;
}

type DiagnosticStatus = {
  platform: string;
  isExpoGo: boolean;
  notificationsEnabled: boolean;
  taskRegistered: boolean;
  lastSince: string | null;
  nextAllowedAt: string | null;
  inTimeWindow: boolean;
};

export default function DeveloperSettingsScreen() {
  const router = useRouter();
  const { profile } = useUserProfile();
  const displayName = profile?.display_name || profile?.username || '';
  const isAdmin = displayName.trim().toLowerCase() === 'admin';
  const [logs, setLogs] = useState<NotificationPollLog[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticStatus | null>(null);
  const [delayedTestRemaining, setDelayedTestRemaining] = useState<number | null>(null);
  const [delayedTestRunning, setDelayedTestRunning] = useState(false);
  const isMountedRef = useRef(true);

  const loadDiagnostics = useCallback(async () => {
    const enabled = await getNotificationsEnabled();
    const lastSince = await getLastSince();
    const nextAllowedAt = await getNextAllowedAt();
    let taskRegistered = false;
    try {
      const tasks = await TaskManager.getRegisteredTasksAsync();
      taskRegistered = tasks.some((task) => task.taskName === 'oap-articles-background-fetch');
    } catch {
      taskRegistered = false;
    }
    setDiagnostics({
      platform: Platform.OS,
      isExpoGo: isExpoGo(),
      notificationsEnabled: enabled,
      taskRegistered,
      lastSince: formatTimestamp(lastSince),
      nextAllowedAt: formatTimestamp(nextAllowedAt),
      inTimeWindow: isWithinWindowNow(),
    });
  }, []);

  const loadLogs = useCallback(async () => {
    const next = await getNotificationLogs();
    setLogs(next);
  }, []);

  useEffect(() => {
    loadDiagnostics();
    loadLogs();
  }, [loadDiagnostics, loadLogs]);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleTestNotification = useCallback(async () => {
    if (Platform.OS !== 'android') {
      Alert.alert('提示', '仅 Android 支持系统通知测试。');
      return;
    }
    const result = await triggerTestNotification();
    if (!result.ok) {
      Alert.alert('提示', '当前环境不支持通知测试，请使用开发构建。');
    } else {
      Alert.alert('提示', '已触发模拟通知。');
    }
    await loadLogs();
    await loadDiagnostics();
  }, [loadLogs, loadDiagnostics]);

  const handleClearLogs = useCallback(async () => {
    await clearNotificationLogs();
    await loadLogs();
  }, [loadLogs]);

  const handleDelayedPollTest = useCallback(async () => {
    if (Platform.OS !== 'android') {
      Alert.alert('提示', '仅 Android 支持延迟轮询测试。');
      return;
    }
    setDelayedTestRunning(true);
    setDelayedTestRemaining(60);
    const result = await delayedPollTest(60 * 1000, (remaining) => {
      if (isMountedRef.current) {
        setDelayedTestRemaining(remaining);
      }
    });
    if (!isMountedRef.current) {
      return;
    }
    setDelayedTestRunning(false);
    setDelayedTestRemaining(null);
    if (!result.ok && result.status === 'delayed_test_failed') {
      Alert.alert('提示', '当前环境不支持延迟测试，请使用开发构建。');
    }
    await loadLogs();
    await loadDiagnostics();
  }, [loadLogs, loadDiagnostics]);

  const logItems = useMemo(() => logs, [logs]);

  if (!isAdmin) {
    return (
      <View style={styles.safeArea}>
        <AmbientBackground variant="explore" />
        <TopBar variant="explore" title="开发者模式" dateText={formatDateLabel()} />
        <View style={styles.content}>
          <View style={styles.card}>
            <Text style={styles.cardRowText}>仅管理员可访问该页面。</Text>
          </View>
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <CaretLeft size={16} color={colors.stone500} weight="bold" />
            <Text style={styles.backText}>返回</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.safeArea}>
      <AmbientBackground variant="explore" />
      <TopBar variant="explore" title="开发者模式" dateText={formatDateLabel()} />

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* 状态诊断卡片 */}
        {diagnostics && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <View style={styles.cardIcon}>
                <Info size={16} color={colors.stone600} weight="fill" />
              </View>
              <Text style={styles.cardTitle}>状态诊断</Text>
            </View>
            <View style={styles.diagList}>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>平台</Text>
                <Text style={styles.diagValue}>{diagnostics.platform}</Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>运行环境</Text>
                <Text style={[styles.diagValue, diagnostics.isExpoGo && styles.diagError]}>
                  {diagnostics.isExpoGo ? 'Expo Go (不支持)' : '开发构建'}
                </Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>通知开关</Text>
                <Text style={[styles.diagValue, !diagnostics.notificationsEnabled && styles.diagWarning]}>
                  {diagnostics.notificationsEnabled ? '已开启' : '已关闭'}
                </Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>后台任务</Text>
                <Text style={[styles.diagValue, !diagnostics.taskRegistered && styles.diagWarning]}>
                  {diagnostics.taskRegistered ? '已注册' : '未注册'}
                </Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>时间窗</Text>
                <Text style={[styles.diagValue, !diagnostics.inTimeWindow && styles.diagWarning]}>
                  {diagnostics.inTimeWindow ? '在时间窗内 (8:00-24:00)' : '不在时间窗'}
                </Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>上次轮询时间</Text>
                <Text style={styles.diagValue}>{diagnostics.lastSince}</Text>
              </View>
              <View style={styles.diagRow}>
                <Text style={styles.diagLabel}>下次允许轮询</Text>
                <Text style={styles.diagValue}>{diagnostics.nextAllowedAt}</Text>
              </View>
            </View>
          </View>
        )}

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.cardIcon}>
              <Code size={16} color={colors.stone600} weight="fill" />
            </View>
            <Text style={styles.cardTitle}>通知调试</Text>
          </View>
          <Text style={styles.cardDesc}>用于模拟系统通知与查看轮询记录。</Text>
          <View style={styles.cardActions}>
            <Pressable onPress={handleTestNotification} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>模拟新文章通知</Text>
            </Pressable>
            <Pressable onPress={handleClearLogs} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>清空记录</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.cardIcon}>
              <Timer size={16} color={colors.stone600} weight="fill" />
            </View>
            <Text style={styles.cardTitle}>延迟轮询测试</Text>
          </View>
          <Text style={styles.cardDesc}>
            点击后等待1分钟，然后执行一次真实的文章检查请求。无论是否有更新都会弹出系统通知。
          </Text>
          {delayedTestRunning && delayedTestRemaining !== null && (
            <View style={styles.countdownContainer}>
              <Text style={styles.countdownText}>
                {delayedTestRemaining > 0 ? `${delayedTestRemaining} 秒后执行...` : '执行中...'}
              </Text>
            </View>
          )}
          <View style={styles.cardActions}>
            <Pressable
              onPress={handleDelayedPollTest}
              style={[styles.primaryButton, delayedTestRunning && styles.buttonDisabled]}
              disabled={delayedTestRunning}
            >
              <Text style={styles.primaryButtonText}>
                {delayedTestRunning ? '测试运行中...' : '启动延迟测试'}
              </Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.logCard}>
          <Text style={styles.logTitle}>轮询记录</Text>
          {logItems.length === 0 ? (
            <Text style={styles.logEmpty}>暂无记录</Text>
          ) : (
            <View style={styles.logList}>
              {logItems.map((item) => (
                <View key={item.id} style={styles.logRow}>
                  <View style={styles.logRowHeader}>
                    <Text style={styles.logTime}>{formatLogTime(item.at)}</Text>
                    <Text style={styles.logStatus}>
                      {statusLabels[item.status] || item.status}
                    </Text>
                  </View>
                  {item.detail ? <Text style={styles.logDetail}>{item.detail}</Text> : null}
                </View>
              ))}
            </View>
          )}
        </View>

        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <CaretLeft size={16} color={colors.stone500} weight="bold" />
          <Text style={styles.backText}>返回</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  content: {
    paddingTop: 16,
    paddingHorizontal: 20,
    gap: 16,
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.8)',
    padding: 16,
    gap: 12,
    ...shadows.cardSoft,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  cardIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: colors.stone100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.stone800,
  },
  cardDesc: {
    fontSize: 12,
    color: colors.stone600,
  },
  cardActions: {
    flexDirection: 'row',
    gap: 12,
    flexWrap: 'wrap',
  },
  primaryButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 999,
    backgroundColor: colors.gold400,
  },
  primaryButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.stone900,
  },
  secondaryButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 999,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.stone200,
  },
  secondaryButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.stone600,
  },
  logCard: {
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.8)',
    padding: 16,
    gap: 12,
    ...shadows.cardSoft,
  },
  logTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.stone800,
  },
  logEmpty: {
    fontSize: 12,
    color: colors.stone500,
  },
  logList: {
    gap: 10,
  },
  logRow: {
    padding: 12,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.9)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.7)',
  },
  logRowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  logTime: {
    fontSize: 11,
    color: colors.stone500,
  },
  logStatus: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.stone700,
  },
  logDetail: {
    marginTop: 6,
    fontSize: 12,
    color: colors.stone700,
  },
  backButton: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 999,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.stone100,
  },
  backText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.stone500,
  },
  cardRowText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.stone700,
  },
  diagList: {
    gap: 8,
  },
  diagRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  diagLabel: {
    fontSize: 12,
    color: colors.stone600,
  },
  diagValue: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.stone800,
  },
  diagWarning: {
    color: colors.gold600,
  },
  diagError: {
    color: colors.imperial600,
  },
  countdownContainer: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: colors.stone100,
    alignItems: 'center',
  },
  countdownText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.stone700,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
});
