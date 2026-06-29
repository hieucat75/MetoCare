/**
 * AI Copilot mock data — single source for all 6 screens.
 * Replace each export with a real API call when the backend is ready;
 * page components import only the slices they need.
 */

// ── Shared types ──────────────────────────────────────────────────────────────

export type StatusLevel = 'good' | 'norm' | 'med' | 'high' | 'low'

// ── M1 · Overview ─────────────────────────────────────────────────────────────

export interface Priority {
  name: string
  sub: string
  icon: string
  iconBg: string
  iconColor: string
  badge: string
  badgeBg: string
  badgeColor: string
  bioKey?: string
}

export interface SystemMini {
  key: string
  name: string
  icon: string
  iconBg: string
  iconColor: string
  barPct: number
  barColor: string
  statLabel: string
  statColor: string
}

export interface HealthOverview {
  patientName: string
  score: number
  scoreLabel: string
  scoreStory: string
  labDate: string
  bestImprovement: { label: string; change: string }
  needsAttention: { label: string; change: string }
  todayAction: { icon: string; title: string; why: string }
  priorities: Priority[]
  systemsMini: SystemMini[]
  monthlyFocus: { title: string; content: string }
  preventive: { title: string; content: string }
  missingInfo: string
}

export const mockHealthOverview: HealthOverview = {
  patientName: 'Anh Minh',
  score: 72,
  scoreLabel: 'Khá tốt',
  scoreStory:
    'Chuyển hóa của bạn đang được kiểm soát tốt. Tháng này, ưu tiên là đường huyết và mỡ máu.',
  labDate: '20/06/2025',
  bestImprovement: { label: 'Triglyceride', change: '↓18%' },
  needsAttention: { label: 'Đường huyết', change: '↑ cao' },
  todayAction: {
    icon: 'Footprints',
    title: 'Đi bộ 20–30 phút sau bữa tối',
    why: 'Giúp cơ bắp hấp thu đường, hạ đường huyết sau ăn — yếu tố quan trọng nhất với bạn lúc này.',
  },
  priorities: [
    {
      name: 'Đường huyết',
      sub: 'Glucose 5.8 · HbA1c 5.7%',
      icon: 'Droplet',
      iconBg: '#FEF3C7',
      iconColor: '#D97706',
      badge: 'Cao',
      badgeBg: '#FEF3C7',
      badgeColor: '#B45309',
      bioKey: 'glucose',
    },
    {
      name: 'LDL Cholesterol',
      sub: '3.6 mmol/L · mục tiêu < 2.6',
      icon: 'Heart',
      iconBg: '#FEE2E2',
      iconColor: '#DC2626',
      badge: 'Cao',
      badgeBg: '#FEE2E2',
      badgeColor: '#991B1B',
      bioKey: 'ldl',
    },
    {
      name: 'Vitamin D',
      sub: '18 ng/mL · đang thiếu',
      icon: 'Sun',
      iconBg: '#E0F2FE',
      iconColor: '#0284C7',
      badge: 'Thiếu',
      badgeBg: '#E0F2FE',
      badgeColor: '#0369A1',
      bioKey: 'vitd',
    },
  ],
  systemsMini: [
    {
      key: 'metabolic',
      name: 'Chuyển hóa',
      icon: 'Flame',
      iconBg: '#FEF3C7',
      iconColor: '#D97706',
      barPct: 62,
      barColor: '#F59E0B',
      statLabel: 'Trung bình',
      statColor: '#B45309',
    },
    {
      key: 'cardio',
      name: 'Tim mạch',
      icon: 'Heart',
      iconBg: '#FEE2E2',
      iconColor: '#DC2626',
      barPct: 58,
      barColor: '#EF4444',
      statLabel: 'Theo dõi',
      statColor: '#DC2626',
    },
    {
      key: 'kidney',
      name: 'Thận',
      icon: 'Droplets',
      iconBg: '#DBEAFE',
      iconColor: '#2563EB',
      barPct: 86,
      barColor: '#22C55E',
      statLabel: 'Tốt',
      statColor: '#16A34A',
    },
    {
      key: 'liver',
      name: 'Gan',
      icon: 'Shield',
      iconBg: '#D1FAE5',
      iconColor: '#059669',
      barPct: 82,
      barColor: '#22C55E',
      statLabel: 'Tốt',
      statColor: '#16A34A',
    },
    {
      key: 'nutrition',
      name: 'Dinh dưỡng',
      icon: 'Apple',
      iconBg: '#FEF3C7',
      iconColor: '#D97706',
      barPct: 54,
      barColor: '#F59E0B',
      statLabel: 'Cần chú ý',
      statColor: '#B45309',
    },
  ],
  monthlyFocus: {
    title: 'Tập trung tháng này',
    content: 'Đưa đường huyết về dưới 5.6 mmol/L',
  },
  preventive: {
    title: 'Cơ hội phòng ngừa',
    content: 'Tầm soát tiền tiểu đường — đặt lịch HbA1c',
  },
  missingInfo:
    'Bổ sung huyết áp gần đây và vòng eo sẽ giúp AI đánh giá nguy cơ tim mạch chính xác hơn (+12% độ tin cậy).',
}

// ── M2 · Body systems ─────────────────────────────────────────────────────────

export interface BiomarkerMini {
  short: string
  value: string
  unit: string
  status: StatusLevel
  bioKey?: string
}

export interface BodySystem {
  key: string
  name: string
  icon: string
  iconBg: string
  iconColor: string
  status: StatusLevel
  statusLabel: string
  statusBg: string
  statusColor: string
  note: string
  markers: BiomarkerMini[]
}

