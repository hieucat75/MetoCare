"use client"

import type { NetworkNode, NetworkEdge } from '@/lib/mock/aiCopilotData'

type Props = {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
  selectedNode: string | null
  onNodeSelect: (id: string) => void
  filter?: string
}

const STATUS_COLOR: Record<string, string> = {
  good: '#22C55E',
  norm: '#6B7280',
  med: '#F59E0B',
  high: '#EF4444',
  low: '#3B82F6',
}

export function NetworkGraph({ nodes, edges, selectedNode, onNodeSelect, filter = 'all' }: Props) {
  const visibleNodes =
    filter === 'all' ? nodes : nodes.filter((n) => n.category === 'all' || n.category === filter)
  const visibleIds = new Set(visibleNodes.map((n) => n.id))
  const visibleEdges = edges.filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to))

  return (
    <svg
      viewBox="0 0 330 370"
      className="w-full max-w-xs mx-auto"
      aria-label="Biểu đồ liên kết chỉ số"
    >
      {visibleEdges.map((edge) => {
        const from = visibleNodes.find((n) => n.id === edge.from)
        const to = visibleNodes.find((n) => n.id === edge.to)
        if (!from || !to) return null
        return (
          <line
            key={`${edge.from}-${edge.to}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke={edge.strength === 'strong' ? '#94A3B8' : '#CBD5E1'}
            strokeWidth={edge.strength === 'strong' ? 2 : 1}
            strokeDasharray={edge.strength === 'med' ? '4 3' : undefined}
          />
        )
      })}
      {visibleNodes.map((node) => {
        const isSelected = selectedNode === node.id
        const color = STATUS_COLOR[node.status] ?? '#6B7280'
        const r = node.isCenter ? 36 : 28

        return (
          <g
            key={node.id}
            onClick={() => onNodeSelect(node.id)}
            className="cursor-pointer"
            role="button"
            aria-label={node.label}
          >
            <circle
              cx={node.x}
              cy={node.y}
              r={r + 4}
              fill={isSelected ? color : 'transparent'}
              opacity={isSelected ? 0.12 : 0}
            />
            <circle
              cx={node.x}
              cy={node.y}
              r={r}
              fill="white"
              stroke={color}
              strokeWidth={isSelected ? 2.5 : 1.5}
              className="drop-shadow-sm"
              style={{ transition: 'stroke-width 0.2s' }}
            />
            <text
              x={node.x}
              y={node.y - (node.sub ? 6 : 0)}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={node.isCenter ? 11 : 10}
              fontWeight={node.isCenter ? '700' : '600'}
              fill={color}
            >
              {node.label}
            </text>
            {node.sub && (
              <text
                x={node.x}
                y={node.y + 9}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={9}
                fill="#9CA3AF"
              >
                {node.sub}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
