'use client'
import * as React from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { Badge, Card } from '@/design-system'
import type { CarePlan, CarePlanItem } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

/** An item is overdue when it has a past due date and is not yet completed. */
function isOverdue(item: CarePlanItem): boolean {
  if (item.completed || !item.due_date) return false
  return new Date(item.due_date).getTime() < Date.now()
}

interface PlanProgress {
  total: number
  done: number
  pct: number
  overdue: number
}

function computeProgress(items: readonly CarePlanItem[]): PlanProgress {
  const total = items.length
  const done = items.filter((it) => it.completed).length
  const overdue = items.filter(isOverdue).length
  const pct = total === 0 ? 0 : Math.round((done / total) * 100)
  return { total, done, pct, overdue }
}

// ── Status badge map (backend uses UPPERCASE status) ──────────────────────────

type BadgeVariant = 'active' | 'approved' | 'pending_review' | 'default'

const STATUS_CONFIG: Record<string, { variant: BadgeVariant; label: string }> = {
  ACTIVE:         { variant: 'active',         label: 'Đang thực hiện' },
  APPROVED:       { variant: 'approved',       label: 'Đã phê duyệt' },
  PENDING_REVIEW: { variant: 'pending_review', label: 'Chờ phê duyệt' },
  DRAFT:          { variant: 'default',        label: 'Bản nháp' },
  ARCHIVED:       { variant: 'default',        label: 'Lưu trữ' },
  SUPERSEDED:     { variant: 'default',        label: 'Đã thay thế' },
  REJECTED:       { variant: 'default',        label: 'Bị từ chối' },
}

// ── Progress ring (Liquid Glass mint hero) ────────────────────────────────────

function ProgressRing({ pct }: { pct: number }) {
  const size = 66
  const stroke = 7
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = c * (1 - pct / 100)
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-hidden="true"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.25)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="#fff"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fill="#fff"
        fontSize="16"
        fontWeight="700"
      >
        {pct}%
      </text>
    </svg>
  )
}

