"use client"

import { useState } from 'react'
import { mockNetworkNodes, mockNetworkEdges, mockNetworkInfo } from '@/lib/mock/aiCopilotData'
import { NetworkGraph } from '@/components/patient/ai-copilot/NetworkGraph'
import Link from 'next/link'

const FILTERS = [
  { key: 'all', label: 'Tất cả' },
  { key: 'metabolic', label: 'Chuyển hóa' },
  { key: 'cardio', label: 'Tim mạch' },
] as const
type Filter = (typeof FILTERS)[number]['key']

export default function NetworkPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<string | null>('insulin')

  const info = selected ? mockNetworkInfo[selected] : null

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto">
      <h2 className="text-base font-bold text-gray-800 mb-1">Biểu đồ kết nối</h2>
      <p className="text-xs text-gray-500 mb-4">
        Các chỉ số không độc lập — chúng ảnh hưởng lẫn nhau. Nhấn vào nút để xem giải thích.
      </p>

      <div className="flex gap-2 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-full transition-colors ${
              filter === f.key
                ? 'bg-teal-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 mb-4">
        <NetworkGraph
          nodes={mockNetworkNodes}
          edges={mockNetworkEdges}
          selectedNode={selected}
          onNodeSelect={setSelected}
          filter={filter}
        />
      </div>

      {info && (
        <div className="bg-teal-50 rounded-xl p-4 space-y-2">
          <div className="flex items-start justify-between">
            <p className="text-sm font-bold text-teal-800">{info.title}</p>
            {info.bioKey && (
              <Link
                href={`/ai-copilot/biomarker/${info.bioKey}`}
                className="text-xs text-teal-600 font-medium underline underline-offset-2 flex-shrink-0 ml-2"
              >
                Chi tiết →
              </Link>
            )}
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">{info.desc}</p>
        </div>
      )}

      <div className="mt-4 bg-gray-50 rounded-xl p-3 border border-gray-100">
        <p className="text-xs font-semibold text-gray-500 mb-1.5">Mẫu hình chính của bạn</p>
        <p className="text-xs text-gray-600 leading-relaxed">
          Tất cả bất thường đều xuất phát từ một gốc: <strong>kháng insulin</strong>. Cải thiện qua
          vận động và giảm đường sẽ cải thiện đồng thời đường huyết, mỡ máu và nguy cơ gan nhiễm mỡ.
        </p>
      </div>
    </div>
  )
}