export const mockBodySystems: BodySystem[] = [
  {
    key: 'metabolic',
    name: 'Chuyển hóa',
    icon: 'Flame',
    iconBg: '#FEF3C7',
    iconColor: '#D97706',
    status: 'med',
    statusLabel: 'Trung bình',
    statusBg: '#FEF3C7',
    statusColor: '#B45309',
    note: 'Có dấu hiệu kháng insulin sớm. Đường huyết và mỡ máu hơi cao nhưng đang cải thiện.',
    markers: [
      { short: 'Glucose', value: '5.8', unit: 'mmol/L', status: 'med', bioKey: 'glucose' },
      { short: 'HbA1c', value: '5.7', unit: '%', status: 'med', bioKey: 'hba1c' },
      { short: 'TyG', value: '8.9', unit: '', status: 'high' },
    ],
  },
  {
    key: 'cardio',
    name: 'Tim mạch',
    icon: 'Heart',
    iconBg: '#FEE2E2',
    iconColor: '#DC2626',
    status: 'med',
    statusLabel: 'Theo dõi',
    statusBg: '#FEE2E2',
    statusColor: '#DC2626',
    note: 'LDL và triglyceride cao hơn mục tiêu. Nguy cơ tim mạch 10 năm ở mức trung bình.',
    markers: [
      { short: 'LDL-C', value: '3.6', unit: 'mmol/L', status: 'high', bioKey: 'ldl' },
      { short: 'HDL-C', value: '1.05', unit: 'mmol/L', status: 'low', bioKey: 'hdl' },
      { short: 'Triglyceride', value: '2.1', unit: 'mmol/L', status: 'med', bioKey: 'tg' },
    ],
  },
  {
    key: 'kidney',
    name: 'Thận',
    icon: 'Droplets',
    iconBg: '#DBEAFE',
    iconColor: '#2563EB',
    status: 'good',
    statusLabel: 'Tốt',
    statusBg: '#D1FAE5',
    statusColor: '#059669',
    note: 'Chức năng lọc của thận bình thường. Tiếp tục kiểm soát đường huyết và huyết áp.',
    markers: [
      { short: 'eGFR', value: '92', unit: 'mL/phút', status: 'good' },
      { short: 'Creatinine', value: '84', unit: 'µmol/L', status: 'good' },
    ],
  },
  {
    key: 'liver',
    name: 'Gan',
    icon: 'Shield',
    iconBg: '#D1FAE5',
    iconColor: '#059669',
    status: 'good',
    statusLabel: 'Tốt',
    statusBg: '#D1FAE5',
    statusColor: '#059669',
    note: 'Men gan trong giới hạn bình thường. Cần lưu ý nguy cơ gan nhiễm mỡ do chuyển hóa.',
    markers: [
      { short: 'ALT', value: '32', unit: 'U/L', status: 'good' },
      { short: 'AST', value: '28', unit: 'U/L', status: 'good' },
      { short: 'GGT', value: '41', unit: 'U/L', status: 'norm' },
    ],
  },
  {
    key: 'inflam',
    name: 'Viêm / Miễn dịch',
    icon: 'Activity',
    iconBg: '#D1FAE5',
    iconColor: '#059669',
    status: 'good',
    statusLabel: 'Thấp',
    statusBg: '#D1FAE5',
    statusColor: '#059669',
    note: 'Mức viêm trong cơ thể thấp — một tín hiệu rất tốt cho tim mạch và chuyển hóa.',
    markers: [{ short: 'hs-CRP', value: '1.1', unit: 'mg/L', status: 'good' }],
  },
  {
    key: 'hormone',
    name: 'Nội tiết',
    icon: 'Atom',
    iconBg: '#EDE9FE',
    iconColor: '#7C3AED',
    status: 'norm',
    statusLabel: 'Khá tốt',
    statusBg: '#EDE9FE',
    statusColor: '#7C3AED',
    note: 'Tuyến giáp hoạt động ổn định. TSH ở mức cao bình thường, nên theo dõi định kỳ.',
    markers: [
      { short: 'TSH', value: '3.8', unit: 'mIU/L', status: 'norm', bioKey: 'tsh' },
      { short: 'FT4', value: '14.2', unit: 'pmol/L', status: 'good' },
    ],
  },
  {
    key: 'nutrition',
    name: 'Dinh dưỡng',
    icon: 'Apple',
    iconBg: '#FEF3C7',
    iconColor: '#D97706',
    status: 'low',
    statusLabel: 'Cần chú ý',
    statusBg: '#FEF3C7',
    statusColor: '#B45309',
    note: 'Đang thiếu Vitamin D, ảnh hưởng đến xương và miễn dịch. Dự trữ sắt ở mức thấp bình thường.',
    markers: [
      { short: 'Vitamin D', value: '18', unit: 'ng/mL', status: 'low', bioKey: 'vitd' },
      { short: 'Ferritin', value: '48', unit: 'ng/mL', status: 'norm' },
      { short: 'B12', value: '410', unit: 'pg/mL', status: 'good' },
    ],
  },
]

// ── M3 · Biomarker detail ──────────────────────────────────────────────────────

export interface BioWhy {
  icon: string
  label: string
  note: string
}
export interface BioPlanItem {
  text: string
  sub: string
  done?: boolean
}
export interface BioContributor {
  name: string
  weight: number
  note: string
}
export interface BioDerived {
  name: string
  val: string
  note: string
}
export interface BioFuture {
  when: string
  text: string
  tone: 'good' | 'med' | 'high'
}
export interface BioNeed {
  title: string
  why: string
}
export interface BioKnowledge {
  q: string
  a: string
}
export interface BioChain {
  short: string
  note: string
  status: StatusLevel
  bioKey?: string
}
export interface RelatedTrend {
  short: string
  from: string
  to: string
  unit: string
  dir: 'up' | 'down'
  good: boolean
}

export interface Biomarker {
  key: string
  name: string
  short: string
  value: string
  unit: string
  range: string
  prev: string
  prevNote: string
  target: string
  status: StatusLevel
  gaugePosition: number
  gaugeTarget: number
  riskText: string
  conclusion: string
  doesWhat: string
  analogy: string
  analogyIcon: string
  why: BioWhy[]
  today: { title: string; why: string }
  plan: BioPlanItem[]
  reasonIntro: string
  contributors: BioContributor[]
  derived: BioDerived[]
  confidence: number
  confidenceNote: string
  evidence: string
  limitations: string[]
  futures: BioFuture[]
  needs: BioNeed[]
  doctorQs: string[]
  knowledge: BioKnowledge[]
  chain: BioChain[]
  trendData: number[]
  trendLabels: string[]
  trendBandLow: number
  trendBandHigh: number
  trendMin: number
  trendMax: number
  trendComment: string
  relatedTrends: RelatedTrend[]
}

