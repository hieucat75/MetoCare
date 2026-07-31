import React from 'react'
import { render, waitFor } from '@testing-library/react-native'

import type { DoctorCardOut } from '../src/api/marketplace'

jest.mock('../src/auth/AuthContext', () => {
  // Stable client reference: a fresh object per render would change the
  // useDoctorList effect dependency and re-fetch forever.
  const stableClient = {}
  return { useAuth: () => ({ client: stableClient }) }
})
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
}))

const SEEDED: DoctorCardOut[] = [
  {
    id: 'doc-1',
    full_name: 'BS. Nguyễn An',
    specialty: 'Nội tiết',
    avatar_url: null,
    consultation_fee: 250000,
    hospital_name: 'BV Đại học Y',
    years_experience: 10,
    languages: 'Tiếng Việt',
    consultation_methods: 'chat',
    rating_avg: 4.5,
    rating_count: 12,
  },
  {
    id: 'doc-2',
    full_name: 'BS. Trần Bình',
    specialty: 'Tim mạch',
    avatar_url: null,
    consultation_fee: null,
    hospital_name: null,
    years_experience: null,
    languages: null,
    consultation_methods: null,
    rating_avg: 0,
    rating_count: 0,
  },
]

jest.mock('../src/api/marketplace', () => ({
  listDoctors: jest.fn(async () => SEEDED),
  getDoctor: jest.fn(),
}))

import MarketplaceScreen from '../app/(app)/marketplace'

describe('MarketplaceScreen', () => {
  it('renders seeded doctors after loading', async () => {
    const view = await render(<MarketplaceScreen />)
    await waitFor(() => expect(view.getByText('BS. Nguyễn An')).toBeTruthy())
    expect(view.getByText('BS. Trần Bình')).toBeTruthy()
    expect(view.getByTestId('doctor-doc-1')).toBeTruthy()
    expect(view.getByTestId('doctor-doc-2')).toBeTruthy()
  })
})
