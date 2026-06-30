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
      { short: 'eGFR', value: '92', unit: 'mL/phút', status: 'good', bioKey: 'egfr' },
      { short: 'Creatinine', value: '84', unit: 'µmol/L', status: 'good', bioKey: 'creatinine' },
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
      { short: 'ALT', value: '32', unit: 'U/L', status: 'good', bioKey: 'alt' },
      { short: 'AST', value: '28', unit: 'U/L', status: 'good', bioKey: 'ast' },
      { short: 'GGT', value: '41', unit: 'U/L', status: 'norm', bioKey: 'ggt' },
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
    markers: [{ short: 'hs-CRP', value: '1.1', unit: 'mg/L', status: 'good', bioKey: 'hs-crp' }],
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
      { short: 'FT4', value: '14.2', unit: 'pmol/L', status: 'good', bioKey: 'ft4' },
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
      { short: 'Ferritin', value: '48', unit: 'ng/mL', status: 'norm', bioKey: 'ferritin' },
      { short: 'B12', value: '410', unit: 'pg/mL', status: 'good', bioKey: 'b12' },
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

  tsh: {
    key: 'tsh',
    name: 'Hormone kích thích tuyến giáp (TSH)',
    short: 'TSH',
    value: '3.8',
    unit: 'mIU/L',
    range: '0.4 – 4.0',
    prev: '3.2',
    prevNote: 'tăng nhẹ so với lần trước',
    target: '< 2.5',
    status: 'norm',
    gaugePosition: 72,
    gaugeTarget: 40,
    riskText: 'Cao bình thường',
    conclusion: 'TSH của bạn ở mức cao bình thường. Tuyến giáp đang hoạt động ổn định nhưng cần theo dõi nếu có triệu chứng mệt mỏi, tăng cân hoặc lạnh tay chân.',
    doesWhat: 'TSH là hormone do tuyến yên sản xuất, điều khiển tuyến giáp tiết T3 và T4 — các hormone điều hòa tốc độ chuyển hóa toàn cơ thể. TSH cao thường gợi ý tuyến giáp hoạt động chậm hơn bình thường.',
    analogy: 'Hãy hình dung TSH như "tín hiệu ga" từ não gửi xuống tuyến giáp. TSH cao nghĩa là não đang đạp ga mạnh hơn vì tuyến giáp chưa cung cấp đủ hormone.',
    analogyIcon: 'Gauge',
    why: [
      { icon: 'User', label: 'Nam · 52 tuổi', note: 'Chức năng tuyến giáp có thể thay đổi theo tuổi' },
      { icon: 'Scale', label: 'BMI 27', note: 'Thừa cân nhẹ có thể ảnh hưởng đến nồng độ TSH' },
    ],
    today: {
      title: 'Ghi nhận triệu chứng tuyến giáp',
      why: 'Lưu lại dấu hiệu như mệt mỏi bất thường, lạnh tay chân, tăng cân không rõ nguyên nhân để cung cấp cho bác sĩ khi tái khám.',
    },
    plan: [
      { text: 'Kiểm tra TSH + FT4 sau 3–6 tháng', sub: 'Theo dõi xu hướng, không cần điều trị nếu không có triệu chứng' },
      { text: 'Ghi nhận triệu chứng hàng ngày', sub: 'Mệt mỏi, lạnh, tăng cân, khô da, táo bón' },
    ],
    reasonIntro: 'TSH 3.8 ở mức cao bình thường (ngưỡng trên 4.0). Chưa cần điều trị nhưng cần theo dõi xu hướng.',
    contributors: [
      { name: 'TSH 3.8 mIU/L', weight: 80, note: 'Gần ngưỡng trên của bình thường' },
      { name: 'FT4 14.2 pmol/L', weight: 40, note: 'FT4 thấp bình thường, phù hợp với TSH cao' },
    ],
    derived: [],
    confidence: 72,
    confidenceNote: 'Cần thêm FT3 và Anti-TPO để đánh giá đầy đủ chức năng tuyến giáp.',
    evidence: 'Theo ATA 2023, TSH 3.8 thuộc ngưỡng bình thường. Suy giáp cận lâm sàng chỉ chẩn đoán khi TSH > 4.5 mIU/L kết hợp với triệu chứng.',
    limitations: [
      'AI không thể chẩn đoán bệnh tuyến giáp từ TSH đơn lẻ',
      'Kết quả có thể thay đổi tùy giờ lấy máu và thuốc đang dùng',
    ],
    futures: [
      { when: 'Nếu TSH tiếp tục tăng', text: 'Nguy cơ suy giáp cận lâm sàng — nên tư vấn chuyên khoa nội tiết.', tone: 'med' },
      { when: 'Nếu TSH ổn định', text: 'Không cần can thiệp, tiếp tục theo dõi định kỳ hàng năm.', tone: 'good' },
    ],
    needs: [
      { title: 'Anti-TPO', why: 'Kháng thể tuyến giáp giúp phát hiện nguyên nhân tự miễn' },
      { title: 'FT3', why: 'Hoàn thiện đánh giá chức năng tuyến giáp' },
    ],
    doctorQs: [
      'TSH 3.8 có cần điều trị không hay chỉ theo dõi?',
      'Tôi nên xét nghiệm FT3 và Anti-TPO không?',
      'Bao lâu nên kiểm tra lại TSH một lần?',
    ],
    knowledge: [
      { q: 'TSH là gì?', a: 'TSH (Thyroid-Stimulating Hormone) là hormone tuyến yên điều khiển tuyến giáp sản xuất T3 và T4.' },
      { q: 'TSH cao nghĩa là gì?', a: 'TSH cao thường gợi ý tuyến giáp hoạt động kém (suy giáp), nhưng cần kết hợp với FT4 và triệu chứng để xác định.' },
    ],
    chain: [
      { short: 'FT4', note: 'Hormone tuyến giáp thực tế', status: 'good', bioKey: 'ft4' },
    ],
    trendData: [3.2, 3.4, 3.5, 3.6, 3.7, 3.8],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0.4,
    trendBandHigh: 4.0,
    trendMin: 0,
    trendMax: 5,
    trendComment: 'TSH có xu hướng tăng nhẹ trong 6 tháng qua. Chưa vượt ngưỡng bình thường nhưng đáng chú ý.',
    relatedTrends: [
      { short: 'FT4', from: '15.1', to: '14.2', unit: 'pmol/L', dir: 'down', good: false },
    ],
  },

  ft4: {
    key: 'ft4',
    name: 'Thyroxine tự do (FT4)',
    short: 'FT4',
    value: '14.2',
    unit: 'pmol/L',
    range: '12 – 22',
    prev: '15.1',
    prevNote: 'giảm nhẹ so với lần trước',
    target: '14 – 22',
    status: 'good',
    gaugePosition: 22,
    gaugeTarget: 45,
    riskText: 'Bình thường',
    conclusion: 'FT4 trong giới hạn bình thường, tuyến giáp đang sản xuất đủ hormone. Khi đọc cùng TSH 3.8, chức năng tuyến giáp hiện ổn định.',
    doesWhat: 'FT4 là dạng thyroxine tự do trong máu — hormone tuyến giáp trực tiếp ảnh hưởng đến nhịp tim, nhiệt độ cơ thể, tốc độ chuyển hóa và năng lượng. Đây là chỉ số phản ánh chức năng tuyến giáp thực tế.',
    analogy: 'Nếu TSH là tín hiệu ga thì FT4 là xăng thực tế được bơm vào động cơ. FT4 bình thường nghĩa là động cơ vẫn đang chạy đủ nhiên liệu.',
    analogyIcon: 'Zap',
    why: [
      { icon: 'Activity', label: 'Chức năng tuyến giáp', note: 'FT4 phản ánh lượng hormone tuyến giáp thực tế đang hoạt động trong cơ thể' },
    ],
    today: {
      title: 'Không cần hành động ngay',
      why: 'FT4 bình thường — tuyến giáp đang hoạt động đủ. Tiếp tục theo dõi định kỳ theo lịch bác sĩ.',
    },
    plan: [
      { text: 'Kiểm tra lại FT4 + TSH sau 6 tháng', sub: 'Theo dõi cùng với TSH để đánh giá xu hướng' },
    ],
    reasonIntro: 'FT4 14.2 pmol/L ở mức thấp bình thường. Kết hợp TSH 3.8 (cao bình thường) gợi ý tuyến giáp bù trừ nhẹ, cần theo dõi.',
    contributors: [
      { name: 'FT4 14.2 pmol/L', weight: 70, note: 'Thấp bình thường trong khoảng 12–22' },
    ],
    derived: [],
    confidence: 68,
    confidenceNote: 'Cần thêm TSH, FT3 và Anti-TPO để đánh giá toàn diện.',
    evidence: 'Theo ETA 2023, FT4 trong khoảng 12–22 pmol/L là bình thường. Chẩn đoán bệnh tuyến giáp cần kết hợp TSH, FT4, FT3 và triệu chứng lâm sàng.',
    limitations: [
      'FT4 đơn lẻ không đủ để chẩn đoán bệnh tuyến giáp',
      'Một số thuốc (biotin, heparin) có thể ảnh hưởng kết quả',
    ],
    futures: [
      { when: 'Nếu FT4 tiếp tục giảm', text: 'Nguy cơ suy giáp cần điều trị thay thế hormone.', tone: 'med' },
      { when: 'Nếu FT4 ổn định', text: 'Tiếp tục theo dõi định kỳ, không cần can thiệp.', tone: 'good' },
    ],
    needs: [
      { title: 'FT3', why: 'Đánh giá đầy đủ chức năng tuyến giáp' },
    ],
    doctorQs: [
      'FT4 14.2 kết hợp với TSH 3.8 có đáng lo không?',
      'Tôi có cần xét nghiệm Anti-TPO không?',
    ],
    knowledge: [
      { q: 'FT4 khác T4 thế nào?', a: 'T4 là tổng thyroxine gắn protein; FT4 là phần tự do thực sự có hoạt tính sinh học. FT4 phản ánh chính xác hơn chức năng tuyến giáp.' },
      { q: 'FT4 thấp có nghĩa gì?', a: 'FT4 thấp (dưới 12 pmol/L) kết hợp TSH cao là dấu hiệu của suy giáp thực sự cần điều trị.' },
    ],
    chain: [
      { short: 'TSH', note: 'Tín hiệu điều khiển từ tuyến yên', status: 'norm', bioKey: 'tsh' },
    ],
    trendData: [15.1, 14.9, 14.8, 14.6, 14.4, 14.2],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 12,
    trendBandHigh: 22,
    trendMin: 10,
    trendMax: 25,
    trendComment: 'FT4 giảm nhẹ nhưng vẫn trong giới hạn bình thường. Xu hướng này đáng theo dõi cùng với TSH.',
    relatedTrends: [
      { short: 'TSH', from: '3.2', to: '3.8', unit: 'mIU/L', dir: 'up', good: false },
    ],
  },

  thyroglobulin: {
    key: 'thyroglobulin',
    name: 'Thyroglobulin',
    short: 'Tg',
    value: '18.5',
    unit: 'ng/mL',
    range: '< 55',
    prev: '',
    prevNote: '',
    target: '< 10',
    status: 'norm',
    gaugePosition: 34,
    gaugeTarget: 18,
    riskText: 'Bình thường',
    conclusion: 'Thyroglobulin trong giới hạn bình thường, không gợi ý bệnh lý tuyến giáp đang hoạt động. Cần theo dõi xu hướng qua các lần xét nghiệm tiếp theo.',
    doesWhat: 'Thyroglobulin là protein do tế bào tuyến giáp sản xuất. Nồng độ cao có thể gợi ý bệnh lý tuyến giáp (viêm, nhân, ung thư). Ở người đã phẫu thuật tuyến giáp, Tg là chỉ số theo dõi tái phát quan trọng.',
    analogy: 'Thyroglobulin như "dấu vết" tuyến giáp để lại trong máu. Ở người bình thường, một lượng nhỏ là bình thường; mức tăng cao đột ngột cần điều tra thêm.',
    analogyIcon: 'Search',
    why: [
      { icon: 'Activity', label: 'Sức khỏe tuyến giáp', note: 'Thyroglobulin phản ánh hoạt động của mô tuyến giáp' },
    ],
    today: {
      title: 'Không cần hành động ngay',
      why: 'Thyroglobulin bình thường. Tiếp tục theo dõi định kỳ theo chỉ định bác sĩ.',
    },
    plan: [
      { text: 'Kiểm tra Tg định kỳ hàng năm', sub: 'Theo dõi xu hướng qua thời gian' },
    ],
    reasonIntro: 'Thyroglobulin 18.5 ng/mL dưới ngưỡng bình thường 55 ng/mL. Không có dấu hiệu bệnh lý đáng lo ngại.',
    contributors: [
      { name: 'Thyroglobulin 18.5 ng/mL', weight: 60, note: 'Trong giới hạn bình thường' },
    ],
    derived: [],
    confidence: 60,
    confidenceNote: 'Ý nghĩa của Thyroglobulin phụ thuộc nhiều vào bối cảnh lâm sàng (có phẫu thuật tuyến giáp không, có kháng thể Anti-Tg không).',
    evidence: 'Theo ATA 2023, Thyroglobulin < 55 ng/mL là bình thường ở người không phẫu thuật tuyến giáp. Ở người sau phẫu thuật, mọi Tg đo được đều đáng chú ý.',
    limitations: [
      'Kháng thể Anti-Tg có thể làm sai lệch kết quả',
      'Giá trị bình thường thay đổi tùy phương pháp xét nghiệm',
    ],
    futures: [
      { when: 'Nếu Tg tăng cao', text: 'Cần siêu âm tuyến giáp và tư vấn chuyên khoa.', tone: 'med' },
    ],
    needs: [
      { title: 'Anti-Tg (kháng thể Thyroglobulin)', why: 'Loại trừ nhiễu khi đo Tg' },
    ],
    doctorQs: [
      'Thyroglobulin 18.5 của tôi có cần theo dõi gì đặc biệt không?',
      'Tôi có cần xét nghiệm Anti-Tg không?',
    ],
    knowledge: [
      { q: 'Thyroglobulin dùng để làm gì?', a: 'Thường dùng để theo dõi tái phát ở người đã phẫu thuật ung thư tuyến giáp. Ở người bình thường, nồng độ thấp là bình thường.' },
    ],
    chain: [
      { short: 'TSH', note: 'Điều hòa tuyến giáp', status: 'norm', bioKey: 'tsh' },
    ],
    trendData: [20, 19.5, 19.2, 18.8, 18.6, 18.5],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0,
    trendBandHigh: 55,
    trendMin: 0,
    trendMax: 60,
    trendComment: 'Thyroglobulin ổn định và trong giới hạn bình thường trong 6 tháng qua.',
    relatedTrends: [],
  },

  'total-cholesterol': {
    key: 'total-cholesterol',
    name: 'Cholesterol toàn phần',
    short: 'Total-C',
    value: '5.9',
    unit: 'mmol/L',
    range: '< 5.2',
    prev: '6.2',
    prevNote: 'giảm nhẹ so với lần trước',
    target: '< 4.5',
    status: 'high',
    gaugePosition: 76,
    gaugeTarget: 55,
    riskText: 'Cao',
    conclusion: 'Cholesterol toàn phần cao hơn ngưỡng khuyến cáo. Kết hợp với LDL cao và HDL thấp, nguy cơ tim mạch của bạn đang ở mức trung bình và cần can thiệp lối sống.',
    doesWhat: 'Cholesterol toàn phần là tổng của LDL, HDL và VLDL trong máu. Mức quá cao làm tăng nguy cơ xơ vữa động mạch — nguyên nhân chính của nhồi máu cơ tim và đột quỵ.',
    analogy: 'Cholesterol như một "đội giao hàng" trong máu — vừa cần thiết vừa nguy hiểm nếu quá nhiều. LDL giao hàng đến tế bào (nhưng để lại mảng bám); HDL thu gom "rác" về gan xử lý.',
    analogyIcon: 'Truck',
    why: [
      { icon: 'User', label: 'Nam · 52 tuổi', note: 'Nguy cơ tim mạch tăng dần sau 45 tuổi ở nam' },
      { icon: 'Armchair', label: 'Ít vận động', note: 'Ít vận động làm giảm HDL và tăng LDL' },
      { icon: 'Scale', label: 'BMI 27', note: 'Thừa cân làm tăng cholesterol toàn phần' },
    ],
    today: {
      title: 'Giảm chất béo bão hòa trong bữa ăn',
      why: 'Thay mỡ động vật bằng dầu ô liu, cá và các loại hạt — cách hiệu quả nhất để hạ LDL và cholesterol toàn phần mà không cần thuốc trong giai đoạn đầu.',
    },
    plan: [
      { text: 'Giảm chất béo bão hòa', sub: 'Hạn chế mỡ động vật, thức ăn chiên rán, phô mai' },
      { text: 'Tăng chất xơ hòa tan', sub: 'Yến mạch, đậu, táo — liên kết cholesterol và đào thải ra ngoài' },
      { text: 'Vận động 150 phút/tuần', sub: 'Đi bộ, bơi lội giúp tăng HDL và hạ LDL' },
      { text: 'Tái xét nghiệm sau 3 tháng', sub: 'Đánh giá hiệu quả thay đổi lối sống trước khi cân nhắc thuốc' },
    ],
    reasonIntro: 'Cholesterol toàn phần 5.9 vượt ngưỡng 5.2 mmol/L. Kết hợp với LDL 3.6 và HDL thấp cho thấy rối loạn lipid máu cần can thiệp.',
    contributors: [
      { name: 'LDL 3.6 mmol/L', weight: 75, note: 'Đóng góp lớn nhất vào cholesterol toàn phần' },
      { name: 'Triglyceride 2.1 mmol/L', weight: 50, note: 'VLDL cao từ triglyceride' },
      { name: 'HDL 1.05 mmol/L', weight: 45, note: 'HDL thấp làm giảm khả năng dọn dẹp cholesterol' },
    ],
    derived: [
      { name: 'Tỷ lệ LDL/HDL', val: '3.4', note: 'Lý tưởng < 3.0 — nguy cơ trung bình' },
    ],
    confidence: 80,
    confidenceNote: 'Đánh giá đầy đủ cần thêm Apolipoprotein B và non-HDL cholesterol.',
    evidence: 'Theo ACC/AHA 2023, cholesterol toàn phần < 5.2 mmol/L là mục tiêu lý tưởng. Mức 5.9 cần can thiệp lối sống tích cực.',
    limitations: [
      'Cholesterol toàn phần đơn lẻ kém dự báo nguy cơ tim mạch hơn LDL và non-HDL',
    ],
    futures: [
      { when: 'Nếu không thay đổi · 2 năm', text: 'Nguy cơ xơ vữa động mạch tăng, có thể cần điều trị bằng statin.', tone: 'high' },
      { when: 'Nếu thay đổi lối sống · 3 tháng', text: 'Có thể giảm 10–15% cholesterol toàn phần chỉ qua chế độ ăn và vận động.', tone: 'good' },
    ],
    needs: [],
    doctorQs: [
      'Cholesterol 5.9 của tôi có cần dùng statin ngay không?',
      'Tỷ lệ LDL/HDL bao nhiêu là cần điều trị thuốc?',
      'Chế độ ăn nào hiệu quả nhất để hạ cholesterol của tôi?',
    ],
    knowledge: [
      { q: 'Cholesterol toàn phần bao nhiêu là cao?', a: '> 5.2 mmol/L là cao; > 6.2 mmol/L là rất cao theo khuyến cáo hiện hành.' },
      { q: 'Cholesterol có hoàn toàn xấu không?', a: 'Không — cơ thể cần cholesterol để tạo hormone, vitamin D và màng tế bào. Vấn đề là khi LDL quá nhiều và HDL quá ít.' },
    ],
    chain: [
      { short: 'LDL-C', note: 'Thành phần chính gây nguy cơ', status: 'high', bioKey: 'ldl' },
      { short: 'HDL-C', note: 'Thành phần bảo vệ', status: 'low', bioKey: 'hdl' },
      { short: 'Triglyceride', note: 'Góp vào VLDL', status: 'med', bioKey: 'tg' },
    ],
    trendData: [6.2, 6.1, 6.0, 5.9, 5.9, 5.9],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0,
    trendBandHigh: 5.2,
    trendMin: 3,
    trendMax: 7,
    trendComment: 'Cholesterol toàn phần đang giảm nhẹ nhưng vẫn cao hơn mục tiêu. Cần tiếp tục duy trì thay đổi lối sống.',
    relatedTrends: [
      { short: 'LDL', from: '3.9', to: '3.6', unit: 'mmol/L', dir: 'down', good: true },
    ],
  },

  alt: {
    key: 'alt',
    name: 'Men gan ALT (Alanine Aminotransferase)',
    short: 'ALT',
    value: '32',
    unit: 'U/L',
    range: '7 – 40',
    prev: '38',
    prevNote: 'giảm tốt từ lần trước',
    target: '< 25',
    status: 'good',
    gaugePosition: 65,
    gaugeTarget: 45,
    riskText: 'Bình thường',
    conclusion: 'ALT trong giới hạn bình thường. Gan không có dấu hiệu tổn thương cấp tính. Tuy nhiên cần lưu ý nguy cơ gan nhiễm mỡ do chuyển hóa khi kết hợp với triglyceride cao.',
    doesWhat: 'ALT là enzyme chủ yếu trong tế bào gan. Khi tế bào gan bị tổn thương, ALT rò rỉ vào máu và tăng cao. Đây là chỉ số nhạy cảm nhất để phát hiện viêm gan và tổn thương gan.',
    analogy: 'Hãy hình dung ALT như "báo động khói" trong tế bào gan. Khi có "đám cháy" (tổn thương), báo động kêu (ALT tăng). Không có báo động nghĩa là gan đang yên tĩnh.',
    analogyIcon: 'Shield',
    why: [
      { icon: 'Droplets', label: 'Triglyceride cao', note: 'Mỡ máu cao kết hợp với thừa cân làm tăng nguy cơ gan nhiễm mỡ' },
    ],
    today: {
      title: 'Hạn chế rượu bia và thức ăn nhiều dầu mỡ',
      why: 'Dù ALT bình thường, rượu bia và ăn nhiều mỡ bão hòa là nguyên nhân hàng đầu gây tổn thương gan âm thầm. Phòng ngừa hiệu quả hơn điều trị.',
    },
    plan: [
      { text: 'Hạn chế rượu bia', sub: 'Tối đa 1–2 đơn vị/ngày, nghỉ ít nhất 2 ngày/tuần' },
      { text: 'Giảm cân nếu thừa cân', sub: 'Giảm 5–10% cân nặng cải thiện đáng kể men gan' },
      { text: 'Kiểm tra ALT + AST sau 6 tháng', sub: 'Theo dõi xu hướng men gan' },
    ],
    reasonIntro: 'ALT 32 U/L nằm trong giới hạn bình thường (< 40). Không có dấu hiệu tổn thương gan cấp tính.',
    contributors: [
      { name: 'ALT 32 U/L', weight: 60, note: 'Trong giới hạn bình thường' },
    ],
    derived: [],
    confidence: 70,
    confidenceNote: 'Đánh giá toàn diện cần AST, GGT, siêu âm gan và bilirubin.',
    evidence: 'Theo EASL 2023, ALT bình thường không loại trừ gan nhiễm mỡ — tới 25% bệnh nhân có ALT bình thường vẫn có gan nhiễm mỡ trên siêu âm.',
    limitations: [
      'ALT bình thường không đồng nghĩa gan hoàn toàn khỏe mạnh',
      'Một số thuốc (statin, paracetamol liều cao) có thể nâng ALT',
    ],
    futures: [
      { when: 'Nếu ALT tăng trên 3× bình thường', text: 'Cần xét nghiệm bổ sung và tư vấn chuyên khoa gan mật.', tone: 'high' },
      { when: 'Nếu duy trì lối sống lành mạnh', text: 'ALT có thể cải thiện về mức tối ưu < 25 U/L.', tone: 'good' },
    ],
    needs: [
      { title: 'Siêu âm gan', why: 'Phát hiện gan nhiễm mỡ ngay cả khi ALT bình thường' },
    ],
    doctorQs: [
      'ALT 32 kết hợp triglyceride cao có nguy cơ gan nhiễm mỡ không?',
      'Tôi có cần siêu âm gan để kiểm tra thêm không?',
    ],
    knowledge: [
      { q: 'ALT bao nhiêu là cao?', a: '> 40 U/L ở nam (hoặc > 35 U/L ở nữ) cần xem xét nguyên nhân. > 3× giới hạn trên là dấu hiệu tổn thương gan đáng kể.' },
      { q: 'ALT và AST khác nhau thế nào?', a: 'ALT chủ yếu có trong gan (đặc hiệu hơn); AST có trong nhiều cơ quan hơn (gan, tim, cơ). Tỷ lệ AST/ALT giúp phân biệt nguyên nhân.' },
    ],
    chain: [
      { short: 'AST', note: 'Men gan bổ trợ', status: 'good', bioKey: 'ast' },
      { short: 'GGT', note: 'Men gan nhạy với rượu', status: 'norm', bioKey: 'ggt' },
    ],
    trendData: [38, 36, 35, 34, 33, 32],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 7,
    trendBandHigh: 40,
    trendMin: 0,
    trendMax: 50,
    trendComment: 'ALT đang giảm dần — tín hiệu tốt. Tiếp tục duy trì thói quen sống lành mạnh.',
    relatedTrends: [
      { short: 'AST', from: '33', to: '28', unit: 'U/L', dir: 'down', good: true },
    ],
  },

  ast: {
    key: 'ast',
    name: 'Men gan AST (Aspartate Aminotransferase)',
    short: 'AST',
    value: '28',
    unit: 'U/L',
    range: '10 – 40',
    prev: '33',
    prevNote: 'giảm tốt từ lần trước',
    target: '< 30',
    status: 'good',
    gaugePosition: 45,
    gaugeTarget: 50,
    riskText: 'Bình thường',
    conclusion: 'AST trong giới hạn bình thường. Cùng với ALT 32, không có dấu hiệu tổn thương gan hay tim đáng kể. Tỷ lệ AST/ALT 0.88 gợi ý nguyên nhân không phải do rượu.',
    doesWhat: 'AST là enzyme có trong gan, cơ tim và cơ xương. Khác với ALT, AST tăng không chỉ do gan mà còn do tổn thương tim, cơ. Xét cùng ALT giúp phân biệt nguyên nhân.',
    analogy: 'AST như "hệ thống cảnh báo rộng" — nhạy hơn với nhiều cơ quan hơn ALT. Khi AST và ALT đều tăng, vấn đề thường ở gan; khi chỉ AST tăng, nên nghĩ đến tim hoặc cơ.',
    analogyIcon: 'Shield',
    why: [
      { icon: 'Activity', label: 'Sức khỏe tổng thể', note: 'AST bình thường gợi ý gan và tim không có tổn thương cấp' },
    ],
    today: {
      title: 'Duy trì lối sống lành mạnh hiện tại',
      why: 'AST đang ở mức tốt. Tiếp tục hạn chế rượu bia, kiểm soát cân nặng và vận động đều để duy trì chức năng gan.',
    },
    plan: [
      { text: 'Hạn chế rượu bia', sub: 'Rượu là nguyên nhân hàng đầu tăng AST' },
      { text: 'Theo dõi AST/ALT cùng nhau', sub: 'Đánh giá tỷ lệ AST/ALT giúp phân biệt nguyên nhân' },
    ],
    reasonIntro: 'AST 28 U/L trong giới hạn bình thường. Tỷ lệ AST/ALT = 0.88 gợi ý không có bệnh gan do rượu (thường > 2.0).',
    contributors: [
      { name: 'AST 28 U/L', weight: 60, note: 'Trong giới hạn bình thường' },
    ],
    derived: [
      { name: 'Tỷ lệ AST/ALT', val: '0.88', note: 'Bình thường — dưới 1.0 gợi ý nguyên nhân không do rượu' },
    ],
    confidence: 72,
    confidenceNote: 'Đánh giá đầy đủ cần ALT, GGT, bilirubin và siêu âm gan.',
    evidence: 'Tỷ lệ AST/ALT > 2.0 là dấu hiệu kinh điển của bệnh gan do rượu (De Ritis ratio). Tỷ lệ < 1.0 thường gặp trong viêm gan virus và gan nhiễm mỡ không do rượu.',
    limitations: [
      'AST tăng có thể do nguyên nhân ngoài gan (nhồi máu cơ tim, tiêu cơ vân)',
      'Tập luyện thể lực nặng trước khi lấy máu có thể nâng AST',
    ],
    futures: [
      { when: 'Nếu AST và ALT đồng thời tăng', text: 'Cần đánh giá chức năng gan đầy đủ và xem xét nguyên nhân.', tone: 'med' },
    ],
    needs: [],
    doctorQs: [
      'Tỷ lệ AST/ALT 0.88 có ý nghĩa gì?',
      'AST và ALT cùng bình thường nhưng triglyceride cao — gan có ổn không?',
    ],
    knowledge: [
      { q: 'AST/ALT ratio là gì?', a: 'Là tỷ lệ giữa hai men gan giúp phân biệt nguyên nhân: > 2.0 gợi ý rượu; 1.0–2.0 xơ gan; < 1.0 viêm gan virus hoặc gan nhiễm mỡ.' },
    ],
    chain: [
      { short: 'ALT', note: 'Men gan đặc hiệu hơn', status: 'good', bioKey: 'alt' },
      { short: 'GGT', note: 'Men gan nhạy với rượu và tắc mật', status: 'norm', bioKey: 'ggt' },
    ],
    trendData: [33, 32, 30, 29, 29, 28],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 10,
    trendBandHigh: 40,
    trendMin: 0,
    trendMax: 50,
    trendComment: 'AST giảm tốt trong 6 tháng qua — phản ánh cải thiện chức năng gan.',
    relatedTrends: [
      { short: 'ALT', from: '38', to: '32', unit: 'U/L', dir: 'down', good: true },
    ],
  },

  ggt: {
    key: 'ggt',
    name: 'Men gan GGT (Gamma-Glutamyl Transferase)',
    short: 'GGT',
    value: '41',
    unit: 'U/L',
    range: '9 – 48',
    prev: '48',
    prevNote: 'giảm tốt từ lần trước',
    target: '< 30',
    status: 'norm',
    gaugePosition: 68,
    gaugeTarget: 48,
    riskText: 'Cao bình thường',
    conclusion: 'GGT ở mức cao bình thường — gần giới hạn trên. Kết hợp với triglyceride cao, điều này gợi ý nguy cơ gan nhiễm mỡ không do rượu (NAFLD) cần theo dõi.',
    doesWhat: 'GGT là enzyme nhạy cảm nhất với tổn thương gan do rượu, thuốc và tắc mật. GGT tăng có thể xuất hiện trước ALT và AST trong bệnh lý gan sớm.',
    analogy: 'GGT như "đầu dò thính nhạy" — phát hiện vấn đề gan sớm hơn ALT và AST. Nhưng nó cũng phản ứng với nhiều thứ khác (rượu, thuốc, hút thuốc), nên cần đọc kèm các chỉ số khác.',
    analogyIcon: 'Radio',
    why: [
      { icon: 'Droplets', label: 'Triglyceride 2.1', note: 'Mỡ máu cao liên quan đến gan nhiễm mỡ và GGT cao' },
      { icon: 'Scale', label: 'BMI 27', note: 'Thừa cân là yếu tố nguy cơ hàng đầu của NAFLD' },
    ],
    today: {
      title: 'Kiểm tra lượng rượu bia đang uống',
      why: 'GGT rất nhạy cảm với rượu bia. Dù mức hiện tại chưa vượt ngưỡng, giảm hoặc bỏ rượu có thể hạ GGT nhanh trong 2–4 tuần.',
    },
    plan: [
      { text: 'Hạn chế rượu bia nghiêm túc', sub: 'Rượu là nguyên nhân số 1 tăng GGT' },
      { text: 'Giảm cân 5–10%', sub: 'Giảm mỡ gan và GGT hiệu quả' },
      { text: 'Tái xét nghiệm sau 3 tháng', sub: 'GGT phản ứng nhanh với thay đổi lối sống' },
    ],
    reasonIntro: 'GGT 41 U/L gần giới hạn trên 48. Kết hợp với triglyceride cao và BMI 27, nguy cơ NAFLD đáng theo dõi.',
    contributors: [
      { name: 'GGT 41 U/L', weight: 65, note: 'Gần giới hạn trên bình thường' },
      { name: 'Triglyceride 2.1', weight: 50, note: 'Mỡ máu cao liên quan đến gan nhiễm mỡ' },
    ],
    derived: [],
    confidence: 68,
    confidenceNote: 'GGT nhạy nhưng không đặc hiệu — cần đọc kèm ALT, AST và bối cảnh lâm sàng.',
    evidence: 'Theo EASL 2023, GGT > 30 U/L là yếu tố nguy cơ độc lập cho bệnh tim mạch và tiểu đường type 2, ngay cả khi trong giới hạn bình thường theo phòng xét nghiệm.',
    limitations: [
      'GGT tăng do nhiều nguyên nhân ngoài gan (thuốc, béo phì, tiểu đường)',
      'Một số thuốc (phenytoin, barbiturat) làm tăng GGT đáng kể',
    ],
    futures: [
      { when: 'Nếu GGT vượt 48 U/L', text: 'Cần siêu âm gan và xem xét nguyên nhân (rượu, thuốc, NAFLD).', tone: 'med' },
      { when: 'Nếu giảm rượu và giảm cân', text: 'GGT có thể giảm về dưới 25 U/L trong 3 tháng.', tone: 'good' },
    ],
    needs: [
      { title: 'Siêu âm gan', why: 'Đánh giá mức độ gan nhiễm mỡ' },
    ],
    doctorQs: [
      'GGT 41 gần ngưỡng trên có nguy cơ gan nhiễm mỡ không?',
      'Tôi có cần siêu âm gan không khi GGT, ALT và triglyceride đều tăng?',
    ],
    knowledge: [
      { q: 'GGT bao nhiêu là đáng lo?', a: '> 48 U/L (nam) hoặc > 36 U/L (nữ) cần điều tra. Ngay cả mức "bình thường cao" > 30 U/L cũng liên quan đến nguy cơ tim mạch.' },
      { q: 'GGT có thể bình thường hóa không?', a: 'Có — hạn chế rượu bia và giảm cân thường hạ GGT hiệu quả trong 2–12 tuần.' },
    ],
    chain: [
      { short: 'ALT', note: 'Men gan đặc hiệu hơn cho tổn thương', status: 'good', bioKey: 'alt' },
      { short: 'AST', note: 'Men gan bổ trợ', status: 'good', bioKey: 'ast' },
    ],
    trendData: [48, 46, 45, 43, 42, 41],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 9,
    trendBandHigh: 48,
    trendMin: 0,
    trendMax: 60,
    trendComment: 'GGT giảm dần trong 6 tháng qua — phản ánh cải thiện chức năng gan. Tiếp tục duy trì.',
    relatedTrends: [
      { short: 'ALT', from: '38', to: '32', unit: 'U/L', dir: 'down', good: true },
    ],
  },

  creatinine: {
    key: 'creatinine',
    name: 'Creatinine máu',
    short: 'Creatinine',
    value: '84',
    unit: 'µmol/L',
    range: '62 – 115',
    prev: '86',
    prevNote: 'ổn định so với lần trước',
    target: '< 100',
    status: 'good',
    gaugePosition: 37,
    gaugeTarget: 42,
    riskText: 'Bình thường',
    conclusion: 'Creatinine bình thường — thận đang lọc tốt. Đây là tín hiệu khích lệ khi bạn đang có tiền sử đường huyết cao, vốn là nguyên nhân hàng đầu gây bệnh thận mạn.',
    doesWhat: 'Creatinine là sản phẩm chuyển hóa của cơ bắp, được thận lọc và thải qua nước tiểu. Khi thận suy yếu, creatinine tích tụ trong máu và tăng cao. Đây là một trong những chỉ số cơ bản nhất để đánh giá chức năng thận.',
    analogy: 'Creatinine như "rác thải cơ bắp" cần thận dọn. Khi thận khỏe, rác được dọn sạch (creatinine bình thường). Khi thận yếu, rác tích tụ (creatinine tăng).',
    analogyIcon: 'Droplets',
    why: [
      { icon: 'Armchair', label: 'Lối sống ít vận động', note: 'Khối cơ ít hơn → creatinine tạo ra ít hơn, kết quả thường thấp hơn nam giới lao động' },
    ],
    today: {
      title: 'Uống đủ 1.5–2 lít nước mỗi ngày',
      why: 'Đủ nước giúp thận lọc hiệu quả và duy trì creatinine ổn định. Đặc biệt quan trọng với bạn khi đường huyết cao có thể gây stress cho thận dài hạn.',
    },
    plan: [
      { text: 'Uống đủ nước mỗi ngày', sub: '1.5–2 lít, tránh uống quá nhiều một lúc' },
      { text: 'Kiểm soát đường huyết', sub: 'Đường huyết ổn định bảo vệ thận hiệu quả nhất' },
      { text: 'Kiểm soát huyết áp', sub: 'Huyết áp < 130/80 mmHg bảo vệ thận khỏi tổn thương' },
      { text: 'Xét nghiệm creatinine hàng năm', sub: 'Phát hiện sớm biến chứng thận do tiểu đường' },
    ],
    reasonIntro: 'Creatinine 84 µmol/L trong giới hạn bình thường. Cần theo dõi định kỳ do nguy cơ biến chứng thận từ tiền tiểu đường.',
    contributors: [
      { name: 'Creatinine 84 µmol/L', weight: 70, note: 'Bình thường, thận đang hoạt động tốt' },
    ],
    derived: [],
    confidence: 78,
    confidenceNote: 'Đánh giá đầy đủ cần eGFR và đạm niệu (albumin nước tiểu) để xác định giai đoạn bệnh thận.',
    evidence: 'Theo KDIGO 2023, creatinine bình thường không loại trừ bệnh thận mạn nếu có albumin niệu. Người tiền tiểu đường nên kiểm tra creatinine + eGFR + albumin/creatinine niệu hàng năm.',
    limitations: [
      'Creatinine thay đổi theo khối cơ — người ít cơ (người già, nữ) có creatinine thấp hơn nhưng thận vẫn có thể suy',
      'Ăn nhiều thịt đỏ trước xét nghiệm có thể nâng creatinine tạm thời',
    ],
    futures: [
      { when: 'Nếu đường huyết không kiểm soát · 5 năm', text: 'Nguy cơ bệnh thận mạn giai đoạn sớm (eGFR giảm, albumin niệu tăng).', tone: 'high' },
      { when: 'Nếu kiểm soát tốt đường huyết và huyết áp', text: 'Thận có thể duy trì chức năng bình thường hàng chục năm.', tone: 'good' },
    ],
    needs: [
      { title: 'Albumin/Creatinine niệu (ACR)', why: 'Phát hiện tổn thương thận sớm trước khi creatinine tăng' },
    ],
    doctorQs: [
      'Với tiền tiểu đường, tôi có cần xét nghiệm albumin niệu hàng năm không?',
      'Huyết áp bao nhiêu là tối ưu để bảo vệ thận của tôi?',
    ],
    knowledge: [
      { q: 'Creatinine cao bao nhiêu là nguy hiểm?', a: '> 115 µmol/L ở nam cần chú ý. > 177 µmol/L thường gợi ý suy thận rõ ràng cần xử lý ngay.' },
      { q: 'Creatinine và eGFR liên quan gì nhau?', a: 'eGFR được tính từ creatinine (cùng tuổi, giới, chủng tộc). eGFR < 60 mL/phút/1.73m² = bệnh thận mạn.' },
    ],
    chain: [
      { short: 'eGFR', note: 'Tính từ creatinine, phản ánh tốc độ lọc', status: 'good', bioKey: 'egfr' },
    ],
    trendData: [86, 86, 85, 85, 84, 84],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 62,
    trendBandHigh: 115,
    trendMin: 40,
    trendMax: 130,
    trendComment: 'Creatinine ổn định trong 6 tháng — thận duy trì chức năng tốt. Tiếp tục kiểm soát đường huyết.',
    relatedTrends: [
      { short: 'eGFR', from: '91', to: '92', unit: 'mL/phút', dir: 'up', good: true },
    ],
  },

  egfr: {
    key: 'egfr',
    name: 'Tốc độ lọc cầu thận ước tính (eGFR)',
    short: 'eGFR',
    value: '92',
    unit: 'mL/phút/1.73m²',
    range: '> 90',
    prev: '91',
    prevNote: 'ổn định so với lần trước',
    target: '> 90',
    status: 'good',
    gaugePosition: 20,
    gaugeTarget: 15,
    riskText: 'Bình thường',
    conclusion: 'eGFR bình thường — thận đang lọc tốt ở mức 92% so với người trẻ khỏe mạnh. Với tiền sử đường huyết cao, duy trì eGFR > 90 là mục tiêu quan trọng.',
    doesWhat: 'eGFR (Estimated Glomerular Filtration Rate) đo tốc độ thận lọc máu mỗi phút. Đây là chỉ số vàng để đánh giá giai đoạn bệnh thận mạn. eGFR giảm dần theo tuổi là bình thường, nhưng giảm nhanh gợi ý bệnh lý.',
    analogy: 'eGFR như "công suất lọc" của thận. 92 mL/phút nghĩa là thận đang lọc gần 140 lít máu mỗi ngày — hiệu suất rất tốt. Khi thận suy, con số này giảm dần.',
    analogyIcon: 'Filter',
    why: [
      { icon: 'User', label: 'Nam · 52 tuổi', note: 'eGFR giảm tự nhiên ~1 mL/phút/năm sau 40 tuổi' },
      { icon: 'Droplet', label: 'Đường huyết cao', note: 'Kiểm soát đường huyết kém là nguyên nhân hàng đầu làm giảm eGFR' },
    ],
    today: {
      title: 'Kiểm soát đường huyết — bảo vệ thận số 1',
      why: 'Mỗi đơn vị HbA1c giảm tương ứng giảm 40% nguy cơ biến chứng thận. Đây là biện pháp hiệu quả nhất để duy trì eGFR.',
    },
    plan: [
      { text: 'Kiểm soát đường huyết chặt', sub: 'HbA1c < 7% giảm nguy cơ biến chứng thận đáng kể' },
      { text: 'Huyết áp < 130/80 mmHg', sub: 'Huyết áp cao là đòn thứ hai tấn công thận' },
      { text: 'Xét nghiệm eGFR + ACR hàng năm', sub: 'Phát hiện sớm biến chứng thận tiểu đường' },
    ],
    reasonIntro: 'eGFR 92 mL/phút/1.73m² trong giới hạn bình thường (G1: > 90). Không có bệnh thận mạn giai đoạn nào.',
    contributors: [
      { name: 'eGFR 92', weight: 80, note: 'Thận lọc bình thường, không suy giảm chức năng' },
    ],
    derived: [],
    confidence: 82,
    confidenceNote: 'Đánh giá hoàn chỉnh cần thêm albumin niệu (ACR) để xác định bệnh thận mạn ngay cả khi eGFR bình thường.',
    evidence: 'Theo KDIGO 2023, eGFR ≥ 90 với không có albumin niệu = bình thường (G1). Bệnh thận mạn chẩn đoán khi eGFR < 60 HOẶC có albumin niệu, kéo dài > 3 tháng.',
    limitations: [
      'eGFR ước tính từ creatinine — kém chính xác ở người có khối cơ cực cao hoặc cực thấp',
      'eGFR bình thường không loại trừ bệnh thận nếu có albumin niệu',
    ],
    futures: [
      { when: 'Nếu đường huyết không kiểm soát', text: 'eGFR có thể giảm 5–10 mL/phút/năm thay vì 1–2 bình thường.', tone: 'high' },
      { when: 'Nếu kiểm soát tốt đường huyết + huyết áp', text: 'eGFR có thể duy trì > 60 hàng chục năm tới.', tone: 'good' },
    ],
    needs: [
      { title: 'Albumin/Creatinine niệu (ACR)', why: 'Phát hiện tổn thương thận sớm ngay cả khi eGFR bình thường' },
    ],
    doctorQs: [
      'eGFR 92 với đường huyết cao — tôi có cần xét nghiệm albumin niệu không?',
      'eGFR của tôi có nguy cơ giảm nhanh không với tiền tiểu đường?',
    ],
    knowledge: [
      { q: 'eGFR bao nhiêu là suy thận?', a: 'eGFR 60–89: G2 (giảm nhẹ); 45–59: G3a; 30–44: G3b; 15–29: G4; < 15: G5 (suy thận giai đoạn cuối).' },
      { q: 'eGFR có thể cải thiện không?', a: 'Có — kiểm soát tốt đường huyết, huyết áp và bỏ thuốc lá có thể làm chậm hoặc ổn định eGFR. Hiếm khi cải thiện đáng kể nếu đã < 60.' },
    ],
    chain: [
      { short: 'Creatinine', note: 'Nguồn tính eGFR', status: 'good', bioKey: 'creatinine' },
      { short: 'Đường huyết', note: 'Nguy cơ biến chứng thận', status: 'med', bioKey: 'glucose' },
    ],
    trendData: [91, 91, 91, 92, 92, 92],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 90,
    trendBandHigh: 120,
    trendMin: 60,
    trendMax: 130,
    trendComment: 'eGFR duy trì ổn định trên 90 trong 6 tháng — thận đang hoạt động tốt. Tiếp tục kiểm soát đường huyết.',
    relatedTrends: [
      { short: 'Creatinine', from: '86', to: '84', unit: 'µmol/L', dir: 'down', good: true },
    ],
  },

  ferritin: {
    key: 'ferritin',
    name: 'Ferritin (Dự trữ sắt)',
    short: 'Ferritin',
    value: '48',
    unit: 'ng/mL',
    range: '22 – 322',
    prev: '42',
    prevNote: 'tăng nhẹ từ lần trước',
    target: '> 50',
    status: 'norm',
    gaugePosition: 16,
    gaugeTarget: 17,
    riskText: 'Thấp bình thường',
    conclusion: 'Ferritin thấp bình thường — dự trữ sắt của bạn đang ở mức tối thiểu. Dù chưa thiếu máu, mức này có thể gây mệt mỏi, giảm sức tập trung và ảnh hưởng đến năng lượng.',
    doesWhat: 'Ferritin là protein lưu trữ sắt trong cơ thể. Đây là chỉ số phản ánh "kho sắt" tổng thể — giảm trước cả hemoglobin khi thiếu sắt. Sắt cần thiết để vận chuyển oxy và tạo năng lượng trong tế bào.',
    analogy: 'Ferritin như "bồn chứa sắt" của cơ thể. Bồn ở mức thấp có nghĩa là dự trữ ít — cơ thể đang "sống nhờ lượng tồn" mà không có đệm an toàn nếu nhu cầu tăng đột ngột.',
    analogyIcon: 'Battery',
    why: [
      { icon: 'Apple', label: 'Chế độ ăn ít sắt', note: 'Thiếu thịt đỏ, rau xanh đậm hoặc đậu trong khẩu phần' },
      { icon: 'Armchair', label: 'Ít vận động', note: 'Luyện tập thể thao tăng nhu cầu sắt' },
    ],
    today: {
      title: 'Bổ sung thực phẩm giàu sắt vào bữa ăn',
      why: 'Thịt đỏ (2–3 lần/tuần), gan, đậu lăng, rau bina và hạt bí ngô là những nguồn sắt dồi dào. Ăn kèm vitamin C giúp hấp thu sắt tốt hơn.',
    },
    plan: [
      { text: 'Tăng thực phẩm giàu sắt heme', sub: 'Thịt đỏ, gan, hải sản — hấp thu hiệu quả hơn sắt thực vật' },
      { text: 'Bổ sung sắt từ thực vật', sub: 'Đậu lăng, rau bina, hạt bí ngô — ăn với vitamin C để tăng hấp thu' },
      { text: 'Hạn chế cà phê, trà gần bữa ăn', sub: 'Tanin trong trà/cà phê ức chế hấp thu sắt' },
      { text: 'Kiểm tra lại Ferritin sau 3 tháng', sub: 'Đánh giá hiệu quả điều chỉnh chế độ ăn' },
    ],
    reasonIntro: 'Ferritin 48 ng/mL ở mức thấp bình thường. Dự trữ sắt đủ để tránh thiếu máu nhưng chưa tối ưu cho năng lượng và sức tập trung.',
    contributors: [
      { name: 'Ferritin 48 ng/mL', weight: 70, note: 'Thấp bình thường, cách ngưỡng thiếu sắt (< 22) không xa' },
    ],
    derived: [],
    confidence: 70,
    confidenceNote: 'Cần thêm huyết đồ (CBC), sắt huyết thanh và TIBC để đánh giá đầy đủ tình trạng sắt.',
    evidence: 'Theo WHO 2023, ferritin < 30 ng/mL là thiếu sắt; 30–50 ng/mL là dự trữ thấp. Nhiều chuyên gia khuyến nghị ferritin > 50–100 ng/mL cho sức khỏe tối ưu ở nam giới.',
    limitations: [
      'Ferritin là protein viêm — tăng giả tạo khi cơ thể đang viêm hoặc nhiễm trùng',
      'Ferritin bình thường không loại trừ thiếu sắt chức năng trong giai đoạn đầu',
    ],
    futures: [
      { when: 'Nếu không bổ sung sắt', text: 'Ferritin có thể tiếp tục giảm về mức thiếu sắt (< 22 ng/mL), gây thiếu máu và mệt mỏi.', tone: 'med' },
      { when: 'Nếu điều chỉnh chế độ ăn', text: 'Ferritin có thể tăng về mức tối ưu > 80 ng/mL trong 3–6 tháng.', tone: 'good' },
    ],
    needs: [
      { title: 'CBC (huyết đồ toàn phần)', why: 'Xác định có thiếu máu thiếu sắt hay không' },
    ],
    doctorQs: [
      'Ferritin 48 có cần uống viên sắt không hay chỉ cần điều chỉnh ăn uống?',
      'Mệt mỏi của tôi có liên quan đến mức ferritin thấp không?',
    ],
    knowledge: [
      { q: 'Ferritin khác sắt huyết thanh thế nào?', a: 'Sắt huyết thanh là sắt đang lưu thông trong máu; Ferritin là sắt dự trữ trong tế bào. Ferritin giảm trước khi sắt huyết thanh và hemoglobin giảm.' },
      { q: 'Thực phẩm nào giàu sắt nhất?', a: 'Sắt heme (hấp thu tốt hơn): gan, thịt đỏ, hải sản. Sắt non-heme (thực vật): đậu lăng, rau bina, hạt bí ngô — cần vitamin C đi kèm.' },
    ],
    chain: [
      { short: 'Vitamin D', note: 'Cùng nhóm vi chất hay thiếu', status: 'low', bioKey: 'vitd' },
    ],
    trendData: [42, 43, 44, 45, 47, 48],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 22,
    trendBandHigh: 322,
    trendMin: 0,
    trendMax: 150,
    trendComment: 'Ferritin tăng nhẹ trong 6 tháng qua — có thể do điều chỉnh chế độ ăn. Tiếp tục bổ sung thực phẩm giàu sắt.',
    relatedTrends: [],
  },

  b12: {
    key: 'b12',
    name: 'Vitamin B12 (Cobalamin)',
    short: 'B12',
    value: '410',
    unit: 'pg/mL',
    range: '200 – 900',
    prev: '385',
    prevNote: 'cải thiện từ lần trước',
    target: '> 400',
    status: 'good',
    gaugePosition: 30,
    gaugeTarget: 28,
    riskText: 'Bình thường',
    conclusion: 'Vitamin B12 trong giới hạn bình thường và đang cải thiện. Bạn đang dùng Metformin — loại thuốc này có thể làm giảm hấp thu B12 lâu dài, nên tiếp tục theo dõi.',
    doesWhat: 'Vitamin B12 thiết yếu cho hệ thần kinh, tạo máu và tổng hợp DNA. Thiếu B12 gây thiếu máu hồng cầu to, tổn thương thần kinh ngoại biên (tê bì tay chân) và giảm nhận thức.',
    analogy: 'B12 như "điện" cho hệ thần kinh và nhà máy tạo máu. Thiếu điện, nhà máy chạy chậm lại và các dây điện (dây thần kinh) dần bị ảnh hưởng — đó là lúc bạn thấy tê bì và mệt mỏi.',
    analogyIcon: 'Zap',
    why: [
      { icon: 'Pill', label: 'Dùng Metformin', note: 'Metformin ức chế hấp thu B12 qua đường tiêu hóa sau khi dùng lâu dài (> 4 năm)' },
      { icon: 'User', label: 'Nam · 52 tuổi', note: 'Hấp thu B12 giảm tự nhiên theo tuổi do giảm yếu tố nội tại dạ dày' },
    ],
    today: {
      title: 'Bổ sung thực phẩm giàu B12',
      why: 'Thịt, cá, trứng và các sản phẩm từ sữa là nguồn B12 tự nhiên tốt nhất. Với người dùng Metformin lâu dài, bác sĩ thường khuyến nghị bổ sung B12 dự phòng.',
    },
    plan: [
      { text: 'Ăn thực phẩm giàu B12 hàng ngày', sub: 'Cá hồi, trứng, thịt bò, sữa chua' },
      { text: 'Hỏi bác sĩ về bổ sung B12', sub: 'Đặc biệt quan trọng khi dùng Metformin > 4 năm' },
      { text: 'Theo dõi B12 hàng năm', sub: 'Phát hiện sớm xu hướng giảm do Metformin' },
    ],
    reasonIntro: 'B12 410 pg/mL ở mức bình thường thấp. Xu hướng cải thiện tốt. Tuy nhiên với Metformin, cần theo dõi chặt hơn so với người bình thường.',
    contributors: [
      { name: 'B12 410 pg/mL', weight: 65, note: 'Bình thường nhưng thấp trong giới hạn tham chiếu' },
      { name: 'Dùng Metformin', weight: 55, note: 'Metformin ức chế hấp thu B12 — nguy cơ tích lũy theo thời gian' },
    ],
    derived: [],
    confidence: 72,
    confidenceNote: 'Nên đánh giá thêm axit methylmalonic (MMA) hoặc homocysteine để xác nhận trạng thái B12 chức năng.',
    evidence: 'Theo ADA 2024, người dùng Metformin nên kiểm tra B12 định kỳ hàng năm. Nghiên cứu cho thấy 30% người dùng Metformin > 4 năm có thiếu hụt B12 ở các mức độ khác nhau.',
    limitations: [
      'B12 huyết thanh có thể bình thường nhưng thiếu hụt chức năng vẫn xảy ra',
      'Bổ sung B12 dạng cyanocobalamin có thể cho kết quả cao giả tạo trong 24 giờ',
    ],
    futures: [
      { when: 'Nếu B12 tiếp tục giảm · 1 năm', text: 'Nguy cơ tê bì tay chân và mệt mỏi liên quan thiếu hụt B12 thần kinh.', tone: 'med' },
      { when: 'Nếu bổ sung và theo dõi', text: 'B12 có thể duy trì > 400 pg/mL ổn định dài hạn.', tone: 'good' },
    ],
    needs: [
      { title: 'Homocysteine', why: 'Tăng khi thiếu B12 chức năng, ngay cả khi B12 huyết thanh bình thường' },
    ],
    doctorQs: [
      'Với Metformin tôi đang dùng, B12 410 có cần bổ sung thêm không?',
      'Tê bì tay chân của tôi có thể do thiếu B12 hay do biến chứng thần kinh tiểu đường không?',
    ],
    knowledge: [
      { q: 'B12 bao nhiêu là thiếu hụt?', a: '< 200 pg/mL là thiếu rõ ràng; 200–300 pg/mL là giới hạn cần theo dõi; > 300 pg/mL thường đủ nhưng ngưỡng tối ưu có thể > 400–500 pg/mL.' },
      { q: 'Metformin ảnh hưởng B12 thế nào?', a: 'Metformin ức chế hấp thu B12 qua đường tiêu hóa bằng cách cạnh tranh với yếu tố nội tại. Liều cao và dùng lâu làm tăng nguy cơ thiếu hụt.' },
    ],
    chain: [
      { short: 'Ferritin', note: 'Cùng nhóm vi chất quan trọng', status: 'norm', bioKey: 'ferritin' },
    ],
    trendData: [370, 375, 385, 390, 400, 410],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 200,
    trendBandHigh: 900,
    trendMin: 150,
    trendMax: 600,
    trendComment: 'B12 cải thiện tốt trong 6 tháng — có thể do điều chỉnh chế độ ăn. Tiếp tục duy trì và theo dõi với Metformin.',
    relatedTrends: [],
  },

  'hs-crp': {
    key: 'hs-crp',
    name: 'CRP độ nhạy cao (hs-CRP)',
    short: 'hs-CRP',
    value: '1.1',
    unit: 'mg/L',
    range: '< 1.0',
    prev: '1.8',
    prevNote: 'cải thiện tốt từ lần trước',
    target: '< 1.0',
    status: 'good',
    gaugePosition: 30,
    gaugeTarget: 20,
    riskText: 'Nguy cơ trung bình thấp',
    conclusion: 'hs-CRP ở mức nguy cơ trung bình thấp (1.0–3.0 mg/L) và đang cải thiện tốt so với lần trước. Đây là tín hiệu tích cực — viêm nhiễm hệ thống đang giảm, bảo vệ tim mạch của bạn.',
    doesWhat: 'hs-CRP là protein viêm được gan sản xuất khi có viêm trong cơ thể. Ở mức "độ nhạy cao", hs-CRP phản ánh viêm mạn tính âm thầm — nguy cơ quan trọng cho bệnh tim mạch, tiểu đường và ung thư.',
    analogy: 'hs-CRP như "nhiệt kế viêm" đo lửa bên trong cơ thể. Lửa nhỏ âm ỉ (hs-CRP 1–3) làm tổn thương dần thành mạch máu theo năm tháng — ngay cả khi bạn chưa cảm thấy gì.',
    analogyIcon: 'Flame',
    why: [
      { icon: 'Scale', label: 'BMI 27 · mỡ bụng', note: 'Mô mỡ, đặc biệt mỡ tạng, sản xuất cytokine viêm liên tục' },
      { icon: 'Armchair', label: 'Ít vận động', note: 'Lối sống tĩnh tại thúc đẩy viêm mạn tính' },
    ],
    today: {
      title: 'Đi bộ 20–30 phút hôm nay',
      why: 'Vận động thể lực là biện pháp chống viêm mạnh nhất không cần thuốc. Chỉ 20 phút đi bộ có thể giảm cytokine viêm trong vài giờ.',
    },
    plan: [
      { text: 'Vận động ít nhất 150 phút/tuần', sub: 'Đi bộ, đạp xe, bơi lội — chống viêm hiệu quả nhất' },
      { text: 'Chế độ ăn chống viêm', sub: 'Ưu tiên cá béo, ô liu, nghệ, gừng, rau xanh lá đậm' },
      { text: 'Giảm cân nếu thừa cân', sub: 'Mỡ tạng là nguồn viêm lớn nhất — giảm 5–10% cân nặng cải thiện CRP rõ rệt' },
      { text: 'Ngủ đủ 7–8 tiếng', sub: 'Thiếu ngủ tăng IL-6 và CRP lên 40–60%' },
    ],
    reasonIntro: 'hs-CRP 1.1 mg/L trong vùng nguy cơ tim mạch trung bình (1–3 mg/L). Cải thiện tốt từ 1.8 nhưng chưa đạt mục tiêu < 1.0.',
    contributors: [
      { name: 'hs-CRP 1.1 mg/L', weight: 65, note: 'Viêm mạn tính mức thấp' },
      { name: 'Mỡ bụng (vòng eo 94cm)', weight: 55, note: 'Mô mỡ tạng liên tục tiết cytokine viêm' },
      { name: 'Glucose cao', weight: 40, note: 'Đường huyết cao thúc đẩy viêm mạch máu' },
    ],
    derived: [],
    confidence: 74,
    confidenceNote: 'Cần loại trừ nhiễm trùng cấp (cúm, viêm, chấn thương) trước khi diễn giải hs-CRP.',
    evidence: 'Theo AHA/CDC 2022, hs-CRP < 1.0 mg/L = nguy cơ thấp; 1.0–3.0 mg/L = nguy cơ trung bình; > 3.0 mg/L = nguy cơ cao. Giảm hs-CRP 1 mg/L giảm nguy cơ tim mạch ~15–20%.',
    limitations: [
      'hs-CRP tăng cao đột ngột khi nhiễm trùng, chấn thương hoặc dùng thuốc tránh thai',
      'Không đặc hiệu — cần loại trừ nhiễm trùng trước khi diễn giải',
    ],
    futures: [
      { when: 'Nếu hs-CRP > 3.0 mg/L', text: 'Nguy cơ tim mạch cao — cần đánh giá toàn diện và can thiệp tích cực hơn.', tone: 'high' },
      { when: 'Nếu tiếp tục vận động và giảm cân', text: 'hs-CRP có thể về < 1.0 mg/L trong 3–6 tháng tới.', tone: 'good' },
    ],
    needs: [],
    doctorQs: [
      'hs-CRP 1.1 với các nguy cơ tim mạch khác của tôi — có cần điều trị gì không?',
      'Vận động và chế độ ăn có đủ để hạ hs-CRP xuống < 1.0 không?',
    ],
    knowledge: [
      { q: 'hs-CRP và CRP thông thường khác nhau thế nào?', a: 'CRP thông thường đo khi nghi ngờ viêm/nhiễm trùng cấp (> 10 mg/L là quan trọng). hs-CRP đo mức viêm mạn tính âm thầm trong khoảng 0.1–10 mg/L để đánh giá nguy cơ tim mạch.' },
      { q: 'Làm gì để hạ hs-CRP?', a: 'Vận động đều, chế độ ăn chống viêm (ít đường, ít chất béo bão hòa, nhiều omega-3), giảm cân, bỏ thuốc lá và ngủ đủ giấc là cách hiệu quả nhất.' },
    ],
    chain: [
      { short: 'LDL-C', note: 'Kết hợp với viêm gây xơ vữa', status: 'high', bioKey: 'ldl' },
      { short: 'Glucose', note: 'Đường huyết cao thúc đẩy viêm', status: 'med', bioKey: 'glucose' },
    ],
    trendData: [1.8, 1.7, 1.5, 1.4, 1.2, 1.1],
    trendLabels: ['01/25', '02/25', '03/25', '04/25', '05/25', '06/25'],
    trendBandLow: 0,
    trendBandHigh: 1.0,
    trendMin: 0,
    trendMax: 4,
    trendComment: 'hs-CRP giảm đều đặn từ 1.8 về 1.1 — tín hiệu rất tích cực. Tiếp tục vận động và chế độ ăn chống viêm.',
    relatedTrends: [
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
