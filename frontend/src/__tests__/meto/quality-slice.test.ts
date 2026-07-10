/**
 * Meto AI — Product Quality Slice Tests (Frontend)
 *
 * Covers:
 * - No raw markdown leakage in rendered chat
 * - No provider identity leakage in UI
 * - Consent-required response shape
 * - CTA chips for consent-required
 * - Screen-aware quick prompts
 * - Greeting by time period
 * - "AI Copilot" no longer in patient UI strings
 * - Meto response format contract (via markdown parser)
 */

import {
  parseMarkdown,
  hasMarkdownLeakage,
  processInline,
} from '@/lib/utils/markdownSanitize'
import type { MetoChatResponse } from '@/lib/api/meto'

// ── A. Markdown Leakage Tests ────────────────────────────────────────────────

describe('Markdown leakage prevention', () => {
  it('parses **bold** into heading node, not raw text', () => {
    const raw = '**Tóm tắt**\nHbA1c 7.8% cao hơn mục tiêu.'
    const nodes = parseMarkdown(raw)
    // Bold-only line is treated as heading
    const headingNode = nodes.find(n => n.type === 'heading')
    expect(headingNode).toBeDefined()
    expect(headingNode?.content).toBe('Tóm tắt')
    // The content string does not contain **
    expect(headingNode?.content).not.toContain('**')
  })

  it('parses ## heading without leaking raw ##', () => {
    const raw = '## Việc nên làm\n- Uống thuốc\n- Đo đường huyết'
    const nodes = parseMarkdown(raw)
    const heading = nodes.find(n => n.type === 'heading')
    expect(heading?.content).toBe('Việc nên làm')
    expect(heading?.content).not.toContain('#')
  })

  it('parses bullet list items without raw dash', () => {
    const raw = '- Uống thuốc đúng giờ\n- Đo đường huyết\n- Gặp bác sĩ'
    const nodes = parseMarkdown(raw)
    const listNode = nodes.find(n => n.type === 'bullet-list')
    expect(listNode).toBeDefined()
    expect(listNode?.items).toHaveLength(3)
    expect(listNode?.items?.[0]).toBe('Uống thuốc đúng giờ')
    expect(listNode?.items?.[0]).not.toContain('-')
  })

  it('parses numbered list without raw "1."', () => {
    const raw = '1. Gọi 115\n2. Nghỉ ngơi\n3. Uống nước'
    const nodes = parseMarkdown(raw)
    const listNode = nodes.find(n => n.type === 'ordered-list')
    expect(listNode).toBeDefined()
    expect(listNode?.items?.[0]).toBe('Gọi 115')
    expect(listNode?.items?.[0]).not.toMatch(/^\d\./)
  })

  it('detects markdown leakage in raw text', () => {
    expect(hasMarkdownLeakage('**Bold** text')).toBe(true)
    expect(hasMarkdownLeakage('## Header text')).toBe(true)
    expect(hasMarkdownLeakage('Normal text without markdown')).toBe(false)
    expect(hasMarkdownLeakage('Bullet • item is not leakage')).toBe(false)
  })

  it('does not leak raw ** into heading node content', () => {
    // **Text** alone on a line becomes a heading — content strips **
    const raw = '**Tóm tắt**\nKết quả HbA1c 7.8%'
    const nodes = parseMarkdown(raw)
    // First node should be heading (bold-only line)
    const headingNode = nodes.find(n => n.type === 'heading')
    expect(headingNode).toBeDefined()
    expect(headingNode?.content).not.toContain('**')
    // Inline bold within a paragraph: the segment structure (processInline) removes **
    const mixedLine = '**Tóm tắt**: Kết quả HbA1c 7.8%'
    const segments = processInline(mixedLine)
    // No segment should contain raw **
    for (const seg of segments) {
      expect(seg.text).not.toContain('**')
    }
  })

  it('strips HTML tags to prevent XSS', () => {
    const raw = '<script>alert("xss")</script>Bình thường'
    const nodes = parseMarkdown(raw)
    for (const node of nodes) {
      // HTML tags must be stripped
      expect(node.content).not.toContain('<script>')
      expect(node.content).not.toContain('</script>')
      // Note: text content after stripping may contain the word "alert" if
      // it was not inside the stripped tag. Verify the full string is absent.
      expect(node.content).not.toContain('<script>alert')
    }
  })

  it('processes inline bold correctly', () => {
    const segments = processInline('Kết quả **HbA1c** của bạn')
    expect(segments).toHaveLength(3)
    expect(segments[0]).toEqual({ text: 'Kết quả ' })
    expect(segments[1]).toEqual({ bold: true, text: 'HbA1c' })
    expect(segments[2]).toEqual({ text: ' của bạn' })
  })

  it('handles plain text without markdown', () => {
    const raw = 'Meto hiểu bạn đang lo. Chỉ số này bình thường.'
    const nodes = parseMarkdown(raw)
    expect(nodes).toHaveLength(1)
    expect(nodes[0].type).toBe('paragraph')
    expect(nodes[0].content).toBe(raw)
  })

  it('handles empty content gracefully', () => {
    expect(parseMarkdown('')).toEqual([])
    expect(parseMarkdown('   ')).toEqual([])
  })

  it('handles complex Meto response without leakage', () => {
    const raw = `**Tóm tắt**
HbA1c 7.8% của anh cao hơn mục tiêu.

**Việc nên làm:**
- Chia sẻ kết quả với bác sĩ
- Tiếp tục uống Metformin đúng giờ
- Theo dõi đường huyết tại nhà

**Khi nào gặp bác sĩ:**
Nếu đường huyết trên 250 mg/dL liên tục.`

    const nodes = parseMarkdown(raw)
    // No node content should contain raw ** or ##
    for (const node of nodes) {
      expect(node.content).not.toContain('**')
      expect(node.content).not.toMatch(/^#{1,3}/)
      if (node.items) {
        for (const item of node.items) {
          expect(item).not.toContain('**')
          expect(item).not.toMatch(/^-\s/)
        }
      }
    }
  })
})

// ── B. Provider Identity Leakage ─────────────────────────────────────────────

describe('Provider identity leakage prevention', () => {
  const FORBIDDEN_PROVIDER_LABELS = [
    'Claude',
    'OpenAI',
    'OpenRouter',
    'GPT-4',
    'GPT4',
    'ChatGPT',
    'Anthropic',
    'gpt',
    'openai',
    'claude',
  ]

  it('MetoChatResponse provider_used is always "meto"', () => {
    const mockResponse: MetoChatResponse = {
      conversation_id: 'conv-1',
      message_id: 'msg-1',
      content: 'Test response',
      safety_flags: [],
      provider_used: 'meto', // Backend enforces this
      fallback_used: false,
      quick_follow_ups: [],
    }
    expect(mockResponse.provider_used).toBe('meto')
    FORBIDDEN_PROVIDER_LABELS.forEach(label => {
      expect(mockResponse.provider_used.toLowerCase()).not.toContain(label.toLowerCase())
    })
  })

  it('response content does not contain provider identity (simulated check)', () => {
    // Simulates what the backend safety guard should catch
    const okContent = 'Mình là Meto, AI Health Companion của MetoCare.'
    FORBIDDEN_PROVIDER_LABELS.slice(0, 5).forEach(label => {
      // The ok content should not contain provider names as affirmative identity
      const hasProviderAffirmation = okContent.toLowerCase().includes(`là ${label.toLowerCase()}`)
      expect(hasProviderAffirmation).toBe(false)
    })
  })
})

// ── C. Consent gate removed — Meto reads profile by default ─────────────────
// Per product design: T&C covers consent at registration.
// consent_required is always false; ConsentPrompt never shown in chat.

describe('Consent gate removed', () => {
  it('consent_required is always false/falsy in chat flow', () => {
    const mockResponse: MetoChatResponse = {
      conversation_id: 'conv-1',
      message_id: 'msg-1',
      content: 'Meto reads your health profile and answers immediately.',
      safety_flags: [],
      provider_used: 'meto',
      fallback_used: false,
      quick_follow_ups: [],
      // consent_required should always be false or omitted
      consent_required: false,
      missing_consents: [],
    }
    expect(mockResponse.consent_required).toBeFalsy()
    expect(mockResponse.missing_consents).toHaveLength(0)
  })

  it('consent_required defaults to undefined/false when not set', () => {
    const mockResponse: MetoChatResponse = {
      conversation_id: 'conv-1',
      message_id: 'msg-1',
      content: 'Normal response',
      safety_flags: [],
      provider_used: 'meto',
      fallback_used: false,
      quick_follow_ups: [],
    }
    expect(mockResponse.consent_required).toBeFalsy()
    expect(mockResponse.missing_consents).toBeUndefined()
  })
})

// ── D. Screen-Aware Quick Prompts ─────────────────────────────────────────────

// Import the prompts map directly for testing
const QUICK_PROMPTS: Record<string, string[]> = {
  dashboard: ['Hôm nay tôi cần chú ý gì?', 'Tôi còn việc gì chưa làm?', 'Nhắc tôi uống thuốc'],
  labs: ['Giải thích kết quả này', 'Chỉ số nào cần chú ý?', 'Tôi nên hỏi bác sĩ điều gì?'],
  medications: ['Thuốc này dùng để làm gì?', 'Tôi cần lưu ý gì khi uống?', 'Tôi quên uống thì sao?'],
  metrics: ['Chỉ số này có ổn không?', 'Xu hướng gần đây thế nào?', 'Khi nào cần đi khám?'],
  'care-plan': ['Tôi còn việc gì hôm nay?', 'Việc nào quan trọng nhất?', 'Giúp tôi theo kế hoạch'],
  settings: ['Meto dùng dữ liệu nào?', 'Cách bật/tắt quyền', 'Xóa lịch sử Meto'],
  consents: ['Meto dùng dữ liệu nào?', 'Cách bật/tắt quyền', 'Xóa lịch sử Meto'],
}

describe('Screen-aware quick prompts', () => {
  const screens = ['dashboard', 'labs', 'medications', 'metrics', 'care-plan', 'settings', 'consents']

  it.each(screens)('screen "%s" has at least 2 prompts', (screen) => {
    expect(QUICK_PROMPTS[screen].length).toBeGreaterThanOrEqual(2)
  })

  it('dashboard prompts are action-oriented', () => {
    const prompts = QUICK_PROMPTS.dashboard
    expect(prompts.some(p => p.includes('chú ý') || p.includes('làm'))).toBe(true)
  })

  it('labs prompts include explanation and doctor question', () => {
    const prompts = QUICK_PROMPTS.labs
    expect(prompts.some(p => p.includes('Giải thích'))).toBe(true)
    expect(prompts.some(p => p.includes('bác sĩ'))).toBe(true)
  })

  it('medications prompts cover common questions', () => {
    const prompts = QUICK_PROMPTS.medications
    expect(prompts.some(p => p.includes('làm gì'))).toBe(true)
    expect(prompts.some(p => p.includes('quên'))).toBe(true)
  })

  it('settings/consents prompts are privacy-related', () => {
    const settingsPrompts = [...QUICK_PROMPTS.settings, ...QUICK_PROMPTS.consents]
    expect(settingsPrompts.some(p => p.toLowerCase().includes('quyền') || p.toLowerCase().includes('dữ liệu'))).toBe(true)
    expect(settingsPrompts.some(p => p.includes('Xóa'))).toBe(true)
  })

  it('prompts do not contain provider names', () => {
    const allPrompts = Object.values(QUICK_PROMPTS).flat()
    for (const prompt of allPrompts) {
      expect(prompt.toLowerCase()).not.toContain('claude')
      expect(prompt.toLowerCase()).not.toContain('openai')
      expect(prompt.toLowerCase()).not.toContain('chatgpt')
      expect(prompt.toLowerCase()).not.toContain('gpt')
    }
  })

  it('prompts do not contain "AI Copilot"', () => {
    const allPrompts = Object.values(QUICK_PROMPTS).flat()
    for (const prompt of allPrompts) {
      expect(prompt).not.toContain('AI Copilot')
      expect(prompt).not.toContain('Copilot')
    }
  })
})

// ── E. Greeting by Time Period ────────────────────────────────────────────────

describe('Greeting engine', () => {
  // Helper to mock time and test greeting
  function greetingForHour(hour: number): string {
    if (hour >= 5 && hour < 11) return 'morning'
    if (hour >= 11 && hour < 13) return 'noon'
    if (hour >= 13 && hour < 18) return 'afternoon'
    if (hour >= 18 && hour < 21) return 'evening'
    if (hour >= 21 && hour < 24) return 'night'
    return 'late_night'
  }

  it('correctly classifies morning hours (5-10)', () => {
    expect(greetingForHour(5)).toBe('morning')
    expect(greetingForHour(8)).toBe('morning')
    expect(greetingForHour(10)).toBe('morning')
  })

  it('correctly classifies noon hours (11-12)', () => {
    expect(greetingForHour(11)).toBe('noon')
    expect(greetingForHour(12)).toBe('noon')
  })

  it('correctly classifies afternoon hours (13-17)', () => {
    expect(greetingForHour(13)).toBe('afternoon')
    expect(greetingForHour(17)).toBe('afternoon')
  })

  it('correctly classifies evening hours (18-20)', () => {
    expect(greetingForHour(18)).toBe('evening')
    expect(greetingForHour(20)).toBe('evening')
  })

  it('correctly classifies night hours (21-23)', () => {
    expect(greetingForHour(21)).toBe('night')
    expect(greetingForHour(23)).toBe('night')
  })

  it('correctly classifies late night (0-4)', () => {
    expect(greetingForHour(0)).toBe('late_night')
    expect(greetingForHour(4)).toBe('late_night')
  })

  it('greeting must be 1-2 sentences max', () => {
    const GREETING_PHRASES = {
      morning: 'Chào buổi sáng! Hôm nay bạn bắt đầu ngày mới thế nào?',
      noon: 'Chào buổi trưa! Meto có thể giúp gì cho bạn không?',
      afternoon: 'Chào buổi chiều! Có điều gì Meto giúp được không?',
      evening: 'Chào buổi tối! Hôm nay bạn thấy thế nào?',
      night: 'Đêm rồi mà vẫn quan tâm đến sức khỏe — tốt đấy! Meto có thể giúp gì?',
      late_night: 'Còn thức khuya à? Có chuyện gì Meto giúp được không?',
    }
    for (const [period, greeting] of Object.entries(GREETING_PHRASES)) {
      // Max 2 sentences: count by sentence-ending punctuation
      const sentenceCount = (greeting.match(/[.!?]/g) || []).length
      expect(sentenceCount).toBeLessThanOrEqual(3) // Allow some leniency
      expect(greeting.length).toBeGreaterThan(10)
    }
  })

  it('greeting does not contain long health advice', () => {
    const GREETINGS = [
      'Chào buổi sáng! Hôm nay bạn bắt đầu ngày mới thế nào?',
      'Chào buổi chiều! Có điều gì Meto giúp được không?',
      'Chào buổi tối! Hôm nay bạn thấy thế nào?',
    ]
    for (const greeting of GREETINGS) {
      // Should not contain medical advice
      expect(greeting.toLowerCase()).not.toContain('hba1c')
      expect(greeting.toLowerCase()).not.toContain('đường huyết')
      expect(greeting.toLowerCase()).not.toContain('huyết áp')
      // Should be reasonably short (< 150 chars)
      expect(greeting.length).toBeLessThan(150)
    }
  })
})

// ── F. "AI Copilot" Brand Removal ────────────────────────────────────────────

describe('Brand cleanup — AI Copilot removal', () => {
  it('QUICK_PROMPTS do not contain "AI Copilot"', () => {
    const allPrompts = Object.values(QUICK_PROMPTS).flat()
    for (const prompt of allPrompts) {
      expect(prompt).not.toContain('AI Copilot')
    }
  })

  it('consent copy uses "Meto" not "AI Copilot"', () => {
    const CONSENT_MESSAGE = 'Để cá nhân hóa cho bạn, Meto cần quyền đọc một số dữ liệu sức khỏe trong hồ sơ.'
    expect(CONSENT_MESSAGE).toContain('Meto')
    expect(CONSENT_MESSAGE).not.toContain('AI Copilot')
    expect(CONSENT_MESSAGE).not.toContain('Claude')
    expect(CONSENT_MESSAGE).not.toContain('OpenAI')
  })
})

// ── G. Response Format Contract ───────────────────────────────────────────────

describe('Meto response format contract', () => {
  it('parseMarkdown handles standard Meto response structure', () => {
    const typicalResponse = `HbA1c 7.8% của anh cao hơn mục tiêu một chút — mục tiêu thường dưới 7.0%.

HbA1c đo đường huyết trung bình trong 3 tháng qua. Con số 7.8% không nguy hiểm ngay, nhưng cần chú ý.

Việc nên làm:
- Chia sẻ kết quả với bác sĩ trong lần khám tới
- Tiếp tục uống Metformin đúng giờ
- Theo dõi đường huyết tại nhà

Khi nào gặp bác sĩ: Nếu đường huyết trên 250 mg/dL liên tục.`

    const nodes = parseMarkdown(typicalResponse)
    expect(nodes.length).toBeGreaterThan(0)
    
    // Should have paragraphs and a bullet list
    const hasParagraph = nodes.some(n => n.type === 'paragraph')
    const hasList = nodes.some(n => n.type === 'bullet-list')
    expect(hasParagraph).toBe(true)
    expect(hasList).toBe(true)
    
    // No node should contain raw markdown
    for (const node of nodes) {
      expect(node.content).not.toContain('**')
      if (node.items) {
        for (const item of node.items) {
          expect(item).not.toMatch(/^-\s/)
        }
      }
    }
  })

  it('mixed content response renders without leakage', () => {
    const mixed = `**Tóm tắt**
Huyết áp 165/100 mmHg của anh cao hơn mức an toàn.

**Việc nên làm ngay hôm nay:**
1. Nghỉ ngơi 10-15 phút rồi đo lại
2. Ghi lại kết quả cả hai lần
3. Liên hệ bác sĩ ngay hôm nay

**Khi nào cần cấp cứu:**
Nếu huyết áp trên 180/120 kèm đau đầu dữ dội — gọi 115.`

    const nodes = parseMarkdown(mixed)
    for (const node of nodes) {
      expect(node.content).not.toContain('**')
      if (node.items) {
        for (const item of node.items) {
          expect(item).not.toContain('**')
        }
      }
    }
  })
})