export const mockBiomarkers: Record<string, Biomarker> = {
  glucose: {
    key: 'glucose',
    name: 'Glucose máu lúc đói',
    short: 'Glucose',
    value: '5.8',
    unit: 'mmol/L',
    range: '3.9 – 5.5',
    prev: '6.1',
    prevNote: 'giảm từ lần trước',
    target: '< 5.6',
    status: 'med',
    gaugePosition: 64,
    gaugeTarget: 48,
    riskText: 'Trung bình',
    conclusion:
      'Đường huyết của bạn hơi cao và, kết hợp với triglyceride, có thể gợi ý một kiểu chuyển hóa sớm cần theo dõi — chưa phải tiểu đường.',
    doesWhat:
      'Glucose là nguồn năng lượng chính cho cơ thể. Sau khi ăn, tụy tiết insulin để đưa glucose từ máu vào tế bào. Chỉ số lúc đói phản ánh khả năng kiểm soát đường của cơ thể khi nghỉ ngơi.',
    analogy:
      'Hãy hình dung glucose như xăng và insulin là người bơm xăng. Khi insulin làm việc kém hiệu quả, xăng ứ lại trong "đường ống" — đó là lúc đường huyết tăng.',
    analogyIcon: 'Fuel',
    why: [
      { icon: 'User', label: 'Nam · 52 tuổi', note: 'Nguy cơ chuyển hóa tăng dần theo tuổi' },
      {
        icon: 'Scale',
        label: 'BMI 27 · vòng eo 94cm',
        note: 'Thừa cân vùng bụng làm tăng kháng insulin',
      },
      {
        icon: 'Armchair',
        label: 'Ít vận động',
        note: 'Cơ ít dùng glucose, đường tích trong máu',
      },
      {
        icon: 'Users',
        label: 'Bố mắc tiểu đường type 2',
        note: 'Yếu tố di truyền làm tăng nguy cơ',
      },
    ],
    today: {
      title: 'Đi bộ 20–30 phút sau bữa tối',
      why: 'Vận động ngay sau ăn giúp cơ hấp thu glucose mà không cần nhiều insulin — cách nhanh nhất hạ đường huyết của bạn.',
    },
    plan: [
      { text: 'Đi bộ sau bữa tối, 5 ngày/tuần', sub: 'Bắt đầu 15 phút, tăng dần lên 30' },
      { text: 'Giảm đồ ngọt & nước ngọt', sub: 'Thay bằng trái cây ít ngọt, nước lọc' },
      { text: 'Thêm rau xanh & chất xơ mỗi bữa', sub: 'Làm chậm hấp thu đường sau ăn' },
      { text: 'Ngủ đủ 7 giờ', sub: 'Thiếu ngủ làm tăng kháng insulin' },
    ],
    reasonIntro:
      'AI kết luận "nguy cơ trung bình" dựa trên việc đối chiếu glucose với các chỉ số liên quan và hồ sơ cá nhân của bạn, không chỉ dựa vào một con số.',
    contributors: [
      { name: 'Glucose lúc đói 5.8', weight: 70, note: 'Cao hơn ngưỡng tối ưu 5.5' },
      { name: 'Triglyceride 2.1', weight: 55, note: 'Gợi ý rối loạn chuyển hóa mỡ–đường' },
      { name: 'Vòng eo 94cm', weight: 45, note: 'Mỡ bụng thúc đẩy kháng insulin' },
      { name: 'Tiền sử gia đình', weight: 35, note: 'Bố mắc tiểu đường type 2' },
    ],
    derived: [
      { name: 'Chỉ số TyG', val: '8.9', note: 'Cao — dấu hiệu kháng insulin' },
      { name: 'HOMA-IR (ước tính)', val: '2.9', note: 'Vượt ngưỡng 2.5' },
    ],
    confidence: 82,
    confidenceNote: 'Độ tin cậy khá cao. Sẽ tăng lên ~92% nếu có thêm HbA1c và insulin lúc đói.',
    evidence:
      'Theo ADA 2025, glucose lúc đói 5.6–6.9 mmol/L được xếp vào nhóm tiền tiểu đường, cần can thiệp lối sống sớm.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'Chưa có HbA1c để xác nhận xu hướng 3 tháng',
      'Kết quả có thể dao động theo bữa ăn tối hôm trước',
    ],
    futures: [
      {
        when: 'Nếu không thay đổi · 1 năm',
        text: 'Glucose có thể tăng dần, nguy cơ tiến tới tiền tiểu đường rõ rệt hơn.',
        tone: 'med',
      },
      {
        when: '3 năm',
        text: 'Khả năng chuyển thành tiểu đường type 2 nếu kèm tăng cân và ít vận động.',
        tone: 'high',
      },
      {
        when: 'Nếu hành động hôm nay',
        text: 'Phần lớn trường hợp đưa được glucose về bình thường trong 3–6 tháng.',
        tone: 'good',
      },
    ],
    needs: [
      {
        title: 'Xét nghiệm HbA1c',
        why: 'Cho biết đường huyết trung bình 3 tháng — xác nhận xu hướng thật sự.',
      },
      {
        title: 'Insulin lúc đói',
        why: 'Giúp tính chính xác mức kháng insulin (HOMA-IR).',
      },
      { title: 'Huyết áp gần đây', why: 'Để đánh giá đầy đủ hội chứng chuyển hóa.' },
    ],
    doctorQs: [
      'Tôi có cần làm nghiệm pháp dung nạp glucose (OGTT) không?',
      'Với chỉ số hiện tại, tôi nên tái khám sau bao lâu?',
      'Tôi có cần dùng thuốc, hay điều chỉnh lối sống là đủ?',
    ],
    knowledge: [
      {
        q: 'Đường huyết bao nhiêu là bình thường?',
        a: 'Lúc đói: 3.9–5.5 mmol/L bình thường; 5.6–6.9 là tiền tiểu đường; ≥7.0 (2 lần) là tiểu đường.',
      },
      {
        q: 'Ăn gì để hạ đường huyết?',
        a: 'Ưu tiên rau xanh, ngũ cốc nguyên hạt, đạm nạc; hạn chế đường, cơm trắng nhiều, nước ngọt.',
      },
      {
        q: 'Tập luyện thế nào là tốt nhất?',
        a: 'Đi bộ sau ăn và tập sức bền 150 phút/tuần giúp cải thiện độ nhạy insulin rõ rệt.',
      },
    ],
    chain: [
      { short: 'Glucose', note: 'Đường huyết của bạn hơi cao', status: 'med', bioKey: 'glucose' },
      {
        short: 'HbA1c',
        note: 'Phản ánh đường huyết 3 tháng',
        status: 'med',
        bioKey: 'hba1c',
      },
      { short: 'TyG', note: 'Chỉ số kháng insulin — đang cao', status: 'high' },
      {
        short: 'Triglyceride',
        note: 'Mỡ máu cao đi kèm',
        status: 'med',
        bioKey: 'tg',
      },
      { short: 'HDL-C', note: 'Mỡ tốt giảm', status: 'low', bioKey: 'hdl' },
      { short: 'Gan nhiễm mỡ', note: 'Nguy cơ liên đới', status: 'med' },
    ],
    trendData: [7.2, 6.9, 6.7, 6.4, 6.1, 5.8],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 3.9,
    trendBandHigh: 5.5,
    trendMin: 3.5,
    trendMax: 7.5,
    trendComment:
      'Đường huyết đang cải thiện rõ rệt 3 tháng qua — bạn đang đi đúng hướng. Giữ nhịp vận động để chạm mục tiêu < 5.6.',
    relatedTrends: [
      { short: 'HbA1c', from: '5.9', to: '5.7', unit: '%', dir: 'down', good: true },
      {
        short: 'Triglyceride',
        from: '2.3',
        to: '2.1',
        unit: 'mmol/L',
        dir: 'down',
        good: true,
      },
      { short: 'HOMA-IR', from: '3.2', to: '2.9', unit: '', dir: 'down', good: true },
    ],
  },
  ldl: {
    key: 'ldl',
    name: 'LDL-Cholesterol',
    short: 'LDL',
    value: '3.6',
    unit: 'mmol/L',
    range: '< 3.0',
    prev: '3.4',
    prevNote: 'tăng nhẹ',
    target: '< 2.6',
    status: 'high',
    gaugePosition: 72,
    gaugeTarget: 40,
    riskText: 'Nguy cơ Cao',
    conclusion:
      'LDL của bạn cao hơn mục tiêu và, đi cùng HDL thấp, làm tăng nguy cơ mảng xơ vữa trong lòng mạch theo thời gian.',
    doesWhat:
      'LDL là loại cholesterol "xấu" vận chuyển mỡ trong máu. Khi dư thừa, nó lắng đọng vào thành mạch, dần tạo mảng xơ vữa làm hẹp lòng mạch máu.',
    analogy:
      'Hãy hình dung lòng mạch như đường ống nước. LDL cao giống như cặn bám dần vào thành ống — lâu ngày ống hẹp lại, dòng chảy khó khăn hơn.',
    analogyIcon: 'Pipette',
    why: [
      {
        icon: 'Utensils',
        label: 'Khẩu phần nhiều mỡ bão hòa',
        note: 'Mỡ động vật, đồ chiên làm tăng LDL',
      },
      { icon: 'Scale', label: 'BMI 27 · thừa cân', note: 'Ảnh hưởng đến chuyển hóa mỡ' },
      { icon: 'Armchair', label: 'Ít vận động', note: 'Vận động giúp tăng HDL, giảm LDL' },
      { icon: 'Users', label: 'Tiền sử gia đình rối loạn mỡ máu', note: 'Yếu tố di truyền' },
    ],
    today: {
      title: 'Thay mỡ động vật bằng dầu thực vật hôm nay',
      why: 'Giảm mỡ bão hòa là cách trực tiếp nhất hạ LDL — bắt đầu ngay từ bữa ăn kế tiếp.',
    },
    plan: [
      { text: 'Ăn yến mạch hoặc đậu mỗi ngày', sub: 'Chất xơ hòa tan giúp giảm LDL' },
      { text: 'Hạn chế đồ chiên, mỡ động vật', sub: 'Thay bằng cá, dầu ô liu' },
      { text: 'Đi bộ nhanh 30 phút/ngày', sub: 'Tăng HDL, cải thiện tỉ lệ mỡ' },
      { text: 'Thêm cá béo 2 lần/tuần', sub: 'Omega-3 hỗ trợ tim mạch' },
    ],
    reasonIntro:
      'AI xếp "nguy cơ cao" vì LDL vượt mục tiêu kết hợp với HDL thấp và triglyceride cao — một bộ ba làm tăng nguy cơ tim mạch.',
    contributors: [
      { name: 'LDL-C 3.6', weight: 75, note: 'Vượt mục tiêu < 2.6' },
      { name: 'HDL-C 1.05 (thấp)', weight: 55, note: 'Giảm lớp bảo vệ mạch máu' },
      { name: 'Triglyceride 2.1', weight: 50, note: 'Đi kèm rối loạn mỡ' },
      { name: 'Vòng eo 94cm', weight: 40, note: 'Mỡ bụng làm xấu hồ sơ mỡ máu' },
    ],
    derived: [
      { name: 'Non-HDL-C', val: '4.4', note: 'Cao — phản ánh toàn bộ mỡ xấu' },
      { name: 'TC/HDL', val: '5.2', note: 'Vượt ngưỡng an toàn 4.5' },
    ],
    confidence: 84,
    confidenceNote: 'Độ tin cậy cao. Sẽ chính xác hơn nếu có thêm ApoB và Lp(a).',
    evidence:
      'Theo ESC/EAS 2023, người nguy cơ trung bình nên giữ LDL < 2.6 mmol/L để giảm biến cố tim mạch.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'Chưa có ApoB để đánh giá chính xác số hạt gây xơ vữa',
      'Cần lặp lại xét nghiệm để xác nhận xu hướng',
    ],
    futures: [
      {
        when: 'Nếu không thay đổi · 1–2 năm',
        text: 'Mảng xơ vữa có thể tiến triển âm thầm trong lòng mạch.',
        tone: 'med',
      },
      {
        when: '5–10 năm',
        text: 'Tăng nguy cơ biến cố tim mạch nếu kèm huyết áp cao.',
        tone: 'high',
      },
      {
        when: 'Nếu hành động sớm',
        text: 'Điều chỉnh lối sống có thể đưa LDL về mục tiêu trong 3–6 tháng.',
        tone: 'good',
      },
    ],
    needs: [
      {
        title: 'Xét nghiệm ApoB',
        why: 'Đo trực tiếp số hạt gây xơ vữa — chính xác hơn LDL.',
      },
      { title: 'Lp(a) một lần', why: 'Phát hiện yếu tố nguy cơ di truyền ít người biết.' },
      { title: 'Huyết áp gần đây', why: 'Để tính nguy cơ tim mạch tổng thể.' },
    ],
    doctorQs: [
      'Với hồ sơ mỡ máu này, tôi có cần dùng statin không?',
      'Mục tiêu LDL phù hợp với tôi là bao nhiêu?',
      'Tôi nên xét nghiệm lại mỡ máu sau bao lâu?',
    ],
    knowledge: [
      {
        q: 'LDL bao nhiêu là an toàn?',
        a: 'Người nguy cơ trung bình nên giữ LDL < 2.6 mmol/L; nguy cơ cao < 1.8 mmol/L.',
      },
      {
        q: 'Ăn gì để giảm LDL?',
        a: 'Tăng yến mạch, đậu, rau, cá béo; giảm mỡ bão hòa và mỡ chuyển hóa (đồ chiên, bánh ngọt công nghiệp).',
      },
      {
        q: 'Cholesterol cao có triệu chứng không?',
        a: 'Thường không có triệu chứng — vì vậy xét nghiệm định kỳ rất quan trọng.',
      },
    ],
    chain: [
      { short: 'LDL-C', note: 'Mỡ xấu của bạn đang cao', status: 'high', bioKey: 'ldl' },
      { short: 'ApoB', note: 'Số hạt gây xơ vữa', status: 'high' },
      { short: 'HDL-C', note: 'Mỡ tốt giảm', status: 'low', bioKey: 'hdl' },
      { short: 'Triglyceride', note: 'Mỡ máu cao đi kèm', status: 'med', bioKey: 'tg' },
      { short: 'Xơ vữa động mạch', note: 'Hệ quả tích lũy lâu dài', status: 'high' },
    ],
    trendData: [3.1, 3.2, 3.3, 3.4, 3.5, 3.6],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0,
    trendBandHigh: 2.6,
    trendMin: 0,
    trendMax: 4,
    trendComment:
      'LDL đang tăng dần — đây là lúc nên siết lại khẩu phần mỡ bão hòa và tăng vận động trước khi cần đến thuốc.',
    relatedTrends: [
      { short: 'HDL-C', from: '1.12', to: '1.05', unit: 'mmol/L', dir: 'down', good: false },
      { short: 'Triglyceride', from: '1.9', to: '2.1', unit: 'mmol/L', dir: 'up', good: false },
      { short: 'TC/HDL', from: '4.8', to: '5.2', unit: '', dir: 'up', good: false },
    ],
  },
  tg: {
    key: 'tg',
    name: 'Triglyceride',
    short: 'Triglyceride',
    value: '2.1',
    unit: 'mmol/L',
    range: '< 1.7',
    prev: '2.3',
    prevNote: 'giảm nhẹ',
    target: '< 1.7',
    status: 'med',
    gaugePosition: 60,
    gaugeTarget: 38,
    riskText: 'Trung bình',
    conclusion:
      'Triglyceride của bạn cao hơn mức khuyến nghị, thường gắn với kháng insulin và khẩu phần nhiều đường, tinh bột.',
    doesWhat:
      'Triglyceride là dạng mỡ dự trữ năng lượng trong máu. Khi ăn dư đường và tinh bột, gan chuyển phần thừa thành triglyceride.',
    analogy:
      'Triglyceride như kho chứa năng lượng dư. Ăn dư đường mà ít vận động thì "kho" đầy lên — mỡ máu tăng theo.',
    analogyIcon: 'Warehouse',
    why: [
      {
        icon: 'Cookie',
        label: 'Khẩu phần nhiều đường & tinh bột',
        note: 'Gan chuyển đường dư thành mỡ',
      },
      { icon: 'Wine', label: 'Có dùng rượu bia', note: 'Rượu làm tăng triglyceride rõ rệt' },
      { icon: 'Activity', label: 'Có kháng insulin', note: 'Liên quan trực tiếp đến đường huyết' },
      { icon: 'Armchair', label: 'Ít vận động', note: 'Giảm khả năng đốt mỡ' },
    ],
    today: {
      title: 'Bỏ một ly nước ngọt / đồ uống có đường hôm nay',
      why: 'Đường lỏng là nguồn làm tăng triglyceride nhanh nhất — cắt giảm cho hiệu quả thấy rõ.',
    },
    plan: [
      { text: 'Hạn chế đường và nước ngọt', sub: 'Yếu tố ảnh hưởng lớn nhất' },
      { text: 'Giảm rượu bia', sub: 'Rượu làm tăng triglyceride mạnh' },
      { text: 'Đi bộ sau ăn mỗi ngày', sub: 'Giúp đốt mỡ và đường' },
      { text: 'Thêm cá béo 2 lần/tuần', sub: 'Omega-3 hạ triglyceride' },
    ],
    reasonIntro:
      'AI gắn triglyceride cao với kiểu chuyển hóa kháng insulin của bạn — nên cải thiện đường huyết cũng giúp hạ triglyceride.',
    contributors: [
      { name: 'Triglyceride 2.1', weight: 65, note: 'Vượt mục tiêu < 1.7' },
      { name: 'Glucose 5.8', weight: 55, note: 'Cùng kiểu rối loạn chuyển hóa' },
      { name: 'HDL-C thấp', weight: 45, note: 'Bộ đôi TG cao – HDL thấp' },
      { name: 'Vòng eo 94cm', weight: 40, note: 'Mỡ bụng thúc đẩy sản xuất mỡ' },
    ],
    derived: [
      { name: 'Chỉ số TyG', val: '8.9', note: 'Cao — dấu hiệu kháng insulin' },
      { name: 'TG/HDL', val: '2.0', note: 'Vượt ngưỡng tối ưu 1.5' },
    ],
    confidence: 80,
    confidenceNote:
      'Lưu ý: triglyceride dao động nhiều theo bữa ăn — nên xét nghiệm lúc đói để chính xác.',
    evidence:
      'Triglyceride lúc đói ≥ 1.7 mmol/L được xem là tăng, thường đi cùng hội chứng chuyển hóa.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'Kết quả phụ thuộc nhiều vào bữa ăn trước xét nghiệm',
      'Cần xét nghiệm lúc đói để so sánh chính xác',
    ],
    futures: [
      {
        when: 'Nếu không thay đổi',
        text: 'Triglyceride cao kéo dài làm tăng nguy cơ tim mạch và gan nhiễm mỡ.',
        tone: 'med',
      },
      {
        when: 'Rất cao (> 5.6)',
        text: 'Có thể gây viêm tụy cấp — cần xử trí y tế.',
        tone: 'high',
      },
      {
        when: 'Nếu hành động hôm nay',
        text: 'Triglyceride đáp ứng nhanh với chế độ ăn — có thể về bình thường trong vài tuần.',
        tone: 'good',
      },
    ],
    needs: [
      { title: 'Xét nghiệm lúc đói', why: 'Để có kết quả triglyceride chính xác, ổn định.' },
      { title: 'Men gan & siêu âm gan', why: 'Đánh giá nguy cơ gan nhiễm mỡ liên quan.' },
    ],
    doctorQs: [
      'Triglyceride của tôi có cần dùng thuốc không?',
      'Tôi nên kiêng gì để hạ triglyceride nhanh nhất?',
      'Tôi có nguy cơ gan nhiễm mỡ không?',
    ],
    knowledge: [
      {
        q: 'Triglyceride cao có nguy hiểm không?',
        a: 'Tăng nhẹ làm tăng nguy cơ tim mạch; rất cao có thể gây viêm tụy.',
      },
      {
        q: 'Làm sao hạ triglyceride?',
        a: 'Giảm đường, tinh bột tinh chế và rượu; tăng vận động và cá béo giàu omega-3.',
      },
    ],
    chain: [
      {
        short: 'Triglyceride',
        note: 'Mỡ máu của bạn đang cao',
        status: 'med',
        bioKey: 'tg',
      },
      { short: 'Glucose', note: 'Cùng kiểu chuyển hóa', status: 'med', bioKey: 'glucose' },
      { short: 'Kháng insulin', note: 'Gốc rễ chung', status: 'high' },
      { short: 'HDL-C', note: 'Mỡ tốt giảm theo', status: 'low', bioKey: 'hdl' },
    ],
    trendData: [2.5, 2.4, 2.3, 2.3, 2.2, 2.1],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0,
    trendBandHigh: 1.7,
    trendMin: 0,
    trendMax: 3,
    trendComment:
      'Triglyceride đang giảm đều — chế độ ăn của bạn đang phát huy tác dụng. Tiếp tục giảm đường để chạm mục tiêu < 1.7.',
    relatedTrends: [
      { short: 'Glucose', from: '6.1', to: '5.8', unit: 'mmol/L', dir: 'down', good: true },
      { short: 'HDL-C', from: '1.02', to: '1.05', unit: 'mmol/L', dir: 'up', good: true },
    ],
  },
  hdl: {
    key: 'hdl',
    name: 'HDL-Cholesterol',
    short: 'HDL',
    value: '1.05',
    unit: 'mmol/L',
    range: '> 1.0',
    prev: '1.02',
    prevNote: 'tăng nhẹ',
    target: '> 1.3',
    status: 'low',
    gaugePosition: 30,
    gaugeTarget: 62,
    riskText: 'Cần cải thiện',
    conclusion:
      'HDL — cholesterol "tốt" — của bạn ở mức thấp, làm giảm khả năng bảo vệ mạch máu, nhất là khi LDL đang cao.',
    doesWhat:
      'HDL thu gom cholesterol dư trong mạch máu mang về gan xử lý. HDL càng cao càng bảo vệ tim mạch tốt.',
    analogy:
      'Nếu LDL là rác bám vào thành ống, thì HDL là "đội dọn dẹp". HDL thấp nghĩa là đội dọn dẹp quá ít so với lượng rác.',
    analogyIcon: 'Recycle',
    why: [
      { icon: 'Armchair', label: 'Ít vận động', note: 'Vận động là cách chính để tăng HDL' },
      { icon: 'Scale', label: 'Thừa cân vùng bụng', note: 'Làm giảm HDL' },
      { icon: 'Activity', label: 'Kháng insulin', note: 'Đi kèm HDL thấp, TG cao' },
    ],
    today: {
      title: 'Đi bộ nhanh 30 phút hôm nay',
      why: 'Vận động aerobic là cách hiệu quả nhất để nâng HDL — bắt đầu ngay hôm nay.',
    },
    plan: [
      { text: 'Tập aerobic 150 phút/tuần', sub: 'Đi bộ nhanh, đạp xe, bơi' },
      { text: 'Dùng dầu ô liu, quả bơ, các loại hạt', sub: 'Chất béo tốt nâng HDL' },
      { text: 'Giảm cân vùng bụng', sub: 'Cải thiện toàn bộ hồ sơ mỡ' },
    ],
    reasonIntro:
      'AI lưu ý HDL thấp vì nó làm khuếch đại nguy cơ từ LDL cao và triglyceride cao của bạn.',
    contributors: [
      { name: 'HDL-C 1.05 (thấp)', weight: 70, note: 'Dưới mục tiêu 1.3' },
      { name: 'Ít vận động', weight: 55, note: 'Yếu tố thay đổi được quan trọng nhất' },
      { name: 'TG cao 2.1', weight: 45, note: 'TG cao thường kéo HDL xuống' },
    ],
    derived: [
      { name: 'TG/HDL', val: '2.0', note: 'Cao — gợi ý kháng insulin' },
      { name: 'TC/HDL', val: '5.2', note: 'Vượt ngưỡng an toàn' },
    ],
    confidence: 78,
    confidenceNote: 'HDL khá ổn định giữa các lần đo nên kết quả đáng tin cậy.',
    evidence:
      'HDL < 1.0 mmol/L (nam) được xem là yếu tố nguy cơ tim mạch độc lập theo các hướng dẫn lipid.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'HDL rất cao không phải lúc nào cũng có lợi',
      'Cần nhìn cùng LDL và TG để đánh giá đầy đủ',
    ],
    futures: [
      {
        when: 'Nếu không thay đổi',
        text: 'HDL thấp kéo dài làm giảm khả năng bảo vệ mạch máu.',
        tone: 'med',
      },
      {
        when: 'Kèm LDL cao',
        text: 'Tổ hợp này đẩy nhanh quá trình xơ vữa.',
        tone: 'high',
      },
      {
        when: 'Nếu tăng vận động',
        text: 'HDL có thể cải thiện trong vài tháng tập đều.',
        tone: 'good',
      },
    ],
    needs: [
      { title: 'Mức độ vận động hàng tuần', why: 'Yếu tố ảnh hưởng lớn nhất đến HDL.' },
      { title: 'ApoA1', why: 'Đo trực tiếp thành phần bảo vệ của HDL.' },
    ],
    doctorQs: [
      'Làm sao để tăng HDL hiệu quả nhất với tôi?',
      'HDL thấp của tôi có cần can thiệp thuốc không?',
    ],
    knowledge: [
      {
        q: 'HDL bao nhiêu là tốt?',
        a: 'Nam nên > 1.0 mmol/L, lý tưởng > 1.3; nữ nên cao hơn một chút.',
      },
      {
        q: 'Làm sao tăng HDL?',
        a: 'Tập aerobic đều, chất béo tốt (dầu ô liu, hạt, cá béo), bỏ thuốc lá, giảm cân.',
      },
    ],
    chain: [
      { short: 'HDL-C', note: 'Mỡ tốt của bạn đang thấp', status: 'low', bioKey: 'hdl' },
      { short: 'LDL-C', note: 'Mỡ xấu cao đi kèm', status: 'high', bioKey: 'ldl' },
      { short: 'Triglyceride', note: 'TG cao kéo HDL xuống', status: 'med', bioKey: 'tg' },
      { short: 'Nguy cơ tim mạch', note: 'Tăng khi HDL thấp', status: 'high' },
    ],
    trendData: [0.98, 1.0, 1.01, 1.02, 1.04, 1.05],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 1.3,
    trendBandHigh: 2.0,
    trendMin: 0.8,
    trendMax: 2,
    trendComment:
      'HDL đang nhích lên — dấu hiệu tốt từ việc bạn vận động nhiều hơn. Giữ nhịp tập để vượt mốc 1.3.',
    relatedTrends: [
      {
        short: 'Triglyceride',
        from: '2.3',
        to: '2.1',
        unit: 'mmol/L',
        dir: 'down',
        good: true,
      },
      { short: 'TG/HDL', from: '2.3', to: '2.0', unit: '', dir: 'down', good: true },
    ],
  },
  vitd: {
    key: 'vitd',
    name: 'Vitamin D (25-OH)',
    short: 'Vitamin D',
    value: '18',
    unit: 'ng/mL',
    range: '30 – 50',
    prev: '16',
    prevNote: 'tăng nhẹ',
    target: '> 30',
    status: 'low',
    gaugePosition: 24,
    gaugeTarget: 64,
    riskText: 'Đang thiếu',
    conclusion:
      'Vitamin D của bạn đang thiếu, có thể ảnh hưởng đến xương, cơ và miễn dịch — rất phổ biến và dễ cải thiện.',
    doesWhat:
      'Vitamin D giúp hấp thu canxi cho xương, hỗ trợ cơ bắp và hệ miễn dịch. Phần lớn được tổng hợp khi da tiếp xúc ánh nắng.',
    analogy:
      'Vitamin D như "chìa khóa" mở cửa cho canxi vào xương. Thiếu chìa khóa thì dù ăn đủ canxi, xương vẫn khó hấp thu.',
    analogyIcon: 'Sun',
    why: [
      {
        icon: 'Building',
        label: 'Ít tiếp xúc ánh nắng',
        note: 'Làm việc trong nhà nhiều',
      },
      {
        icon: 'Shirt',
        label: 'Che chắn khi ra nắng',
        note: 'Giảm tổng hợp vitamin D qua da',
      },
      { icon: 'Fish', label: 'Khẩu phần ít cá béo', note: 'Nguồn vitamin D tự nhiên' },
      { icon: 'Calendar', label: 'Tuổi 52', note: 'Khả năng tổng hợp giảm theo tuổi' },
    ],
    today: {
      title: 'Ra nắng nhẹ 15 phút buổi sáng',
      why: 'Ánh nắng sớm giúp cơ thể tự tổng hợp vitamin D — cách tự nhiên và miễn phí.',
    },
    plan: [
      { text: 'Phơi nắng 15–20 phút buổi sáng', sub: '3–4 lần/tuần, tránh nắng gắt' },
      { text: 'Ăn cá béo, trứng, nấm', sub: 'Nguồn vitamin D từ thực phẩm' },
      { text: 'Cân nhắc bổ sung theo chỉ định', sub: 'Hỏi bác sĩ về liều phù hợp' },
      { text: 'Xét nghiệm lại sau 3 tháng', sub: 'Đánh giá đáp ứng' },
    ],
    reasonIntro:
      'AI xác định thiếu vitamin D dựa trên ngưỡng < 20 ng/mL và lối sống ít tiếp xúc nắng của bạn.',
    contributors: [
      { name: 'Vitamin D 18 ng/mL', weight: 75, note: 'Dưới ngưỡng đủ 30' },
      { name: 'Ít tiếp xúc ánh nắng', weight: 55, note: 'Nguyên nhân thường gặp nhất' },
      { name: 'Tuổi 52', weight: 35, note: 'Giảm tổng hợp theo tuổi' },
    ],
    derived: [],
    confidence: 86,
    confidenceNote: 'Độ tin cậy cao — xét nghiệm 25-OH là tiêu chuẩn đánh giá vitamin D.',
    evidence: 'Mức < 20 ng/mL được xem là thiếu; 20–29 là không đủ; ≥ 30 ng/mL là đủ.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'Nhu cầu bổ sung khác nhau tùy cá nhân',
      'Bổ sung quá liều cũng có hại',
    ],
    futures: [
      {
        when: 'Nếu không cải thiện',
        text: 'Thiếu kéo dài ảnh hưởng mật độ xương và cơ.',
        tone: 'med',
      },
      {
        when: 'Nếu bổ sung đúng cách',
        text: 'Mức vitamin D thường cải thiện rõ trong 2–3 tháng.',
        tone: 'good',
      },
    ],
    needs: [{ title: 'Canxi & PTH', why: 'Đánh giá ảnh hưởng lên chuyển hóa xương.' }],
    doctorQs: [
      'Tôi nên bổ sung vitamin D liều bao nhiêu?',
      'Tôi có cần kiểm tra mật độ xương không?',
    ],
    knowledge: [
      {
        q: 'Thiếu vitamin D có biểu hiện gì?',
        a: 'Mệt mỏi, đau cơ xương, dễ ốm vặt; nhiều người không có triệu chứng rõ.',
      },
      {
        q: 'Bổ sung vitamin D thế nào?',
        a: 'Kết hợp ánh nắng, thực phẩm và viên bổ sung theo chỉ định bác sĩ.',
      },
    ],
    chain: [
      { short: 'Vitamin D', note: 'Đang thiếu', status: 'low', bioKey: 'vitd' },
      { short: 'Canxi', note: 'Hấp thu phụ thuộc vitamin D', status: 'norm' },
      { short: 'Sức khỏe xương', note: 'Ảnh hưởng mật độ xương', status: 'med' },
    ],
    trendData: [14, 15, 15, 16, 17, 18],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 30,
    trendBandHigh: 50,
    trendMin: 10,
    trendMax: 50,
    trendComment:
      'Vitamin D đang tăng chậm. Để đạt mức đủ (> 30), bạn nên phơi nắng đều và cân nhắc bổ sung theo tư vấn bác sĩ.',
    relatedTrends: [],
  },
  hba1c: {
    key: 'hba1c',
    name: 'HbA1c',
    short: 'HbA1c',
    value: '5.7',
    unit: '%',
    range: '< 5.7',
    prev: '5.9',
    prevNote: 'giảm',
    target: '< 5.7',
    status: 'med',
    gaugePosition: 58,
    gaugeTarget: 48,
    riskText: 'Trung bình',
    conclusion:
      'HbA1c của bạn ở ranh giới tiền tiểu đường, phản ánh đường huyết trung bình 3 tháng — phù hợp với glucose lúc đói đang cao.',
    doesWhat:
      'HbA1c đo tỉ lệ đường gắn vào hồng cầu, cho biết mức đường huyết trung bình trong khoảng 3 tháng — ổn định hơn một lần đo glucose.',
    analogy:
      'Nếu glucose là "ảnh chụp" tại một thời điểm, thì HbA1c là "đoạn phim 3 tháng" — cho thấy xu hướng thật sự.',
    analogyIcon: 'Film',
    why: [
      {
        icon: 'Droplet',
        label: 'Glucose lúc đói 5.8',
        note: 'Đường huyết nền cao kéo HbA1c lên',
      },
      { icon: 'Scale', label: 'BMI 27', note: 'Thừa cân làm tăng kháng insulin' },
    ],
    today: {
      title: 'Đi bộ 20–30 phút sau bữa tối',
      why: 'Kiểm soát đường huyết mỗi ngày là cách hạ HbA1c bền vững nhất.',
    },
    plan: [
      { text: 'Kiểm soát khẩu phần tinh bột', sub: 'Ưu tiên ngũ cốc nguyên hạt' },
      { text: 'Đi bộ sau ăn 5 ngày/tuần', sub: 'Giảm đường huyết sau ăn' },
      { text: 'Xét nghiệm lại HbA1c sau 3 tháng', sub: 'Theo dõi đúng chu kỳ hồng cầu' },
    ],
    reasonIntro:
      'AI dùng HbA1c để xác nhận xu hướng đường huyết — vì một lần đo glucose có thể dao động, còn HbA1c phản ánh 3 tháng.',
    contributors: [
      { name: 'HbA1c 5.7%', weight: 65, note: 'Ngay ranh giới tiền tiểu đường' },
      { name: 'Glucose lúc đói 5.8', weight: 60, note: 'Nhất quán với HbA1c' },
    ],
    derived: [{ name: 'eAG (đường TB ước tính)', val: '6.5', note: 'mmol/L — tương ứng HbA1c' }],
    confidence: 88,
    confidenceNote: 'Độ tin cậy cao vì HbA1c ổn định và nhất quán với glucose của bạn.',
    evidence: 'Theo ADA, HbA1c 5.7–6.4% là tiền tiểu đường; ≥ 6.5% là tiểu đường.',
    limitations: [
      'AI không thay thế chẩn đoán của bác sĩ',
      'HbA1c có thể sai lệch khi có thiếu máu hoặc bệnh hồng cầu',
    ],
    futures: [
      {
        when: 'Nếu không thay đổi',
        text: 'HbA1c có thể vượt 6.5% và chuyển sang tiểu đường.',
        tone: 'high',
      },
      {
        when: 'Nếu cải thiện lối sống',
        text: 'Phần lớn trường hợp đưa HbA1c về dưới 5.7% trong 3–6 tháng.',
        tone: 'good',
      },
    ],
    needs: [{ title: 'Insulin lúc đói', why: 'Để đánh giá mức kháng insulin kèm theo.' }],
    doctorQs: [
      'HbA1c của tôi có cần theo dõi sát hơn không?',
      'Bao lâu tôi nên xét nghiệm HbA1c một lần?',
    ],
    knowledge: [
      {
        q: 'HbA1c khác glucose thế nào?',
        a: 'Glucose là đường huyết tức thời; HbA1c là trung bình khoảng 3 tháng.',
      },
      {
        q: 'HbA1c bao nhiêu là bình thường?',
        a: '< 5.7% bình thường; 5.7–6.4% tiền tiểu đường; ≥ 6.5% tiểu đường.',
      },
    ],
    chain: [
      {
        short: 'HbA1c',
        note: 'Đường huyết 3 tháng ở ranh giới',
        status: 'med',
        bioKey: 'hba1c',
      },
      { short: 'Glucose', note: 'Đường huyết lúc đói cao', status: 'med', bioKey: 'glucose' },
      { short: 'Kháng insulin', note: 'Gốc rễ chung', status: 'high' },
    ],
    trendData: [6.1, 6.0, 5.9, 5.9, 5.8, 5.7],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 4,
    trendBandHigh: 5.7,
    trendMin: 4,
    trendMax: 6.5,
    trendComment:
      'HbA1c đang giảm về sát ngưỡng bình thường — nỗ lực của bạn đang có kết quả rõ ràng. Chỉ còn một chút nữa.',
    relatedTrends: [
      { short: 'Glucose', from: '6.1', to: '5.8', unit: 'mmol/L', dir: 'down', good: true },
      { short: 'Triglyceride', from: '2.3', to: '2.1', unit: 'mmol/L', dir: 'down', good: true },
    ],
  },
}

