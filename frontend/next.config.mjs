/** @type {import('next').NextConfig} */
const nextConfig = {
  // Expose backend URL to the browser bundle
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1',
  },
  // Strict mode for better React error detection in development
  reactStrictMode: true,
}

export default nextConfig
