'use client'

import * as React from 'react'
import { Plus, Flame, Sunrise, Sun, Moon, Coffee, Sparkles, type LucideIcon } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { GlassModal } from '@/components/patient/modal'
import { Field, MintFab } from '@/components/patient/forms'
import { useAuth } from '@/lib/auth/context'
import { getNutritionLog, logNutrition, type NutritionEntry } from '@/lib/api/patient'

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'

const MEAL_TYPE_OPTIONS: { value: MealType; label: string }[] = [
  { value: 'breakfast', label: 'Sáng' },
  { value: 'lunch', label: 'Trưa' },
  { value: 'dinner', label: 'Tối' },
  { value: 'snack', label: 'Bữa phụ' },
]
const MEAL_LABELS: Record<MealType, string> = { breakfast: 'Sáng', lunch: 'Trưa', dinner: 'Tối', snack: 'Bữa phụ' }
const MEAL_ICONS: Record<MealType, LucideIcon> = { breakfast: Sunrise, lunch: Sun, dinner: Moon, snack: Coffee }

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function groupByDate(entries: NutritionEntry[]): Array<{ label: string; items: NutritionEntry[] }> {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const map = new Map<string, NutritionEntry[]>()
  for (const entry of entries) {
    const d = new Date(entry.logged_at)
    const key = isSameDay(d, today)
      ? 'Hôm nay'
      : isSameDay(d, yesterday)
        ? 'Hôm qua'
        : d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
    const arr = map.get(key) ?? []
    arr.push(entry)
    map.set(key, arr)
  }
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }))
}

const todayCalories = (entries: NutritionEntry[]) =>
  entries.filter((e) => isSameDay(new Date(e.logged_at), new Date())).reduce((s, e) => s + (e.calories_kcal ?? 0), 0)

const formatTime = (iso: string) => new Date(iso).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })

function EntryItem({ entry, last }: { entry: NutritionEntry; last?: boolean }) {
  const mealType = entry.meal_type as MealType
  const Icon = MEAL_ICONS[mealType] ?? Coffee
  const label = MEAL_LABELS[mealType] ?? entry.meal_type
  return (
    <div className="py-3" style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-[rgba(227,245,236,0.9)]">
          <Icon className="size-[18px] text-[#0f9c6e]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="text-[12px] font-semibold text-[#0f9c6e]">{label}</span>
              <p className="text-[14px] text-[#0e2a33]">{entry.description}</p>
            </div>
            <div className="shrink-0 text-right">
              {entry.calories_kcal != null && (
                <p className="text-[14px] font-bold text-[#0e2a33]">{entry.calories_kcal} kcal</p>
              )}
              <p className="text-[12px] text-[#566e66]">{formatTime(entry.logged_at)}</p>
            </div>
          </div>
          {(entry.carbs_g != null || entry.protein_g != null || entry.fat_g != null) && (
            <p className="mt-0.5 text-[12px] text-[#566e66]">
              {[
                entry.carbs_g != null && `Carb ${entry.carbs_g}g`,
                entry.protein_g != null && `Đạm ${entry.protein_g}g`,
                entry.fat_g != null && `Béo ${entry.fat_g}g`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
        </div>
      </div>
      {entry.ai_coaching && (
        <div
          className="ml-12 mt-2 rounded-[10px] border border-[rgba(216,201,246,0.7)] bg-[rgba(243,238,251,0.6)] p-2.5"
          style={{ borderLeft: '3px solid rgba(109,63,190,0.5)' }}
        >
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 size-3.5 shrink-0 text-[#6d3fbe]" aria-hidden="true" />
            <p className="text-[12px] leading-snug text-[#6d3fbe]">
              <span className="font-semibold">Gợi ý AI:</span> {entry.ai_coaching}
              <span className="mt-0.5 block text-[11px] opacity-80">(AI · không thay thế tư vấn dinh dưỡng)</span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

function AddMealModal({
  open,
  onOpenChange,
  onAdd,
  patientId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdd: (entry: NutritionEntry) => void
  patientId: string
}) {
  const [mealType, setMealType] = React.useState<MealType>('breakfast')
  const [description, setDescription] = React.useState('')
  const [calories, setCalories] = React.useState('')
  const [carbs, setCarbs] = React.useState('')
  const [protein, setProtein] = React.useState('')
  const [fat, setFat] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  const [descError, setDescError] = React.useState<string | null>(null)

  function reset() {
    setMealType('breakfast')
    setDescription('')
    setCalories('')
    setCarbs('')
    setProtein('')
    setFat('')
    setSubmitError(null)
    setDescError(null)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setDescError(null)
    setSubmitError(null)
    if (!description.trim()) {
      setDescError('Vui lòng nhập mô tả bữa ăn')
      return
    }
    setSubmitting(true)
    try {
      const entry = await logNutrition(patientId, {
        meal_type: mealType,
        description: description.trim(),
        calories_kcal: calories ? Number(calories) : undefined,
        carbs_g: carbs ? Number(carbs) : undefined,
        protein_g: protein ? Number(protein) : undefined,
        fat_g: fat ? Number(fat) : undefined,
      })
      onAdd(entry)
      reset()
      onOpenChange(false)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Không thể ghi nhật ký dinh dưỡng')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <GlassModal
      open={open}
      onOpenChange={(o) => {
        if (!o) reset()
        onOpenChange(o)
      }}
      title="Thêm bữa ăn"
      footer={
        <>
          <button
            type="button"
            className="mc-btn-glass flex-1"
            disabled={submitting}
            onClick={() => {
              reset()
              onOpenChange(false)
            }}
          >
            Huỷ
          </button>
          <button type="submit" form="add-meal-form" className="mc-btn flex-1" disabled={submitting}>
            {submitting ? 'Đang lưu…' : 'Lưu'}
          </button>
        </>
      }
    >
      <form id="add-meal-form" onSubmit={handleSubmit} className="space-y-4">
        <Field label="Bữa ăn">
          <div className="grid grid-cols-4 gap-2">
            {MEAL_TYPE_OPTIONS.map((o) => {
              const active = mealType === o.value
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setMealType(o.value)}
                  className="min-h-[44px] rounded-xl border text-[13px] font-semibold"
                  style={{
                    borderColor: active ? '#0f9c6e' : 'rgba(16,48,44,0.12)',
                    background: active ? 'rgba(227,245,236,0.8)' : 'rgba(255,255,255,0.6)',
                    color: active ? '#0b7f5b' : '#365651',
                  }}
                >
                  {o.label}
                </button>
              )
            })}
          </div>
        </Field>
        <Field label="Mô tả bữa ăn">
          <textarea
            className="mc-input py-3"
            style={{ minHeight: 76, lineHeight: 1.5 }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="VD: cơm trắng 1 bát, rau luộc, ức gà…"
          />
          {descError && <p className="mt-1 text-[12px] text-[#d92d20]">{descError}</p>}
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Calories (kcal)">
            <input type="number" inputMode="decimal" min={0} className="mc-input" value={calories} onChange={(e) => setCalories(e.target.value)} placeholder="0" />
          </Field>
          <Field label="Carbs (g)">
            <input type="number" inputMode="decimal" min={0} className="mc-input" value={carbs} onChange={(e) => setCarbs(e.target.value)} placeholder="0" />
          </Field>
          <Field label="Đạm (g)">
            <input type="number" inputMode="decimal" min={0} className="mc-input" value={protein} onChange={(e) => setProtein(e.target.value)} placeholder="0" />
          </Field>
          <Field label="Béo (g)">
            <input type="number" inputMode="decimal" min={0} className="mc-input" value={fat} onChange={(e) => setFat(e.target.value)} placeholder="0" />
          </Field>
        </div>
        {submitError && (
          <p className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">{submitError}</p>
        )}
      </form>
    </GlassModal>
  )
}

export default function NutritionPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [entries, setEntries] = React.useState<NutritionEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [addModalOpen, setAddModalOpen] = React.useState(false)

  const loadLog = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getNutritionLog(patientId, { limit: 20 })
      setEntries(res.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được nhật ký dinh dưỡng')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    loadLog()
  }, [loadLog])

  if (!patientId) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Nhật ký dinh dưỡng" />
        <PatientEmptyState icon={Flame} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  const todayKcal = todayCalories(entries)
  const groups = groupByDate(entries)
  const todayEntries = entries.filter((e) => isSameDay(new Date(e.logged_at), new Date()))

  return (
    <div className="pt-2">
      <PatientScreenHeader
        title="Nhật ký dinh dưỡng"
        subtitle="Ghi lại bữa ăn hằng ngày"
        action={
          <MintFab label="Thêm bữa ăn" onClick={() => setAddModalOpen(true)}>
            <Plus className="size-5 text-white" aria-hidden="true" />
          </MintFab>
        }
      />

      {/* Today's calorie summary — mint hero */}
      <div className="mc-hero mt-3 flex items-center gap-3 rounded-[18px] p-4">
        <span className="grid size-12 place-items-center rounded-full bg-white/20">
          <Flame className="size-6 text-white" aria-hidden="true" />
        </span>
        <div>
          <p className="text-[12.5px] text-white/80">Tổng calo hôm nay</p>
          <p className="text-[26px] font-extrabold leading-tight">
            {todayKcal.toLocaleString('vi-VN')} <span className="text-[14px] font-medium text-white/80">kcal</span>
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        {loading && <PatientSkeleton />}

        {!loading && error && <PatientErrorState title="Không tải được nhật ký" message={error} onRetry={loadLog} />}

        {!loading && !error && todayEntries.length === 0 && entries.length === 0 && (
          <PatientEmptyState
            icon={Coffee}
            title="Chưa có nhật ký hôm nay"
            description="Hãy ghi lại bữa ăn đầu tiên của bạn!"
            actionLabel="Thêm bữa ăn"
            onAction={() => setAddModalOpen(true)}
          />
        )}

        {!loading &&
          !error &&
          entries.length > 0 &&
          groups.map(({ label, items }) => (
            <div key={label}>
              <p className="mb-2 px-1 text-[13px] font-semibold text-[#566e66]">{label}</p>
              <GlassCard className="px-4 py-1">
                {items.map((entry, i) => (
                  <EntryItem key={entry.id} entry={entry} last={i === items.length - 1} />
                ))}
              </GlassCard>
            </div>
          ))}
      </div>

      <AddMealModal
        open={addModalOpen}
        onOpenChange={setAddModalOpen}
        patientId={patientId}
        onAdd={(entry) => setEntries((prev) => [entry, ...prev])}
      />
    </div>
  )
}