// ── M4 · Network ──────────────────────────────────────────────────────────────

export interface NetworkNode {
  id: string
  label: string
  sub: string
  x: number
  y: number
  category: 'all' | 'metabolic' | 'cardio'
  status: StatusLevel
  isCenter?: boolean
  bioKey?: string
}

export interface NetworkEdge {
  from: string
  to: string
  strength: 'strong' | 'med'
}

export interface NetworkInfo {
  title: string
  desc: string
  bioKey?: string
}

export const mockNetworkNodes: NetworkNode[] = [
  {
    id: 'insulin',
    label: 'Kháng insulin',
    sub: 'Mẫu hình trung tâm',
    x: 165,
    y: 172,
    category: 'all',
    status: 'high',
    isCenter: true,
  },
  {
    id: 'glucose',
    label: 'Glucose',
    sub: '↑ cao',
    x: 58,
    y: 62,
    category: 'metabolic',
    status: 'med',
    bioKey: 'glucose',
  },
  {
    id: 'insulinM',
    label: 'Insulin',
    sub: '↑ cao',
    x: 272,
    y: 62,
    category: 'metabolic',
    status: 'high',
  },
  {
    id: 'homa',
    label: 'HOMA-IR',
    sub: '↑ 2.9',
    x: 42,
    y: 188,
    category: 'metabolic',
    status: 'high',
  },
  {
    id: 'hdl',
    label: 'HDL-C',
    sub: '↓ thấp',
    x: 288,
    y: 188,
    category: 'cardio',
    status: 'low',
    bioKey: 'hdl',
  },
  {
    id: 'tg',
    label: 'Triglyceride',
    sub: '↑ cao',
    x: 74,
    y: 306,
    category: 'cardio',
    status: 'med',
    bioKey: 'tg',
  },
  {
    id: 'fatty',
    label: 'Gan nhiễm mỡ',
    sub: 'nguy cơ',
    x: 256,
    y: 306,
    category: 'cardio',
    status: 'med',
  },
]