/** Mint gradient summary hero — only shown when the plan has goal items. */
function PlanProgressHero({ plan, progress }: { plan: CarePlan; progress: PlanProgress }) {
  return (
    <div className="rounded-3xl bg-gradient-to-br from-mint-400 to-mint-700 p-5 text-white shadow-pillow-mint">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-white/85">Tiến độ kế hoạch</span>
        {plan.approved_at && (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/20 px-2 py-1 text-[11px] font-semibold">
            <ShieldCheck className="size-3" aria-hidden="true" />
            Bác sĩ đã duyệt
          </span>
        )}
      </div>
      <div className="mt-3.5 flex items-center gap-4">
        <ProgressRing pct={progress.pct} />
        <div className="flex-1">
          <p className="text-[15px] font-bold leading-snug">
            {progress.pct >= 100
              ? 'Hoàn thành tất cả mục tiêu 🎉'
              : progress.pct >= 50
                ? 'Bạn đang đi đúng hướng'
                : 'Cùng bắt đầu nào'}
          </p>
          <p className="mt-1 text-[12.5px] text-white/85">
            Hoàn thành {progress.done}/{progress.total} mục tiêu
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Goal item row ──────────────────────────────────────────────────────────────

function GoalRow({ item }: { item: CarePlanItem }) {
  const overdue = isOverdue(item)
  return (
    <div className="flex items-center gap-3 border-b border-text/5 py-3 last:border-b-0">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-mint-50">
        {item.completed ? (
          <CheckCircle2 className="size-5 text-success" aria-hidden="true" />
        ) : overdue ? (
          <AlertTriangle className="size-5 text-danger" aria-hidden="true" />
        ) : (
          <Circle className="size-5 text-mint-500" aria-hidden="true" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p
          className={`text-[14px] font-semibold ${
            item.completed ? 'text-text-muted line-through' : 'text-text'
          }`}
        >
          {item.title}
        </p>
        {item.frequency && <p className="text-[12px] text-text-muted">{item.frequency}</p>}
        {overdue && !item.frequency && <p className="text-[12px] text-danger">Quá hạn</p>}
      </div>
      {item.completed ? (
        <span className="rounded-lg bg-success-light px-2 py-1 text-[11px] font-semibold text-green-800">
          Hoàn thành
        </span>
      ) : overdue ? (
        <span className="rounded-lg bg-danger-light px-2 py-1 text-[11px] font-semibold text-red-800">
          Quá hạn
        </span>
      ) : (
        <span className="rounded-lg bg-info-light px-2 py-1 text-[11px] font-semibold text-blue-800">
          Đang làm
        </span>
      )}
    </div>
  )
}

// ── Doctor note (approved content) ─────────────────────────────────────────────

function DoctorNote({ plan }: { plan: CarePlan }) {
  if (!plan.content) return null
  return (
    <div className="rounded-2xl border border-white/85 bg-white/60 p-4 shadow-glass backdrop-blur-xl">
      <div className="mb-2 flex items-center gap-2.5">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-mint-50 text-[11px] font-bold text-mint-600">
          BS
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[12.5px] font-bold text-text">
            {plan.doctor_name ?? 'Bác sĩ phụ trách'}
          </p>
          {plan.approved_at && (
            <p className="text-[10.5px] text-text-muted">Cập nhật · {formatDate(plan.approved_at)}</p>
          )}
        </div>
        {plan.ai_generated ? (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-ai-border bg-ai-light px-2 py-1 text-[10px] font-semibold text-ai">
            <Sparkles className="size-3" aria-hidden="true" />
            AI · chờ duyệt
          </span>
        ) : (
          plan.approved_at && (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-success-border bg-success-light px-2 py-1 text-[10px] font-semibold text-green-800">
              <ShieldCheck className="size-3" aria-hidden="true" />
              Đã duyệt
            </span>
          )
        )}
      </div>
      <p className="whitespace-pre-line text-[13px] leading-relaxed text-text-muted">
        {plan.content}
      </p>
    </div>
  )
}

// ── Care plan card ─────────────────────────────────────────────────────────────

export function CarePlanCard({ plan }: { plan: CarePlan }) {
  const cfg = STATUS_CONFIG[plan.status] ?? { variant: 'default' as BadgeVariant, label: plan.status }
  const items = plan.items ?? []
  const progress = computeProgress(items)

  return (
    <Card variant="glass" padding="md">
      {/* Title + status */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[18px] font-bold leading-snug text-text">{plan.title}</h2>
          <p className="mt-0.5 text-[12px] text-text-muted">
            Tạo: {formatDate(plan.created_at)}
            {(plan.version ?? 0) > 1 && <> &middot; v{plan.version}</>}
          </p>
        </div>
        <Badge variant={cfg.variant} dot size="sm">
          {cfg.label}
        </Badge>
      </div>

      {/* Progress hero — only when there are goal items to summarize */}
      {progress.total > 0 && (
        <div className="mt-4">
          <PlanProgressHero plan={plan} progress={progress} />
        </div>
      )}

      {/* Overdue alert */}
      {progress.overdue > 0 && (
        <div className="mt-3 flex items-start gap-2.5 rounded-2xl border border-warning-border bg-warning-light px-3.5 py-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden="true" />
          <div>
            <p className="text-[13px] font-bold text-amber-800">
              {progress.overdue} mục tiêu quá hạn
            </p>
            <p className="mt-0.5 text-[12px] leading-snug text-amber-700">
              Hãy thử đặt nhắc nhở để theo kịp kế hoạch nhé.
            </p>
          </div>
        </div>
      )}

      {/* Goal list */}
      {items.length > 0 && (
        <div className="mt-3 rounded-2xl border border-white/85 bg-white/55 px-4 shadow-glass backdrop-blur-xl">
          {items.map((item) => (
            <GoalRow key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* Plan content (no structured items) — render as body text */}
      {items.length === 0 && plan.content && (
        <p className="mt-3 whitespace-pre-line text-[15px] text-text-muted">{plan.content}</p>
      )}

      {/* Doctor note (only when items exist, to avoid duplicating the body text above) */}
      {items.length > 0 && (
        <div className="mt-3">
          <DoctorNote plan={plan} />
        </div>
      )}
    </Card>
  )
}
