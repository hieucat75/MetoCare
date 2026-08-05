import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import { EnvironmentBanner } from '@/components/EnvironmentBanner'

const inter = Inter({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: 'MetoCare',
  description: 'Nền tảng quản lý sức khỏe chuyển hóa',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="vi" className={inter.variable}>
      <body className={`${inter.className} bg-background min-h-screen`}>
        <EnvironmentBanner />
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
