'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function Home() {
  const router = useRouter()

  useEffect(() => {
    const seen = localStorage.getItem('intro_seen')
    if (seen) {
      router.replace('/dashboard')
    } else {
      router.replace('/intro')
    }
  }, [router])

  return null
}
