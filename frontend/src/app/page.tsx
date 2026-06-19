import { redirect } from 'next/navigation'

// Root "/" → patient dashboard; patient layout handles auth redirect to /login
export default function Home() {
  redirect('/dashboard')
}
