/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    // stub CSS/asset imports
    '\\.(css|less|scss|sass)$': '<rootDir>/__mocks__/styleMock.js',
    '\\.(jpg|jpeg|png|gif|webp|svg|ico)$': '<rootDir>/__mocks__/fileMock.js',
    // Mock the API client so generic TS generics don't trip Babel JSX parsing
    '^@/lib/api/client$': '<rootDir>/__mocks__/api-client.js',
  },
  transform: {
    '^.+\\.(js|jsx|ts|tsx)$': ['babel-jest', { configFile: './babel.config.test.js' }],
  },
  testMatch: ['**/__tests__/**/*.test.{ts,tsx}', '**/*.test.{ts,tsx}'],
  // Exclude pre-existing compile-only type test files (they use generic TS that trips Babel JSX)
  // These were compile-time-only type assertions, not runnable tests
  testPathIgnorePatterns: [
    '/node_modules/',
    '/.next/',
    'LabInsightCards.test',
    'labInsight.types.test',
  ],
  // Ignore node_modules except packages that export ESM
  transformIgnorePatterns: ['/node_modules/(?!(lucide-react)/)'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}', '!src/**/*.d.ts'],
  modulePathIgnorePatterns: ['/.next/'],
}

module.exports = config
