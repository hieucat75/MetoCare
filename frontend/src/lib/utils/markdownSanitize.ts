/**
 * Meto AI — Markdown sanitizer / renderer utility.
 *
 * Converts raw markdown from the AI model to safe HTML for display in chat bubbles.
 * Prevents raw `**`, `##`, `*` etc from appearing as plain text.
 *
 * Supports a limited, safe subset:
 *   - **bold** → <strong>
 *   - *italic* → <em>
 *   - ## Heading → <p class="font-semibold">
 *   - ### Heading → <p class="font-medium">
 *   - - bullet / * bullet / • bullet → <ul><li>
 *   - 1. numbered list → <ol><li>
 *   - \n\n → paragraph break
 *   - Strips any raw HTML to prevent XSS
 *
 * Does NOT use dangerouslySetInnerHTML — use the `MarkdownMessage` component instead.
 */

export interface MarkdownNode {
  type: 'paragraph' | 'heading' | 'bullet-list' | 'ordered-list' | 'bold' | 'text'
  content: string
  level?: number
  items?: string[]
}

/**
 * Sanitize a raw string: strip HTML tags.
 */
function stripHtml(text: string): string {
  return text.replace(/<[^>]*>/g, '')
}

/**
 * Process inline markdown: bold, italic → returns segments for rendering.
 */
export function processInline(text: string): Array<{ bold?: boolean; italic?: boolean; text: string }> {
  const segments: Array<{ bold?: boolean; italic?: boolean; text: string }> = []
  // Regex: **bold** or *italic*
  const re = /\*\*(.+?)\*\*|\*(.+?)\*/g
  let lastIdx = 0
  let match: RegExpExecArray | null

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ text: text.slice(lastIdx, match.index) })
    }
    if (match[1] !== undefined) {
      segments.push({ bold: true, text: match[1] })
    } else if (match[2] !== undefined) {
      segments.push({ italic: true, text: match[2] })
    }
    lastIdx = match.index + match[0].length
  }
  if (lastIdx < text.length) {
    segments.push({ text: text.slice(lastIdx) })
  }
  return segments.length > 0 ? segments : [{ text }]
}

/**
 * Parse raw markdown text into structured nodes for rendering.
 */
export function parseMarkdown(raw: string): MarkdownNode[] {
  // Strip HTML for safety
  const safe = stripHtml(raw)

  const nodes: MarkdownNode[] = []
  const lines = safe.split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Empty line — skip (paragraph breaks handled by grouping)
    if (line.trim() === '') {
      i++
      continue
    }

    // H1 or H2 heading: ## / ###
    const headingMatch = line.match(/^(#{1,3})\s+(.+)/)
    if (headingMatch) {
      nodes.push({
        type: 'heading',
        content: headingMatch[2].trim(),
        level: headingMatch[1].length,
      })
      i++
      continue
    }

    // Bold-only line that looks like a section header: **text**
    const boldHeaderMatch = line.match(/^\*\*(.+?)\*\*\s*$/)
    if (boldHeaderMatch) {
      nodes.push({
        type: 'heading',
        content: boldHeaderMatch[1].trim(),
        level: 3,
      })
      i++
      continue
    }

    // Bullet list
    if (/^[\-\*•]\s+/.test(line.trim())) {
      const items: string[] = []
      while (i < lines.length && /^[\-\*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].replace(/^[\s]*[\-\*•]\s+/, '').trim())
        i++
      }
      nodes.push({ type: 'bullet-list', content: '', items })
      continue
    }

    // Ordered list
    if (/^\d+\.\s+/.test(line.trim())) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, '').trim())
        i++
      }
      nodes.push({ type: 'ordered-list', content: '', items })
      continue
    }

    // Regular paragraph — collect non-empty, non-list, non-heading lines
    const paragraphLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,3})\s/.test(lines[i]) &&
      !/^[\-\*•]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !/^\*\*(.+?)\*\*\s*$/.test(lines[i])
    ) {
      paragraphLines.push(lines[i])
      i++
    }
    if (paragraphLines.length > 0) {
      nodes.push({ type: 'paragraph', content: paragraphLines.join(' ') })
    }
  }

  return nodes
}

/**
 * Test helper: check if raw text contains markdown leakage
 * (raw `**`, `##`, etc. that should have been rendered).
 */
export function hasMarkdownLeakage(text: string): boolean {
  return /\*\*[^*]+\*\*/.test(text) || /^#{1,3}\s/m.test(text)
}
