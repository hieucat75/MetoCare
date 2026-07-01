'use client'
/**
 * MarkdownMessage — renders Meto AI response text without markdown leakage.
 *
 * Parses raw model output (which may contain **bold**, ## headings, - bullets)
 * into React elements. No dangerouslySetInnerHTML. Safe for patient chat.
 */
import * as React from 'react'
import { parseMarkdown, processInline } from '@/lib/utils/markdownSanitize'

type InlineSegment = { bold?: boolean; italic?: boolean; text: string }

function InlineText({ segments }: { segments: InlineSegment[] }) {
  return (
    <>
      {segments.map((seg, i) => {
        if (seg.bold) return <strong key={i} className="font-semibold">{seg.text}</strong>
        if (seg.italic) return <em key={i}>{seg.text}</em>
        return <React.Fragment key={i}>{seg.text}</React.Fragment>
      })}
    </>
  )
}

interface Props {
  content: string
  className?: string
}

export function MarkdownMessage({ content, className }: Props) {
  const nodes = parseMarkdown(content)

  if (nodes.length === 0) {
    return <span className={className}>{content}</span>
  }

  return (
    <div className={className}>
      {nodes.map((node, idx) => {
        switch (node.type) {
          case 'heading':
            return (
              <p
                key={idx}
                className={`font-semibold text-[15px] leading-snug ${idx > 0 ? 'mt-2' : ''}`}
              >
                {node.content}
              </p>
            )

          case 'paragraph':
            return (
              <p key={idx} className={`text-[15px] leading-relaxed ${idx > 0 ? 'mt-1.5' : ''}`}>
                <InlineText segments={processInline(node.content)} />
              </p>
            )

          case 'bullet-list':
            return (
              <ul key={idx} className={`space-y-0.5 ${idx > 0 ? 'mt-1.5' : ''}`}>
                {(node.items ?? []).map((item, j) => (
                  <li key={j} className="flex gap-1.5 text-[15px] leading-relaxed">
                    <span className="shrink-0 mt-1 w-1.5 h-1.5 rounded-full bg-current opacity-60" />
                    <span>
                      <InlineText segments={processInline(item)} />
                    </span>
                  </li>
                ))}
              </ul>
            )

          case 'ordered-list':
            return (
              <ol key={idx} className={`space-y-0.5 ${idx > 0 ? 'mt-1.5' : ''}`}>
                {(node.items ?? []).map((item, j) => (
                  <li key={j} className="flex gap-2 text-[15px] leading-relaxed">
                    <span className="shrink-0 font-semibold text-[13px] w-4 text-right opacity-70">{j + 1}.</span>
                    <span>
                      <InlineText segments={processInline(item)} />
                    </span>
                  </li>
                ))}
              </ol>
            )

          default:
            return (
              <p key={idx} className="text-[15px] leading-relaxed">
                {node.content}
              </p>
            )
        }
      })}
    </div>
  )
}
