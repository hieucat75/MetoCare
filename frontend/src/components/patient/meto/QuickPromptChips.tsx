'use client'
import * as React from 'react'

// Quick prompts per screen
const QUICK_PROMPTS: Record<string, string[]> = {
  dashboard: [
    'Hôm nay tôi cần chú ý gì?',
    'Tóm tắt sức khỏe của tôi',
    'Tôi có việc gì cần làm không?',
  ],
  labs: [
    'Giải thích kết quả này cho tôi',
    'Kết quả nào bất thường?',
    'Tôi nên hỏi bác sĩ điều gì?',
  ],
  medications: [
    'Thuốc này dùng để làm gì?',
    'Tôi có cần uống thuốc hôm nay không?',
    'Tôi nên lưu ý gì khi dùng thuốc này?',
  ],
  metrics: [
    'Chỉ số này có đáng lo không?',
    'Xu hướng chỉ số của tôi như thế nào?',
    'Tôi nên làm gì để cải thiện?',
  ],
  nutrition: [
    'Hôm nay tôi nên ăn gì?',
    'Tôi nên tránh thực phẩm nào?',
    'Chế độ ăn của tôi có ổn không?',
  ],
  'care-plan': [
    'Tôi còn việc gì chưa làm?',
    'Hôm nay tôi cần ưu tiên gì?',
    'Giải thích kế hoạch này cho tôi',
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
    <div className="flex gap-2 overflow-x-auto pb-2 px-1 scrollbar-hide">
      {prompts.map((p) => (
        <button
          key={p}
          onClick={() => onSelect(p)}
          className="shrink-0 rounded-full border border-[#0F9C6E]/30 bg-white/80 px-4 py-2 text-[15px] text-[#0F9C6E] font-medium whitespace-nowrap active:scale-95 transition-transform"
        >
          {p}
        </button>
      ))}
    </div>
  )
}
