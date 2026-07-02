import * as React from 'react'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export type LegalSection = {
  heading: string
  body: readonly string[]
}

type Props = {
  title: string
  version: string
  updated: string
  intro?: string
  sections: readonly LegalSection[]
}

/**
 * Shared reader chrome for the Terms / Privacy full-text pages.
 * Readable (≥16px), Soft Mint, dark-mode aware; opened in its own tab.
 */
export function LegalDocument({ title, version, updated, intro, sections }: Props) {
  return (
    <article className="text-text dark:text-white/90">
      <Link
        href="/register"
        className="mb-4 inline-flex min-h-[44px] items-center gap-1.5 text-[16px] font-semibold text-neu-green hover:underline underline-offset-2"
      >
        <ArrowLeft className="h-5 w-5" aria-hidden="true" />
        Quay lại
      </Link>

      <h1 className="text-[24px] font-extrabold text-neu-text dark:text-white">{title}</h1>
      <p className="mt-1 text-[15px] text-text-subtle dark:text-white/60">
        Phiên bản {version} · Cập nhật {updated}
      </p>

      {intro && (
        <p className="mt-4 text-[16px] leading-relaxed text-text-muted dark:text-white/70">
          {intro}
        </p>
      )}

      <div className="mt-5 space-y-5">
        {sections.map((section, i) => (
          <section key={section.heading}>
            <h2 className="text-[18px] font-bold text-neu-text dark:text-white">
              {i + 1}. {section.heading}
            </h2>
            <div className="mt-2 space-y-2">
              {section.body.map((para, j) => (
                <p key={j} className="text-[16px] leading-relaxed text-text dark:text-white/85">
                  {para}
                </p>
              ))}
            </div>
          </section>
        ))}
      </div>

      <p className="mt-6 text-[14px] leading-relaxed text-text-subtle dark:text-white/50">
        Đây là bản tóm tắt phục vụ trải nghiệm sản phẩm và sẽ được rà soát bởi bộ phận pháp lý.
        Nếu có câu hỏi, vui lòng liên hệ hỗ trợ MetoCare.
      </p>
    </article>
  )
}
