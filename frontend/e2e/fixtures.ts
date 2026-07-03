import type { Page, Route } from '@playwright/test'

// ---------------------------------------------------------------------------
// Mocked backend fixtures for the doctor + admin portals.
//
// Every request to `**/api/v1/**` is intercepted and fulfilled with a small,
// realistic Vietnamese fixture so the pages render populated (never an error /
// empty state). Auth tokens are seeded into localStorage BEFORE the app boots
// so the portal layouts pass their RBAC gate without a real login round-trip.
// ---------------------------------------------------------------------------

export type PortalRole = 'doctor' | 'internal_admin'

const NOW = '2026-07-03T02:30:00Z'

const DOCTOR_USER = {
  id: 'doc-1',
  email: 'bs.nguyen@metocare.vn',
  phone: null,
  role: 'doctor',
  full_name: 'BS. Nguyễn Minh Anh',
  mfa_enabled: true,
  notify_medication: true,
  notify_lab_results: true,
  notify_doctor_messages: true,
}

const ADMIN_USER = {
  id: 'adm-1',
  email: 'admin@metocare.vn',
  phone: null,
  role: 'internal_admin',
  full_name: 'Trần Quản Trị',
  mfa_enabled: true,
  notify_medication: false,
  notify_lab_results: false,
  notify_doctor_messages: false,
}

const DOCTOR_STATS = {
  pending_reviews: 8,
  urgent_reviews: 2,
  total_patients: 143,
  reviews_today: 5,
  avg_review_time_min: 12,
}

const QUEUE = {
  total: 3,
  pending_count: 3,
  items: [
    {
      id: 'q-1',
      patient_id: 'p-1',
      patient_name: 'Lê Thị Hồng',
      item_type: 'lab_result',
      priority: 'urgent',
      status: 'pending_review',
      summary: 'HbA1c 8.9% — vượt ngưỡng, cần đánh giá phác đồ.',
      submitted_at: NOW,
      assigned_doctor_id: null,
    },
    {
      id: 'q-2',
      patient_id: 'p-2',
      patient_name: 'Phạm Văn Dũng',
      item_type: 'ai_session',
      priority: 'high',
      status: 'pending_review',
      summary: 'Phiên tư vấn AI về chế độ ăn — chờ bác sĩ duyệt.',
      submitted_at: NOW,
      assigned_doctor_id: null,
    },
    {
      id: 'q-3',
      patient_id: 'p-3',
      patient_name: 'Đỗ Thanh Mai',
      item_type: 'care_plan',
      priority: 'normal',
      status: 'pending_review',
      summary: 'Kế hoạch chăm sóc 90 ngày — bản nháp cần duyệt.',
      submitted_at: NOW,
      assigned_doctor_id: null,
    },
  ],
}

const CONSULTATIONS = [
  {
    id: 'c-1001',
    patient_id: 'p-1',
    doctor_id: 'doc-1',
    status: 'PAID',
    consultation_type: 'CHAT',
    consultation_price: 250000,
    payment_status: 'PAID',
    data_consent_accepted: true,
    data_consent_accepted_at: NOW,
    chief_complaint: 'Đường huyết dao động, mệt mỏi buổi sáng.',
    patient_note: 'Muốn được tư vấn điều chỉnh chế độ ăn và thuốc.',
    created_at: NOW,
    paid_at: NOW,
    confirmed_at: NOW,
    disclaimer: 'Tư vấn từ xa không thay thế khám trực tiếp.',
  },
  {
    id: 'c-1002',
    patient_id: 'p-2',
    doctor_id: 'doc-1',
    status: 'COMPLETED',
    consultation_type: 'VIDEO',
    consultation_price: 400000,
    payment_status: 'PAID',
    data_consent_accepted: true,
    chief_complaint: 'Tái khám sau 4 tuần điều chỉnh phác đồ.',
    created_at: NOW,
    completed_at: NOW,
  },
]