export const mockNetworkEdges: NetworkEdge[] = [
  { from: 'insulin', to: 'glucose', strength: 'strong' },
  { from: 'insulin', to: 'insulinM', strength: 'strong' },
  { from: 'insulin', to: 'homa', strength: 'strong' },
  { from: 'insulin', to: 'hdl', strength: 'med' },
  { from: 'insulin', to: 'tg', strength: 'med' },
  { from: 'tg', to: 'fatty', strength: 'med' },
  { from: 'hdl', to: 'fatty', strength: 'med' },
]

export const mockNetworkInfo: Record<string, NetworkInfo> = {
  insulin: {
    title: 'Kháng insulin',
    desc: 'Khi tế bào kém đáp ứng với insulin, tụy phải tiết nhiều hơn để giữ đường huyết ổn định. Đây là "gốc rễ" kết nối đường huyết, mỡ máu và gan nhiễm mỡ của bạn.',
  },
  glucose: {
    title: 'Glucose',
    desc: 'Đường huyết tăng là hệ quả trực tiếp của kháng insulin — tế bào không nhận đủ đường nên đường ứ lại trong máu.',
    bioKey: 'glucose',
  },
  insulinM: {
    title: 'Insulin',
    desc: 'Insulin trong máu cao là cách cơ thể bù trừ cho tình trạng kháng — thường xuất hiện sớm, trước khi đường huyết tăng rõ.',
  },
  homa: {
    title: 'HOMA-IR',
    desc: 'Chỉ số tính từ glucose và insulin, lượng hóa mức độ kháng insulin. Của bạn là 2.9 — vượt ngưỡng 2.5.',
  },
  hdl: {
    title: 'HDL-C',
    desc: 'Kháng insulin làm giảm cholesterol "tốt" HDL, khiến mạch máu mất đi một lớp bảo vệ quan trọng.',
    bioKey: 'hdl',
  },
  tg: {
    title: 'Triglyceride',
    desc: 'Khi kháng insulin, gan tăng sản xuất mỡ và đẩy triglyceride trong máu lên cao.',
    bioKey: 'tg',
  },
  fatty: {
    title: 'Gan nhiễm mỡ',
    desc: 'Mỡ tích tụ trong gan là hệ quả thường gặp của kháng insulin kéo dài — cần theo dõi men gan.',
  },
}

