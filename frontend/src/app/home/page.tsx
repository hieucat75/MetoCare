import { redirect } from 'next/navigation'

// Legacy design-mockup route. Superseded by the official patient IA.
// Kept as a redirect so any old bookmark/deep-link lands on the real dashboard.
export default function HomeRedirect() {
  redirect('/dashboard')
}
