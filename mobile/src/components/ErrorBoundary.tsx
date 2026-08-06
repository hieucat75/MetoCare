/**
 * WS5-F2: production-safe root error boundary.
 *
 * Catches uncaught render errors anywhere in the tree, reports them (sanitized)
 * to the monitor, and shows a calm Vietnamese fallback with a retry that
 * re-mounts the subtree (navigation recovery) instead of a white screen. Never
 * surfaces the raw error/stack to the user (no PHI leakage).
 */
import React from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { captureException } from '../lib/monitor'
import { colors } from '../theme/tokens'

interface Props {
  children: React.ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends React.Component<Props, State> {
  override state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  override componentDidCatch(error: Error): void {
    // Only the (sanitized) message/stack + app context are reported — never the
    // component props/state, which could carry PHI.
    captureException(error, { fatal: true, extra: { boundary: 'root' } })
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false })
  }

  override render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }
    return (
      <View style={styles.container} accessibilityRole="alert" testID="error-boundary-fallback">
        <Text style={styles.title}>Đã xảy ra sự cố</Text>
        <Text style={styles.body}>
          Ứng dụng gặp lỗi ngoài dự kiến. Dữ liệu của bạn vẫn an toàn. Vui lòng thử lại.
        </Text>
        <Pressable
          style={styles.button}
          onPress={this.handleRetry}
          accessibilityRole="button"
          accessibilityLabel="Thử lại"
          testID="error-boundary-retry"
        >
          <Text style={styles.buttonText}>Thử lại</Text>
        </Pressable>
      </View>
    )
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: colors.bg,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0F172A',
    marginBottom: 8,
    textAlign: 'center',
  },
  body: {
    fontSize: 15,
    color: '#475569',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 22,
  },
  button: {
    backgroundColor: '#0F9C6E',
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
})