// ── M5 · Journey ──────────────────────────────────────────────────────────────

export type JourneyCategory = 'all' | 'lab' | 'win' | 'weight' | 'bp' | 'med' | 'life'

export interface JourneyEvent {
  id: string
  date: string
  category: JourneyCategory
  icon: string
  iconBg: string
  iconColor: string
  title: string
  tag?: string
  desc: string
  ai?: string
}

export interface JourneyData {
  weightCurrent: string
  weightDelta: string
  weightHistory: number[]
  bpCurrent: string
  bpHistory: number[]
  events: JourneyEvent[]
}

export const mockJourneyData: JourneyData = {
  weightCurrent: '75.5',
  weightDelta: '↓2.5',
  weightHistory: [78, 77.6, 77, 76.4, 76, 75.5],
  bpCurrent: '122/78',
  bpHistory: [132, 130, 128, 126, 124, 122],
  events: [
    {
      id: 'j1',
      date: '20/06/2025',
      category: 'lab',
      icon: 'FlaskConical',
      iconBg: '#D1FAE5',
      iconColor: '#059669',
      title: 'Kết quả xét nghiệm mới',
      desc: 'Glucose 5.8 · HbA1c 5.7% · Triglyceride 2.1',
      ai: 'Đường huyết cải thiện rõ rệt 3 tháng qua. Bạn đang đi đúng hướng — giữ nhịp vận động!',
    },
    {
      id: 'j2',
      date: '31/05/2025',
      category: 'win',
      icon: 'Flame',
      iconBg: '#FEF3C7',
      iconColor: '#D97706',
      title: 'Chuỗi đi bộ 30 ngày',
      tag: 'Thành tựu',
      desc: 'Hoàn thành mục tiêu vận động cả tháng 5',
    },
    {
      id: 'j3',
      date: '18/04/2025',
      category: 'weight',
      icon: 'Scale',
      iconBg: '#D1FAE5',
      iconColor: '#059669',
      title: 'Giảm 2.5 kg',
      desc: 'Cân nặng 78.0 → 75.5 kg · vòng eo giảm 3cm',
      ai: 'Giảm cân vùng bụng giúp cải thiện độ nhạy insulin — yếu tố then chốt với bạn.',
    },
    {
      id: 'j4',
      date: '12/03/2025',
      category: 'bp',
      icon: 'HeartPulse',
      iconBg: '#FEE2E2',
      iconColor: '#DC2626',
      title: 'Huyết áp ổn định',
      desc: 'Trung bình 122/78 mmHg trong 4 tuần',
    },
    {
      id: 'j5',
      date: '05/02/2025',
      category: 'med',
      icon: 'Pill',
      iconBg: '#DBEAFE',
      iconColor: '#2563EB',
      title: 'Bắt đầu dùng Metformin',
      desc: '500mg/ngày theo chỉ định bác sĩ',
    },
    {
      id: 'j6',
      date: '15/12/2024',
      category: 'lab',
      icon: 'FlaskConical',
      iconBg: '#D1FAE5',
      iconColor: '#059669',
      title: 'Phát hiện tiền tiểu đường',
      desc: 'Glucose 6.4 · HbA1c 6.0%',
      ai: 'AI khuyến nghị can thiệp lối sống sớm — thời điểm vàng để đảo ngược.',
    },
    {
      id: 'j7',
      date: '20/10/2024',
      category: 'life',
      icon: 'Salad',
      iconBg: '#D1FAE5',
      iconColor: '#059669',
      title: 'Thay đổi chế độ ăn',
      desc: 'Giảm đường, nước ngọt; tăng rau xanh & chất xơ',
    },
    {
      id: 'j8',
      date: '08/05/2024',
      category: 'lab',
      icon: 'Flag',
      iconBg: '#EDE9FE',
      iconColor: '#7C3AED',
      title: 'Bắt đầu hành trình MetoCare',
      desc: 'Hồ sơ sức khỏe đầu tiên được thiết lập',
    },
  ],
}

