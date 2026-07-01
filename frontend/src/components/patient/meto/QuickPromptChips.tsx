'use client'
/**
 * QuickPromptChips — screen-aware quick prompt suggestions.
 *
 * Prompts are tailored per screen per 05_UI_UX_SPEC.md and the product quality slice spec.
 * Maps to backend QUICK_PROMPTS in app/ai/prompt/safety.py.
 */
import * as React from 'react'

// Quick prompts per screen — aligned with backend safety.py
const QUICK_PROMPTS: Record<string, string[]> = {
  dashboard: [
    'Hôm nay tôi cần chú ý gì?',
    'Tôi còn việc gì chưa làm?',
    'Nhắc tôi uống thuốc',
  ],
  labs: [
    'Giải thích kết quả này',
    'Chỉ số nào cần chú ý?',
    'Tôi nên hỏi bác sĩ điều gì?',
  ],
  medications: [
    'Thuốc này dùng để làm gì?',
    'Tôi cần lưu ý gì khi uống?',
    'Tôi quên uống thì sao?',
  ],
  metrics: [
    'Chỉ số này có ổn không?',
    'Xu hướng gần đây thế nào?',
    'Khi nào cần đi khám?',
  ],
  nutrition: [
    'Hôm nay tôi nên ăn gì?',
    'Tôi nên tránh thực phẩm nào?',
    'Chế độ ăn của tôi có ổn không?',
  ],
  'care-plan': [
    'Tôi còn việc gì hôm nay?',
    'Việc nào quan trọng nhất?',
    'Giúp tôi theo kế hoạch',
  ],
  // Legacy key alias
  care_plan: [
    'Tôi còn việc gì hôm nay?',
    'Việc nào quan trọng nhất?',
    'Giúp tôi theo kế hoạch',
  ],
  settings: [
    'Meto dùng dữ liệu nào?',
    'Cách bật/tắt quyền',
    'Xóa lịch sử Meto',
  ],
  consents: [
    'Meto dùng dữ liệu nào?',
    'Cách bật/tắt quyền',
    'Xóa lịch sử Meto',
  ],
  profile: [
    'Hồ sơ của tôi còn thiếu gì?',
    'Tôi nên cập nhật thông tin gì?',
  ],
}

type Props = {
  screenId: string
  onSelect: (prompt: string) => void
}

export function QuickPromptChips({ screenId, onSelect }: Props) {
  const prompts = QUICK_PROMPTS[screenId] ?? QUICK_PROMPTS.dashboard
  return (
    <div
      className="flex gap-2 overflow-x-auto pb-2 px-1 scrollbar-hide"
      aria-label="Gợi ý câu hỏi nhanh"
      role="list"
    >
      {prompts.map((p) => (
        <button
          key={p}
          onClick={() => onSelect(p)}
          role="listitem"
          className="shrink-0 rounded-full border border-[#0F9C6E]/30 bg-white/80 px-4 py-2 text-[15px] text-[#0F9C6E] font-medium whitespace-nowrap active:scale-95 transition-transform"
        >
          {p}
        </button>
      ))}
    </div>
  )
}
