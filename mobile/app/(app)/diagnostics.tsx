import React, { useState } from 'react'
import { ScrollView, Share, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import {
  clearDiagnostics,
  formatDiagnosticsReport,
  getBufferedReports,
  getRequestLog,
  type BufferedReport,
  type RequestLogEntry,
} from '../../src/lib/monitor'
import { colors, spacing, typography } from '../../src/theme/tokens'

/**
 * Operator/tester diagnostics (WS4-F1 / WS4-F2).
 *
 * Renders what the monitor retained on-device — crash reports and recent API
 * calls with their `X-Request-ID` — and lets the tester export it to the pilot
 * support channel. Everything shown is redacted at capture time; this screen
 * only formats. There is no network sink: the tester sends it deliberately.
 *
 * Copy is local to this file rather than `src/i18n/vi.ts` because this is an
 * operator surface, not a patient journey, and the shared dictionary is being
 * edited concurrently.
 */

const copy = {
  title: 'Nhật ký kỹ thuật',
  subtitle:
    'Thông tin kỹ thuật đã được ẩn dữ liệu nhạy cảm. Gửi kèm khi báo lỗi để đội ngũ đối chiếu với log máy chủ.',
  errors: 'Sự cố ứng dụng',
  requests: 'Yêu cầu gần đây',
  empty: 'Chưa ghi nhận sự cố hay yêu cầu nào trong phiên này.',
  share: 'Gửi nhật ký cho hỗ trợ',
  refresh: 'Làm mới',
  clear: 'Xoá nhật ký',
  back: 'Quay lại',
  fatal: 'NGHIÊM TRỌNG',
  transportFailure: 'không có phản hồi',
}

interface Snapshot {
  reports: readonly BufferedReport[]
  requests: readonly RequestLogEntry[]
}

function readSnapshot(): Snapshot {
  return { reports: getBufferedReports(), requests: getRequestLog() }
}

function shortTime(timestamp: string): string {
  return timestamp.slice(11, 19) || timestamp
}

export default function DiagnosticsScreen() {
  const [snapshot, setSnapshot] = useState<Snapshot>(readSnapshot)

  const { reports, requests } = snapshot
  const isEmpty = reports.length === 0 && requests.length === 0

  const refresh = () => setSnapshot(readSnapshot())

  const handleShare = () => {
    // Share, not clipboard: `expo-clipboard` is not a dependency and RN's core
    // Clipboard is deprecated — the share sheet needs neither and lands the
    // text straight in the support channel. The text is also selectable below.
    void Share.share({ message: formatDiagnosticsReport() }).catch(() => {
      // Sheet dismissed / unavailable — nothing to recover.
    })
  }

  const handleClear = () => {
    clearDiagnostics()
    refresh()
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{copy.title}</Text>
        <Text style={styles.subtitle}>{copy.subtitle}</Text>

        {isEmpty ? (
          <GlassCard style={styles.card} testID="diagnostics-empty">
            <Text style={styles.body}>{copy.empty}</Text>
          </GlassCard>
        ) : (
          <>
            {reports.length > 0 && (
              <>
                <Text style={styles.section}>
                  {copy.errors} ({reports.length})
                </Text>
                {reports.map((report, index) => (
                  <GlassCard
                    key={`${report.timestamp}-${index}`}
                    style={styles.card}
                    testID={`diagnostics-report-${index}`}
                  >
                    <Text style={styles.meta}>
                      {shortTime(report.timestamp)}
                      {report.fatal ? ` · ${copy.fatal}` : ''}
                    </Text>
                    <Text style={styles.body} selectable>
                      {report.message}
                    </Text>
                  </GlassCard>
                ))}
              </>
            )}

            {requests.length > 0 && (
              <>
                <Text style={styles.section}>
                  {copy.requests} ({requests.length})
                </Text>
                {requests.map((entry, index) => (
                  <View key={`${entry.requestId}-${index}`} testID={`diagnostics-request-${index}`}>
                    <Text style={styles.body} selectable>
                      {`${entry.method} ${entry.path} → ${
                        entry.status === 0 ? copy.transportFailure : entry.status
                      }`}
                    </Text>
                    <Text style={styles.meta} selectable>
                      {`${shortTime(entry.timestamp)} · ${entry.requestId}`}
                    </Text>
                  </View>
                ))}
              </>
            )}
          </>
        )}

        <PrimaryButton
          label={copy.share}
          onPress={handleShare}
          style={styles.action}
          testID="diagnostics-share"
        />
        <PrimaryButton
          label={copy.refresh}
          onPress={refresh}
          variant="ghost"
          style={styles.action}
          testID="diagnostics-refresh"
        />
        <PrimaryButton
          label={copy.clear}
          onPress={handleClear}
          variant="ghost"
          style={styles.action}
          testID="diagnostics-clear"
        />
        <PrimaryButton
          label={copy.back}
          onPress={() => router.back()}
          variant="ghost"
          style={styles.action}
          testID="diagnostics-back"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  title: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.xl,
  },
  section: { ...typography.heading, color: colors.ink, marginBottom: spacing.md },
  card: { marginBottom: spacing.md },
  meta: { ...typography.caption, color: colors.inkMuted },
  body: { ...typography.body, color: colors.ink },
  action: { marginTop: spacing.md },
})
