/** Jest config using the jest-expo preset (RN + Expo module transforms). */
module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  // Jest's 5s default is measured INSIDE the test body, and the first test to
  // touch a screen pays for transforming the whole React Native + Expo Router
  // module graph. On a cold cache that alone exceeds 5s, so screen suites failed
  // with "Exceeded timeout of 5000 ms" while their assertions were fine — 6 of 28
  // suites on a cold parallel run, 0 once the cache was warm. CI always runs cold,
  // so this must be sized for the cold path, not the local warm one.
  testTimeout: 30000,
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|expo-router|@react-native-community/.*))',
  ],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    'app/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
  ],
  coverageThreshold: {
    global: {
      statements: 50,
      branches: 40,
      functions: 45,
      lines: 50,
    },
  },
}