const PATIENT_SUMMARY = {
  patient_id: 'p-1',
  generated_at: NOW,
  vitals: {
    latest: [
      { id: 'v1', metric_type: 'glucose_fasting', value: 7.8, unit: 'mmol/L', measured_at: NOW, status: 'high' },
      { id: 'v2', metric_type: 'blood_pressure', value: '135/85', unit: 'mmHg', measured_at: NOW, status: 'elevated' },
      { id: 'v3', metric_type: 'weight', value: 72, unit: 'kg', measured_at: NOW, status: 'normal' },
    ],
    trend: 'Đường huyết đói giảm nhẹ so với tháng trước.',
  },
  lab_documents: [
    { id: 'l1', lab_name: 'Vinmec', file_type: 'pdf', ocr_status: 'done', status: 'reviewed', created_at: NOW },
  ],
  metabolic_score: { latest_score: 68, trend: 'up', recorded_at: NOW },
  medications: [
    { id: 'm1', name: 'Metformin', dose: '850mg x2', note: 'Sau ăn', created_at: NOW },
    { id: 'm2', name: 'Empagliflozin', dose: '10mg x1', note: 'Buổi sáng', created_at: NOW },
  ],
  symptoms: [
    { id: 's1', description: 'Mệt mỏi buổi sáng', severity: 'moderate', reported_at: NOW },
  ],
  nutrition: [
    { id: 'n1', description: 'Cơm gạo lứt + ức gà', meal_type: 'lunch', calories_kcal: 520, logged_at: NOW },
  ],
  upcoming_appointments: [
    { id: 'a1', doctor_id: 'doc-1', status: 'CONFIRMED', notes: 'Tái khám', slot_start: NOW, created_at: NOW },
  ],
  active_care_plans: [{ id: 'cp1', title: 'Kiểm soát đường huyết 90 ngày', version: 2 }],
}

const NOTES = [
  {
    id: 'note-1',
    consultation_id: 'c-1001',
    doctor_id: 'doc-1',
    content: 'Khuyến nghị tăng liều Metformin và theo dõi đường huyết đói 3 ngày/tuần.',
    note_type: 'recommendation',
    created_at: NOW,
  },
]

const ADMIN_STATS = {
  total_users: 1284,
  active_patients: 963,
  active_doctors: 47,
  total_clinics: 6,
  ai_sessions_today: 128,
  pending_reviews: 21,
  flagged_ai_sessions: 3,
  audit_events_today: 342,
}

const ADMIN_CONSULTATIONS = [
  {
    id: 'c-1001',
    patient_id: 'p-1',
    patient_name: 'Lê Thị Hồng',
    doctor_id: 'doc-1',
    doctor_name: 'BS. Nguyễn Minh Anh',
    status: 'PAID',
    consultation_type: 'CHAT',
    consultation_price: 250000,
    payment_status: 'PAID',
    created_at: NOW,
  },
  {
    id: 'c-1002',
    patient_id: 'p-2',
    patient_name: 'Phạm Văn Dũng',
    doctor_id: 'doc-1',
    doctor_name: 'BS. Nguyễn Minh Anh',
    status: 'COMPLETED',
    consultation_type: 'VIDEO',
    consultation_price: 400000,
    payment_status: 'PAID',
    created_at: NOW,
  },
  {
    id: 'c-1003',
    patient_id: 'p-3',
    patient_name: 'Đỗ Thanh Mai',
    doctor_id: 'doc-2',
    doctor_name: 'BS. Vũ Hải Yến',
    status: 'REQUESTED',
    consultation_type: 'IN_PERSON',
    consultation_price: 500000,
    payment_status: 'UNPAID',
    created_at: NOW,
  },
]

const ADMIN_CONSULTATION_STATS = {
  by_status: { REQUESTED: 4, CONFIRMED: 2, PAID: 9, IN_PROGRESS: 1, COMPLETED: 18, CANCELLED: 3 },
  total: 37,
  paid_count: 27,
  mock_revenue: 9450000,
}

