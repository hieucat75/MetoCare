/**
 * Global Jest setup: registers RNTL matchers and provides deterministic
 * in-memory mocks for native modules so logic and components can be tested
 * headlessly (no simulator). These mocks exercise adapter/logic behaviour;
 * true Keychain/Keystore + biometric hardware paths are native-runtime pending.
 *
 * RNTL v14 auto-registers its built-in matchers (toBeOnTheScreen,
 * toHaveTextContent, …) on import, so no extend-expect import is required.
 */

// React 19 concurrent renderer requires this flag for act()-wrapped updates
// (RNTL render/fireEvent). Without it render returns without bound queries.
;(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

// --- expo-secure-store: in-memory store ---
jest.mock('expo-secure-store', () => {
  const mem = new Map<string, string>()
  return {
    setItemAsync: jest.fn(async (k: string, v: string) => {
      mem.set(k, v)
    }),
    getItemAsync: jest.fn(async (k: string) => (mem.has(k) ? mem.get(k)! : null)),
    deleteItemAsync: jest.fn(async (k: string) => {
      mem.delete(k)
    }),
    isAvailableAsync: jest.fn(async () => true),
    WHEN_UNLOCKED: 'whenUnlocked',
    __mem: mem,
  }
})

// --- AsyncStorage: official mock ---
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
)

// --- expo-crypto: deterministic-ish uuid ---
jest.mock('expo-crypto', () => {
  let n = 0
  return {
    randomUUID: jest.fn(() => {
      n += 1
      return `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
    }),
  }
})

// --- expo-local-authentication: defaults to available + success ---
jest.mock('expo-local-authentication', () => ({
  hasHardwareAsync: jest.fn(async () => true),
  isEnrolledAsync: jest.fn(async () => true),
  authenticateAsync: jest.fn(async () => ({ success: true })),
  AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2 },
}))

// --- netinfo: online by default ---
jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn(() => () => {}),
  fetch: jest.fn(async () => ({ isConnected: true, isInternetReachable: true })),
}))

// --- react-native-safe-area-context: pass-through mock ---
jest.mock('react-native-safe-area-context', () => {
  const React = require('react')
  const { View } = require('react-native')
  return {
    SafeAreaProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    SafeAreaView: ({ children, style }: { children: React.ReactNode; style?: unknown }) =>
      React.createElement(View, { style }, children),
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    initialWindowMetrics: null,
  }
})

// --- expo-constants: extra config ---
jest.mock('expo-constants', () => ({
  __esModule: true,
  default: {
    expoConfig: {
      extra: { appEnv: 'development', apiUrl: 'http://localhost:8000/api/v1' },
    },
  },
}))
