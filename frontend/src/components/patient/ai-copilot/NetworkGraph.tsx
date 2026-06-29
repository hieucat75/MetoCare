'use client'

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

const TEAL = '#0E6E66'

export function NetworkGraph({ nodes, edges, selectedNode, onNodeSelect, filter = 'all' }: Props) {
  const visibleNodes =
    filter === 'all' ? nodes : nodes.filter((n) => n.category === 'all' || n.category === filter)
  const visibleIds = new Set(visibleNodes.map((n) => n.id))
  const visibleEdges = edges.filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to))

  // Compute which nodes and edges are "active" relative to the selected node
  const connectedIds = new Set<string>()
  const activeEdgeKeys = new Set<string>()
  if (selectedNode) {
    visibleEdges.forEach((e) => {
      if (e.from === selectedNode || e.to === selectedNode) {
        connectedIds.add(e.from)
        connectedIds.add(e.to)
        activeEdgeKeys.add(`${e.from}-${e.to}`)
      }
    })
  }

  const hasSelection = selectedNode !== null

  return (
    <svg
      viewBox="0 0 330 370"
      className="w-full max-w-xs mx-auto"
      aria-label="Biểu đồ liên kết chỉ số"
    >
      {/* Edges — render before nodes so nodes sit on top */}
      {visibleEdges.map((edge) => {
        const from = visibleNodes.find((n) => n.id === edge.from)
        const to = visibleNodes.find((n) => n.id === edge.to)
        if (!from || !to) return null

        const key = `${edge.from}-${edge.to}`
        const isActive = activeEdgeKeys.has(key)
        const opacity = !hasSelection ? 1 : isActive ? 1 : 0.12
        const stroke = isActive
          ? TEAL
          : edge.strength === 'strong'
          ? '#94A3B8'
          : '#CBD5E1'
        const strokeWidth = isActive ? 2.5 : edge.strength === 'strong' ? 2 : 1

        return (
          <line
            key={key}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke={stroke}
            strokeWidth={strokeWidth}
            strokeDasharray={!isActive && edge.strength === 'med' ? '4 3' : undefined}
            style={{ opacity, transition: 'opacity 0.25s ease, stroke 0.25s ease' }}
          />
        )
      })}

      {/* Nodes */}
      {visibleNodes.map((node) => {
        const isSelected = selectedNode === node.id
        const isConnected = connectedIds.has(node.id) && !isSelected
        const isDimmed = hasSelection && !isSelected && !isConnected
        const nodeOpacity = isDimmed ? 0.2 : 1

        const color = STATUS_COLOR[node.status] ?? '#6B7280'
        const strokeColor = isSelected ? TEAL : isConnected ? color : color
        const strokeWidth = isSelected ? 3 : isConnected ? 2.5 : 1.5
        const r = node.isCenter ? 36 : 28

        return (
          <g
            key={node.id}
            onClick={() => onNodeSelect(node.id)}
            className="cursor-pointer"
            role="button"
            aria-label={node.label}
            style={{ opacity: nodeOpacity, transition: 'opacity 0.25s ease' }}
          >
            {/* Halo — shown for selected and connected nodes */}
            <circle
              cx={node.x}
              cy={node.y}
              r={r + 7}
              fill={isSelected ? TEAL : color}
              style={{
                opacity: isSelected ? 0.18 : isConnected ? 0.1 : 0,
                transition: 'opacity 0.25s ease',
              }}
            />
            {/* Main circle */}
            <circle
              cx={node.x}
              cy={node.y}
              r={r}
              fill="white"
              stroke={strokeColor}
              strokeWidth={strokeWidth}
              style={{ transition: 'stroke-width 0.25s ease, stroke 0.25s ease' }}
            />
            {/* Label */}
            <text
              x={node.x}
              y={node.y - (node.sub ? 6 : 0)}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={node.isCenter ? 11 : 10}
              fontWeight={isSelected || node.isCenter ? '700' : '600'}
              fill={isSelected ? TEAL : color}
              style={{ transition: 'fill 0.25s ease' }}
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
                fill={isSelected ? TEAL : '#9CA3AF'}
                fontWeight={isSelected ? '600' : '400'}
                style={{ transition: 'fill 0.25s ease' }}
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