// ── M6 · Coach ────────────────────────────────────────────────────────────────

export interface CoachTask {
  id: string
  text: string
  sub: string
}

export interface CoachStreak {
  icon: string
  days: number
  label: string
  color: string
  bg: string
}

export interface CoachGoal {
  name: string
  pct: number
  color: string
}

export interface CoachWin {
  icon: string
  label: string
}

export interface CoachData {
  patientName: string
  motivation: string
  yesterdayHighlight?: string
  tasks: CoachTask[]
  streaks: CoachStreak[]
  goals: CoachGoal[]
  weekSummary: string
  wins: CoachWin[]
}

export const mockCoachData: CoachData = {
  patientName: 'Anh Minh',
  motivation:
    '3 tháng qua anh đã làm rất tốt — glucose giảm đều. Hôm nay chỉ cần giữ nhịp, đừng bỏ buổi đi bộ nhé!',
  yesterdayHighlight:
    'Đi bộ 28 phút sau bữa tối — chuỗi 12 ngày liên tiếp! Glucose hôm nay giảm đáng kể.',
  tasks: [
    { id: 'c1', text: 'Đi bộ 25 phút sau bữa tối', sub: 'Ưu tiên cao' },
    { id: 'c2', text: 'Uống đủ 2 lít nước', sub: 'Thay cho nước ngọt' },
    { id: 'c3', text: 'Thêm rau xanh vào bữa trưa', sub: 'Làm chậm hấp thu đường' },
  ],
  streaks: [
    { icon: 'Footprints', days: 12, label: 'Ngày đi bộ', color: '#059669', bg: '#D1FAE5' },
    { icon: 'Droplets', days: 7, label: 'Ngày uống đủ nước', color: '#2563EB', bg: '#DBEAFE' },
    { icon: 'Salad', days: 5, label: 'Ngày ăn rau xanh', color: '#D97706', bg: '#FEF3C7' },
  ],
  goals: [
    { name: 'Đưa glucose < 5.6', pct: 74, color: '#F59E0B' },
    { name: 'Tăng HDL > 1.3', pct: 42, color: '#DC2626' },
    { name: 'Giảm 2 kg nữa', pct: 60, color: '#059669' },
    { name: 'Tập 150 phút/tuần', pct: 83, color: '#7C3AED' },
  ],
  weekSummary:
    'Bạn hoàn thành 5/7 ngày vận động và giảm rõ lượng đường. Tuần tới hãy thử thêm 1 buổi tập sức bền để tăng độ nhạy insulin.',
  wins: [
    { icon: 'Flame', label: 'Chuỗi 12 ngày đi bộ' },
    { icon: 'TrendingDown', label: 'Glucose giảm 0.3' },
    { icon: 'Star', label: 'Tuần vàng hoàn thành' },
  ],
}