const ADMIN_DOCTORS = [
  {
    id: 'dv-1',
    user_id: 'doc-1',
    full_name: 'BS. Nguyễn Minh Anh',
    specialty: 'Nội tiết',
    license_no: 'VN-38271',
    hospital_name: 'BV Bạch Mai',
    years_experience: 11,
    verification_status: 'VERIFIED',
    is_verified: true,
    is_active: true,
  },
  {
    id: 'dv-2',
    user_id: 'doc-2',
    full_name: 'BS. Vũ Hải Yến',
    specialty: 'Dinh dưỡng',
    license_no: 'VN-44120',
    hospital_name: 'BV Chợ Rẫy',
    years_experience: 7,
    verification_status: 'PENDING',
    is_verified: false,
    is_active: true,
  },
]

const ADMIN_USERS = {
  total: 1284,
  items: [
    {
      id: 'p-1',
      email: 'hong.le@example.vn',
      full_name: 'Lê Thị Hồng',
      role: 'patient',
      is_active: true,
      created_at: NOW,
      last_login_at: NOW,
    },
    {
      id: 'doc-1',
      email: 'bs.nguyen@metocare.vn',
      full_name: 'BS. Nguyễn Minh Anh',
      role: 'doctor',
      is_active: true,
      created_at: NOW,
      last_login_at: NOW,
    },
  ],
}

const ADMIN_AUDIT_LOGS = {
  total: 342,
  items: [
    {
      id: 'al-1',
      actor_id: 'adm-1',
      actor_email: 'admin@metocare.vn',
      action: 'consultation.view',
      resource_type: 'consultation',
      resource_id: 'c-1001',
      ip_address: '10.0.0.5',
      occurred_at: NOW,
      metadata: null,
    },
  ],
}

// ---------------------------------------------------------------------------
// Route matcher — resolves a JSON body from the request pathname.
// ---------------------------------------------------------------------------

function resolveBody(pathname: string, role: PortalRole): unknown {
  const p = pathname.replace(/\/+$/, '')

  if (p.endsWith('/auth/me')) return role === 'doctor' ? DOCTOR_USER : ADMIN_USER

  // Doctor portal
  if (p.endsWith('/doctor/stats')) return DOCTOR_STATS
  if (p.includes('/doctor/queue')) return QUEUE
  if (p.endsWith('/doctors/me/consultations')) return CONSULTATIONS
  if (/\/consultations\/[^/]+\/patient-summary$/.test(p)) return PATIENT_SUMMARY
  if (/\/consultations\/[^/]+\/notes$/.test(p)) return NOTES
  if (/\/consultations\/[^/]+$/.test(p)) return CONSULTATIONS[0]
  if (p.endsWith('/consultations')) return CONSULTATIONS

  // Admin portal
  if (p.endsWith('/admin/stats')) return ADMIN_STATS
  if (p.endsWith('/admin/consultations/stats')) return ADMIN_CONSULTATION_STATS
  if (p.includes('/admin/consultations')) return ADMIN_CONSULTATIONS
  if (p.includes('/admin/doctors')) return ADMIN_DOCTORS
  if (p.includes('/admin/users')) return ADMIN_USERS
  if (p.includes('/admin/audit-logs')) return ADMIN_AUDIT_LOGS

  // Safe fallback so nothing errors.
  return {}
}

/**
 * Install the mocked API + seeded auth tokens on a page for the given role.
 * Call BEFORE `page.goto`.
 */
export async function mockPortal(page: Page, role: PortalRole): Promise<void> {
  // Seed tokens before any app script runs (origin-scoped localStorage).
  await page.addInitScript(() => {
    localStorage.setItem('meto_access', 'e2e-access-token')
    localStorage.setItem('meto_refresh', 'e2e-refresh-token')
  })

  await page.route('**/api/v1/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const body = resolveBody(url.pathname, role)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}
