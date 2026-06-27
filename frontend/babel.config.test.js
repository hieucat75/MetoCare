module.exports = {
  presets: [
    ['@babel/preset-env', { targets: { node: 'current' } }],
    '@babel/preset-typescript',
  ],
  plugins: [],
  overrides: [
    {
      // Apply JSX transform only to .tsx and .jsx files
      test: /\.[jt]sx$/,
      presets: [['@babel/preset-react', { runtime: 'automatic' }]],
    },
  ],
}
